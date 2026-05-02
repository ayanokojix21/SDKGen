"""Tests for backend/job_manager.py."""
import asyncio
import pytest
from backend.job_manager import create_job, get_queue, remove_queue, put_event, put_sentinel, build_zip


def test_create_job():
    """Test standard job creation."""
    job_id, state = create_job(
        target_url="https://api.example.com",
        language="python",
        page_content="content",
        page_links=[{"text": "docs", "href": "/docs"}],
    )

    assert job_id is not None
    assert state["target_url"] == "https://api.example.com"
    assert state["language"] == "python"
    assert state["status"] == "running"


def test_get_queue():
    """Test queue retrieval."""
    job_id, _ = create_job("https://api.com", "python", "", [])
    q = get_queue(job_id)
    assert q is not None

    # Non-existent job
    assert get_queue("nonexistent") is None


def test_remove_queue():
    """Test queue removal."""
    job_id, _ = create_job("https://api.com", "python", "", [])
    assert get_queue(job_id) is not None

    remove_queue(job_id)
    assert get_queue(job_id) is None


@pytest.mark.asyncio
async def test_put_event():
    """Test putting events onto the queue."""
    job_id, _ = create_job("https://api.com", "python", "", [])
    await put_event(job_id, {"type": "test_event"})

    q = get_queue(job_id)
    event = await asyncio.wait_for(q.get(), timeout=1.0)
    assert event["type"] == "test_event"


@pytest.mark.asyncio
async def test_put_sentinel():
    """Test sentinel event."""
    job_id, _ = create_job("https://api.com", "python", "", [])
    await put_sentinel(job_id)

    q = get_queue(job_id)
    event = await asyncio.wait_for(q.get(), timeout=1.0)
    assert event["type"] == "__done__"


def test_build_zip():
    """Test ZIP file creation."""
    files = {
        "client.py": "class Client: pass",
        "README.md": "# SDK",
    }
    buf = build_zip(files)

    assert buf is not None
    assert buf.tell() == 0  # positioned at start
    assert len(buf.read()) > 0  # has content
