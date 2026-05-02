"""Tests for backend/agents/qa_tester.py — qa_tester_node."""
import pytest
from unittest.mock import patch, AsyncMock
from backend.graph.schemas import QaReport, QaSummary, QaTestResult


@pytest.mark.asyncio
async def test_qa_tester_success(mock_state, mock_api_schema, mock_sdk_files, mock_structured_llm):
    """Test QA passing."""
    mock_state["api_schema"] = mock_api_schema
    mock_state["sdk_files"] = mock_sdk_files

    report = QaReport(
        summary=QaSummary(passed=2, failed=0, recommendation="proceed"),
        test_plan=[
            QaTestResult(
                test_id="1", category="static", target="client.py",
                description="Syntax check", status="pass", details="OK", fix_suggestion=None,
            )
        ],
    )
    mock_structured_llm.ainvoke.return_value = report

    from backend.agents.qa_tester import qa_tester_node
    result = await qa_tester_node(mock_state)

    assert result["status"] == "success"
    assert any(e["type"] == "qa_done" for e in result["sse_events"])


@pytest.mark.asyncio
async def test_qa_tester_failures(mock_state, mock_api_schema, mock_sdk_files, mock_structured_llm):
    """Test QA with failures."""
    mock_state["api_schema"] = mock_api_schema
    mock_state["sdk_files"] = mock_sdk_files

    report = QaReport(
        summary=QaSummary(passed=1, failed=2, recommendation="fix_by_engineer"),
        test_plan=[],
    )
    mock_structured_llm.ainvoke.return_value = report

    from backend.agents.qa_tester import qa_tester_node
    result = await qa_tester_node(mock_state)

    assert result["status"] == "running"  # failed_count > 0 means still running


@pytest.mark.asyncio
async def test_qa_tester_missing_inputs(mock_state):
    """Test failure when inputs are missing."""
    mock_state["api_schema"] = None
    mock_state["sdk_files"] = None

    from backend.agents.qa_tester import qa_tester_node
    result = await qa_tester_node(mock_state)

    assert result["status"] == "failed"
    assert "Missing inputs" in result["messages"][0].content
