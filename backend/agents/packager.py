"""
Packager Agent — Final step in the Docs-to-Code pipeline.

Deterministic agent (no LLM call for core logic). Copies sdk_files to
final_files, then optionally calls the Narrator LLM for a spoken summary.
Sets the job status to "success".
"""

import json
import logging
from pathlib import Path

from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger(__name__)

_NARRATE_PATH = Path(__file__).parent.parent / "prompts" / "narrate.txt"
_NARRATE_PROMPT = _NARRATE_PATH.read_text(encoding="utf-8")


async def packager_node(state: dict) -> dict:
    """
    Packager agent node for the LangGraph graph.

    Finalizes the SDK: copies files, generates narration, sets status.
    This is the terminal node — after this, the graph ends.
    """
    sse_events = []
    messages = []

    sdk_files = state.get("sdk_files") or {}
    api_schema = state.get("api_schema") or {}
    language = state.get("language", "python")
    qa_iteration = state.get("qa_iteration", 0)

    if not sdk_files:
        logger.warning("Packager: no SDK files to package")
        messages.append(AIMessage(
            content="No SDK files available to package.",
            name="packager",
        ))
        return {
            "final_files": None,
            "narration_text": None,
            "status": "failed",
            "failure_reason": "No SDK files produced by engineer",
            "messages": messages,
            "sse_events": [{"type": "packager_failed", "reason": "No SDK files"}],
        }

    # ── Copy SDK files to final_files ────────────────────────────────────
    final_files = dict(sdk_files)

    sse_events.append({
        "type": "packager_start",
        "file_count": len(final_files),
    })

    # ── Generate narration ───────────────────────────────────────────────
    narration_text = await _generate_narration(
        api_name=api_schema.get("api_name", "API"),
        language=language,
        endpoint_count=len(api_schema.get("endpoints", [])),
        qa_iteration=qa_iteration,
    )

    # ── Build completion ─────────────────────────────────────────────────
    summary = (
        f"SDK packaged: {len(final_files)} files ready for download. "
        f"Status: success."
    )
    messages.append(AIMessage(content=summary, name="packager"))

    sse_events.append({
        "type": "packager_done",
        "file_count": len(final_files),
        "files": list(final_files.keys()),
        "narration": narration_text,
    })

    logger.info(f"Packager: {summary}")

    return {
        "final_files": final_files,
        "narration_text": narration_text,
        "status": "success",
        "messages": messages,
        "sse_events": sse_events,
    }


async def _generate_narration(
    api_name: str,
    language: str,
    endpoint_count: int,
    qa_iteration: int,
) -> str | None:
    """
    Call the Narrator LLM for a short spoken summary.
    Non-critical — returns None on failure.
    """
    fixes_applied = "yes" if qa_iteration > 1 else "no"
    prompt = _NARRATE_PROMPT.replace("{api_name}", api_name)
    prompt = prompt.replace("{language}", language)
    prompt = prompt.replace("{endpoint_count}", str(endpoint_count))
    prompt = prompt.replace("{qa_iteration}", str(qa_iteration))
    prompt = prompt.replace("{fixes_applied}", fixes_applied)
    prompt = prompt.replace("{status}", "success")

    try:
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            temperature=0.7,
        )

        response = await llm.ainvoke([
            SystemMessage(content=prompt),
            HumanMessage(content="Generate the narration summary."),
        ])

        narration = response.content.strip()
        # Strip quotes if the LLM wraps it
        if narration.startswith('"') and narration.endswith('"'):
            narration = narration[1:-1]

        logger.info(f"Narration: {narration}")
        return narration

    except Exception as e:
        logger.warning(f"Narration generation failed (non-critical): {e}")
        return None
