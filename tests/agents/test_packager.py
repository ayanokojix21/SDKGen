"""Tests for backend/agents/packager.py — packager_node."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock


@pytest.mark.asyncio
@patch("backend.agents.packager._get_narrate_llm")
async def test_packager_node_success(mock_get_llm, mock_state, mock_sdk_files, mock_api_schema):
    """Test SDK packaging with narration and delivery events."""
    mock_state["sdk_files"] = mock_sdk_files
    mock_state["api_schema"] = mock_api_schema

    # Mock the narration LLM
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "We built a Python SDK for TestAPI with 1 endpoint."
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)
    mock_get_llm.return_value = mock_llm

    from backend.agents.packager import packager_node
    result = await packager_node(mock_state)

    assert result["status"] == "success"
    assert result["final_files"] is not None
    assert "client.py" in result["final_files"]
    assert "models.py" in result["final_files"]
    assert len(result["messages"]) == 1

    # Verify delivery SSE events
    event_types = [e["type"] for e in result["sse_events"]]
    assert "file_ready" in event_types      # per-file events
    assert "packager_done" in event_types   # summary
    assert "narrate" in event_types         # TTS
    assert "complete" in event_types        # triggers UI buttons
    
    # Verify file_ready events contain content for VS Code injection
    file_readies = [e for e in result["sse_events"] if e["type"] == "file_ready"]
    assert len(file_readies) == 2  # client.py + models.py
    assert all("content" in e for e in file_readies)
    assert all("filename" in e for e in file_readies)

    # Verify complete event has summary
    complete = next(e for e in result["sse_events"] if e["type"] == "complete")
    assert "summary" in complete
    assert complete["summary"]["language"] == "python"


@pytest.mark.asyncio
async def test_packager_no_sdk_files(mock_state):
    """Test failure when no SDK files exist."""
    mock_state["sdk_files"] = None

    from backend.agents.packager import packager_node
    result = await packager_node(mock_state)

    assert result["status"] == "failed"
    assert "No SDK files" in result["failure_reason"]


@pytest.mark.asyncio
@patch("backend.agents.packager._get_narrate_llm")
async def test_packager_removes_empty_files(mock_get_llm, mock_state, mock_api_schema):
    """Test that empty files are removed."""
    mock_state["sdk_files"] = {"good.py": "print('hello')", "empty.py": "   "}
    mock_state["api_schema"] = mock_api_schema

    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "SDK ready."
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)
    mock_get_llm.return_value = mock_llm

    from backend.agents.packager import packager_node
    result = await packager_node(mock_state)

    assert "good.py" in result["final_files"]
    assert "empty.py" not in result["final_files"]
    
    # Only 1 file_ready event (empty.py was removed)
    file_readies = [e for e in result["sse_events"] if e["type"] == "file_ready"]
    assert len(file_readies) == 1
    assert file_readies[0]["filename"] == "good.py"
