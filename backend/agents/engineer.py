"""
Engineer Agent — Generates SDK code from validated api_schema.
Upgraded with Structured Outputs, RAG, and detailed per-file prompts.
"""

import logging
from pathlib import Path
from typing import Dict, List
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from backend.llm import get_structured_llm, get_token_usage
from backend.graph.schemas import GeneratedSdk
from backend.tools.research_tools import query_docs
from backend.tools.syntax_check import check_syntax

logger = logging.getLogger(__name__)

# ── Load detailed prompts from disk ──────────────────────────────────────────
_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _load_prompt(language: str) -> str:
    """Load the language-specific engineer prompt file."""
    filename = f"engineer_{language}.txt"
    prompt_path = _PROMPTS_DIR / filename
    try:
        return prompt_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("[engineer] Prompt file %s not found — using fallback", filename)
        return ""


# Fallback prompt used when the .txt file is missing or empty
_FALLBACK_PROMPT = """\
You are a Senior Software Engineer. Your goal is to write a high-quality, production-ready SDK.
You will be provided with an API schema and relevant documentation context.

Rules:
1. Write idiomatic code for the target language.
2. Include docstrings and type hints.
3. You MUST generate exactly 4 files:
   - client.py (or .ts): The SDK client class with one method per endpoint.
   - models.py (or .ts): Data classes/interfaces for request/response bodies.
   - tests/test_client.py (or .ts): Unit tests that mock HTTP calls.
   - README.md: With Installation, Authentication, Quick Start, and API Reference sections.
4. The README.md MUST contain:
   - A title: "# {api_name} {language} SDK"
   - Installation section with the required package (e.g., `pip install httpx`)
   - Authentication section showing how to initialize the client with credentials
   - Quick Start section with a working code example calling one endpoint
   - API Reference table with columns: Method, Endpoint, Description
   - All code examples must use the ACTUAL class and method names from the client file
5. Ensure the README explains how to use the SDK and how to provide authentication.
6. If fixing an SDK, pay close attention to the provided test results and documentation context.
7. You MUST implement robust retry logic with exponential backoff for 429 (Too Many Requests) and 5xx (Server Error) HTTP status codes in the SDK client.
8. No syntax errors. Every file must parse without errors.
9. No incomplete methods. Every method body must be fully implemented.
10. No placeholder comments like "# TODO" or "pass".
11. No hardcoded API keys or secrets.
"""


async def engineer_node(state: dict) -> dict:
    """
    Engineer node using Structured Output and RAG.
    Loads the detailed prompt file for the target language.
    """
    api_schema = state.get("api_schema")
    language = state.get("language", "python")
    instruction = state.get("instruction", "Generate the SDK")
    collection_name = state.get("vector_store_collection")

    if not api_schema:
        return {
            "messages": [AIMessage(content="No API schema found. Cannot generate SDK.", name="engineer")],
            "sse_events": [{"type": "engineer_error", "error": "No api_schema found"}]
        }

    # ── Load the detailed prompt for this language ──────────────────────────
    prompt_text = _load_prompt(language)
    if not prompt_text:
        prompt_text = _FALLBACK_PROMPT

    # Fill known placeholders that exist in the prompt files
    api_name = api_schema.get("api_name", "API")
    base_url = api_schema.get("base_url", "")
    prompt_text = (
        prompt_text
        .replace("{api_schema}", str(api_schema))
        .replace("{api_name}", api_name)
        .replace("{ApiName}", api_name.replace(" ", "").replace("-", ""))
        .replace("{base_url}", base_url)
        .replace("{instruction}", instruction)
        .replace("{existing_sdk_files}", str(state.get("sdk_files") or "None"))
        .replace("{test_results}", str(state.get("test_results") or "None"))
    )

    # ── Phase 1: Retrieve context for code details (RAG) ──────────────────
    context = ""
    if collection_name:
        query = f"API models, error handling, and request/response examples for {api_name}"
        docs = await query_docs(query, collection_name, k=10)
        context = "\n\n".join([f"SOURCE: {d.metadata.get('source')}\nCONTENT: {d.page_content}" for d in docs])

    # ── Phase 2: Generate SDK (Structured Output) ───────────────────────
    structured_llm = get_structured_llm(GeneratedSdk)

    human_msg = f"""
INSTRUCTION: {instruction}
API SCHEMA: {api_schema}
LANGUAGE: {language}
"""
    if context:
        human_msg += f"\n\nDOCUMENTATION CONTEXT:\n{context}"

    if state.get("sdk_files") and state.get("test_results"):
        human_msg += f"\n\nPREVIOUS TEST RESULTS (from QA): {state['test_results']}"
    if state.get("syntax_errors"):
        human_msg += f"\n\nPREVIOUS SYNTAX ERRORS (fix ALL of these): {state['syntax_errors']}"

    try:
        sdk_obj: GeneratedSdk = await structured_llm.ainvoke([
            SystemMessage(content=prompt_text),
            HumanMessage(content=human_msg)
        ])

        sdk_files = {f.filename: f.content for f in sdk_obj.files}

        sse_events = []

        # Emit per-file writing events
        for filename, content in sdk_files.items():
            sse_events.append({"type": "engineer_writing", "filename": filename})
            line_count = content.count("\n") + 1
            sse_events.append({
                "type": "engineer_file_done",
                "filename": filename,
                "line_count": line_count,
            })

        # ── Phase 3: Syntax Check ─────────────────────────────────────────
        check_results = await check_syntax(sdk_files, language)
        syntax_errors = [f"{r['file']}: {e}" for r in check_results if not r["valid"] for e in r["errors"]]

        # Emit per-error syntax events
        for err in syntax_errors:
            parts = err.split(": ", 1)
            sse_events.append({
                "type": "engineer_syntax_error",
                "filename": parts[0] if len(parts) > 1 else "unknown",
                "error": parts[1] if len(parts) > 1 else err,
            })

        summary = f"SDK generated: {len(sdk_files)} files. {len(syntax_errors)} syntax issues found."

        # Final summary event
        sse_events.append({
            "type": "engineer_done",
            "file_count": len(sdk_files),
            "syntax_errors": len(syntax_errors),
        })

        # If no syntax errors this run, reset the iteration counter so future
        # QA-triggered cycles get a fresh allowance of retries
        new_engineer_iteration = (
            0 if not syntax_errors
            else state.get("engineer_iteration", 0) + 1
        )

        # Propagate token tracking to state (BUG 5 fix)
        token_usage = get_token_usage()

        return {
            "sdk_files": sdk_files,
            "syntax_errors": syntax_errors,
            "engineer_iteration": new_engineer_iteration,
            "messages": [AIMessage(content=summary, name="engineer")],
            "sse_events": sse_events,
            **token_usage,
        }

    except Exception as e:
        logger.error(f"Engineer failed: {e}")
        return {
            "messages": [AIMessage(content=f"Engineer error: {str(e)}", name="engineer")],
            "sse_events": [{"type": "engineer_error", "error": str(e)}]
        }
