"""
Architect Agent — Transforms knowledge_base into validated api_schema.

Takes the Researcher's raw knowledge_base and normalizes it into a clean,
structured api_schema that the Engineer can directly consume. Runs the
Gemma-optimized prompt, then applies deterministic post-validation via
validate_schema to catch and auto-fix structural issues.
"""

import json
import logging
from pathlib import Path

from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from backend.tools.validate_schema import validate_schema

logger = logging.getLogger(__name__)

# Load prompt once at module level
_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "architect.txt"
_ARCHITECT_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")


async def architect_node(state: dict) -> dict:
    """
    Architect agent node for the LangGraph graph.

    Transforms knowledge_base → api_schema with LLM + deterministic validation.
    """
    sse_events = []
    messages = []
    schema_fixes: list[str] = []

    knowledge_base = state.get("knowledge_base", {})
    language = state.get("language", "python")
    supervisor_instruction = _get_last_supervisor_instruction(state.get("messages", []))

    if not knowledge_base:
        logger.warning("Architect: no knowledge_base — returning empty schema")
        messages.append(AIMessage(
            content="No knowledge base available — cannot generate schema.",
            name="architect",
        ))
        return {
            "api_schema": None,
            "schema_fixes": [],
            "messages": messages,
            "sse_events": [{
                "type": "agent_warn",
                "message": "Architect received empty knowledge_base",
            }],
        }

    sse_events.append({
        "type": "architect_start",
        "endpoint_count": len(knowledge_base.get("endpoints_raw", [])),
    })

    # ── LLM Call: knowledge_base → api_schema ────────────────────────────
    prompt = _ARCHITECT_PROMPT.replace(
        "{knowledge_base}", json.dumps(knowledge_base, indent=2)
    )
    prompt = prompt.replace("{language}", language)
    prompt = prompt.replace("{instruction}", supervisor_instruction or "Generate the API schema")

    try:
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            temperature=0.1,
        )

        response = await llm.ainvoke([
            SystemMessage(content=prompt),
            HumanMessage(content="Transform this knowledge_base into an api_schema. Return JSON only."),
        ])

        api_schema = _parse_schema(response.content)

    except Exception as e:
        logger.error(f"Architect LLM call failed: {e}")
        messages.append(AIMessage(
            content=f"Architect failed to generate schema: {e}",
            name="architect",
        ))
        sse_events.append({
            "type": "agent_error",
            "agent": "architect",
            "error": str(e),
        })
        return {
            "api_schema": None,
            "schema_fixes": [],
            "messages": messages,
            "sse_events": sse_events,
        }

    if api_schema is None:
        logger.error("Architect: Failed to parse LLM output as JSON")
        messages.append(AIMessage(
            content="Architect failed to parse LLM response as valid JSON.",
            name="architect",
        ))
        return {
            "api_schema": None,
            "schema_fixes": [],
            "messages": messages,
            "sse_events": sse_events,
        }

    # ── Deterministic Post-Validation ────────────────────────────────────
    validation = validate_schema(api_schema)
    api_schema = validation["schema"]
    schema_fixes = validation["fixes"]

    if validation["errors"]:
        logger.warning(
            f"Architect: Schema has {len(validation['errors'])} validation errors: "
            f"{validation['errors']}"
        )
        sse_events.append({
            "type": "architect_validation_warnings",
            "errors": validation["errors"],
            "fixes": schema_fixes,
        })

    if schema_fixes:
        sse_events.append({
            "type": "architect_auto_fixes",
            "fixes": schema_fixes,
        })

    # ── Build completion message ─────────────────────────────────────────
    endpoint_count = len(api_schema.get("endpoints", []))
    fix_count = len(schema_fixes)
    error_count = len(validation["errors"])

    summary = (
        f"API schema generated: {endpoint_count} endpoints normalized. "
        f"Auth: {api_schema.get('auth', {}).get('type', 'unknown')}. "
        f"{fix_count} auto-fixes applied, {error_count} validation errors."
    )

    messages.append(AIMessage(content=summary, name="architect"))

    sse_events.append({
        "type": "architect_done",
        "endpoint_count": endpoint_count,
        "fix_count": fix_count,
        "valid": validation["valid"],
    })

    logger.info(f"Architect: {summary}")

    return {
        "api_schema": api_schema,
        "schema_fixes": schema_fixes,
        "messages": messages,
        "sse_events": sse_events,
    }


def _parse_schema(content: str) -> dict | None:
    """Parse the Architect LLM response into an api_schema dict."""
    text = content.strip()

    # Strip markdown fences
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        schema = json.loads(text)
    except json.JSONDecodeError:
        logger.error(f"Failed to parse schema JSON: {text[:300]}...")
        return None

    # Basic structural validation
    if not isinstance(schema, dict):
        logger.error(f"Schema is not a dict: {type(schema).__name__}")
        return None

    # Ensure required top-level fields
    if "endpoints" not in schema:
        schema["endpoints"] = []
    if "base_url" not in schema:
        schema["base_url"] = ""
    if "auth" not in schema:
        schema["auth"] = {"type": "none", "location": "none", "key_name": "", "example": ""}
    if "api_name" not in schema:
        schema["api_name"] = "Unknown API"

    return schema


def _get_last_supervisor_instruction(messages: list) -> str | None:
    """Extract the last supervisor instruction from message history."""
    for msg in reversed(messages):
        if hasattr(msg, "name") and msg.name == "supervisor":
            content = msg.content
            if ":" in content:
                return content.split(":", 1)[1].strip()
            return content
    return None
