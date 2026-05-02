"""Tests for backend/agents/supervisor.py — supervisor_node."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from langchain_core.messages import AIMessage
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
    # Should have exactly 1 supervisor event (no reroute — first routing)
    assert any(e["type"] == "supervisor" for e in result["sse_events"])
    assert result["sse_events"][-1]["routing_to"] == "researcher"
    assert result["sse_events"][-1]["iteration"] == 1


@pytest.mark.asyncio
async def test_supervisor_budget_cutoff(mock_state, mock_structured_llm):
    """Test budget cutoff logic — $2.00 limit."""
    mock_state["estimated_cost_usd"] = 3.0  # Over budget

    from backend.agents.supervisor import supervisor_node
    result = await supervisor_node(mock_state)

    assert result["next_agent"] == "end"
    assert result["status"] == "failed"
    assert "Budget" in result["failure_reason"]
    # Should emit safety_cutoff event
    assert any(e["type"] == "safety_cutoff" for e in result["sse_events"])


@pytest.mark.asyncio
async def test_supervisor_handles_llm_error(mock_state, mock_structured_llm):
    """Test graceful error handling."""
    mock_structured_llm.ainvoke.side_effect = Exception("LLM timeout")

    from backend.agents.supervisor import supervisor_node
    result = await supervisor_node(mock_state)

    assert result["next_agent"] == "end"
    assert result["status"] == "failed"
    assert "Supervisor error" in result["failure_reason"]
    # Should emit safety_cutoff event
    assert any(e["type"] == "safety_cutoff" for e in result["sse_events"])


@pytest.mark.asyncio
async def test_supervisor_reroute_detection(mock_state, mock_structured_llm):
    """Test reroute event is emitted when routing backwards."""
    # Simulate QA tester was the last agent
    mock_state["messages"] = [AIMessage(content="QA done", name="qa_tester")]
    
    # Supervisor routes back to engineer (backward = reroute)
    decision = SupervisorDecision(
        next_agent="engineer",
        reasoning="QA failed — code bug",
        instruction="Fix appid param"
    )
    mock_structured_llm.ainvoke.return_value = decision

    from backend.agents.supervisor import supervisor_node
    result = await supervisor_node(mock_state)

    assert result["next_agent"] == "engineer"
    # Should emit BOTH reroute and supervisor events
    event_types = [e["type"] for e in result["sse_events"]]
    assert "reroute" in event_types
    assert "supervisor" in event_types
    
    reroute = next(e for e in result["sse_events"] if e["type"] == "reroute")
    assert reroute["from"] == "qa_tester"
    assert reroute["to"] == "engineer"


@pytest.mark.asyncio
async def test_supervisor_no_reroute_on_forward(mock_state, mock_structured_llm):
    """Test no reroute event when routing forward in the pipeline."""
    mock_state["messages"] = [AIMessage(content="Research done", name="researcher")]
    
    decision = SupervisorDecision(
        next_agent="architect",
        reasoning="Schema needed",
        instruction="Build schema"
    )
    mock_structured_llm.ainvoke.return_value = decision

    from backend.agents.supervisor import supervisor_node
    result = await supervisor_node(mock_state)

    event_types = [e["type"] for e in result["sse_events"]]
    assert "reroute" not in event_types
    assert "supervisor" in event_types
