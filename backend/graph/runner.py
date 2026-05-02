"""
backend/graph/runner.py
────────────────────────
Async graph runner — bridges LangGraph execution and the SSE queue.

How it works
─────────────
1. Calls compiled_graph.astream_events(initial_state, config, version="v2")
   This yields every node lifecycle event as it happens.

2. For each "on_node_end" event whose output contains an "sse_events" list,
   extract and forward those events to the job's asyncio.Queue.

3. When the graph finishes (or raises), put the terminal sentinel / error event
   so the SSE generator knows to close the stream.

4. Writes the final state snapshot to disk via job_manager.write_final_checkpoint().

Why astream_events instead of ainvoke?
────────────────────────────────────────
• ainvoke blocks until the entire graph finishes — no real-time streaming.
• astream_events yields events as each node completes — we get SSE events
  progressively, so the Chrome/VS Code extension sees live updates.
• version="v2" is required for LangGraph 1.x (v1 is deprecated).

Thread safety
─────────────
• This function is launched via asyncio.create_task() — it runs in the same
  event loop as FastAPI, so all queue operations are safe without locks.

IMPORTANT: compiled_graph is accessed at RUNTIME via the module reference
(backend.graph.graph.compiled_graph), NOT imported as a local name at module
load time. This is because compiled_graph is initially None and only set
during init_graph() at FastAPI startup.
"""

from __future__ import annotations

import asyncio
import logging

from backend import job_manager
import backend.graph.graph as graph_module    # module reference — NOT the variable

log = logging.getLogger(__name__)

# LangGraph astream_events version — always use v2 for LangGraph 1.x
_STREAM_VERSION = "v2"


async def run_graph(job_id: str, initial_state: dict) -> None:
    """
    Background asyncio task — launched by POST /generate/start.
    Runs the compiled LangGraph and pipes sse_events to the job queue.

    Args:
        job_id:        Unique job identifier (used as thread_id for checkpointing)
        initial_state: The fully-initialised state dict from create_initial_state()
    """
    # Access at runtime — NOT the import-time snapshot
    graph = graph_module.compiled_graph

    if graph is None:
        log.error("[runner] compiled_graph is None — was init_graph() called?")
        await job_manager.put_error(job_id, "Graph not initialised. Server startup error.")
        return

    config = {
        "configurable": {
            "thread_id": job_id,   # ← MongoDB checkpointer uses this as the partition key
        },
        "recursion_limit": 50,     # LangGraph hard ceiling on top of our own limits
    }

    log.info("[runner] starting graph for job=%s", job_id)

    try:
        async for event in graph.astream_events(
            initial_state,
            config=config,
            version=_STREAM_VERSION,
        ):
            await _handle_event(job_id, event)

        # Graph completed successfully — write snapshot and signal done
        log.info("[runner] graph finished for job=%s", job_id)
        await _write_final_snapshot(job_id)
        await job_manager.put_sentinel(job_id)

    except asyncio.CancelledError:
        log.warning("[runner] task cancelled for job=%s", job_id)
        await job_manager.put_error(job_id, "Job was cancelled.")

    except Exception as exc:
        log.exception("[runner] unhandled exception for job=%s: %s", job_id, exc)
        await job_manager.put_error(job_id, f"Internal error: {exc}")

    finally:
        # Give frontend time to consume final events before destroying the queue.
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            pass  # Server shutting down — clean up immediately
        job_manager.remove_all_queues(job_id)
        log.info("[runner] cleaned up queue for job=%s", job_id)

# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────

async def _handle_event(job_id: str, event: dict) -> None:
    """
    Process a single astream_events event.

    We care about two event types:
    • "on_node_end"  — a node finished; its output may contain sse_events
    • "on_chain_end" — the overall graph (named "LangGraph") has finished

    All sse_events produced by agent nodes are forwarded to the SSE queue.
    """
    kind: str      = event.get("event", "")
    name: str      = event.get("name", "")
    data: dict     = event.get("data", {})

    if kind == "on_node_end":
        output: dict = data.get("output") or {}

        # sse_events is an append-only list in state — the node returns a delta
        node_sse_events: list[dict] = output.get("sse_events", [])
        for sse_event in node_sse_events:
            log.debug("[runner] job=%s sse_event type=%s", job_id, sse_event.get("type"))
            await job_manager.put_event(job_id, sse_event)

    elif kind == "on_chain_end" and name == "LangGraph":
        # The whole graph has finished — the final sse_events are in the output values
        final_output: dict = data.get("output") or {}
        final_sse: list[dict] = final_output.get("sse_events", [])

        # Forward any events we haven't seen yet
        if final_sse:
            last_event = final_sse[-1]
            if last_event.get("type") not in ("done", "job_started"):
                await job_manager.put_event(job_id, last_event)


async def _write_final_snapshot(job_id: str) -> None:
    """
    Reads the final checkpoint from MongoDB (or InMemorySaver) via the compiled
    graph's get_state API, and writes it to disk for offline inspection.
    """
    try:
        graph = graph_module.compiled_graph
        if graph is None:
            return
        config = {"configurable": {"thread_id": job_id}}
        snapshot = await graph.aget_state(config)
        if snapshot and snapshot.values:
            job_manager.write_final_checkpoint(job_id, dict(snapshot.values))
    except Exception as exc:
        log.warning("[runner] failed to write final snapshot for job=%s: %s", job_id, exc)
