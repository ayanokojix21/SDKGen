"""
Live HTTP Request tool for the QA Tester agent.
Makes real HTTP calls to live API endpoints to verify the generated SDK.

SAFETY RULES ARE HARDCODED — not overridable by any LLM prompt:
  1. Allowed methods: GET and POST only
  2. Block private IPs: 127.x, 192.168.x, 10.x, 172.16-31.x
  3. Timeout: 10 seconds hard limit
  4. Max 15 requests per job (enforced by caller via qa_iteration guard)
  5. User-Agent: 'docs-to-code-qa/1.0'
"""

import time
import socket
import ipaddress
import logging
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────
_ALLOWED_METHODS = {"GET", "POST"}
_TIMEOUT_SECONDS = 10.0
_USER_AGENT = "docs-to-code-qa/1.0"
_MAX_RESPONSE_BODY = 500  # chars


async def execute_http_request(
    method: str,
    url: str,
    headers: dict | None = None,
    params: dict | None = None,
    body: dict | None = None,
    expected_status: int = 200,
    endpoint_name: str = "",
) -> dict:
    """
    Makes a real HTTP call to a live API endpoint.

    Args:
        method: HTTP method (only GET and POST allowed).
        url: Full URL to call.
        headers: Optional request headers.
        params: Optional query parameters.
        body: Optional JSON request body (POST only).
        expected_status: Expected HTTP status code.
        endpoint_name: Name of the endpoint being tested.

    Returns:
        dict with keys: endpoint_name, method, url, status_code,
        response_body (500 char cap), passed, error, latency_ms
    """
    # ── Safety: method check ──────────────────────────────────────────────
    method = method.upper()
    if method not in _ALLOWED_METHODS:
        return _error_result(
            endpoint_name, method, url,
            f"Method {method} not allowed — only GET and POST permitted"
        )

    # ── Safety: private IP block ──────────────────────────────────────────
    try:
        hostname = urlparse(url).hostname
        if not hostname:
            return _error_result(endpoint_name, method, url, "Invalid URL — no hostname")

        if _is_private_ip(hostname):
            return _error_result(
                endpoint_name, method, url,
                f"Private IP blocked: {hostname}"
            )
    except Exception as e:
        return _error_result(endpoint_name, method, url, f"URL validation error: {e}")

    # ── Build request headers ─────────────────────────────────────────────
    req_headers = {"User-Agent": _USER_AGENT}
    if headers:
        req_headers.update(headers)

    # ── Execute request ───────────────────────────────────────────────────
    start = time.time()
    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT_SECONDS,
            follow_redirects=True,
        ) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=req_headers,
                params=params,
                json=body if method == "POST" and body else None,
            )

        latency_ms = int((time.time() - start) * 1000)
        passed = response.status_code == expected_status
        response_body = response.text[:_MAX_RESPONSE_BODY]

        return {
            "endpoint_name": endpoint_name,
            "method": method,
            "url": str(response.url),  # actual URL after params/redirects
            "status_code": response.status_code,
            "response_body": response_body,
            "passed": passed,
            "error": None if passed else f"Expected {expected_status}, got {response.status_code}",
            "latency_ms": latency_ms,
        }

    except httpx.TimeoutException:
        latency_ms = int((time.time() - start) * 1000)
        return {
            "endpoint_name": endpoint_name,
            "method": method,
            "url": url,
            "status_code": 0,
            "response_body": "",
            "passed": False,
            "error": "Request timed out (10s)",
            "latency_ms": latency_ms,
        }

    except httpx.ConnectError as e:
        return _error_result(endpoint_name, method, url, f"Connection failed: {e}")

    except Exception as e:
        latency_ms = int((time.time() - start) * 1000)
        return {
            "endpoint_name": endpoint_name,
            "method": method,
            "url": url,
            "status_code": 0,
            "response_body": "",
            "passed": False,
            "error": str(e),
            "latency_ms": latency_ms,
        }


def _is_private_ip(hostname: str) -> bool:
    """
    Check if a hostname resolves to a private or reserved IP address.
    Blocks: 127.x, 10.x, 192.168.x, 172.16-31.x, ::1, etc.
    We allow NAT64 addresses (64:ff9b::/96) even though they are 'reserved'.
    """
    try:
        # Try parsing as IP directly first
        ip = ipaddress.ip_address(hostname)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
    except ValueError:
        pass

    # Resolve hostname to IP
    try:
        resolved = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC)
        for family, _, _, _, sockaddr in resolved:
            ip_str = sockaddr[0]
            ip = ipaddress.ip_address(ip_str)
            # We explicitly allow NAT64 (64:ff9b::/96)
            if ip.version == 6 and str(ip).startswith("64:ff9b:"):
                continue
                
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
                return True
    except (socket.gaierror, OSError):
        # Can't resolve — let httpx handle the error
        return False

    return False


def _error_result(endpoint_name: str, method: str, url: str, error: str) -> dict:
    """Build a standardized error response."""
    return {
        "endpoint_name": endpoint_name,
        "method": method,
        "url": url,
        "status_code": 0,
        "response_body": "",
        "passed": False,
        "error": error,
        "latency_ms": 0,
    }
