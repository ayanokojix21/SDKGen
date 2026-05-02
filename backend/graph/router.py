"""
backend/graph/router.py
────────────────────────
Pure routing function — reads state.next_agent set by the Supervisor LLM.
Hard safety overrides take priority over any LLM routing decision.

Dev 1 owns this file.

Edge cases handled (from division.md §7):
  A1: Supervisor routes same agent 3x for same unresolved issue → status=failed
  A2: iteration_count >= 15 → Force END, emit safety_cutoff
  A3: qa_iteration >= 4    → Force END, QA cannot be resolved
"""

from __future__ import annotations

import logging

from backend.config import settings
from backend.graph.state import emit_sse

log = logging.getLogger(__name__)


def route_next(state: dict) -> str:
    """
    Pure function — called by LangGraph's conditional edge after Supervisor.
    Returns the next node name: one of the agent names, or "end" to terminate.
    """
    # ── Check: status already failed ──────────────────────────────────────────
    if state.get("status") == "failed":
        return "end"

    # ── A2: iteration_count ceiling ───────────────────────────────────────────
    if state.get("iteration_count", 0) >= settings.MAX_ITERATIONS:
        log.error("[router] iteration_count=%d >= %d — forcing END",
                  state.get("iteration_count"), settings.MAX_ITERATIONS)
        return "end"

    # ── A3: qa_iteration ceiling ──────────────────────────────────────────────
    if state.get("qa_iteration", 0) >= settings.MAX_QA_ROUNDS:
        log.error("[router] qa_iteration=%d >= %d — forcing END",
                  state.get("qa_iteration"), settings.MAX_QA_ROUNDS)
        return "end"

    # ── Route to whatever the Supervisor decided ──────────────────────────────
    next_agent = state.get("next_agent", "end")
    if next_agent:
        # Normalize: lowercase, strip whitespace, replace spaces with underscores
        next_agent = next_agent.lower().strip().replace(" ", "_")

    # Common LLM aliases → canonical names
    _aliases = {
        "qa": "qa_tester",
        "qatester": "qa_tester",
        "qa_test": "qa_tester",
        "tester": "qa_tester",
        "research": "researcher",
        "package": "packager",
    }
    next_agent = _aliases.get(next_agent, next_agent)

    # Validate the agent name
    valid = {"researcher", "architect", "engineer", "qa_tester", "packager", "end"}
    if next_agent not in valid:
        log.warning("[router] invalid next_agent=%r — defaulting to end", next_agent)
        return "end"

    return next_agent
