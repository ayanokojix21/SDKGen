"""Tests for backend/agents/supervisor.py — supervisor_node."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from backend.graph.schemas import SupervisorDecision


@pytest.mark.asyncio
async def test_supervisor_node_routing(mock_state, mock_structured_llm):
    """Test standard routing behavior."""
    decision = SupervisorDecision(next_agent="researcher", reasoning="Need docs", instruction="Crawl API docs")
    mock_structured_llm.ainvoke.return_value = decision

    from backend.agents.supervisor import supervisor_node
    result = await supervisor_node(mock_state)

    assert result["next_agent"] == "researcher"
    assert result["instruction"] == "Crawl API docs"
    assert result["iteration_count"] == 1
    assert len(result["messages"]) == 1
    assert len(result["sse_events"]) == 1
    assert result["sse_events"][0]["type"] == "supervisor"


@pytest.mark.asyncio
async def test_supervisor_budget_cutoff(mock_state, mock_structured_llm):
    """Test budget cutoff logic — $2.00 limit."""
    mock_state["estimated_cost_usd"] = 3.0  # Over budget

    from backend.agents.supervisor import supervisor_node
    result = await supervisor_node(mock_state)

    assert result["next_agent"] == "end"
    assert result["status"] == "failed"
    assert "Budget" in result["failure_reason"]


@pytest.mark.asyncio
async def test_supervisor_handles_llm_error(mock_state, mock_structured_llm):
    """Test graceful error handling."""
    mock_structured_llm.ainvoke.side_effect = Exception("LLM timeout")

    from backend.agents.supervisor import supervisor_node
    result = await supervisor_node(mock_state)

    assert result["next_agent"] == "end"
    assert result["status"] == "failed"
    assert "Supervisor error" in result["failure_reason"]
