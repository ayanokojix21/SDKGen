"""Tests for backend/graph/runner.py — run_graph async task."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from backend.graph.runner import run_graph, _handle_event


@pytest.mark.asyncio
@patch("backend.graph.graph.compiled_graph")
@patch("backend.job_manager.put_sentinel", new_callable=AsyncMock)
@patch("backend.job_manager.put_event", new_callable=AsyncMock)
async def test_run_graph_graph_not_compiled(mock_put_event, mock_put_sentinel, mock_graph):
    """Test that run_graph handles None compiled_graph."""
    import backend.graph.graph as graph_module
    graph_module.compiled_graph = None

    with patch("backend.job_manager.put_error", new_callable=AsyncMock) as mock_error:
        await run_graph("test_job", {})
        mock_error.assert_called_once()


@pytest.mark.asyncio
async def test_handle_event_on_node_end():
    """Test that _handle_event forwards sse_events from on_node_end."""
    event = {
        "event": "on_node_end",
        "name": "researcher",
        "data": {
            "output": {
                "sse_events": [{"type": "researcher_done", "pages": 3}]
            }
        },
    }

    with patch("backend.job_manager.put_event", new_callable=AsyncMock) as mock_put:
        await _handle_event("test_job", event)
        mock_put.assert_called_once_with("test_job", {"type": "researcher_done", "pages": 3})


@pytest.mark.asyncio
async def test_handle_event_ignores_unrelated():
    """Test that _handle_event ignores non-relevant events."""
    event = {
        "event": "on_node_start",
        "name": "researcher",
        "data": {},
    }

    with patch("backend.job_manager.put_event", new_callable=AsyncMock) as mock_put:
        await _handle_event("test_job", event)
        mock_put.assert_not_called()
