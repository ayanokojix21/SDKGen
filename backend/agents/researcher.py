"""
Researcher Agent — LLM-Guided Selective Crawling.

The most complex agent in the system. Handles three distinct scenarios:
  1. First crawl — full Phase 1 (LLM selection) + Phase 2 (scraping) + Phase 3 (knowledge base build)
  2. Targeted re-crawl — Supervisor sends specific instruction after QA failure
  3. Merging new findings into existing knowledge base

This agent directly determines the quality of everything downstream:
schema, SDK, and test accuracy all depend on clean, complete research.
"""

import re
import json
import logging
from pathlib import Path
from langchain_core.messages import AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from backend.tools.scrape_web import scrape_web
from backend.tools.select_pages import select_pages_to_crawl

logger = logging.getLogger(__name__)

# Load prompts once at module level
_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "researcher.txt"
_RESEARCHER_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")


async def researcher_node(state: dict) -> dict:
    """
    Researcher agent node for the LangGraph graph.

    Detects whether this is a first crawl or a re-crawl, then executes
    the appropriate phases. Returns updated state dict.
    """
    is_recrawl = state.get("knowledge_base") is not None
    supervisor_instruction = _get_last_supervisor_instruction(state.get("messages", []))

    sse_events = []
    messages = []

    if is_recrawl:
        # ── TARGETED RE-CRAWL ─────────────────────────────────────────────
        goal = supervisor_instruction or "Find missing API documentation"
        sse_events.append({
            "type": "researcher_recrawl",
            "reason": goal,
        })
        logger.info(f"Researcher: targeted re-crawl — {goal}")

        result = await _run_phases(
            state=state,
            goal=goal,
            is_recrawl=True,
            sse_events=sse_events,
        )
    else:
        # ── FIRST CRAWL ──────────────────────────────────────────────────
        goal = "Find all pages needed to generate a complete, correct SDK"
        logger.info("Researcher: first crawl")

        result = await _run_phases(
            state=state,
            goal=goal,
            is_recrawl=False,
            sse_events=sse_events,
        )

    # Build completion message for Supervisor
    kb = result.get("knowledge_base")
    if kb:
        endpoint_count = len(kb.get("endpoints_raw", []))
        page_count = len(kb.get("pages_crawled", []))
        summary = (
            f"Knowledge base {'updated' if is_recrawl else 'complete'}. "
            f"{endpoint_count} endpoints found across {page_count} pages. "
            f"Auth: {kb.get('auth', {}).get('type', 'unknown')}."
        )
    else:
        summary = "Research completed but could not build knowledge base."

    messages.append(AIMessage(content=summary, name="researcher"))

    return {
        "crawl_plan": result.get("crawl_plan", state.get("crawl_plan")),
        "crawled_pages": result.get("crawled_pages", state.get("crawled_pages")),
        "knowledge_base": result.get("knowledge_base", state.get("knowledge_base")),
        "messages": messages,
        "sse_events": sse_events,
    }


async def _run_phases(
    state: dict,
    goal: str,
    is_recrawl: bool,
    sse_events: list,
) -> dict:
    """
    Execute the 3 research phases:
      Phase 1 — LLM page selection
      Phase 2 — Targeted scraping
      Phase 3 — Knowledge base build / merge
    """
    page_links = state.get("page_links", [])
    page_content = state.get("page_content", "")
    existing_crawled = state.get("crawled_pages") or []
    existing_kb = state.get("knowledge_base")

    # ── Edge case R8: page_links is empty ─────────────────────────────────
    if not page_links:
        logger.warning("No page_links — extracting links from page_content via regex")
        page_links = _extract_links_from_content(page_content, state.get("target_url", ""))
        sse_events.append({
            "type": "agent_warn",
            "message": "No links from Chrome — extracting from page content",
        })

    # ══════════════════════════════════════════════════════════════════════
    # PHASE 1 — LLM Page Selection
    # ══════════════════════════════════════════════════════════════════════
    sse_events.append({
        "type": "researcher_analysing",
        "link_count": len(page_links),
    })

    already_crawled_urls = [p["url"] for p in existing_crawled] if is_recrawl else None

    crawl_plan_result = await select_pages_to_crawl(
        links=page_links,
        landing_content=page_content,
        goal=goal,
        already_crawled=already_crawled_urls,
    )

    crawl_plan = crawl_plan_result.get("crawl_plan", [])
    skipped = crawl_plan_result.get("skipped", [])

    sse_events.append({
        "type": "researcher_crawl_plan",
        "selected": [
            {"url": p["url"], "reason": p["reason"], "priority": p["priority"]}
            for p in crawl_plan
        ],
        "skipped_count": len(skipped),
    })

    logger.info(f"Researcher Phase 1: {len(crawl_plan)} selected, {len(skipped)} skipped")

    # ══════════════════════════════════════════════════════════════════════
    # PHASE 2 — Targeted Scraping
    # ══════════════════════════════════════════════════════════════════════
    scraped_pages = []
    already_crawled_set = {
        p["url"].rstrip("/").lower() for p in existing_crawled
    }

    for page_info in sorted(crawl_plan, key=lambda x: x.get("priority", 99)):
        url = page_info["url"]

        # Skip pages we've already scraped
        if url.rstrip("/").lower() in already_crawled_set:
            logger.info(f"Skipping already-crawled: {url}")
            continue

        sse_events.append({
            "type": "researcher_scraping",
            "url": url,
            "reason": page_info.get("reason", ""),
        })

        result = await scrape_web(url, state)

        # Handle errors — skip but continue
        if "error" in result:
            error = result["error"]
            logger.warning(f"Scrape error for {url}: {error}")
            sse_events.append({
                "type": "agent_warn",
                "message": f"Skipped {url}: {error}",
            })
            continue

        scraped_pages.append({
            "url": url,
            "content": result["content"],
        })

        sse_events.append({
            "type": "researcher_scraped",
            "url": url,
            "char_count": result["char_count"],
        })

        logger.info(f"Researcher Phase 2: scraped {url} ({result['char_count']} chars)")

    # Combine with existing crawled pages
    all_crawled = existing_crawled + scraped_pages

    # ══════════════════════════════════════════════════════════════════════
    # PHASE 3 — Knowledge Base Build / Merge
    # ══════════════════════════════════════════════════════════════════════
    if not scraped_pages and not existing_kb:
        # Nothing scraped and no existing KB — use landing page content
        logger.warning("No pages scraped — using landing page content for KB")
        scraped_pages = [{
            "url": state.get("target_url", ""),
            "content": page_content,
        }]

    if is_recrawl and existing_kb:
        # Merge new content into existing knowledge base
        knowledge_base = await _merge_knowledge_base(existing_kb, scraped_pages)
    else:
        # Build fresh knowledge base from all scraped content
        knowledge_base = await _build_knowledge_base(scraped_pages)

    if knowledge_base:
        endpoint_count = len(knowledge_base.get("endpoints_raw", []))
        page_count = len(knowledge_base.get("pages_crawled", []))
        sse_events.append({
            "type": "researcher_done",
            "endpoint_count": endpoint_count,
            "page_count": page_count,
        })
    else:
        sse_events.append({
            "type": "agent_warn",
            "message": "Failed to build knowledge base from scraped content",
        })

    return {
        "crawl_plan": crawl_plan,
        "crawled_pages": all_crawled,
        "knowledge_base": knowledge_base,
    }


async def _build_knowledge_base(scraped_pages: list[dict]) -> dict | None:
    """
    Call Gemini Pro with all scraped content to build a structured knowledge base.
    """
    if not scraped_pages:
        return None

    # Combine all scraped content into a single context
    pages_text = ""
    for page in scraped_pages:
        pages_text += f"\n\n--- PAGE: {page['url']} ---\n{page['content']}\n"

    try:
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            temperature=0.1,
        )

        response = await llm.ainvoke([
            SystemMessage(content=_RESEARCHER_PROMPT),
            HumanMessage(content=f"Build the knowledge base from these pages:\n{pages_text}"),
        ])

        return _parse_knowledge_base(response.content)

    except Exception as e:
        logger.error(f"Failed to build knowledge base: {e}")
        return None


async def _merge_knowledge_base(
    existing_kb: dict,
    new_pages: list[dict],
) -> dict | None:
    """
    Merge new page content into an existing knowledge base.
    """
    if not new_pages:
        return existing_kb

    pages_text = ""
    for page in new_pages:
        pages_text += f"\n\n--- NEW PAGE: {page['url']} ---\n{page['content']}\n"

    merge_prompt = (
        f"{_RESEARCHER_PROMPT}\n\n"
        f"EXISTING KNOWLEDGE BASE (merge new findings into this):\n"
        f"{json.dumps(existing_kb, indent=2)}\n\n"
        f"NEW PAGE CONTENT TO MERGE:\n{pages_text}"
    )

    try:
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            temperature=0.1,
        )

        response = await llm.ainvoke([
            SystemMessage(content="You are merging new API documentation into an existing knowledge base."),
            HumanMessage(content=merge_prompt),
        ])

        return _parse_knowledge_base(response.content)

    except Exception as e:
        logger.error(f"Failed to merge knowledge base: {e}")
        return existing_kb  # Return existing KB on failure


def _parse_knowledge_base(content: str) -> dict | None:
    """Parse LLM response into a knowledge base dict."""
    text = content.strip()

    # Strip markdown fences
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        kb = json.loads(text)
    except json.JSONDecodeError:
        logger.error(f"Failed to parse knowledge base JSON: {text[:300]}...")
        return None

    # Validate required fields
    if "endpoints_raw" not in kb:
        kb["endpoints_raw"] = []
    if "base_url" not in kb:
        kb["base_url"] = ""
    if "auth" not in kb:
        kb["auth"] = {"type": "none", "location": "header", "key_name": "", "example": ""}
    if "pages_crawled" not in kb:
        kb["pages_crawled"] = []
    if "api_name" not in kb:
        kb["api_name"] = "Unknown API"

    return kb


def _get_last_supervisor_instruction(messages: list) -> str | None:
    """Extract the last supervisor instruction from message history."""
    for msg in reversed(messages):
        if hasattr(msg, "name") and msg.name == "supervisor":
            content = msg.content
            # Supervisor messages are like: "Routing to researcher: <instruction>"
            if ":" in content:
                return content.split(":", 1)[1].strip()
            return content
    return None


def _extract_links_from_content(content: str, base_url: str) -> list[dict]:
    """
    Edge case R8: Extract links from page content via regex when
    page_links list is empty (Chrome injection didn't capture links).
    """
    # Find URLs in the text
    url_pattern = r'https?://[^\s<>"\')\]]+' 
    urls = re.findall(url_pattern, content)

    # Deduplicate and filter
    seen = set()
    links = []
    for url in urls:
        url = url.rstrip(".,;:)")
        if url in seen:
            continue
        seen.add(url)
        # Only include links that look like they could be doc pages
        if any(skip in url.lower() for skip in ["twitter.com", "github.com/issues", "facebook.com", "linkedin.com"]):
            continue
        links.append({
            "text": url.split("/")[-1] or url,
            "href": url,
            "inNav": False,
        })

    return links[:50]  # Cap at 50
