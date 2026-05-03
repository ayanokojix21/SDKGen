"""Tests for backend/main.py — FastAPI endpoints."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock


@pytest.fixture
def test_client():
    from fastapi.testclient import TestClient
    from backend.main import app

    with patch("backend.main.init_graph", new_callable=AsyncMock), \
         patch("backend.main.teardown_graph", new_callable=AsyncMock):
        with TestClient(app) as client:
            yield client


# ── /health ───────────────────────────────────────────────────────────────────

def test_health_check(test_client):
    with patch("backend.graph.graph.compiled_graph", None), \
         patch("backend.graph.graph._checkpointer", None):
        response = test_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "api_key_set" in data
    assert "graph_compiled" in data


# ── /generate/start ───────────────────────────────────────────────────────────

def test_start_generation_no_api_key(test_client, monkeypatch):
    monkeypatch.setattr("backend.config.settings.GOOGLE_API_KEY", "")
    response = test_client.post(
        "/generate/start",
        json={"target_url": "https://api.example.com", "language": "python"},
    )
    assert response.status_code == 503


def test_start_generation_invalid_language(test_client, monkeypatch):
    monkeypatch.setattr("backend.config.settings.GOOGLE_API_KEY", "test_key")
    response = test_client.post(
        "/generate/start",
        json={"target_url": "https://api.example.com", "language": "rust"},
    )
    assert response.status_code == 400


def test_start_generation_success(test_client, monkeypatch):
    monkeypatch.setattr("backend.config.settings.GOOGLE_API_KEY", "test_key")
    with patch("backend.main.run_graph", new_callable=AsyncMock):
        response = test_client.post(
            "/generate/start",
            json={"target_url": "https://api.example.com", "language": "python"},
        )
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert len(data["job_id"]) == 36  # UUID


def test_start_generation_typescript(test_client, monkeypatch):
    monkeypatch.setattr("backend.config.settings.GOOGLE_API_KEY", "test_key")
    with patch("backend.main.run_graph", new_callable=AsyncMock):
        response = test_client.post(
            "/generate/start",
            json={"target_url": "https://api.example.com", "language": "typescript"},
        )
    assert response.status_code == 200


# ── /generate/stream ──────────────────────────────────────────────────────────

def test_stream_generation_not_found(test_client):
    response = test_client.get("/generate/stream?job_id=nonexistent")
    assert response.status_code == 404


def test_stream_generation_missing_job_id(test_client):
    response = test_client.get("/generate/stream")
    assert response.status_code == 422  # missing required query param


# ── /download/{job_id} ────────────────────────────────────────────────────────

def test_download_sdk_graph_not_ready(test_client):
    with patch("backend.graph.graph.compiled_graph", None):
        response = test_client.get("/download/test-job-id")
    assert response.status_code == 503


def test_download_sdk_job_not_found(test_client):
    mock_graph = AsyncMock()
    mock_graph.aget_state.side_effect = Exception("not found")
    with patch("backend.graph.graph.compiled_graph", mock_graph):
        response = test_client.get("/download/bad-job-id")
    assert response.status_code == 404


def test_download_sdk_no_files_yet(test_client):
    mock_graph = AsyncMock()
    mock_snapshot = MagicMock()
    mock_snapshot.values = {"status": "running"}
    mock_graph.aget_state.return_value = mock_snapshot
    with patch("backend.graph.graph.compiled_graph", mock_graph):
        response = test_client.get("/download/running-job-id")
    assert response.status_code == 202


def test_download_sdk_success(test_client):
    mock_graph = AsyncMock()
    mock_snapshot = MagicMock()
    mock_snapshot.values = {
        "final_files": {
            "client.py": "class Client: pass",
            "README.md": "# SDK",
        }
    }
    mock_graph.aget_state.return_value = mock_snapshot
    with patch("backend.graph.graph.compiled_graph", mock_graph):
        response = test_client.get("/download/done-job-id")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "sdk_done-job" in response.headers["content-disposition"]


# ── /job/{job_id}/files ───────────────────────────────────────────────────────

def test_get_job_files_graph_not_ready(test_client):
    with patch("backend.graph.graph.compiled_graph", None):
        response = test_client.get("/job/test-job-id/files")
    assert response.status_code == 503


def test_get_job_files_not_found(test_client):
    mock_graph = AsyncMock()
    mock_graph.aget_state.side_effect = Exception("not found")
    with patch("backend.graph.graph.compiled_graph", mock_graph):
        response = test_client.get("/job/bad-job-id/files")
    assert response.status_code == 404


def test_get_job_files_still_running(test_client):
    mock_graph = AsyncMock()
    mock_snapshot = MagicMock()
    mock_snapshot.values = {"status": "running"}
    mock_graph.aget_state.return_value = mock_snapshot
    with patch("backend.graph.graph.compiled_graph", mock_graph):
        response = test_client.get("/job/running-job-id/files")
    assert response.status_code == 202


def test_get_job_files_success(test_client):
    mock_graph = AsyncMock()
    mock_snapshot = MagicMock()
    sdk_files = {
        "client.py": "class Client: pass",
        "models.py": "class Model: pass",
        "tests/test_client.py": "def test_init(): pass",
        "README.md": "# SDK",
    }
    mock_snapshot.values = {"final_files": sdk_files}
    mock_graph.aget_state.return_value = mock_snapshot
    with patch("backend.graph.graph.compiled_graph", mock_graph):
        response = test_client.get("/job/done-job-id/files")
    assert response.status_code == 200
    data = response.json()
    assert data == sdk_files


def test_get_job_files_uses_sdk_files_fallback(test_client):
    """Falls back to sdk_files key if final_files is absent."""
    mock_graph = AsyncMock()
    mock_snapshot = MagicMock()
    mock_snapshot.values = {"sdk_files": {"client.py": "# client"}}
    mock_graph.aget_state.return_value = mock_snapshot
    with patch("backend.graph.graph.compiled_graph", mock_graph):
        response = test_client.get("/job/done-job-id/files")
    assert response.status_code == 200
    assert "client.py" in response.json()
