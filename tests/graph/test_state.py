"""Tests for backend/graph/state.py — state helpers."""
import pytest
from backend.graph.state import SDKJobState, create_initial_state, emit_sse, build_state_summary


def test_create_initial_state():
    state = create_initial_state(
        job_id="job1",
        target_url="http://api.example.com",
        language="python",
        page_content="API docs content",
        page_links=[{"text": "docs", "href": "/docs"}],
    )

    assert state["job_id"] == "job1"
    assert state["target_url"] == "http://api.example.com"
    assert state["language"] == "python"
    assert state["page_content"] == "API docs content"
    assert state["qa_iteration"] == 0
    assert state["total_tokens"] == 0
    assert state["estimated_cost_usd"] == 0.0
    assert state["status"] == "running"
    assert state["next_agent"] == "supervisor"
    assert state["crawled_pages"] is None
    assert len(state["sse_events"]) == 1
    assert state["sse_events"][0]["type"] == "job_started"


def test_emit_sse():
    result = emit_sse("test_event", key="value")
    assert "sse_events" in result
    assert len(result["sse_events"]) == 1
    assert result["sse_events"][0]["type"] == "test_event"
    assert result["sse_events"][0]["key"] == "value"


def test_build_state_summary():
    state = create_initial_state(
        job_id="job1",
        target_url="http://api.example.com",
        language="python",
        page_content="API docs content",
        page_links=[],
    )
    summary = build_state_summary(state)

    assert "job1" in summary
    assert "http://api.example.com" in summary
    assert "python" in summary
    assert "running" in summary


def test_build_state_summary_with_schema():
    state = create_initial_state(
        job_id="job1",
        target_url="http://api.example.com",
        language="python",
        page_content="content",
        page_links=[],
    )
    state["api_schema"] = {"endpoints": [{"name": "test"}]}
    state["sdk_files"] = {"client.py": "code"}

    summary = build_state_summary(state)
    assert "1 endpoints" in summary
    assert "client.py" in summary
