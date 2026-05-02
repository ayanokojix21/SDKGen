"""
backend/graph/state.py
──────────────────────
Single source of truth for the LangGraph multi-agent system.
Updated for Token Tracking, MongoDB Vector Search, and Structured Outputs.
"""

from __future__ import annotations

import json
import operator
from datetime import datetime, timezone
from typing import Annotated, Optional, Sequence, TypedDict

from langchain_core.messages import BaseMessage


class SDKJobState(TypedDict):
    """
    LangGraph state TypedDict.
    """

    # ── Conversation ──────────────────────────────────────────────────────────
    messages: Annotated[Sequence[BaseMessage], operator.add]

    # ── Job metadata ──────────────────────────────────────────────────────────
    job_id: str
    target_url: str
    language: str                  # "python" | "typescript"
    page_content: str              # landing page text
    page_links: list[dict]         # [{"text":"Auth","href":"...","inNav":True}]

    # ── Token & Cost Tracking ─────────────────────────────────────────────────
    total_tokens: int
    estimated_cost_usd: float

    # ── Researcher & RAG ──────────────────────────────────────────────────────
    crawl_plan: Optional[list[dict]]     # [{url, reason, priority}]
    crawled_pages: Optional[list[dict]]  # [{url, scraped_at}]
    # Vector store reference - instead of holding ALL page content in state
    vector_store_collection: Optional[str]
    # Small structured snippets for the Supervisor to see
    research_summary: Optional[str]

    # ── Architect outputs ─────────────────────────────────────────────────────
    api_schema: Optional[dict]           # Pydantic-validated endpoint schema
    schema_fixes: Annotated[list[str], operator.add]

    # ── Engineer outputs ──────────────────────────────────────────────────────
    sdk_files: Optional[dict]            # {"client.py": "...", "models.py": "..."}
    syntax_errors: Annotated[list[str], operator.add]

    # ── QA Tester outputs ─────────────────────────────────────────────────────
    test_results: Optional[list[dict]]
    qa_iteration: int

    # ── Packager outputs ──────────────────────────────────────────────────────
    final_files: Optional[dict]
    narration_text: Optional[str]

    # ── Routing & control ─────────────────────────────────────────────────────
    next_agent: str
    instruction: str
    iteration_count: int
    status: str                          # "running" | "success" | "failed"
    failure_reason: Optional[str]

    # ── SSE event queue ───────────────────────────────────────────────────────
    sse_events: Annotated[list[dict], operator.add]


def emit_sse(type_: str, **kwargs) -> dict:
    """Helper to format SSE events."""
    return {"sse_events": [{"type": type_, **kwargs}]}


def build_state_summary(state: dict) -> str:
    """
    Builds a concise text summary of the current state for the Supervisor.
    The Supervisor uses this to decide routing.
    """
    lines = [
        f"Job ID: {state.get('job_id', 'unknown')}",
        f"Target URL: {state.get('target_url', 'unknown')}",
        f"Language: {state.get('language', 'unknown')}",
        f"Status: {state.get('status', 'unknown')}",
        f"Iteration: {state.get('iteration_count', 0)}",
        f"QA Iteration: {state.get('qa_iteration', 0)}",
        f"Tokens Used: {state.get('total_tokens', 0)}",
        f"Estimated Cost: ${state.get('estimated_cost_usd', 0.0):.4f}",
    ]

    if state.get("research_summary"):
        lines.append(f"Research Summary: {state['research_summary'][:500]}")
    if state.get("api_schema"):
        ep_count = len(state["api_schema"].get("endpoints", []))
        lines.append(f"API Schema: {ep_count} endpoints defined")
    if state.get("sdk_files"):
        lines.append(f"SDK Files: {list(state['sdk_files'].keys())}")
    if state.get("syntax_errors"):
        lines.append(f"Syntax Errors: {state['syntax_errors']}")
    if state.get("test_results"):
        lines.append(f"Test Results: {state['test_results']}")
    if state.get("failure_reason"):
        lines.append(f"Failure Reason: {state['failure_reason']}")

    # Last few messages for context
    msgs = state.get("messages", [])
    if msgs:
        last_msgs = msgs[-3:]
        lines.append("Recent Messages:")
        for m in last_msgs:
            name = getattr(m, "name", "unknown")
            content = m.content[:200] if hasattr(m, "content") else str(m)[:200]
            lines.append(f"  [{name}]: {content}")

    return "\n".join(lines)


def create_initial_state(
    job_id: str,
    target_url: str,
    language: str,
    page_content: str,
    page_links: list[dict],
) -> SDKJobState:
    return {
        "messages": [],
        "job_id": job_id,
        "target_url": target_url,
        "language": language,
        "page_content": page_content,
        "page_links": page_links,
        
        "total_tokens": 0,
        "estimated_cost_usd": 0.0,

        "crawl_plan": None,
        "crawled_pages": None,
        "vector_store_collection": None,
        "research_summary": None,

        "api_schema": None,
        "schema_fixes": [],

        "sdk_files": None,
        "syntax_errors": [],

        "test_results": None,
        "qa_iteration": 0,

        "final_files": None,
        "narration_text": None,

        "next_agent": "supervisor",
        "instruction": "Begin SDK generation.",
        "iteration_count": 0,
        "status": "running",
        "failure_reason": None,

        "sse_events": [
            _make_event("job_started", job_id=job_id, url=target_url, language=language)
        ],
    }

def _make_event(event_type: str, **kwargs) -> dict:
    return {
        "type": event_type,
        "ts":   datetime.now(timezone.utc).isoformat(),
        **kwargs,
    }
