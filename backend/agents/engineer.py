"""
Engineer Agent — Generates SDK code from validated api_schema.
Upgraded with Structured Outputs and RAG.
"""

import logging
from typing import Dict, List
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from backend.llm import get_structured_llm
from backend.graph.schemas import GeneratedSdk
from backend.tools.research_tools import query_docs
from backend.tools.syntax_check import check_syntax

logger = logging.getLogger(__name__)

ENGINEER_PROMPT = """
You are a Senior Software Engineer. Your goal is to write a high-quality, production-ready SDK.
You will be provided with an API schema and relevant documentation context.

Rules:
1. Write idiomatic code for the target language.
2. Include docstrings and type hints.
3. Ensure the README explains how to use the SDK and how to provide authentication.
4. If fixing an SDK, pay close attention to the provided test results and documentation context.
"""

async def engineer_node(state: dict) -> dict:
    """
    Engineer node using Structured Output and RAG.
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

    # ── Phase 1: Retrieve context for code details (RAG) ──────────────────
    context = ""
    if collection_name:
        query = f"API models, error handling, and request/response examples for {api_schema['api_name']}"
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
        human_msg += f"\n\nPREVIOUS SDK FILES: {state['sdk_files']}\nTEST RESULTS: {state['test_results']}"

    try:
        sdk_obj: GeneratedSdk = await structured_llm.ainvoke([
            SystemMessage(content=ENGINEER_PROMPT),
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

        return {
            "sdk_files": sdk_files,
            "syntax_errors": syntax_errors,
            "messages": [AIMessage(content=summary, name="engineer")],
            "sse_events": sse_events,
        }

    except Exception as e:
        logger.error(f"Engineer failed: {e}")
        return {
            "messages": [AIMessage(content=f"Engineer error: {str(e)}", name="engineer")],
            "sse_events": [{"type": "engineer_error", "error": str(e)}]
        }
