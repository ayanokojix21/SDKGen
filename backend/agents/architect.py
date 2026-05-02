"""
Architect Agent — Transforms Vector Store data into validated api_schema.
"""

import logging
from urllib.parse import urlparse
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from backend.llm import get_structured_llm
from backend.graph.schemas import ApiSchema
from backend.tools.research_tools import query_docs
from backend.tools.validate_schema import validate_schema

logger = logging.getLogger(__name__)

ARCHITECT_PROMPT = """
You are an API Architect. Your goal is to design a clean, correct API schema from documentation.
You will be provided with relevant documentation snippets retrieved from a vector store.

Rules:
1. Ensure endpoint paths are absolute (starting with /).
2. Group related functionality into logical endpoint names (CamelCase).
3. Identify path parameters, query parameters, and request bodies carefully.
4. CRITICAL: DO NOT invent endpoints. ONLY include endpoints explicitly described in the documentation context.
5. CRITICAL: The base_url MUST be derived from the TARGET_URL provided. Do NOT use placeholder domains like 'vectorstore.com', 'example.com', or 'api.example.com'.
6. If QA reports 404 errors for an endpoint, that endpoint is INVALID — remove it from the schema entirely.
7. If QA reports 404 errors on every endpoint, the base_url itself is wrong — correct it to the TARGET_URL domain.
"""


async def architect_node(state: dict) -> dict:
    """
    Architect node using RAG and Structured Output.
    """
    job_id = state["job_id"]
    collection_name = state.get("vector_store_collection")
    instruction = state.get("instruction", "Generate the API schema")
    target_url = state.get("target_url", "")

    # Derive the expected base URL from the target URL so the LLM cannot hallucinate it
    expected_base_url = _derive_base_url(target_url)

    if not collection_name:
        return {
            "messages": [AIMessage(content="No research data found. Cannot build schema.", name="architect")],
            "sse_events": [{"type": "architect_error", "error": "No vector store found"}]
        }

    # ── Phase 1: Retrieve context from Vector Store (RAG) ──────────────────
    query = f"API base URL, authentication, and endpoint definitions. {instruction}"
    docs = await query_docs(query, collection_name, k=50)

    context = "\n\n".join([f"SOURCE: {d.metadata.get('source')}\nCONTENT: {d.page_content}" for d in docs])

    # ── Phase 2: Generate Schema (Structured Output) ──────────────────────
    structured_llm = get_structured_llm(ApiSchema)

    sse_events = [{"type": "architect_validating", "context_length": len(context)}]

    # Provide QA failure context if we're in a retry
    qa_failure_context = ""
    if state.get("test_results"):
        failed = [r for r in state["test_results"] if not r.get("passed", True)]
        if failed:
            qa_failure_context = (
                f"\n\nQA FAILURE CONTEXT: The following endpoints FAILED live HTTP tests "
                f"and must be REMOVED or CORRECTED:\n" +
                "\n".join([f"  - {r.get('endpoint_name', '?')}: {r.get('error', 'unknown error')}" for r in failed])
            )

    human_msg = (
        f"INSTRUCTION: {instruction}\n"
        f"TARGET_URL: {target_url}\n"
        f"EXPECTED BASE URL (use this domain): {expected_base_url}\n"
        f"\nDOCUMENTATION CONTEXT:\n{context}"
        f"{qa_failure_context}"
    )

    try:
        api_schema_obj: ApiSchema = await structured_llm.ainvoke([
            SystemMessage(content=ARCHITECT_PROMPT),
            HumanMessage(content=human_msg)
        ])

        api_schema = api_schema_obj.model_dump()

        # ── Phase 3: Deterministic base_url correction ─────────────────────
        # If the LLM still hallucinated the base URL, forcefully correct it
        if expected_base_url and not _urls_share_domain(api_schema.get("base_url", ""), expected_base_url):
            logger.warning(
                "[architect] LLM hallucinated base_url='%s' — overriding with '%s'",
                api_schema.get("base_url"), expected_base_url
            )
            api_schema["base_url"] = expected_base_url
            sse_events.append({
                "type": "architect_fix",
                "fix": f"Corrected hallucinated base_url to {expected_base_url}"
            })

        # ── Phase 4: Post-Validation & Auto-Fixes ─────────────────────────
        validation = validate_schema(api_schema)
        api_schema = validation["schema"]
        schema_fixes = validation["fixes"]

        # Emit per-fix events for the frontend
        for fix in schema_fixes:
            sse_events.append({"type": "architect_fix", "fix": fix})

        summary = (
            f"API schema generated: {len(api_schema['endpoints'])} endpoints. "
            f"{len(schema_fixes)} auto-fixes applied. base_url={api_schema['base_url']}"
        )

        return {
            "api_schema": api_schema,
            "schema_fixes": schema_fixes,
            "architect_iteration": state.get("architect_iteration", 0) + 1,
            "messages": [AIMessage(content=summary, name="architect")],
            "sse_events": sse_events + [{
                "type": "architect_done",
                "endpoint_count": len(api_schema["endpoints"]),
                "fixes_count": len(schema_fixes),
            }]
        }

    except Exception as e:
        logger.error(f"Architect failed: {e}")
        return {
            "architect_iteration": state.get("architect_iteration", 0) + 1,
            "messages": [AIMessage(content=f"Architect error: {str(e)}", name="architect")],
            "sse_events": sse_events + [{"type": "architect_error", "error": str(e)}]
        }


def _derive_base_url(target_url: str) -> str:
    """
    Extracts the scheme + netloc from the target URL to use as the expected base URL.
    e.g. 'https://jsonplaceholder.typicode.com/guide/' → 'https://jsonplaceholder.typicode.com'
    """
    if not target_url:
        return ""
    try:
        parsed = urlparse(target_url)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
    except Exception:
        pass
    return ""


def _urls_share_domain(url_a: str, url_b: str) -> bool:
    """Returns True if both URLs share the same netloc (domain)."""
    if not url_a or not url_b:
        return False
    try:
        return urlparse(url_a).netloc == urlparse(url_b).netloc
    except Exception:
        return False
