"""
QA Tester Agent — Static Analysis + Live HTTP Verification.
Upgraded with Structured Outputs.
"""

import logging
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from backend.llm import get_structured_llm
from backend.graph.schemas import QaReport
from backend.tools.execute_http import execute_http_request

logger = logging.getLogger(__name__)

QA_TESTER_PROMPT = """
You are a Quality Assurance Engineer. Your goal is to verify that the generated SDK matches the API schema and follows best practices.

You must perform static analysis and report failures.
Recommendation rules:
- 'fix_by_engineer' if there are logical bugs, missing methods, or type errors.
- 'fix_by_researcher' if the schema seems wrong compared to expected API behavior.
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

    # ── Phase 1: Static Analysis (Structured Output) ────────────────────
    structured_llm = get_structured_llm(QaReport)
    
    human_msg = f"""
API SCHEMA: {api_schema}
SDK FILES: {sdk_files}
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
            f"Passed: {passed_count}, Failed: {failed_count}."
        )

        # Final qa_done summary event
        sse_events.append({
            "type": "qa_done",
            "passed": passed_count,
            "failed": failed_count,
            "total": total_count,
            "recommendation": recommendation,
        })

        return {
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
