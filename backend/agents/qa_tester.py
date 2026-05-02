"""
QA Tester Agent — Static Analysis + Live HTTP Verification.
Upgraded with Structured Outputs.
"""

import logging
import re
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from backend.llm import get_structured_llm
from backend.graph.schemas import QaReport
from backend.tools.execute_http import execute_http_request

logger = logging.getLogger(__name__)

QA_TESTER_PROMPT = """
You are a Quality Assurance Engineer. Your goal is to verify that the generated SDK matches the API schema and follows best practices.

You must perform static analysis and review the LIVE HTTP TEST RESULTS to report failures.
Recommendation rules:
- 'fix_by_engineer' if there are logical bugs, missing methods, or type errors.
- 'fix_by_researcher' if the schema seems wrong compared to expected API behavior (e.g., getting 404s or 401s that contradict the schema).
- 'proceed' if everything is correct.
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
        method = ep.get("method", "GET")
        
        headers = {}
        params = {}
        if auth.get("type") == "api_key":
            if auth.get("location") == "header":
                headers[auth.get("key_name", "x-api-key")] = auth.get("example", "test")
            elif auth.get("location") == "query" or auth.get("location") == "query_param":
                params[auth.get("key_name", "api_key")] = auth.get("example", "test")
        elif auth.get("type") == "bearer":
            headers["Authorization"] = f"Bearer {auth.get('example', 'test')}"
            
        body = None
        if method in ("POST", "PUT", "PATCH"):
            body = {"title": "test", "body": "test_body", "userId": 1}
            
        try:
            res = await execute_http_request(
                method=method, url=url, headers=headers, params=params, body=body, expected_status=200, endpoint_name=ep.get("name", "unknown")
            )
            http_results.append(res)
            sse_events.append({
                "type": "qa_test",
                "endpoint": ep.get("name", "unknown"),
                "status_code": res.get("status_code", 0),
                "passed": res.get("passed", False),
                "latency_ms": res.get("latency_ms", 0)
            })
        except Exception as e:
            res = {"endpoint_name": ep.get("name", "unknown"), "passed": False, "error": str(e)}
            http_results.append(res)
            sse_events.append({
                "type": "qa_test",
                "endpoint": ep.get("name", "unknown"),
                "status_code": 0,
                "passed": False,
                "latency_ms": 0,
                "error": str(e)
            })

    # ── Phase 2: Static Analysis (Structured Output) ────────────────────
    structured_llm = get_structured_llm(QaReport)
    
    human_msg = f"""
API SCHEMA: {api_schema}
SDK FILES: {sdk_files}
LIVE HTTP TEST RESULTS: {http_results}
"""

    try:
        report: QaReport = await structured_llm.ainvoke([
            SystemMessage(content=QA_TESTER_PROMPT),
            HumanMessage(content=human_msg)
        ])
        
        passed_count = report.summary.passed
        failed_count = report.summary.failed
        total_count = passed_count + failed_count
        recommendation = report.summary.recommendation

        # Emit per-test events for frontend rendering
        sse_events = []
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

        sse_events.append({
            "type": "qa_done",
            "passed": passed_count,
            "failed": failed_count,
            "recommendation": recommendation
        })

        # Final qa_done summary event
        sse_events.append({
            "type": "qa_done",
            "passed": passed_count,
            "failed": failed_count,
            "total": total_count,
            "recommendation": recommendation,
        })

        return {
            "test_results": test_results,
            "qa_iteration": state.get("qa_iteration", 0) + 1,
            "messages": [AIMessage(content=summary_text, name="qa_tester")],
            "sse_events": sse_events,
            "status": "success" if failed_count == 0 else "running"
        }

    except Exception as e:
        logger.error(f"QA failed: {e}")
        return {
            "messages": [AIMessage(content=f"QA error: {str(e)}", name="qa_tester")],
            "sse_events": [{"type": "qa_error", "error": str(e)}]
        }
