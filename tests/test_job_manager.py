"""Tests for backend/job_manager.py."""
import asyncio
import io
import zipfile
import pytest
from backend.job_manager import (
    create_job,
    subscribe,
    unsubscribe,
    remove_all_queues,
    put_event,
    put_sentinel,
    put_error,
    build_zip,
)


def test_create_job_returns_uuid_and_state():
    job_id, state = create_job(
        target_url="https://api.example.com",
        language="python",
        page_content="content",
        page_links=[{"text": "docs", "href": "/docs"}],
    )
    assert job_id is not None
    assert len(job_id) == 36  # UUID format
    assert state["target_url"] == "https://api.example.com"
    assert state["language"] == "python"


def test_create_job_typescript():
    job_id, state = create_job("https://api.example.com", "typescript", "", [])
    assert state["language"] == "typescript"


def test_subscribe_returns_queue():
    job_id, _ = create_job("https://api.com", "python", "", [])
    q = subscribe(job_id)
    assert q is not None


def test_subscribe_nonexistent_job_returns_none():
    assert subscribe("nonexistent-job-id") is None


def test_subscribe_multiple_returns_independent_queues():
    job_id, _ = create_job("https://api.com", "python", "", [])
    q1 = subscribe(job_id)
    q2 = subscribe(job_id)
    assert q1 is not None
    assert q2 is not None
    assert q1 is not q2


def test_unsubscribe_removes_queue():
    job_id, _ = create_job("https://api.com", "python", "", [])
    q = subscribe(job_id)
    assert q is not None
    unsubscribe(job_id, q)
    # After unsubscribe, a new subscribe still works (job still exists)
    q2 = subscribe(job_id)
    assert q2 is not None


def test_remove_all_queues():
    job_id, _ = create_job("https://api.com", "python", "", [])
    subscribe(job_id)
    subscribe(job_id)
    remove_all_queues(job_id)
    # Job no longer exists — subscribe returns None
    assert subscribe(job_id) is None


def test_remove_all_queues_nonexistent_is_safe():
    remove_all_queues("does-not-exist")  # should not raise


@pytest.mark.asyncio
async def test_put_event_delivered_to_subscriber():
    job_id, _ = create_job("https://api.com", "python", "", [])
    q = subscribe(job_id)
    await put_event(job_id, {"type": "researcher_done", "page_count": 3})
    event = await asyncio.wait_for(q.get(), timeout=1.0)
    assert event["type"] == "researcher_done"
    assert event["page_count"] == 3


@pytest.mark.asyncio
async def test_put_event_delivered_to_all_subscribers():
    job_id, _ = create_job("https://api.com", "python", "", [])
    q1 = subscribe(job_id)
    q2 = subscribe(job_id)
    await put_event(job_id, {"type": "architect_done"})
    e1 = await asyncio.wait_for(q1.get(), timeout=1.0)
    e2 = await asyncio.wait_for(q2.get(), timeout=1.0)
    assert e1["type"] == "architect_done"
    assert e2["type"] == "architect_done"


@pytest.mark.asyncio
async def test_put_event_nonexistent_job_is_safe():
    await put_event("nonexistent", {"type": "test"})  # should not raise


@pytest.mark.asyncio
async def test_put_sentinel_sends_done():
    job_id, _ = create_job("https://api.com", "python", "", [])
    q = subscribe(job_id)
    await put_sentinel(job_id)
    event = await asyncio.wait_for(q.get(), timeout=1.0)
    assert event["type"] == "__done__"


@pytest.mark.asyncio
async def test_put_error_sends_error_then_sentinel():
    job_id, _ = create_job("https://api.com", "python", "", [])
    q = subscribe(job_id)
    await put_error(job_id, "something went wrong")
    error_event = await asyncio.wait_for(q.get(), timeout=1.0)
    sentinel_event = await asyncio.wait_for(q.get(), timeout=1.0)
    assert error_event["type"] == "error"
    assert error_event["message"] == "something went wrong"
    assert sentinel_event["type"] == "__done__"


def test_build_zip_contains_all_files():
    files = {
        "client.py": "class Client: pass",
        "models.py": "class Model: pass",
        "tests/test_client.py": "def test_init(): pass",
        "README.md": "# SDK",
    }
    buf = build_zip(files)
    assert isinstance(buf, io.BytesIO)
    assert buf.tell() == 0  # positioned at start

    with zipfile.ZipFile(buf) as zf:
        names = zf.namelist()
        assert set(names) == set(files.keys())
        assert zf.read("client.py").decode() == "class Client: pass"
        assert zf.read("README.md").decode() == "# SDK"


def test_build_zip_empty_files():
    buf = build_zip({})
    assert buf.tell() == 0
    with zipfile.ZipFile(buf) as zf:
        assert zf.namelist() == []


def test_build_zip_returns_valid_bytes():
    buf = build_zip({"file.py": "x = 1"})
    content = buf.read()
    assert len(content) > 0
    # ZIP magic bytes
    assert content[:2] == b"PK"
