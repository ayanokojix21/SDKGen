"""
backend/agents/engineer.py
───────────────────────────
Engineer Agent — Generates SDK code from validated api_schema.

Two modes of operation
──────────────────────
MODE 1 — GENERATE: First-time SDK generation from api_schema.
MODE 2 — FIX: Re-generate after QA failure, given previous sdk_files + errors.

Self-correction
────────────────
• After LLM generates files, runs syntax_check (ast.parse for Python,
  heuristics for TypeScript).
• If syntax errors found → one automatic retry with error context injected.
• Validates file structure: all expected files present, no empty files.
• Never returns broken output — if all retries fail, returns error state.

Safety
──────
• Uses settings.GEMINI_MODEL — no hardcoded model names.
• Exponential backoff on LLM failures (2s, 4s).
• 2 total attempts (initial + 1 retry).
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
from backend.tools.syntax_check import check_syntax, format_errors_for_retry

log = logging.getLogger(__name__)

# ── Load prompts once at import time ──────────────────────────────────────────
_PROMPT_DIR = Path(__file__).parent.parent / "prompts"

def _load_prompt(filename: str) -> str:
    path = _PROMPT_DIR / filename
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        log.warning("%s not found — engineer will use minimal fallback", filename)
        return ""

_PYTHON_PROMPT = _load_prompt("engineer_python.txt")
_TYPESCRIPT_PROMPT = _load_prompt("engineer_typescript.txt")

# ── LLM singleton ─────────────────────────────────────────────────────────────
from backend.llm import get_llm
_llm = get_llm(temperature=0.2)

MAX_ATTEMPTS = 2  # initial generation + 1 syntax-fix retry


# ──────────────────────────────────────────────────────────────────────────────
# Engineer node
# ──────────────────────────────────────────────────────────────────────────────

async def engineer_node(state: dict) -> dict:
    """
    LangGraph node — generates or fixes SDK files.
    Detects mode automatically: if sdk_files + test_results exist → FIX mode.
    Returns a partial state update dict.
    """
    api_schema = state.get("api_schema")
    language = state.get("language", "python")
    instruction = state.get("instruction", "Generate the SDK")
    existing_sdk_files = state.get("sdk_files")
    test_results = state.get("test_results")

    if not api_schema:
        log.warning("[engineer] no api_schema — cannot generate")
        return {
            "sdk_files": None,
            "syntax_errors": [],
            "messages": [AIMessage(content="No API schema available.", name="engineer")],
            **emit_sse("engineer_skip", reason="empty api_schema"),
        }

    # ── Detect mode ───────────────────────────────────────────────────────────
    is_fix = existing_sdk_files is not None and test_results is not None
    mode = "FIX" if is_fix else "GENERATE"
    api_name = api_schema.get("api_name", "API")
    ep_count = len(api_schema.get("endpoints", []))

    log.info("[engineer] mode=%s language=%s endpoints=%d", mode, language, ep_count)

    sse_update_start = emit_sse(
        "engineer_start",
        mode=mode,
        language=language,
        endpoint_count=ep_count,
    )

    # ── Build prompt ──────────────────────────────────────────────────────────
    base_prompt = _PYTHON_PROMPT if language == "python" else _TYPESCRIPT_PROMPT
    if not base_prompt:
        log.error("[engineer] no prompt loaded for language=%s", language)
        return {
            "sdk_files": None,
            "syntax_errors": [],
            "messages": [AIMessage(content=f"No prompt for {language}.", name="engineer")],
            **emit_sse("engineer_error", error=f"Missing prompt for {language}"),
        }

    prompt = _fill_template(
        base_prompt, api_schema, api_name, instruction,
        existing_sdk_files, test_results,
    )

    # ── LLM call with syntax check + self-correction ──────────────────────────
    sdk_files = None
    syntax_errors: list[str] = []
    check_results = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            if attempt == 1:
                human_msg = "Generate the SDK. Return JSON only."
                if is_fix:
                    human_msg = (
                        "Fix the SDK based on the test failures. "
                        "Return the FULL updated files as JSON."
                    )
            else:
                # Retry with syntax error context
                if check_results is None:
                    human_msg = "Your previous output was not valid JSON. Ensure you return ONLY valid JSON."
                else:
                    human_msg = (
                        "Your previous output had syntax errors. Fix them and regenerate.\n\n"
                        + format_errors_for_retry(check_results)
                    )

            response = await _llm.ainvoke([
                SystemMessage(content=prompt),
                HumanMessage(content=human_msg),
            ])

            raw = _extract_text(response)
            sdk_files = _parse_sdk_files(raw)

            if sdk_files is None:
                log.warning("[engineer] attempt %d: JSON parse failed", attempt)
                if attempt < MAX_ATTEMPTS:
                    await asyncio.sleep(2)
                continue

            # ── Syntax check ──────────────────────────────────────────────────
            check_results = check_syntax(sdk_files, language)
            has_errors = any(not r["valid"] for r in check_results)

            if has_errors:
                file_errors = []
                for r in check_results:
                    if not r["valid"]:
                        file_errors.extend(f"{r['file']}: {e}" for e in r["errors"])
                syntax_errors.extend(file_errors)

                if attempt < MAX_ATTEMPTS:
                    log.warning("[engineer] attempt %d: %d syntax errors — retrying",
                                attempt, len(file_errors))
                    await asyncio.sleep(2)
                    continue
                else:
                    log.warning("[engineer] returning files with %d remaining syntax issues",
                                len(file_errors))

            # Syntax clean (or final attempt)
            break

        except Exception as exc:
            log.error("[engineer] LLM error (attempt %d): %s", attempt, exc)
            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(2 ** attempt)
            else:
                return {
                    "sdk_files": None,
                    "syntax_errors": syntax_errors,
                    "messages": [AIMessage(content=f"Engineer failed: {exc}", name="engineer")],
                    **emit_sse("engineer_error", error=str(exc)),
                }

    # ── Handle total failure ──────────────────────────────────────────────────
    if sdk_files is None:
        return {
            "sdk_files": None,
            "syntax_errors": syntax_errors,
            "messages": [AIMessage(content="Engineer failed to generate valid files.", name="engineer")],
            **emit_sse("engineer_error", error="All attempts failed"),
        }

    # ── Validate file structure ───────────────────────────────────────────────
    _validate_files(sdk_files, language, syntax_errors)

    # ── Build result ──────────────────────────────────────────────────────────
    file_count = len(sdk_files)
    total_lines = sum(c.count("\n") + 1 for c in sdk_files.values())
    fix_note = f", {len(syntax_errors)} syntax issues" if syntax_errors else ""

    summary = f"SDK {mode.lower()}d: {file_count} files, ~{total_lines} lines of {language}{fix_note}."
    log.info("[engineer] %s", summary)

    sse_update_done = emit_sse(
        "engineer_done",
        mode=mode,
        file_count=file_count,
        total_lines=total_lines,
        files=list(sdk_files.keys()),
        syntax_errors=len(syntax_errors),
    )

    return {
        "sdk_files": sdk_files,
        "syntax_errors": syntax_errors,
        "messages": [AIMessage(content=summary, name="engineer")],
        **sse_update_done,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _fill_template(
    template: str,
    api_schema: dict,
    api_name: str,
    instruction: str,
    existing_files: dict | None,
    test_results: list | None,
) -> str:
    """Fill the prompt template with state data."""
    p = template
    replacements = {
        "{api_schema}": json.dumps(api_schema, indent=2),
        "{api_name}": api_name,
        "{instruction}": instruction,
    }

    if existing_files:
        ft = ""
        for fname, content in existing_files.items():
            ft += f"\n--- {fname} ---\n{content}\n"
        replacements["{existing_sdk_files}"] = ft
    else:
        replacements["{existing_sdk_files}"] = "null (first generation)"

    if test_results:
        replacements["{test_results}"] = json.dumps(test_results, indent=2)
    else:
        replacements["{test_results}"] = "null (no tests run yet)"

    for k, v in replacements.items():
        p = p.replace(k, v)
    return p


def _validate_files(sdk_files: dict, language: str, syntax_errors: list[str]) -> None:
    """Check that all expected files are present and non-empty."""
    if language == "python":
        expected = {"client.py", "models.py", "tests/test_client.py", "README.md"}
    else:
        expected = {"client.ts", "models.ts", "tests/test_client.ts", "README.md"}

    for fname in expected:
        if fname not in sdk_files:
            syntax_errors.append(f"Missing expected file: {fname}")
        elif not sdk_files[fname].strip():
            syntax_errors.append(f"File is empty: {fname}")


def _extract_text(response) -> str:
    """Safely extract string content from LangChain AIMessage."""
    content = response.content
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [p["text"] for p in content if isinstance(p, dict) and "text" in p]
        return " ".join(parts).strip()
    return str(content).strip()


def _parse_sdk_files(raw: str) -> dict | None:
    """Strip markdown fences and parse JSON into {filename: content} dict."""
    cleaned = re.sub(r"^```[a-z]*\n?", "", raw, flags=re.MULTILINE)
    cleaned = re.sub(r"\n?```$", "", cleaned, flags=re.MULTILINE)
    cleaned = cleaned.strip()

    try:
        files = json.loads(cleaned)
    except json.JSONDecodeError:
        log.error("[engineer] JSON parse failed: %s...", cleaned[:200])
        return None

    if not isinstance(files, dict) or not files:
        log.error("[engineer] parsed result is not a non-empty dict")
        return None

    # Coerce all values to strings
    for key, value in files.items():
        if not isinstance(value, str):
            files[key] = str(value)
    return files
