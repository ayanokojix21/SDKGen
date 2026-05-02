"""
Researcher Agent — Upgraded with RAG, Nomic, Cohere, and Serper.
"""

import logging
from typing import List, Optional
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage

from backend.llm import get_structured_llm, get_llm
from backend.graph.schemas import CrawlPlan, KnowledgeBaseSummary
from backend.tools.scrape_web import scrape_web
from backend.tools.select_pages import select_pages_to_crawl
from backend.tools.research_tools import chunk_and_index, serper_search

logger = logging.getLogger(__name__)

RESEARCHER_PROMPT = """
You are a Lead Researcher. Your job is to build a structured Knowledge Base summary for an API.
You have access to scraped page content that has been indexed into a vector store.
Your goal is to extract the core API name, base URL, and Authentication scheme.
"""

async def researcher_node(state: dict) -> dict:
    """
    Researcher node updated for Vector Search and Serper.
    """
    job_id = state["job_id"]
    collection_name = f"job_{job_id}"
    supervisor_instruction = _get_last_supervisor_instruction(state.get("messages", []))
    is_recrawl = state.get("vector_store_collection") is not None

    sse_events = []
    
    # ── Phase 1: Select Pages ───────────────────────────────────────────
    goal = supervisor_instruction or "Build complete knowledge base for SDK generation"
    
    sse_events.append({"type": "researcher_analysing", "goal": goal})
    
    already_crawled = [p["url"] for p in state.get("crawled_pages", [])] if is_recrawl else []
    
    plan: CrawlPlan = await select_pages_to_crawl(
        links=state["page_links"],
        landing_content=state["page_content"],
        goal=goal,
        already_crawled=already_crawled
    )
    
    sse_events.append({
        "type": "researcher_crawl_plan",
        "selected": [{"url": p.url, "reason": p.reason} for p in plan.crawl_plan],
        "skipped_count": len(plan.skipped)
    })

    # ── Phase 2: Scrape & Index (Vector DB) ─────────────────────────────
    scraped_this_run = []
    for p in sorted(plan.crawl_plan, key=lambda x: x.priority):
        sse_events.append({"type": "researcher_scraping", "url": p.url})
        
        result = await scrape_web(p.url, state)
        if "error" in result:
            continue
            
        # Index into MongoDB Atlas via Nomic
        await chunk_and_index(p.url, result["content"], collection_name)
        
        scraped_this_run.append({"url": p.url, "scraped_at": "now"})
        sse_events.append({"type": "researcher_scraped", "url": p.url, "char_count": result["char_count"]})

    import re
    # ── Optional: Serper Search (if instruction looks like it needs live data) ──
    if supervisor_instruction and re.search(r'\b(latest|search)\b', supervisor_instruction.lower()):
        sse_events.append({"type": "researcher_serper", "query": supervisor_instruction})
        search_result = await serper_search(supervisor_instruction)
        await chunk_and_index("google_search", search_result, collection_name)

    # ── Phase 3: Knowledge Base Summary (Structured) ────────────────────
    # We use a summary node to tell the Supervisor what we found
    structured_llm = get_structured_llm(KnowledgeBaseSummary)
    
    # In a real RAG, we'd query the Vector Store here to build the summary.
    # For now, we'll use the landing page + a hint that data is indexed.
    summary_msg = f"API Landing Content: {state['page_content'][:3000]}\n\nData for {len(scraped_this_run)} pages has been indexed into collection {collection_name}."
    
    summary: KnowledgeBaseSummary = await structured_llm.ainvoke([
        SystemMessage(content=RESEARCHER_PROMPT),
        HumanMessage(content=summary_msg)
    ])

    # ── Emit researcher_done summary ───────────────────────────────────────
    sse_events.append({
        "type": "researcher_done",
        "endpoint_count": "?",  # Not yet known; architect determines this
        "page_count": len(scraped_this_run) + len(already_crawled),
    })

    return {
        "vector_store_collection": collection_name,
        "research_summary": summary.model_dump_json(),
        "crawled_pages": (state.get("crawled_pages") or []) + scraped_this_run,
        "messages": [AIMessage(content=f"Research complete for {summary.api_name}. Data indexed in Vector Store.", name="researcher")],
        "sse_events": sse_events
    }

def _get_last_supervisor_instruction(messages: list) -> str | None:
    for msg in reversed(messages):
        if hasattr(msg, "name") and msg.name == "supervisor":
            return msg.content.split(":", 1)[1].strip() if ":" in msg.content else msg.content
    return None
