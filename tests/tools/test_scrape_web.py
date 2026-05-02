"""Tests for backend/tools/scrape_web.py."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from backend.tools.scrape_web import scrape_web, _urls_match, _clean_text


def test_urls_match():
    assert _urls_match("https://example.com", "http://example.com") is True
    assert _urls_match("https://example.com/", "https://example.com") is True
    assert _urls_match("https://A.com/path", "https://a.com/path") is True
    assert _urls_match("https://a.com", "https://b.com") is False


def test_clean_text():
    text = "Hello\n\n\n\n\nWorld    Extra"
    cleaned = _clean_text(text)
    assert "\n\n\n" not in cleaned
    assert "    " not in cleaned


@pytest.mark.asyncio
async def test_scrape_web_landing_fast_path():
    """Test that landing page uses Chrome-injected content."""
    state = {
        "target_url": "https://api.example.com",
        "page_content": "A" * 500,  # > 300 chars
    }
    result = await scrape_web("https://api.example.com", state)
    assert result["source"] == "chrome_injection"
    assert result["char_count"] > 0


@pytest.mark.asyncio
async def test_scrape_web_landing_too_short():
    """Test that short landing content falls through to Playwright."""
    state = {
        "target_url": "https://api.example.com",
        "page_content": "short",  # < 300 chars
    }

    with patch("backend.tools.scrape_web._playwright_scrape", new_callable=AsyncMock) as mock_pw:
        mock_pw.return_value = {"url": "https://api.example.com", "content": "scraped content", "source": "playwright", "char_count": 50}
        result = await scrape_web("https://api.example.com", state)

    assert result["source"] == "playwright"
    mock_pw.assert_called_once()


@pytest.mark.asyncio
async def test_scrape_web_subpage():
    """Test that sub-pages always go through Playwright."""
    state = {
        "target_url": "https://api.example.com",
        "page_content": "A" * 500,
    }

    with patch("backend.tools.scrape_web._playwright_scrape", new_callable=AsyncMock) as mock_pw:
        mock_pw.return_value = {"url": "https://api.example.com/docs", "content": "docs page", "source": "playwright", "char_count": 30}
        result = await scrape_web("https://api.example.com/docs", state)

    assert result["source"] == "playwright"
    mock_pw.assert_called_once_with("https://api.example.com/docs")
