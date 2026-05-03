"""
Researcher Agent — Upgraded with RAG, Nomic, Cohere, and Serper.
"""

import logging
import re
from pathlib import Path
from typing import List, Optional
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage

from backend.llm import get_structured_llm, get_llm, get_token_usage
from backend.graph.schemas import CrawlPlan, KnowledgeBaseSummary
from backend.tools.scrape_web import scrape_web
from backend.tools.select_pages import select_pages_to_crawl
from backend.tools.research_tools import chunk_and_index, serper_search, query_docs

logger = logging.getLogger(__name__)

# ── Load detailed prompt from disk ────────────────────────────────────────────
_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _load_researcher_prompt() -> str:
    """Load the researcher prompt file."""
    prompt_path = _PROMPTS_DIR / "researcher.txt"
    try:
        text = prompt_path.read_text(encoding="utf-8")
        logger.info("[researcher] Loaded prompt from researcher.txt (%d chars)", len(text))
        return text
    except FileNotFoundError:
        logger.warning("[researcher] researcher.txt not found — using fallback")
        return ""


_RESEARCHER_PROMPT_FILE = _load_researcher_prompt()

_FALLBACK_PROMPT = """\
You are a Lead Researcher. Your job is to build a structured Knowledge Base summary for an API.
You have access to documentation content that has been indexed into a vector store.
Your goal is to extract the core API name, base URL, Authentication scheme, and key endpoint summary.

Rules:
1. The base_url MUST be derived from the TARGET_URL provided. Do NOT use placeholder domains.
2. For authentication, identify the type (api_key, bearer, basic, none), where it goes (header, query), and the key name.
3. For key_endpoints_summary, describe the main endpoint categories you found in the documentation.
4. If the documentation is sparse, note that in your summary.
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
    
    # Always index the landing page content first (fast path — no HTTP needed)
    landing_content = state.get("page_content", "")
    target_url = state.get("target_url", "")
    if landing_content and len(landing_content) > 200 and target_url not in already_crawled:
        sse_events.append({"type": "researcher_scraping", "url": target_url})
        await chunk_and_index(target_url, landing_content[:15000], collection_name)
        scraped_this_run = [{"url": target_url, "scraped_at": "now"}]
        already_crawled.append(target_url)
        sse_events.append({"type": "researcher_scraped", "url": target_url, "char_count": len(landing_content[:15000])})
    else:
        scraped_this_run = []

    # Only run select_pages if there are links to choose from
    if state["page_links"]:
        plan: CrawlPlan = await select_pages_to_crawl(
            links=state["page_links"],
            landing_content=landing_content,
            goal=goal,
            already_crawled=already_crawled
        )
        
        sse_events.append({
            "type": "researcher_crawl_plan",
            "selected": [{"url": p.url, "reason": p.reason} for p in plan.crawl_plan],
            "skipped_count": len(plan.skipped)
        })

        # ── Phase 2: Scrape & Index (Vector DB) ─────────────────────────────
        for p in sorted(plan.crawl_plan, key=lambda x: x.priority):
            if p.url in already_crawled:
                logger.info("[researcher] Skipping %s — already crawled", p.url)
                continue
                
            sse_events.append({"type": "researcher_scraping", "url": p.url})
            
            result = await scrape_web(p.url, state)
            if "error" in result:
                continue
                
            await chunk_and_index(p.url, result["content"], collection_name)
            
            scraped_this_run.append({"url": p.url, "scraped_at": "now"})
            already_crawled.append(p.url)
            sse_events.append({"type": "researcher_scraped", "url": p.url, "char_count": result["char_count"]})
    else:
        # No page_links — try to scrape the target URL directly via Playwright
        # (this gets the full rendered page, which may have more content than Chrome injection)
        logger.info("[researcher] No page_links provided — scraping target URL directly")
        sse_events.append({
            "type": "researcher_crawl_plan",
            "selected": [{"url": target_url, "reason": "Direct scrape — no navigation links available"}],
            "skipped_count": 0
        })
        if target_url not in already_crawled:
            result = await scrape_web(target_url, state)
            if "error" not in result:
                await chunk_and_index(target_url, result["content"], collection_name)
                scraped_this_run.append({"url": target_url, "scraped_at": "now"})
                already_crawled.append(target_url)
                sse_events.append({"type": "researcher_scraped", "url": target_url, "char_count": result["char_count"]})

    # ── Optional: Serper Search (if instruction looks like it needs live data) ──
    if supervisor_instruction and re.search(r'\b(latest|search)\b', supervisor_instruction.lower()):
        sse_events.append({"type": "researcher_serper", "query": supervisor_instruction})
        search_result = await serper_search(supervisor_instruction)
        await chunk_and_index("google_search", search_result, collection_name)

    # ── Phase 3: Knowledge Base Summary (Structured) ────────────────────
    # BUG 11 fix: Query the Vector Store for relevant context instead of
    # using only the landing page content. This ensures the summary is built
    # from the actual scraped endpoint documentation, not a marketing page.
    structured_llm = get_structured_llm(KnowledgeBaseSummary)
    
    target_url = state.get("target_url", "")
    rag_context = ""
    try:
        docs = await query_docs(
            query="API base URL, authentication, endpoints, and getting started",
            collection_name=collection_name,
            k=20,
        )
        rag_context = "\n\n".join([
            f"SOURCE: {d.metadata.get('source')}\nCONTENT: {d.page_content}"
            for d in docs
        ])
    except Exception as exc:
        logger.warning("[researcher] Vector store query failed, falling back to landing page: %s", exc)
    
    # Fall back to landing page content if RAG returned nothing
    if not rag_context:
        rag_context = f"Landing Page Content:\n{(state.get('page_content') or '')[:5000]}"
        
    prompt_text = _RESEARCHER_PROMPT_FILE or _FALLBACK_PROMPT
    
    # Replace known placeholders if loading from .txt
    prompt_text = (
        prompt_text
        .replace("{target_url}", target_url)
        .replace("{instruction}", supervisor_instruction or "Extract knowledge base")
        .replace("{existing_knowledge_base}", state.get("research_summary") or "None")
    )
    
    summary_msg = (
        f"TARGET_URL: {target_url}\n\n"
        f"DOCUMENTATION CONTEXT (from {len(scraped_this_run)} newly scraped pages + existing index):\n"
        f"{rag_context[:8000]}"
    )
    
    # The .txt file has {crawled_pages} placeholder, we can just replace it or append it
    prompt_text = prompt_text.replace("{crawled_pages}", summary_msg)
    
    summary: KnowledgeBaseSummary = await structured_llm.ainvoke([
        SystemMessage(content=prompt_text),
        HumanMessage(content=summary_msg)
    ])

    # ── Emit researcher_done summary ───────────────────────────────────────
    sse_events.append({
        "type": "researcher_done",
        "endpoint_count": "?",  # Not yet known; architect determines this
        "page_count": len(already_crawled),  # total unique pages crawled across all runs
    })

    # Propagate token tracking to state (BUG 5 fix)
    token_usage = get_token_usage()

    return {
        "vector_store_collection": collection_name,
        "research_summary": summary.model_dump_json(),
        "crawled_pages": (state.get("crawled_pages") or []) + scraped_this_run,
        "messages": [AIMessage(content=f"Research complete for {summary.api_name}. Data indexed in Vector Store.", name="researcher")],
        "sse_events": sse_events,
        **token_usage,
    }

def _get_last_supervisor_instruction(messages: list) -> str | None:
    for msg in reversed(messages):
        if hasattr(msg, "name") and msg.name == "supervisor":
            return msg.content.split(":", 1)[1].strip() if ":" in msg.content else msg.content
    return None
