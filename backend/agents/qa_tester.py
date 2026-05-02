"""
QA Tester Agent — Static Analysis + Live HTTP Verification.

The final gatekeeper. Performs two types of validation:
  1. Static Analysis: Checks SDK code against schema (via LLM)
  2. Live HTTP Verification: Hits real endpoints via execute_http tool

Produces a detailed failure report that determines if the Supervisor
routes to Engineer (code bug) or Researcher (docs gap).
"""

import re
import json
import logging
from pathlib import Path
from langchain_core.messages import AIMessage
from backend.llm import get_llm
from langchain_core.messages import SystemMessage, HumanMessage

from backend.tools.execute_http import execute_http_request

logger = logging.getLogger(__name__)

# Load prompt once at module level
_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "qa_tester.txt"
_QA_TESTER_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")


async def qa_tester_node(state: dict) -> dict:
    """
    QA Tester agent node for the LangGraph graph.
    """
    api_schema = state.get("api_schema")
    sdk_files = state.get("sdk_files")
    language = state.get("language", "python")
    qa_iteration = state.get("qa_iteration", 0)
    
    sse_events = []
    messages = []

    if not api_schema or not sdk_files:
        logger.error("QA Tester: Missing api_schema or sdk_files")
        return {
            "status": "failed",
            "failure_reason": "QA Tester: Missing api_schema or sdk_files to test",
            "messages": [AIMessage(content="QA failed: Missing inputs.", name="qa_tester")],
            "sse_events": [{"type": "agent_warn", "message": "QA failed: Missing inputs"}]
        }

    # ══════════════════════════════════════════════════════════════════════
    # PHASE 1 — Static Analysis (LLM)
    # ══════════════════════════════════════════════════════════════════════
    logger.info(f"QA Tester: Starting Static Analysis (Iteration {qa_iteration})")
    sse_events.append({"type": "qa_analysing", "iteration": qa_iteration})

    # Prepare prompt with context
    # Note: We use the prompt pulled from Git, but we need to fill the variables
    instruction = _get_last_supervisor_instruction(state.get("messages", [])) or "Verify the SDK is correct."
    
    # Prepare prompt with context - use replace() instead of format() 
    # to avoid errors with literal curly braces in the JSON example.
    formatted_prompt = _QA_TESTER_PROMPT
    replacements = {
        "{api_schema}": json.dumps(api_schema, indent=2),
        "{language}": language,
        "{sdk_files}": json.dumps(sdk_files, indent=2),
        "{qa_iteration}": str(qa_iteration),
        "{instruction}": instruction
    }
    for k, v in replacements.items():
        formatted_prompt = formatted_prompt.replace(k, v)

    try:
        llm = get_llm(temperature=0.1)

        response = await llm.ainvoke([
            HumanMessage(content=formatted_prompt),
        ])

        qa_report = _parse_qa_report(response.content)
    except Exception as e:
        logger.error(f"QA Static Analysis failed: {e}")
        qa_report = {"summary": {"recommendation": "fix_by_engineer"}, "test_plan": []}

    # ══════════════════════════════════════════════════════════════════════
    # PHASE 2 — Live HTTP Verification
    # ══════════════════════════════════════════════════════════════════════
    # Only run live tests if static analysis isn't a total disaster
    # and it's the first or second iteration.
    test_results = []
    
    if qa_iteration < 3:
        logger.info("QA Tester: Starting Live HTTP Verification")
        
        # Extract endpoints to test from schema
        endpoints = api_schema.get("endpoints", [])
        if not endpoints and "endpoints_raw" in api_schema: # Fallback if schema is raw
            endpoints = api_schema["endpoints_raw"]

        for ep in endpoints:
            # Construct a test request using the logic from our Step 1 prompt
            # (Since the new prompt doesn't explicitly return test cases for execution,
            # we'll use a helper to derive them from the schema).
            test_case = _derive_test_case(ep, api_schema.get("auth", {}))
            
            if test_case["skip"]:
                logger.info(f"Skipping live test for {ep.get('name')}: {test_case['reason']}")
                continue

            sse_events.append({
                "type": "qa_testing",
                "endpoint": ep.get("name"),
                "url": test_case["url"]
            })

            res = await execute_http_request(
                method=test_case["method"],
                url=test_case["url"],
                headers=test_case["headers"],
                params=test_case["params"],
                body=test_case["body"],
                endpoint_name=ep.get("name")
            )

            test_results.append(res)

            if res["passed"]:
                sse_events.append({
                    "type": "qa_test_pass",
                    "endpoint": res["endpoint_name"],
                    "latency_ms": res["latency_ms"]
                })
            else:
                sse_events.append({
                    "type": "qa_test_fail",
                    "endpoint": res["endpoint_name"],
                    "error": res["error"]
                })
                # Add failure to the report plan if not already there
                qa_report["test_plan"].append({
                    "test_id": f"LIVE-{ep.get('name')}",
                    "category": "live_verification",
                    "target": ep.get("name"),
                    "description": f"Live HTTP request to {res['url']}",
                    "status": "fail",
                    "details": res["error"],
                    "fix_suggestion": "Verify endpoint path and parameters in knowledge base"
                })
                qa_report["summary"]["failed"] += 1
                qa_report["summary"]["recommendation"] = "fix_by_researcher"

    # ══════════════════════════════════════════════════════════════════════
    # FINALIZE
    # ══════════════════════════════════════════════════════════════════════
    passed_count = qa_report["summary"].get("passed", 0)
    failed_count = qa_report["summary"].get("failed", 0)
    
    summary_text = (
        f"QA Iteration {qa_iteration} complete. "
        f"Recommendation: {qa_report['summary']['recommendation']}. "
        f"Passed: {passed_count}, Failed: {failed_count}."
    )
    
    messages.append(AIMessage(content=summary_text, name="qa_tester"))
    
    sse_events.append({
        "type": "qa_done",
        "passed": passed_count,
        "failed": failed_count,
        "recommendation": qa_report["summary"]["recommendation"]
    })

    return {
        "test_results": test_results,
        "qa_iteration": qa_iteration + 1,
        "messages": messages,
        "sse_events": sse_events,
        "status": "success" if failed_count == 0 else "running"
    }


def _derive_test_case(ep: dict, auth: dict) -> dict:
    """
    Helper to construct a live HTTP test case from a schema endpoint.
    Uses safe test values.
    """
    path = ep.get("path", "")
    method = ep.get("method", "GET").upper()
    
    # Substitue path params with '1'
    url_path = re.sub(r'\{.*?\}', '1', path)
    
    # We need the base_url from the schema or a default
    # Note: Researcher puts base_url in knowledge_base, 
    # Architect puts it in api_schema.
    # We'll assume it's there.
    base_url = ep.get("base_url") or "https://jsonplaceholder.typicode.com" # fallback for testing
    
    url = f"{base_url.rstrip('/')}/{url_path.lstrip('/')}"
    
    case = {
        "method": method,
        "url": url,
        "headers": {},
        "params": {},
        "body": None,
        "skip": False,
        "reason": ""
    }

    # Safety: Only GET/POST
    if method not in ["GET", "POST"]:
        case["skip"] = True
        case["reason"] = f"Method {method} not supported in live tests"
        return case

    # Auth injection
    auth_type = auth.get("type", "none")
    key_name = auth.get("key_name", "Authorization")
    example = auth.get("example", "test_key")

    if auth_type == "api_key":
        if auth.get("location") == "query_param":
            case["params"][key_name] = example
        else:
            case["headers"][key_name] = example
    elif auth_type == "bearer":
        case["headers"]["Authorization"] = f"Bearer {example}"

    # Safe defaults for common params
    if method == "POST":
        case["body"] = { "title": "test", "body": "test_body", "userId": 1 }

    return case


def _parse_qa_report(content: str) -> dict:
    """Parse the LLM's JSON QA report."""
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        report = json.loads(text)
    except json.JSONDecodeError:
        logger.error(f"Failed to parse QA report JSON: {text[:300]}...")
        return {"summary": {"passed": 0, "failed": 1, "recommendation": "fix_by_engineer"}, "test_plan": []}

    return report


def _get_last_supervisor_instruction(messages: list) -> str | None:
    """Extract the last supervisor instruction from message history."""
    for msg in reversed(messages):
        if hasattr(msg, "name") and msg.name == "supervisor":
            content = msg.content
            if ":" in content:
                return content.split(":", 1)[1].strip()
            return content
    return None
