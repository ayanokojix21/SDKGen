"""
Select Pages Tool — Uses LLM to choose the most valuable documentation pages to crawl.
"""

import logging
from pathlib import Path
from typing import List, Optional
from langchain_core.messages import SystemMessage, HumanMessage
from backend.llm import get_structured_llm
from backend.graph.schemas import CrawlPlan

logger = logging.getLogger(__name__)

# ── Load detailed prompt from disk ────────────────────────────────────────────
_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _load_select_pages_prompt() -> str:
    """Load the select_pages prompt file."""
    prompt_path = _PROMPTS_DIR / "select_pages.txt"
    try:
        text = prompt_path.read_text(encoding="utf-8")
        logger.info("[select_pages] Loaded prompt from select_pages.txt (%d chars)", len(text))
        return text
    except FileNotFoundError:
        logger.warning("[select_pages] select_pages.txt not found — using fallback")
        return ""


_SELECT_PAGES_PROMPT_FILE = _load_select_pages_prompt()

_FALLBACK_PROMPT = """
You are an expert documentation analyst. Your goal is to select the most relevant pages to crawl for generating a complete SDK.

HARD LIMIT: Select at most 6 pages. Prefer fewer high-value pages over many low-value ones.

Focus on:
1. Authentication / Getting Started
2. Endpoint Reference / API Reference
3. Error Codes / Rate Limits
4. Data Models / Objects

Ignore:
1. Pricing / Billing
2. Blog / Changelogs
3. Tutorials (unless they are the only source of endpoint info)
4. Legal / Privacy
5. Community, forums, social links
6. Marketing, case studies, testimonials

Prefer pages with "inNav": true — they are primary navigation links.
If a link is a fragment (#section) on the current page, skip it.
"""


async def select_pages_to_crawl(
    links: List[dict],
    landing_content: str,
    goal: str,
    already_crawled: Optional[List[str]] = None,
) -> CrawlPlan:
    """
    Sends landing page links to LLM for crawl plan selection using structured output.
    Now loads the detailed prompt from select_pages.txt.
    """
    structured_llm = get_structured_llm(CrawlPlan)

    # Choose prompt: file prompt or fallback
    prompt_text = _SELECT_PAGES_PROMPT_FILE or _FALLBACK_PROMPT

    # Fill placeholders if loading from .txt file
    prompt_text = (
        prompt_text
        .replace("{goal}", goal)
        .replace("{landing_content}", landing_content[:5000])
        .replace("{links}", str(links))
    )

    human_msg = f"""
GOAL: {goal}
LANDING PAGE CONTENT (first 5000 chars): {landing_content[:5000]}
AVAILABLE LINKS:
{links}
"""
    if already_crawled:
        human_msg += f"\nALREADY CRAWLED (Do not re-select these): {already_crawled}"

    try:
        # returns a CrawlPlan instance
        result: CrawlPlan = await structured_llm.ainvoke([
            SystemMessage(content=prompt_text),
            HumanMessage(content=human_msg)
        ])
        return result
    except Exception as e:
        logger.error(f"Failed to select pages: {e}")
        # Return empty plan on failure
        return CrawlPlan(crawl_plan=[], skipped=[], notes=f"Error: {str(e)}")
