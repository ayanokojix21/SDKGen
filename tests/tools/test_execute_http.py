"""Tests for backend/tools/execute_http.py."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
from backend.tools.execute_http import execute_http_request, _is_private_ip


@pytest.mark.asyncio
async def test_execute_http_success():
    """Test successful HTTP request."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = '{"success": true}'
    mock_response.url = "https://api.example.com/users"

    with patch("backend.tools.execute_http.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__.return_value = mock_client
        mock_client.request.return_value = mock_response

        result = await execute_http_request("GET", "https://api.example.com/users", endpoint_name="get_users")

    assert result["passed"] is True
    assert result["status_code"] == 200
    assert result["endpoint_name"] == "get_users"
    assert result["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_execute_http_wrong_status():
    """Test failed HTTP request with unexpected status."""
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.text = "Not Found"
    mock_response.url = "https://api.example.com/missing"

    with patch("backend.tools.execute_http.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__.return_value = mock_client
        mock_client.request.return_value = mock_response

        result = await execute_http_request("GET", "https://api.example.com/missing", endpoint_name="test")

    assert result["passed"] is False
    assert result["status_code"] == 404
    assert "Expected 200" in result["error"]


@pytest.mark.asyncio
async def test_execute_http_timeout():
    """Test timeout handling."""
    with patch("backend.tools.execute_http.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__.return_value = mock_client
        mock_client.request.side_effect = httpx.TimeoutException("Timeout")

        result = await execute_http_request("GET", "https://api.example.com/slow", endpoint_name="test")

    assert result["passed"] is False
    assert "timed out" in result["error"]


@pytest.mark.asyncio
async def test_execute_http_blocked_method():
    """Test that DELETE/PUT methods are blocked."""
    result = await execute_http_request("DELETE", "https://api.example.com/users/1", endpoint_name="test")
    assert result["passed"] is False
    assert "not allowed" in result["error"]


@pytest.mark.asyncio
async def test_execute_http_private_ip():
    """Test that private IPs are blocked."""
    result = await execute_http_request("GET", "http://127.0.0.1/admin", endpoint_name="test")
    assert result["passed"] is False
    assert "Private IP" in result["error"]


def test_is_private_ip():
    assert _is_private_ip("127.0.0.1") is True
    assert _is_private_ip("192.168.1.1") is True
    assert _is_private_ip("10.0.0.1") is True
    # Public IPs should not be private
    assert _is_private_ip("8.8.8.8") is False
