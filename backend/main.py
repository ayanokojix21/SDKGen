"""
backend/main.py
───────────────
FastAPI application — the public face of the SDK Generator backend.

Endpoints
─────────
  GET  /health                → server + API key + MongoDB status
  POST /generate/start        → create job, launch graph, return job_id
  GET  /generate/stream       → SSE stream for a job (EventSourceResponse)
  GET  /download/{job_id}     → ZIP of final SDK files
  WS   /ws                    → WebSocket bridge (Chrome ↔ VS Code, Dev 4)

Patterns used
─────────────
• FastAPI lifespan (async context manager) for startup/shutdown — ensures
  MongoDB connection is opened before any request is served.
• sse-starlette EventSourceResponse with asyncio.Queue per job — the only
  correct pattern for non-blocking SSE in an async FastAPI app.
• asyncio.create_task() for graph execution — non-blocking; returns job_id
  immediately while the graph runs in the background.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, HttpUrl
from sse_starlette.sse import EventSourceResponse

import backend.job_manager as job_manager
from backend.config import settings
from backend.graph.graph import init_graph, teardown_graph
from backend.graph.runner import run_graph

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


# ──────────────────────────────────────────────────────────────────────────────
# Lifespan — startup + shutdown
# ──────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Runs once at server startup (before first request) and once at shutdown.
    - Initialises the LangGraph compiled graph with MongoDB checkpointer.
    - Teardown closes the MongoDB connection gracefully.
    """
    log.info("=== Docs-to-Code backend starting up ===")
    await init_graph()
    log.info("=== Graph ready. Server accepting requests. ===")
    yield
    log.info("=== Docs-to-Code backend shutting down ===")
    await teardown_graph()


# ──────────────────────────────────────────────────────────────────────────────
# App
# ──────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Docs-to-Code — SDK Generator",
    description=(
        "Multi-agent SDK generator powered by LangGraph + Gemini. "
        "Accepts an API docs URL, autonomously generates a typed SDK, "
        "verifies it against the live API, and delivers it straight to VS Code."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # Chrome extension + local dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────────────────────────────────────
# Pydantic models
# ──────────────────────────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    target_url:   str
    language:     str        = "python"   # "python" | "typescript"
    page_content: str        = ""
    page_links:   list[dict] = []

class GenerateResponse(BaseModel):
    job_id:  str
    message: str = "Job started"


# ──────────────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["meta"])
async def health_check():
    """
    Returns server status, whether the Gemini API key is configured,
    and whether the MongoDB checkpointer is connected.
    """
    from backend.graph.graph import compiled_graph, _checkpointer
    return {
        "status":         "ok",
        "api_key_set":    bool(settings.GOOGLE_API_KEY),
        "mongodb_set":    bool(settings.MONGODB_URI),
        "graph_compiled": compiled_graph is not None,
        "checkpointer":   type(_checkpointer).__name__ if _checkpointer else None,
    }


@app.post("/generate/start", response_model=GenerateResponse, tags=["sdk"])
async def start_generation(request: GenerateRequest):
    """
    Starts a new SDK generation job.

    1. Creates job_id + initial LangGraph state
    2. Registers a per-job asyncio.Queue for SSE streaming
    3. Launches the graph runner as a background asyncio task
    4. Returns the job_id immediately (non-blocking)

    The client should immediately open GET /generate/stream?job_id=<id>
    """
    if not settings.GOOGLE_API_KEY:
        raise HTTPException(status_code=503, detail="GOOGLE_API_KEY not configured.")

    language = request.language.lower()
    if language not in ("python", "typescript"):
        raise HTTPException(status_code=400, detail="language must be 'python' or 'typescript'")

    job_id, initial_state = job_manager.create_job(
        target_url=request.target_url,
        language=language,
        page_content=request.page_content,
        page_links=request.page_links,
    )

    # Launch the graph runner as a non-blocking background task
    asyncio.create_task(
        run_graph(job_id, initial_state),
        name=f"graph-{job_id}",
    )

    log.info("[main] job=%s started for url=%s", job_id, request.target_url)
    return GenerateResponse(job_id=job_id)


@app.get("/generate/stream", tags=["sdk"])
async def stream_generation(request: Request, job_id: str):
    """
    SSE endpoint — streams agent events in real time for a given job.

    The client receives a stream of JSON-encoded server-sent events:
      data: {"type":"supervisor","routing_to":"researcher","iteration":1,"ts":"..."}
      data: {"type":"researcher_start","pages_selected":4,"ts":"..."}
      ...
      data: {"type":"done"}  ← sentinel, close the stream

    The stream closes automatically when:
    - The graph finishes (sentinel received)
    - The client disconnects (CancelledError / GeneratorExit caught)
    """
    q = job_manager.get_queue(job_id)
    if q is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    async def event_generator() -> AsyncIterator[dict]:
        try:
            while True:
                # Respect client disconnect — request.is_disconnected() is polled
                # alongside the queue wait to avoid hanging on abandoned connections.
                if await request.is_disconnected():
                    log.info("[sse] client disconnected from job=%s", job_id)
                    break

                try:
                    event: dict = await asyncio.wait_for(q.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    # Send a keep-alive comment so the connection doesn't time out
                    yield {"comment": "keep-alive"}
                    continue

                if event.get("type") == "__done__":
                    # Terminal sentinel — signal end-of-stream and stop
                    yield {"data": json.dumps({"type": "done"})}
                    break

                yield {"data": json.dumps(event)}

        except (asyncio.CancelledError, GeneratorExit):
            log.info("[sse] generator cancelled for job=%s", job_id)
        finally:
            job_manager.remove_queue(job_id)

    return EventSourceResponse(event_generator())


@app.get("/download/{job_id}", tags=["sdk"])
async def download_sdk(job_id: str):
    """
    Returns a ZIP archive containing the generated SDK files.

    The final_files dict is read from the MongoDB checkpoint via LangGraph's
    get_state API, packaged into a ZIP, and streamed to the client.
    """
    import backend.graph.graph as graph_module
    graph = graph_module.compiled_graph
    if graph is None:
        raise HTTPException(status_code=503, detail="Graph not initialised.")

    try:
        config   = {"configurable": {"thread_id": job_id}}
        snapshot = await graph.aget_state(config)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Job not found: {exc}")

    if not snapshot or not snapshot.values:
        raise HTTPException(status_code=404, detail="No checkpoint found for this job.")

    state      = dict(snapshot.values)
    final_files: Optional[dict] = state.get("final_files") or state.get("sdk_files")

    if not final_files:
        raise HTTPException(
            status_code=202,
            detail="SDK not ready yet — job may still be running or failed.",
        )

    zip_buffer = job_manager.build_zip(final_files)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="sdk_{job_id[:8]}.zip"'},
    )


# ──────────────────────────────────────────────────────────────────────────────
# WebSocket Bridge  (Dev 4 — Chrome ↔ VS Code)
# ──────────────────────────────────────────────────────────────────────────────

# Active WS connections: { connection_id: WebSocket }
_ws_clients: dict[str, WebSocket] = {}


@app.websocket("/ws")
async def websocket_bridge(ws: WebSocket):
    """
    Local WebSocket bridge — Chrome extension connects here to relay messages
    to VS Code (and vice versa).

    Protocol (see docs/implementation.md §11):
      Chrome sends:  { type: "new_job",   job_id, url, language }
      VS Code sends: { type: "vscode_ready", workspace }
      Server relays: messages to all OTHER connected clients
    """
    await ws.accept()
    conn_id = id(ws)
    _ws_clients[conn_id] = ws
    log.info("[ws] client connected id=%s (total=%d)", conn_id, len(_ws_clients))

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_text(json.dumps({"type": "error", "message": "Invalid JSON"}))
                continue

            # Handle ping/pong
            if msg.get("type") == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
                continue

            # Relay to all other connected clients
            dead = []
            for cid, client in _ws_clients.items():
                if cid != conn_id:
                    try:
                        await client.send_text(raw)
                    except Exception:
                        dead.append(cid)

            # Clean up disconnected clients
            for cid in dead:
                _ws_clients.pop(cid, None)

    except WebSocketDisconnect:
        log.info("[ws] client disconnected id=%s", conn_id)
    finally:
        _ws_clients.pop(conn_id, None)
