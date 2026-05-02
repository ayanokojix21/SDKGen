"""
backend/agents/architect.py
────────────────────────────
Architect Agent — Transforms knowledge_base into validated api_schema.

Responsibilities
─────────────────
1. Load the Gemma-optimized architect prompt
2. Call Gemini with knowledge_base → get raw api_schema JSON
3. Run deterministic validate_schema() for post-validation + auto-fixes
4. If validation has critical errors → retry LLM once with error context
5. Emit SSE events for each phase

Self-correction
────────────────
• validate_schema auto-fixes trivial issues (trailing slashes, missing full_url,
  undeclared path params, body on GET)
• If critical errors remain after auto-fix → one LLM retry with error feedback
• If still broken → return schema as-is with errors logged (let QA catch the rest)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from backend.config import settings
from backend.graph.state import emit_sse
from backend.tools.validate_schema import validate_schema

log = logging.getLogger(__name__)

# ── Load prompt once at import time ───────────────────────────────────────────
_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "architect.txt"

def _load_prompt() -> str:
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        log.warning("architect.txt not found — using minimal fallback")
        return _FALLBACK_PROMPT

_FALLBACK_PROMPT = """\
You are an API schema architect. Convert the knowledge_base into a clean api_schema.
Return ONLY valid JSON with: api_name, base_url, auth, endpoints[].
Each endpoint needs: name (snake_case), method, path, full_url, description,
headers, query_params, path_params, body, response.

KNOWLEDGE BASE:
{knowledge_base}
"""

# ── LLM singleton ─────────────────────────────────────────────────────────────
from backend.llm import get_llm
_llm = get_llm(temperature=0.1)

MAX_RETRIES = 2  # initial + 1 retry with error context


# ──────────────────────────────────────────────────────────────────────────────
# Architect node
# ──────────────────────────────────────────────────────────────────────────────

async def architect_node(state: dict) -> dict:
    """
    LangGraph node — transforms knowledge_base → validated api_schema.
    Returns a partial state update dict.
    """
    knowledge_base = state.get("knowledge_base")
    language = state.get("language", "python")
    instruction = state.get("instruction", "Generate the API schema")

    if not knowledge_base:
        log.warning("[architect] empty knowledge_base — skipping")
        return {
            "api_schema": None,
            "schema_fixes": [],
            "messages": [AIMessage(content="No knowledge base available.", name="architect")],
            **emit_sse("architect_skip", reason="empty knowledge_base"),
        }

    endpoint_count = len(knowledge_base.get("endpoints_raw", []))
    log.info("[architect] starting — %d raw endpoints", endpoint_count)

    # ── Build prompt ──────────────────────────────────────────────────────────
    base_prompt = _load_prompt()
    prompt = base_prompt.replace("{knowledge_base}", json.dumps(knowledge_base, indent=2))
    prompt = prompt.replace("{language}", language)
    prompt = prompt.replace("{instruction}", instruction)

    # ── LLM call with validation + self-correction retry ──────────────────────
    api_schema = None
    schema_fixes: list[str] = []
    validation_errors: list[str] = []
    last_error = ""

    for attempt in range(1, MAX_RETRIES + 1):
        human_msg = "Transform this knowledge_base into an api_schema. Return JSON only."
        if attempt > 1 and validation_errors:
            human_msg = (
                "Your previous schema had validation errors. Fix them:\n\n"
                + "\n".join(f"- {e}" for e in validation_errors)
                + "\n\nReturn corrected JSON only. No explanation."
            )

        try:
            response = await _llm.ainvoke([
                SystemMessage(content=prompt),
                HumanMessage(content=human_msg),
            ])
            raw = _extract_text(response)
            api_schema = _parse_json(raw)
        except json.JSONDecodeError as exc:
            last_error = f"JSON parse error (attempt {attempt}): {exc}"
            log.warning("[architect] %s — raw=%r", last_error, raw[:200] if 'raw' in dir() else "N/A")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(2)
                continue
            break
        except Exception as exc:
            last_error = f"LLM error (attempt {attempt}): {exc}"
            log.error("[architect] %s", last_error)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(2)
                continue
            break

        if api_schema is None:
            continue

        # ── Ensure required top-level fields ──────────────────────────────────
        api_schema.setdefault("endpoints", [])
        api_schema.setdefault("base_url", "")
        api_schema.setdefault("auth", {"type": "none", "location": "none", "key_name": None})
        api_schema.setdefault("api_name", knowledge_base.get("api_name", "Unknown API"))

        # ── Deterministic post-validation ─────────────────────────────────────
        validation = validate_schema(api_schema)
        api_schema = validation["schema"]
        schema_fixes = validation["fixes"]
        validation_errors = validation["errors"]

        if not validation_errors:
            log.info("[architect] schema valid on attempt %d (%d auto-fixes)", attempt, len(schema_fixes))
            break

        log.warning("[architect] attempt %d: %d validation errors — %s",
                     attempt, len(validation_errors), validation_errors[:3])

    # ── Handle total failure ──────────────────────────────────────────────────
    if api_schema is None:
        log.error("[architect] failed to produce schema: %s", last_error)
        return {
            "api_schema": None,
            "schema_fixes": [],
            "messages": [AIMessage(content=f"Architect failed: {last_error}", name="architect")],
            **emit_sse("architect_error", error=last_error),
        }

    # ── Build result ──────────────────────────────────────────────────────────
    ep_count = len(api_schema.get("endpoints", []))
    auth_type = api_schema.get("auth", {}).get("type", "unknown")
    fix_count = len(schema_fixes)
    err_count = len(validation_errors)

    summary = (
        f"API schema generated: {ep_count} endpoints, auth={auth_type}. "
        f"{fix_count} auto-fixes, {err_count} validation errors."
    )
    log.info("[architect] %s", summary)

    # Merge SSE events
    sse_update = emit_sse(
        "architect_done",
        endpoint_count=ep_count,
        auth_type=auth_type,
        auto_fixes=fix_count,
        validation_errors=err_count,
        valid=err_count == 0,
    )

    return {
        "api_schema": api_schema,
        "schema_fixes": schema_fixes,
        "messages": [AIMessage(content=summary, name="architect")],
        **sse_update,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _extract_text(response) -> str:
    """Safely extract string content from LangChain AIMessage."""
    content = response.content
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [p["text"] for p in content if isinstance(p, dict) and "text" in p]
        return " ".join(parts).strip()
    return str(content).strip()


def _parse_json(raw: str) -> dict | None:
    """Strip markdown fences and parse JSON."""
    cleaned = re.sub(r"^```[a-z]*\n?", "", raw, flags=re.MULTILINE)
    cleaned = re.sub(r"\n?```$", "", cleaned, flags=re.MULTILINE)
    result = json.loads(cleaned.strip())
    if not isinstance(result, dict):
        return None
    return result
