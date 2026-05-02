"""Tests for backend/agents/architect.py — architect_node."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from backend.graph.schemas import ApiSchema, AuthConfig, Endpoint


@pytest.mark.asyncio
@patch("backend.agents.architect.query_docs", new_callable=AsyncMock)
@patch("backend.agents.architect.validate_schema")
async def test_architect_node_success(mock_validate, mock_query, mock_state, mock_structured_llm):
    """Test successful schema generation."""
    mock_state["vector_store_collection"] = "job_test_123"

    mock_query.return_value = [MagicMock(page_content="docs content", metadata={"source": "url"})]

    mock_schema = ApiSchema(
        api_name="TestAPI",
        base_url="http://api",
        auth=AuthConfig(type="none", location="header", key_name="", example=""),
        endpoints=[
            Endpoint(name="get_users", path="/users", method="GET", description="Get users",
                     path_params=[], query_params=[], request_body=None, response_schema=None)
        ],
    )
    mock_structured_llm.ainvoke.return_value = mock_schema

    mock_validate.return_value = {
        "valid": True,
        "schema": mock_schema.model_dump(),
        "fixes": [],
        "errors": [],
    }

    from backend.agents.architect import architect_node
    result = await architect_node(mock_state)

    assert "api_schema" in result
    assert result["api_schema"]["api_name"] == "TestAPI"
    assert len(result["messages"]) == 1
    assert any(e["type"] == "architect_done" for e in result["sse_events"])


@pytest.mark.asyncio
async def test_architect_no_vector_store(mock_state):
    """Test error when no vector store is available."""
    mock_state["vector_store_collection"] = None

    from backend.agents.architect import architect_node
    result = await architect_node(mock_state)

    assert "No research data" in result["messages"][0].content
    assert any(e["type"] == "architect_error" for e in result["sse_events"])


@pytest.mark.asyncio
@patch("backend.agents.architect.query_docs", new_callable=AsyncMock)
async def test_architect_handles_llm_error(mock_query, mock_state, mock_structured_llm):
    """Test error handling in architect."""
    mock_state["vector_store_collection"] = "job_test_123"
    mock_query.return_value = []
    mock_structured_llm.ainvoke.side_effect = Exception("LLM Error")

    from backend.agents.architect import architect_node
    result = await architect_node(mock_state)

    assert any(e["type"] == "architect_error" for e in result["sse_events"])
