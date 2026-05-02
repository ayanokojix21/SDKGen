"""Tests for backend/agents/researcher.py — researcher_node."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from backend.graph.schemas import CrawlPlan, CrawlPage, KnowledgeBaseSummary, AuthConfig


@pytest.mark.asyncio
@patch("backend.agents.researcher.chunk_and_index", new_callable=AsyncMock)
@patch("backend.agents.researcher.scrape_web", new_callable=AsyncMock)
@patch("backend.agents.researcher.select_pages_to_crawl", new_callable=AsyncMock)
async def test_researcher_node_initial_crawl(mock_select, mock_scrape, mock_chunk, mock_state, mock_structured_llm):
    """Test initial crawl logic."""
    mock_state["vector_store_collection"] = None  # initial run

    mock_select.return_value = CrawlPlan(
        crawl_plan=[CrawlPage(url="https://api.example.com/docs", reason="docs", priority=1)],
        skipped=[],
        notes="Found docs",
    )

    mock_scrape.return_value = {"content": "API documentation", "char_count": 100, "url": "https://api.example.com/docs"}

    mock_structured_llm.ainvoke.return_value = KnowledgeBaseSummary(
        api_name="TestAPI",
        base_url="https://api.example.com",
        auth=AuthConfig(type="none", location="header", key_name="", example=""),
        key_endpoints_summary="GET /users",
    )

    from backend.agents.researcher import researcher_node
    result = await researcher_node(mock_state)

    assert result["vector_store_collection"] == "job_test_job_123"
    assert result["research_summary"] is not None
    assert len(result["messages"]) == 1
    mock_scrape.assert_called_once()
    mock_chunk.assert_called_once()


@pytest.mark.asyncio
@patch("backend.agents.researcher.chunk_and_index", new_callable=AsyncMock)
@patch("backend.agents.researcher.scrape_web", new_callable=AsyncMock)
@patch("backend.agents.researcher.select_pages_to_crawl", new_callable=AsyncMock)
async def test_researcher_handles_scrape_error(mock_select, mock_scrape, mock_chunk, mock_state, mock_structured_llm):
    """Test that researcher skips pages that error during scraping."""
    mock_state["vector_store_collection"] = None

    mock_select.return_value = CrawlPlan(
        crawl_plan=[CrawlPage(url="https://api.example.com/bad", reason="test", priority=1)],
        skipped=[],
        notes="",
    )

    mock_scrape.return_value = {"error": "timeout", "content": "", "char_count": 0, "url": "https://api.example.com/bad"}

    mock_structured_llm.ainvoke.return_value = KnowledgeBaseSummary(
        api_name="TestAPI", base_url="https://api.example.com",
        auth=AuthConfig(type="none", location="header", key_name="", example=""),
        key_endpoints_summary="None found",
    )

    from backend.agents.researcher import researcher_node
    result = await researcher_node(mock_state)

    # chunk_and_index should NOT be called since scrape returned error
    mock_chunk.assert_not_called()
    assert result["vector_store_collection"] == "job_test_job_123"
