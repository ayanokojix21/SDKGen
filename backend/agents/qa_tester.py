"""
QA Tester Agent — Static Analysis + Live HTTP Verification.
Upgraded with Structured Outputs.
"""

import logging
import re
from pathlib import Path
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from backend.llm import get_structured_llm, get_token_usage
from backend.graph.schemas import QaReport
from backend.tools.execute_http import execute_http_request

logger = logging.getLogger(__name__)

# ── Load detailed prompt from disk ────────────────────────────────────────────
_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _load_qa_tester_prompt() -> str:
    """Load the qa_tester prompt file."""
    prompt_path = _PROMPTS_DIR / "qa_tester.txt"
    try:
        text = prompt_path.read_text(encoding="utf-8")
        logger.info("[qa_tester] Loaded prompt from qa_tester.txt (%d chars)", len(text))
        return text
    except FileNotFoundError:
        logger.warning("[qa_tester] qa_tester.txt not found — using fallback")
        return ""


_QA_TESTER_PROMPT_FILE = _load_qa_tester_prompt()

_FALLBACK_PROMPT = """\
You are a Quality Assurance Engineer. Your goal is to verify that the generated SDK matches the API schema and follows best practices.

You must perform static analysis and review the LIVE HTTP TEST RESULTS to report failures.

IMPORTANT: HTTP status codes differ by method. A POST that returns 201 is CORRECT, not a failure.
  - GET, PUT, PATCH, DELETE → expected 200
  - POST → expected 200 OR 201 (both are success)
  - Any 2xx response (200-299) means the live HTTP test PASSED. Do NOT report it as a failure.
  - Only report a status code failure if the code is 4xx or 5xx.

Recommendation rules:
- 'fix_by_engineer' if there are logical bugs, missing methods, or type errors in the SDK code.
- 'fix_by_architect' if the schema seems wrong compared to expected API behavior (e.g., getting 404s or 401s that contradict the schema).
- 'proceed' if all live HTTP tests returned 2xx AND the SDK code looks correct.

CRITICAL: Your recommendation MUST be one of EXACTLY these three strings: 'proceed', 'fix_by_engineer', or 'fix_by_architect'. No other values.
"""


async def qa_tester_node(state: dict) -> dict:
    """
    QA Tester node using Structured Output.
    """
    api_schema = state.get("api_schema")
    sdk_files = state.get("sdk_files")

    if not api_schema or not sdk_files:
        return {
            "status": "failed",
            "messages": [AIMessage(content="QA failed: Missing inputs.", name="qa_tester")],
            "sse_events": [{"type": "qa_error", "error": "Missing inputs"}]
        }

    # ── Phase 1: Live HTTP Verification ─────────────────────────────────────
    http_results = []
    base_url = api_schema.get("base_url", "").rstrip("/")
    endpoints = api_schema.get("endpoints", [])
    auth = api_schema.get("auth", {})

    sse_events = [{"type": "qa_started", "total_endpoints": len(endpoints)}]

    for ep in endpoints:
        path = ep.get("path", "")
        # Replace path params with 1
        path = re.sub(r'\{[^\}]+\}', '1', path)
        url = f"{base_url}{path}"
        method = ep.get("method", "GET").upper()

        headers = {}
        params = {}
        if auth.get("type") == "api_key":
            if auth.get("location") == "header":
                headers[auth.get("key_name", "x-api-key")] = auth.get("example", "test")
            elif auth.get("location") in ("query", "query_param"):
                params[auth.get("key_name", "api_key")] = auth.get("example", "test")
        elif auth.get("type") == "bearer":
            headers["Authorization"] = f"Bearer {auth.get('example', 'test')}"

        body = None
        if method in ("POST", "PUT", "PATCH"):
            body = {"title": "test", "body": "test_body", "userId": 1}

        # For live tests, we accept ANY 2xx as success to avoid false negatives
        expected = 200  # base expectation; we override below for any 2xx

        try:
            res = await execute_http_request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                body=body,
                expected_status=expected,
                endpoint_name=ep.get("name", "unknown"),
            )
            # Accept any 2xx as passing (BUG 15 fix: also clear the misleading error)
            status_code = res.get("status_code", 0)
            if 200 <= status_code < 300:
                res["passed"] = True
                res["error"] = None  # Clear the "Expected 200, got 201" error

            http_results.append(res)
            sse_events.append({
                "type": "qa_test_pass" if res.get("passed") else "qa_test_fail",
                "endpoint": ep.get("name", "unknown"),
                "status_code": status_code,
                "passed": res.get("passed", False),
                "latency_ms": res.get("latency_ms", 0),
                "error": res.get("error") or "",
            })
        except Exception as e:
            res = {"endpoint_name": ep.get("name", "unknown"), "passed": False, "error": str(e), "status_code": 0, "method": method, "url": url}
            http_results.append(res)
            sse_events.append({
                "type": "qa_test_fail",
                "endpoint": ep.get("name", "unknown"),
                "status_code": 0,
                "passed": False,
                "latency_ms": 0,
                "error": str(e),
            })

    # ── Phase 2: Static Analysis (Structured Output) ────────────────────
    structured_llm = get_structured_llm(QaReport)

    http_summary = (
        f"{sum(1 for r in http_results if r.get('passed'))}/{len(http_results)} endpoints passed live HTTP tests.\n"
        + "\n".join([
            f"  {'✓' if r.get('passed') else '✗'} {r.get('endpoint_name', '?')} "
            f"[{r.get('method', 'GET')} {r.get('url', '?')}] "
            f"→ {r.get('status_code', 0)} "
            + (f"ERROR: {r.get('error')}" if r.get('error') else "OK")
            for r in http_results
        ])
    )
    
    qa_iteration = state.get("qa_iteration", 0) + 1
    
    prompt_text = _QA_TESTER_PROMPT_FILE or _FALLBACK_PROMPT
    
    # Fill placeholders if loaded from txt
    prompt_text = (
        prompt_text
        .replace("{api_schema}", str(api_schema))
        .replace("{language}", state.get("language", "python"))
        .replace("{sdk_files}", str(sdk_files))
        .replace("{qa_iteration}", str(qa_iteration))
        .replace("{instruction}", state.get("instruction", "Verify SDK"))
    )

    human_msg = f"""
LIVE HTTP TEST RESULTS:
{http_summary}

Please provide your QA report based on the API schema, SDK files, and the live HTTP test results.
"""

    try:
        report: QaReport = await structured_llm.ainvoke([
            SystemMessage(content=prompt_text),
            HumanMessage(content=human_msg)
        ])

        passed_count = report.summary.passed
        failed_count = report.summary.failed
        total_count = passed_count + failed_count
        raw_recommendation = report.summary.recommendation

        # BUG 6 fix: Normalize recommendation to the canonical vocabulary
        # The prompt files used "pass_to_packager" and "fix_by_researcher"
        # but the Supervisor and code logic expects "proceed" and "fix_by_architect"
        _recommendation_aliases = {
            "pass_to_packager": "proceed",
            "fix_by_researcher": "fix_by_architect",
            "pass": "proceed",
            "packager": "proceed",
        }
        recommendation = _recommendation_aliases.get(
            raw_recommendation.lower().strip(),
            raw_recommendation.lower().strip(),
        )

        # Emit per-test events from LLM report (phase 2 overlay on phase 1 events)
        for test in report.test_plan:
            if test.status == "pass":
                sse_events.append({
                    "type": "qa_test_pass",
                    "endpoint": test.target,
                    "status_code": 200,
                })
            elif test.status == "fail":
                sse_events.append({
                    "type": "qa_test_fail",
                    "endpoint": test.target,
                    "expected": "pass",
                    "actual": "fail",
                    "error": test.details or test.fix_suggestion or "Test failed",
                })

        summary_text = (
            f"QA complete. Recommendation: {recommendation}. "
            f"Passed: {passed_count}, Failed: {failed_count}. "
            f"HTTP pass rate: {sum(1 for r in http_results if r.get('passed'))}/{len(http_results)}"
        )

        test_results = [r.model_dump() for r in report.test_plan]

        # Reset engineer_iteration when a new QA cycle starts so the engineer
        # isn't permanently locked out for future fix cycles
        engineer_iteration_reset = 0 if recommendation == "proceed" else state.get("engineer_iteration", 0)

        # Single qa_done event
        sse_events.append({
            "type": "qa_done",
            "passed": passed_count,
            "failed": failed_count,
            "total": total_count,
            "recommendation": recommendation,
        })

        # If QA passes, route to packager
        next_agent = "packager" if recommendation == "proceed" else None

        # Propagate token tracking to state (BUG 5 fix)
        token_usage = get_token_usage()

        result = {
            "test_results": test_results,
            "qa_iteration": qa_iteration,
            "engineer_iteration": engineer_iteration_reset,
            "messages": [AIMessage(content=summary_text, name="qa_tester")],
            "sse_events": sse_events,
            "status": "success" if recommendation == "proceed" else "running",
            **token_usage,
        }
        if next_agent:
            result["next_agent"] = next_agent

        return result

    except Exception as e:
        logger.error(f"QA failed: {e}")
        return {
            "qa_iteration": state.get("qa_iteration", 0) + 1,
            "messages": [AIMessage(content=f"QA error: {str(e)}", name="qa_tester")],
            "sse_events": sse_events + [{"type": "qa_error", "error": str(e)}],
        }
