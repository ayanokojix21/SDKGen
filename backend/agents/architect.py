"""
Architect Agent — Transforms Vector Store data into validated api_schema.
"""

import logging
import json
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
"""

async def architect_node(state: dict) -> dict:
    """
    Architect node using RAG and Structured Output.
    """
    job_id = state["job_id"]
    collection_name = state.get("vector_store_collection")
    instruction = state.get("instruction", "Generate the API schema")

    if not collection_name:
        return {
            "messages": [AIMessage(content="No research data found. Cannot build schema.", name="architect")],
            "sse_events": [{"type": "architect_error", "error": "No vector store found"}]
        }

    # ── Phase 1: Retrieve context from Vector Store (RAG) ──────────────────
    # We query for general API structure and specific instructions
    query = f"API base URL, authentication, and endpoint definitions. {instruction}"
    docs = await query_docs(query, collection_name, k=15)
    
    context = "\n\n".join([f"SOURCE: {d.metadata.get('source')}\nCONTENT: {d.page_content}" for d in docs])

    # ── Phase 2: Generate Schema (Structured Output) ──────────────────────
    structured_llm = get_structured_llm(ApiSchema)
    
    sse_events = [{"type": "architect_starting", "context_length": len(context)}]

    try:
        api_schema_obj: ApiSchema = await structured_llm.ainvoke([
            SystemMessage(content=ARCHITECT_PROMPT),
            HumanMessage(content=f"INSTRUCTION: {instruction}\n\nDOCUMENTATION CONTEXT:\n{context}")
        ])
        
        api_schema = api_schema_obj.model_dump()

        # ── Phase 3: Post-Validation & Auto-Fixes ──────────────────────────
        validation = validate_schema(api_schema)
        api_schema = validation["schema"]
        schema_fixes = validation["fixes"]
        
        summary = (
            f"API schema generated: {len(api_schema['endpoints'])} endpoints. "
            f"{len(schema_fixes)} auto-fixes applied."
        )

        return {
            "api_schema": api_schema,
            "schema_fixes": schema_fixes,
            "messages": [AIMessage(content=summary, name="architect")],
            "sse_events": sse_events + [{
                "type": "architect_done",
                "endpoint_count": len(api_schema['endpoints']),
                "auto_fixes": len(schema_fixes)
            }]
        }

    except Exception as e:
        logger.error(f"Architect failed: {e}")
        return {
            "messages": [AIMessage(content=f"Architect error: {str(e)}", name="architect")],
            "sse_events": sse_events + [{"type": "architect_error", "error": str(e)}]
        }
