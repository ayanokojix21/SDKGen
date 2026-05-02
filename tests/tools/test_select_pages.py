"""Tests for backend/tools/select_pages.py."""
import pytest
from unittest.mock import AsyncMock
from backend.graph.schemas import CrawlPlan, CrawlPage


@pytest.mark.asyncio
async def test_select_pages_to_crawl(mock_structured_llm):
    """Test successful page selection."""
    mock_plan = CrawlPlan(
        crawl_plan=[CrawlPage(url="https://api.example.com/docs", reason="API docs", priority=1)],
        skipped=["https://api.example.com/pricing"],
        notes="Found docs",
    )
    mock_structured_llm.ainvoke.return_value = mock_plan

    from backend.tools.select_pages import select_pages_to_crawl
    plan = await select_pages_to_crawl(
        links=[{"text": "API Docs", "href": "https://api.example.com/docs"}],
        landing_content="Welcome to the API",
        goal="Build SDK",
    )

    assert len(plan.crawl_plan) == 1
    assert plan.crawl_plan[0].url == "https://api.example.com/docs"
    mock_structured_llm.ainvoke.assert_called_once()


@pytest.mark.asyncio
async def test_select_pages_with_already_crawled(mock_structured_llm):
    """Test that already_crawled URLs are passed to the LLM."""
    mock_plan = CrawlPlan(crawl_plan=[], skipped=[], notes="All already crawled")
    mock_structured_llm.ainvoke.return_value = mock_plan

    from backend.tools.select_pages import select_pages_to_crawl
    plan = await select_pages_to_crawl(
        links=[{"text": "Docs", "href": "/docs"}],
        landing_content="content",
        goal="Build SDK",
        already_crawled=["https://api.example.com/docs"],
    )

    assert len(plan.crawl_plan) == 0


@pytest.mark.asyncio
async def test_select_pages_error_fallback(mock_structured_llm):
    """Test that errors return an empty CrawlPlan."""
    mock_structured_llm.ainvoke.side_effect = Exception("LLM error")

    from backend.tools.select_pages import select_pages_to_crawl
    plan = await select_pages_to_crawl(
        links=[], landing_content="content", goal="Build SDK",
    )

    assert len(plan.crawl_plan) == 0
    assert "Error" in plan.notes
