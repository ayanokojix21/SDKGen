"""Tests for backend/agents/engineer.py — engineer_node."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from backend.graph.schemas import GeneratedSdk, SdkFile


@pytest.mark.asyncio
@patch("backend.agents.engineer.check_syntax", new_callable=AsyncMock)
@patch("backend.agents.engineer.query_docs", new_callable=AsyncMock)
async def test_engineer_node_success(mock_query, mock_check_syntax, mock_state, mock_structured_llm, mock_api_schema):
    """Test successful SDK generation and syntax check."""
    mock_state["api_schema"] = mock_api_schema

    mock_query.return_value = [MagicMock(page_content="example", metadata={"source": "url"})]

    mock_sdk = GeneratedSdk(
        files=[SdkFile(filename="client.py", content="class Client:\n    pass")],
        internal_notes="Looks good",
    )
    mock_structured_llm.ainvoke.return_value = mock_sdk

    mock_check_syntax.return_value = [{"file": "client.py", "valid": True, "errors": []}]

    from backend.agents.engineer import engineer_node
    result = await engineer_node(mock_state)

    assert "sdk_files" in result
    assert "client.py" in result["sdk_files"]
    assert len(result["syntax_errors"]) == 0
    assert any(e["type"] == "engineer_done" for e in result["sse_events"])


@pytest.mark.asyncio
@patch("backend.agents.engineer.check_syntax", new_callable=AsyncMock)
@patch("backend.agents.engineer.query_docs", new_callable=AsyncMock)
async def test_engineer_syntax_errors(mock_query, mock_check_syntax, mock_state, mock_structured_llm, mock_api_schema):
    """Test that syntax errors are reported."""
    mock_state["api_schema"] = mock_api_schema
    mock_query.return_value = []

    mock_sdk = GeneratedSdk(
        files=[SdkFile(filename="bad.py", content="def (broken")],
        internal_notes="",
    )
    mock_structured_llm.ainvoke.return_value = mock_sdk

    mock_check_syntax.return_value = [{"file": "bad.py", "valid": False, "errors": ["SyntaxError: invalid syntax"]}]

    from backend.agents.engineer import engineer_node
    result = await engineer_node(mock_state)

    assert len(result["syntax_errors"]) > 0
    assert "SyntaxError" in result["syntax_errors"][0]


@pytest.mark.asyncio
async def test_engineer_no_schema(mock_state):
    """Test failure when schema is missing."""
    mock_state["api_schema"] = None

    from backend.agents.engineer import engineer_node
    result = await engineer_node(mock_state)

    assert "No API schema found" in result["messages"][0].content
