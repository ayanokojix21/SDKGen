"""Tests for backend/graph/graph.py — graph compilation."""
import pytest
from unittest.mock import patch, MagicMock
from langgraph.checkpoint.memory import MemorySaver
from backend.graph.graph import _build_graph


def test_build_graph_compilation():
    """Test that _build_graph compiles a valid graph with InMemorySaver."""
    checkpointer = MemorySaver()
    graph = _build_graph(checkpointer)

    assert graph is not None


def test_build_graph_has_all_nodes():
    """Verify all agent nodes are registered."""
    checkpointer = MemorySaver()
    graph = _build_graph(checkpointer)

    # The graph should have all the expected nodes
    node_names = set(graph.nodes.keys())
    expected = {"supervisor", "researcher", "architect", "engineer", "qa_tester", "packager"}
    # LangGraph also adds __start__ and __end__ nodes
    assert expected.issubset(node_names), f"Missing nodes: {expected - node_names}"


@pytest.mark.asyncio
async def test_init_graph_fallback_to_memory(monkeypatch):
    """Test that init_graph falls back to InMemorySaver when MONGODB_URI is empty."""
    monkeypatch.setattr("backend.config.settings.MONGODB_URI", "")
    monkeypatch.setattr("backend.config.settings.GOOGLE_API_KEY", "test")

    from backend.graph.graph import init_graph, compiled_graph
    import backend.graph.graph as graph_module

    await init_graph()
    assert graph_module.compiled_graph is not None
    assert isinstance(graph_module._checkpointer, MemorySaver)
