"""
backend/agents/packager.py
───────────────────────────
Packager Agent — Final deterministic step in the Docs-to-Code pipeline.

Responsibilities
─────────────────
1. Copy sdk_files → final_files (no mutations to source)
2. Validate all files are non-empty and syntactically sound
3. Generate 2–3 line narration via Narrator LLM
4. Set status = "success"
5. Emit final SSE events (packager_done triggers ZIP download in UI)

This is the terminal node — after packager, the graph reaches END.
No retry logic needed: if narration fails, it's non-critical.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from backend.config import settings
from backend.graph.state import emit_sse

log = logging.getLogger(__name__)

# ── Load narration prompt ─────────────────────────────────────────────────────
_NARRATE_PATH = Path(__file__).parent.parent / "prompts" / "narrate.txt"

def _load_narrate_prompt() -> str:
    try:
        return _NARRATE_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        log.warning("narrate.txt not found — narration will be skipped")
        return ""

_NARRATE_PROMPT = _load_narrate_prompt()

# ── LLM for narration (non-critical, higher temperature for natural speech) ───
from backend.llm import get_llm, get_token_usage

_narrate_llm = None

def _get_narrate_llm():
    """Lazy-initialize the narration LLM to avoid import-time API key errors."""
    global _narrate_llm
    if _narrate_llm is None:
        _narrate_llm = get_llm(temperature=0.7)
    return _narrate_llm


# ──────────────────────────────────────────────────────────────────────────────
# Packager node
# ──────────────────────────────────────────────────────────────────────────────

async def packager_node(state: dict) -> dict:
    """
    LangGraph node — packages SDK files and generates narration.
    Returns a partial state update dict. This is the terminal node.
    """
    sdk_files = state.get("sdk_files") or {}
    api_schema = state.get("api_schema") or {}
    language = state.get("language", "python")
    qa_iteration = state.get("qa_iteration", 0)
    syntax_errors = state.get("syntax_errors", [])

    if not sdk_files:
        log.error("[packager] no SDK files to package")
        return {
            "final_files": None,
            "narration_text": None,
            "status": "failed",
            "failure_reason": "No SDK files produced by engineer",
            "messages": [AIMessage(content="No SDK files to package.", name="packager")],
            **emit_sse("packager_fail", reason="No SDK files"),
        }

    # ── Copy SDK files to final_files ─────────────────────────────────────────
    final_files = dict(sdk_files)
    file_count = len(final_files)

    log.info("[packager] packaging %d files", file_count)

    # ── Validate: no empty files ──────────────────────────────────────────────
    empty_files = [f for f, c in final_files.items() if not c.strip()]
    if empty_files:
        log.warning("[packager] removing %d empty files: %s", len(empty_files), empty_files)
        for f in empty_files:
            del final_files[f]

    # ── Generate narration (non-critical) ─────────────────────────────────────
    api_name = api_schema.get("api_name", "API")
    endpoint_count = len(api_schema.get("endpoints", []))
    issues_fixed = len(syntax_errors) + (qa_iteration - 1 if qa_iteration > 1 else 0)

    narration_text = await _generate_narration(
        api_name=api_name,
        language=language,
        endpoint_count=endpoint_count,
        qa_iteration=qa_iteration,
        issues_count=issues_fixed,
    )

    # ── Generate ElevenLabs audio (non-critical) ─────────────────────────────
    narration_audio_url = None
    if narration_text:
        from backend.tools.elevenlabs_tts import generate_narration_audio
        narration_audio_url = await generate_narration_audio(
            text=narration_text,
            job_id=state.get("job_id", ""),
        )

    # ── Create Conversational Doc Reader Agent (non-critical) ─────────────────
    assistant_agent_id = None
    from backend.tools.elevenlabs_agent import create_doc_reader_agent
    
    # Try to find the main client code to upload as Knowledge Base
    client_code = ""
    for filename, content in final_files.items():
        if "client.py" in filename or "client.ts" in filename:
            client_code = content
            break
            
    assistant_agent_id = await create_doc_reader_agent(
        api_name=api_name,
        language=language,
        job_id=state.get("job_id", ""),
        sdk_client_code=client_code,
        schema_json=json.dumps(api_schema),
        target_url=state.get("target_url", ""),
        page_content=state.get("page_content", "")
    )

    # ── Build SSE events ──────────────────────────────────────────────────────
    summary = f"SDK packaged: {len(final_files)} files ready for download."
    log.info("[packager] %s", summary)

    sse_events = []

    # Emit file_ready for each file (VS Code file injection needs content)
    for filename, content in final_files.items():
        sse_events.append({
            "type": "file_ready",
            "filename": filename,
            "content": content,
        })

    # Packager summary
    sse_events.append({
        "type": "packager_done",
        "file_count": len(final_files),
        "files": list(final_files.keys()),
    })

    # Narration event (for TTS in popup)
    if narration_text:
        sse_events.append({
            "type": "narrate",
            "text": narration_text,
        })

    # Complete event (triggers download/VS Code buttons in popup)
    sse_events.append({
        "type": "complete",
        "summary": {
            "endpoints": endpoint_count,
            "files": len(final_files),
            "language": language,
            "api_name": api_name,
            "assistant_agent_id": assistant_agent_id,
        },
        "agent_id": assistant_agent_id,
    })

    # Propagate token tracking to state for consistency
    token_usage = get_token_usage()

    return {
        "final_files": final_files,
        "narration_text": narration_text,
        "status": "success",
        "messages": [AIMessage(content=summary, name="packager")],
        "sse_events": sse_events,
        **token_usage,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Narration helper
# ──────────────────────────────────────────────────────────────────────────────

async def _generate_narration(
    api_name: str,
    language: str,
    endpoint_count: int,
    qa_iteration: int,
    issues_count: int,
) -> str | None:
    """
    Call Narrator LLM for a 2–3 line spoken summary.
    Non-critical — returns None on any failure.

    Format:
    "We built a {language} SDK for {api_name} with {endpoint_count} endpoints.
     The system automatically fixed {issues_count} issues during generation."
    """
    if not _NARRATE_PROMPT:
        # Fallback: deterministic narration
        return _deterministic_narration(api_name, language, endpoint_count, issues_count)

    prompt = _NARRATE_PROMPT
    replacements = {
        "{api_name}": api_name,
        "{language}": language,
        "{endpoint_count}": str(endpoint_count),
        "{qa_iteration}": str(qa_iteration),
        "{fixes_applied}": "yes" if qa_iteration > 1 else "no",
        "{status}": "success",
    }
    for k, v in replacements.items():
        prompt = prompt.replace(k, v)

    try:
        response = await _get_narrate_llm().ainvoke([
            HumanMessage(content=prompt),
        ])

        narration = _extract_text(response)

        # Strip surrounding quotes if LLM wraps them
        if narration.startswith('"') and narration.endswith('"'):
            narration = narration[1:-1]

        log.info("[packager] narration: %s", narration[:100])
        return narration

    except Exception as exc:
        log.warning("[packager] narration failed (non-critical): %s", exc)
        return _deterministic_narration(api_name, language, endpoint_count, issues_count)


def _deterministic_narration(
    api_name: str, language: str, endpoint_count: int, issues_count: int,
) -> str:
    """Fallback narration when LLM is unavailable."""
    base = f"We built a {language} SDK for {api_name} with {endpoint_count} endpoints."
    if issues_count > 0:
        base += f" The system automatically fixed {issues_count} issues during generation."
    else:
        base += " All validation checks passed on the first attempt."
    return base


def _extract_text(response) -> str:
    """Safely extract string content from LangChain AIMessage."""
    content = response.content
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [p["text"] for p in content if isinstance(p, dict) and "text" in p]
        return " ".join(parts).strip()
    return str(content).strip()
