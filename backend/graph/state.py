"""
backend/graph/state.py
──────────────────────
Single source of truth for the LangGraph multi-agent system.

Design principles
─────────────────
• All fields typed explicitly — no untyped dicts at graph boundaries.
• Annotated reducers used only where append semantics are needed
  (messages, sse_events, schema_fixes, syntax_errors).
• Helper functions here so agents import ONE module, not many.
"""

from __future__ import annotations

import json
import operator
from datetime import datetime, timezone
from typing import Annotated, Optional, Sequence

from langchain_core.messages import BaseMessage


# ──────────────────────────────────────────────────────────────────────────────
# Core State
# ──────────────────────────────────────────────────────────────────────────────

class SDKJobState(dict):
    """
    LangGraph state TypedDict (expressed as a plain dict subclass so the type
    checker can validate field access while LangGraph can use it natively).

    Field groups:
      - Job metadata      (immutable after create_initial_state)
      - Researcher        (populated by agents/researcher.py)
      - Architect         (populated by agents/architect.py)
      - Engineer          (populated by agents/engineer.py)
      - QA Tester         (populated by agents/qa_tester.py)
      - Packager          (populated by agents/packager.py)
      - Routing / control (managed by supervisor.py + router.py)
      - SSE event queue   (append-only, consumed by FastAPI /generate/stream)
    """

    # ── Conversation (append-only) ────────────────────────────────────────────
    messages: Annotated[Sequence[BaseMessage], operator.add]

    # ── Job metadata ──────────────────────────────────────────────────────────
    job_id: str
    target_url: str
    language: str                  # "python" | "typescript"
    page_content: str              # landing page text injected by Chrome extension
    page_links: list[dict]         # [{"text":"Auth","href":"/docs/auth","inNav":True}]

    # ── Researcher outputs ────────────────────────────────────────────────────
    crawl_plan: Optional[list[dict]]     # [{url, reason, priority}]
    crawled_pages: Optional[list[dict]]  # [{url, content, scraped_at}]
    knowledge_base: Optional[dict]       # structured research output (see researcher prompt)

    # ── Architect outputs ─────────────────────────────────────────────────────
    api_schema: Optional[dict]           # validated endpoint schema
    schema_fixes: Annotated[list[str], operator.add]  # auto-fixes log

    # ── Engineer outputs ──────────────────────────────────────────────────────
    sdk_files: Optional[dict]            # {"client.py": "...", "models.py": "..."}
    syntax_errors: Annotated[list[str], operator.add]

    # ── QA Tester outputs ─────────────────────────────────────────────────────
    test_results: Optional[list[dict]]   # [{endpoint, method, status_code, passed, ...}]
    qa_iteration: int

    # ── Packager outputs ──────────────────────────────────────────────────────
    final_files: Optional[dict]          # linted, delivery-ready files
    narration_text: Optional[str]

    # ── Routing & control ─────────────────────────────────────────────────────
    next_agent: str                      # set by supervisor
    instruction: str                     # specific directive for the next agent
    iteration_count: int                 # total graph hops — ceiling: MAX_ITERATIONS
    status: str                          # "running" | "success" | "failed"
    failure_reason: Optional[str]

    # ── SSE event queue (append-only, piped by runner.py → asyncio.Queue) ────
    sse_events: Annotated[list[dict], operator.add]


# ──────────────────────────────────────────────────────────────────────────────
# Factories & Helpers
# ──────────────────────────────────────────────────────────────────────────────

def create_initial_state(
    job_id: str,
    target_url: str,
    language: str,
    page_content: str,
    page_links: list[dict],
) -> dict:
    """
    Returns the fully-initialised state dict for a new job.
    Pass this directly to compiled_graph.ainvoke / astream_events.
    """
    return {
        # Conversation
        "messages": [],

        # Job metadata
        "job_id": job_id,
        "target_url": target_url,
        "language": language,
        "page_content": page_content,
        "page_links": page_links,

        # Researcher
        "crawl_plan": None,
        "crawled_pages": None,
        "knowledge_base": None,

        # Architect
        "api_schema": None,
        "schema_fixes": [],

        # Engineer
        "sdk_files": None,
        "syntax_errors": [],

        # QA Tester
        "test_results": None,
        "qa_iteration": 0,

        # Packager
        "final_files": None,
        "narration_text": None,

        # Routing
        "next_agent": "supervisor",
        "instruction": "Begin SDK generation.",
        "iteration_count": 0,
        "status": "running",
        "failure_reason": None,

        # SSE queue
        "sse_events": [
            _make_event("job_started", job_id=job_id, url=target_url, language=language)
        ],
    }


def build_state_summary(state: dict) -> str:
    """
    Concise JSON summary of state for the Supervisor LLM.
    Includes enough context for the Supervisor to make correct routing decisions,
    including failure details and QA failure breakdown.
    """
    # Summarise test_results for the supervisor
    qa_summary: dict = {}
    if state.get("test_results") is not None:
        results: list[dict] = state["test_results"]
        passed  = sum(1 for r in results if r.get("passed"))
        failed  = len(results) - passed
        failures = [
            {"endpoint": r.get("endpoint"), "status_code": r.get("status_code"),
             "error": r.get("error")}
            for r in results if not r.get("passed")
        ]
        qa_summary = {
            "passed": passed,
            "failed": failed,
            "total": len(results),
            "failure_details": failures[:5],  # cap at 5 to avoid bloating prompt
        }

    summary = {
        "job_id":           state.get("job_id"),
        "target_url":       state.get("target_url"),
        "language":         state.get("language"),
        "status":           state.get("status"),
        "iteration_count":  state.get("iteration_count"),
        "qa_iteration":     state.get("qa_iteration"),
        # Boolean flags — what's been completed
        "has_crawl_plan":      state.get("crawl_plan")    is not None,
        "has_knowledge_base":  state.get("knowledge_base") is not None,
        "has_api_schema":      state.get("api_schema")    is not None,
        "has_sdk_files":       state.get("sdk_files")     is not None,
        "has_test_results":    state.get("test_results")  is not None,
        "has_final_files":     state.get("final_files")   is not None,
        # Detail for fix routing
        "schema_fixes":        state.get("schema_fixes", []),
        "syntax_errors":       state.get("syntax_errors", []),
        "qa_summary":          qa_summary,
        "failure_reason":      state.get("failure_reason"),
        "last_instruction":    state.get("instruction"),
    }
    return json.dumps(summary, indent=2, default=str)


def emit_sse(event_type: str, **kwargs) -> dict:
    """
    Returns a **partial state update** dict that appends ONE SSE event.
    Usage inside any agent node:
        return {**emit_sse("researcher_start", page_count=4), "crawl_plan": plan}
    """
    return {"sse_events": [_make_event(event_type, **kwargs)]}


def _make_event(event_type: str, **kwargs) -> dict:
    return {
        "type": event_type,
        "ts":   datetime.now(timezone.utc).isoformat(),
        **kwargs,
    }
