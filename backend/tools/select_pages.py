import logging
from typing import List, Optional
from langchain_core.messages import SystemMessage, HumanMessage
from backend.llm import get_structured_llm
from backend.graph.schemas import CrawlPlan

logger = logging.getLogger(__name__)

SELECT_PAGES_PROMPT = """
You are an expert documentation analyst. Your goal is to select the most relevant pages to crawl for generating a complete SDK.

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
"""

async def select_pages_to_crawl(
    links: List[dict],
    landing_content: str,
    goal: str,
    already_crawled: Optional[List[str]] = None,
) -> CrawlPlan:
    """
    Sends landing page links to LLM for crawl plan selection using structured output.
    """
    structured_llm = get_structured_llm(CrawlPlan)

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
            SystemMessage(content=SELECT_PAGES_PROMPT),
            HumanMessage(content=human_msg)
        ])
        return result
    except Exception as e:
        logger.error(f"Failed to select pages: {e}")
        # Return empty plan on failure
        return CrawlPlan(crawl_plan=[], skipped=[], notes=f"Error: {str(e)}")
