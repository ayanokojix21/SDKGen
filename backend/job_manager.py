"""
backend/job_manager.py
──────────────────────
In-process job registry + SSE queue management.

Responsibilities
─────────────────
• create_job()    — builds initial state, registers a per-job asyncio.Queue
• get_queue()     — returns the queue for a running job (or None)
• remove_queue()  — called by SSE generator on client disconnect
• build_zip()     — packages sdk_files dict into an in-memory ZIP
• write_checkpoint_file() — writes a JSON snapshot of state to backend/jobs/{job_id}/
  so the dev team can inspect state after a run without needing MongoDB access.

Design
──────
• One asyncio.Queue per job_id — runner puts events, SSE generator gets them
• Queues are stored in a module-level dict — safe for single-process (uvicorn --reload)
• build_zip() returns BytesIO so FastAPI can stream it without touching disk
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.config import settings
from backend.graph.state import create_initial_state

log = logging.getLogger(__name__)

# ── Per-job SSE queue registry ─────────────────────────────────────────────────
# { job_id: asyncio.Queue }
_queues: dict[str, asyncio.Queue] = {}


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def create_job(
    target_url: str,
    language: str,
    page_content: str,
    page_links: list[dict],
) -> tuple[str, dict]:
    """
    Creates a new job_id, initialises the state dict, and registers a fresh
    asyncio.Queue for SSE streaming.

    Returns (job_id, initial_state).
    """
    job_id = str(uuid.uuid4())
    initial_state = create_initial_state(
        job_id=job_id,
        target_url=target_url,
        language=language,
        page_content=page_content,
        page_links=page_links,
    )

    # Register SSE queue
    _queues[job_id] = asyncio.Queue()

    # Write initial checkpoint file for offline inspection
    _write_checkpoint_file(job_id, {"status": "started", "target_url": target_url,
                                     "language": language, "created_at": _now_iso()})

    log.info("[job_manager] created job=%s url=%s language=%s", job_id, target_url, language)
    return job_id, initial_state


def get_queue(job_id: str) -> Optional[asyncio.Queue]:
    """Returns the SSE queue for job_id, or None if the job doesn't exist."""
    return _queues.get(job_id)


def remove_queue(job_id: str) -> None:
    """Remove the SSE queue on client disconnect — prevents memory leaks."""
    removed = _queues.pop(job_id, None)
    if removed:
        log.info("[job_manager] removed queue for job=%s", job_id)


async def put_event(job_id: str, event: dict) -> None:
    """
    Safely puts one SSE event dict onto the job queue.
    No-op if the job queue no longer exists (client disconnected before graph finished).
    """
    q = _queues.get(job_id)
    if q is not None:
        await q.put(event)


async def put_sentinel(job_id: str) -> None:
    """Signal end-of-stream to the SSE generator."""
    await put_event(job_id, {"type": "__done__"})


async def put_error(job_id: str, message: str) -> None:
    """Signal a fatal error to the SSE generator."""
    await put_event(job_id, {"type": "error", "message": message})
    await put_sentinel(job_id)


def build_zip(files: dict[str, str]) -> io.BytesIO:
    """
    Packages a {filename → content} dict into an in-memory ZIP.
    Returns a BytesIO positioned at byte 0 — ready for FastAPI StreamingResponse.

    Args:
        files: e.g. {"client.py": "...", "models.py": "...", "tests/test_client.py": "..."}
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for filename, content in files.items():
            zf.writestr(filename, content)
    buf.seek(0)
    return buf


def write_final_checkpoint(job_id: str, final_state: dict) -> None:
    """
    Writes the final state snapshot to disk so the team can inspect completed jobs.
    Called by runner.py after graph finishes.
    """
    safe_state = {
        k: v for k, v in final_state.items()
        if k not in ("messages",)   # skip non-serialisable LangChain messages
    }
    _write_checkpoint_file(job_id, safe_state)


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────

def _write_checkpoint_file(job_id: str, data: dict) -> None:
    """Persists a JSON file to backend/jobs/{job_id}/state.json."""
    try:
        job_dir = Path(settings.JOBS_DIR) / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_path = job_dir / "state.json"
        with open(checkpoint_path, "w", encoding="utf-8") as f:
            json.dump({**data, "updated_at": _now_iso()}, f, indent=2, default=str)
    except Exception as exc:
        log.warning("[job_manager] failed to write checkpoint file for job=%s: %s", job_id, exc)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
