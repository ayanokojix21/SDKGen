"""Tests for backend/main.py — FastAPI endpoints."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock


@pytest.fixture
def test_client():
    """Create a test client with mocked lifespan."""
    from fastapi.testclient import TestClient
    from backend.main import app

    # Use TestClient which handles lifespan; mock init_graph/teardown_graph
    with patch("backend.main.init_graph", new_callable=AsyncMock), \
         patch("backend.main.teardown_graph", new_callable=AsyncMock):
        with TestClient(app) as client:
            yield client


def test_health_check(test_client):
    """Test healthcheck endpoint."""
    with patch("backend.graph.graph.compiled_graph", None), \
         patch("backend.graph.graph._checkpointer", None):
        response = test_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "ok"


def test_start_generation_no_api_key(test_client, monkeypatch):
    """Test that /generate/start returns 503 without API key."""
    monkeypatch.setattr("backend.config.settings.GOOGLE_API_KEY", "")

    response = test_client.post(
        "/generate/start",
        json={"target_url": "https://api.example.com", "language": "python"},
    )
    assert response.status_code == 503


def test_start_generation_invalid_language(test_client, monkeypatch):
    """Test that invalid language is rejected."""
    monkeypatch.setattr("backend.config.settings.GOOGLE_API_KEY", "test_key")

    response = test_client.post(
        "/generate/start",
        json={"target_url": "https://api.example.com", "language": "rust"},
    )
    assert response.status_code == 400


def test_start_generation_success(test_client, monkeypatch):
    """Test successful job creation."""
    monkeypatch.setattr("backend.config.settings.GOOGLE_API_KEY", "test_key")

    with patch("backend.main.run_graph", new_callable=AsyncMock):
        response = test_client.post(
            "/generate/start",
            json={"target_url": "https://api.example.com", "language": "python"},
        )

    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data


def test_stream_generation_not_found(test_client):
    """Test streaming for non-existent job."""
    response = test_client.get("/generate/stream?job_id=nonexistent")
    assert response.status_code == 404


def test_download_sdk_graph_not_ready(test_client):
    """Test download when graph is not initialized."""
    with patch("backend.graph.graph.compiled_graph", None):
        response = test_client.get("/download/test-job-id")
    assert response.status_code == 503
