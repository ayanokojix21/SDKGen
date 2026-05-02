"""Tests for backend/graph/router.py — route_next function."""
import pytest
from backend.graph.router import route_next


def test_router_valid_agents(mock_state):
    for agent in ("researcher", "architect", "engineer", "qa_tester", "packager", "end"):
        mock_state["next_agent"] = agent
        assert route_next(mock_state) == agent


def test_router_invalid_agent(mock_state):
    mock_state["next_agent"] = "nonexistent"
    assert route_next(mock_state) == "end"


def test_router_failed_status(mock_state):
    mock_state["status"] = "failed"
    mock_state["next_agent"] = "researcher"
    assert route_next(mock_state) == "end"


def test_router_max_iterations(mock_state):
    mock_state["iteration_count"] = 15
    mock_state["next_agent"] = "researcher"
    assert route_next(mock_state) == "end"


def test_router_max_qa_rounds(mock_state):
    mock_state["qa_iteration"] = 4
    mock_state["next_agent"] = "qa_tester"
    assert route_next(mock_state) == "end"


def test_router_within_limits(mock_state):
    mock_state["iteration_count"] = 3
    mock_state["qa_iteration"] = 1
    mock_state["next_agent"] = "researcher"
    assert route_next(mock_state) == "researcher"
