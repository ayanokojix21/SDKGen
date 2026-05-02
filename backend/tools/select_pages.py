"""
LLM Crawl Planner tool for the Researcher agent.
Sends landing page links to Gemini Flash, which decides
which pages are worth crawling for SDK generation.
This is the key innovation — no heuristics, no keyword matching.
"""

import json
import os
import logging
from pathlib import Path
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

# Load the prompt template once at module level
_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "select_pages.txt"
_SELECT_PAGES_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")


async def select_pages_to_crawl(
    links: list[dict],
    landing_content: str,
    goal: str,
    already_crawled: list[str] | None = None,
) -> dict:
    """
    Sends landing page links to the LLM for crawl plan selection.

    Args:
        links: List of dicts with keys: text, href, inNav.
        landing_content: First ~3000 chars of the landing page text.
        goal: What we're trying to achieve (e.g. "Build complete SDK"
              or a targeted re-crawl instruction from Supervisor).
        already_crawled: URLs already scraped — exclude from plan.

    Returns:
        dict with keys:
          - crawl_plan: list of {url, reason, priority}
          - skipped: list of {url, reason}
          - notes: str
    """
    if not links:
        logger.warning("No links provided to select_pages_to_crawl")
        return _empty_plan("No links available to select from.")

    # Build the already-crawled context for re-crawl scenarios
    already_crawled_text = ""
    if already_crawled:
        urls = "\n".join(f"  - {url}" for url in already_crawled)
        already_crawled_text = f"\nALREADY_CRAWLED (do NOT re-select these):\n{urls}\n"

    # Prepare the user message with all context
    user_message = f"""GOAL: {goal}

LANDING PAGE CONTENT (first 3000 chars):
{landing_content[:3000]}
{already_crawled_text}
AVAILABLE LINKS:
{json.dumps(links, indent=2)}"""

    try:
        # Use Gemini Flash — fast and cheap for this classification task
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            temperature=0.1,  # Low temp for consistent structured output
        )

        response = await llm.ainvoke([
            SystemMessage(content=_SELECT_PAGES_PROMPT),
            HumanMessage(content=user_message),
        ])

        # Parse the JSON response
        result = _parse_llm_response(response.content)

        # Filter out already-crawled URLs from the plan
        if already_crawled:
            crawled_set = {url.rstrip("/").lower() for url in already_crawled}
            result["crawl_plan"] = [
                p for p in result["crawl_plan"]
                if p["url"].rstrip("/").lower() not in crawled_set
            ]

        # ── Edge case R1: LLM selected 0 pages ───────────────────────────
        if not result["crawl_plan"]:
            logger.warning("LLM selected 0 pages — falling back to nav links")
            result = _fallback_to_nav_links(links, already_crawled)

        return result

    except Exception as e:
        logger.error(f"LLM crawl planning failed: {e}")
        # Fallback: return navigation-level links
        return _fallback_to_nav_links(links, already_crawled)


def _parse_llm_response(content: str) -> dict:
    """
    Parse the LLM's JSON response, handling common formatting issues.
    """
    # Strip markdown code fences if present
    text = content.strip()
    if text.startswith("```"):
        # Remove opening fence (```json or ```)
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse LLM response as JSON: {text[:200]}...")
        raise

    # Validate structure
    if "crawl_plan" not in result:
        result["crawl_plan"] = []
    if "skipped" not in result:
        result["skipped"] = []
    if "notes" not in result:
        result["notes"] = ""

    # Validate each entry in crawl_plan has required fields
    valid_plan = []
    for i, entry in enumerate(result["crawl_plan"]):
        if isinstance(entry, dict) and "url" in entry:
            entry.setdefault("reason", "Selected for SDK generation")
            entry.setdefault("priority", i + 1)
            valid_plan.append(entry)
    result["crawl_plan"] = valid_plan

    return result


def _fallback_to_nav_links(
    links: list[dict],
    already_crawled: list[str] | None = None,
) -> dict:
    """
    Fallback: return all navigation-level links (inNav=True), max 5.
    Used when LLM returns 0 pages or fails entirely.
    """
    crawled_set = set()
    if already_crawled:
        crawled_set = {url.rstrip("/").lower() for url in already_crawled}

    # Prefer nav links, then any links
    nav_links = [l for l in links if l.get("inNav", False)]
    candidates = nav_links if nav_links else links

    plan = []
    for i, link in enumerate(candidates):
        href = link.get("href", "")
        if href.rstrip("/").lower() in crawled_set:
            continue
        plan.append({
            "url": href,
            "reason": f"Fallback: navigation link '{link.get('text', '')}'",
            "priority": i + 1,
        })
        if len(plan) >= 5:
            break

    return {
        "crawl_plan": plan,
        "skipped": [],
        "notes": "Using fallback — LLM page selection returned no results.",
    }


def _empty_plan(notes: str) -> dict:
    """Return an empty crawl plan with a note."""
    return {
        "crawl_plan": [],
        "skipped": [],
        "notes": notes,
    }
