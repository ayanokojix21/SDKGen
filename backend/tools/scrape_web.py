"""
Playwright-based web scraper tool for the Researcher agent.
Scrapes a single URL and returns clean text content.
Uses Chrome-injected content for the landing page (fast path),
falls back to Playwright for all sub-pages.
"""

import re
import logging
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)


async def scrape_web(url: str, state: dict) -> dict:
    """
    Scrapes a single URL and returns clean text content.

    Args:
        url: The URL to scrape.
        state: The current SDKJobState dict (needs target_url and page_content).

    Returns:
        dict with keys:
          - url (str): The URL that was scraped.
          - content (str): Cleaned text content, max 15000 chars.
          - source (str): 'chrome_injection' | 'playwright'
          - char_count (int): Length of content.
        OR on error:
          - url (str)
          - error (str): 'not_found' | 'login_required' | 'timeout' | 'insufficient_content' | str
          - content (str): Empty string.
          - char_count (int): 0
    """
    # ── Landing page fast path ────────────────────────────────────────────
    # If the URL matches the target and Chrome already sent us good content,
    # skip Playwright entirely.
    target_url = state.get("target_url", "")
    page_content = state.get("page_content", "")

    if _urls_match(url, target_url) and len(page_content) > 300:
        return {
            "url": url,
            "content": page_content[:15000],
            "source": "chrome_injection",
            "char_count": min(len(page_content), 15000),
        }

    # ── Edge case R5: Chrome content too short ────────────────────────────
    # If it's the landing page but content is < 300 chars, fall through
    # to Playwright scraping below.

    # ── Playwright path for sub-pages ─────────────────────────────────────
    return await _playwright_scrape(url)


async def _playwright_scrape(url: str) -> dict:
    """
    Launches headless Chromium, navigates to URL, strips noise elements,
    and returns cleaned text content.
    """
    browser = None
    try:
        p = await async_playwright().start()
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # Navigate with timeout
        response = await page.goto(url, timeout=15000, wait_until="domcontentloaded")

        # ── Check for HTTP errors ─────────────────────────────────────────
        if response and response.status == 404:
            return _error_result(url, "not_found")

        if response and response.status in (401, 403):
            return _error_result(url, "login_required")

        # ── Check for login redirect ──────────────────────────────────────
        final_url = page.url.lower()
        if any(keyword in final_url for keyword in ["/login", "/signin", "/sign-in", "/auth"]):
            if "/auth" in url.lower():
                # The user actually wanted the auth page — don't skip it
                pass
            else:
                return _error_result(url, "login_required")

        # Wait for content to settle
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except PlaywrightTimeout:
            # networkidle can be flaky — proceed with what we have
            pass

        # ── Remove noise elements ─────────────────────────────────────────
        content = await page.evaluate("""() => {
            const selectorsToRemove = [
                'nav', 'header', 'footer', 'script', 'style', 'noscript',
                '.sidebar', '.nav', '.navigation', '.menu', '.header', '.footer',
                '.breadcrumb', '.breadcrumbs', '.cookie-banner', '.cookie-consent',
                '[role="banner"]', '[role="navigation"]', '[role="complementary"]',
                '.ads', '.advertisement', '.social-share', '.comments'
            ];
            selectorsToRemove.forEach(sel => {
                try {
                    document.querySelectorAll(sel).forEach(el => el.remove());
                } catch(e) {}
            });
            return document.body ? document.body.innerText : '';
        }""")

        content = _clean_text(content)

        # ── Edge case R4: insufficient content ────────────────────────────
        if len(content) < 200:
            # Try raw body text as fallback
            raw_content = await page.evaluate(
                "() => document.body ? document.body.innerText : ''"
            )
            raw_content = _clean_text(raw_content)
            if len(raw_content) < 200:
                return _error_result(url, "insufficient_content")
            content = raw_content

        content = content[:15000]

        return {
            "url": url,
            "content": content,
            "source": "playwright",
            "char_count": len(content),
        }

    except PlaywrightTimeout:
        logger.warning(f"Timeout scraping {url}")
        return _error_result(url, "timeout")
    except Exception as e:
        logger.error(f"Error scraping {url}: {e}")
        return _error_result(url, str(e))
    finally:
        if browser:
            await browser.close()


def _urls_match(url1: str, url2: str) -> bool:
    """Compare two URLs ignoring trailing slashes and protocol differences."""
    def normalize(u: str) -> str:
        u = u.rstrip("/").lower()
        u = re.sub(r'^https?://', '', u)
        return u
    return normalize(url1) == normalize(url2)


def _clean_text(text: str) -> str:
    """Remove excessive whitespace and blank lines from scraped text."""
    # Collapse multiple blank lines into one
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Collapse multiple spaces into one
    text = re.sub(r'[ \t]{2,}', ' ', text)
    return text.strip()


def _error_result(url: str, error: str) -> dict:
    """Build a standardized error response."""
    return {
        "url": url,
        "error": error,
        "content": "",
        "char_count": 0,
    }
