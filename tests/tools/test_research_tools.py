"""Tests for backend/tools/research_tools.py."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from langchain_core.documents import Document


@pytest.mark.asyncio
@patch("backend.tools.research_tools.get_vector_store")
@patch("backend.tools.research_tools.CohereRerank")
@patch("backend.tools.research_tools.ContextualCompressionRetriever")
async def test_query_docs_with_rerank(mock_ccr, mock_rerank, mock_get_vs, monkeypatch):
    """Test query_docs with Cohere reranking enabled."""
    monkeypatch.setenv("COHERE_API_KEY", "mock_key")

    # Mock vector store and retriever
    mock_vs = MagicMock()
    mock_retriever = MagicMock()
    mock_vs.as_retriever.return_value = mock_retriever
    mock_get_vs.return_value = mock_vs

    # Mock the compression retriever
    mock_compression = MagicMock()
    mock_compression.ainvoke = AsyncMock(return_value=[
        Document(page_content="Doc 1", metadata={"source": "url1"}),
        Document(page_content="Doc 2", metadata={"source": "url2"}),
    ])
    mock_ccr.return_value = mock_compression

    from backend.tools.research_tools import query_docs
    docs = await query_docs("test query", "test_collection", k=5)

    assert len(docs) == 2
    assert docs[0].page_content == "Doc 1"
    mock_compression.ainvoke.assert_called_once_with("test query")


@pytest.mark.asyncio
@patch("backend.tools.research_tools.get_vector_store")
async def test_query_docs_without_cohere(mock_get_vs, monkeypatch):
    """Test query_docs falls back when COHERE_API_KEY is missing."""
    monkeypatch.delenv("COHERE_API_KEY", raising=False)

    mock_vs = MagicMock()
    mock_base_retriever = MagicMock()
    mock_base_retriever.ainvoke = AsyncMock(return_value=[
        Document(page_content="Fallback doc", metadata={"source": "url"}),
    ])
    mock_vs.as_retriever.return_value = mock_base_retriever
    mock_get_vs.return_value = mock_vs

    from backend.tools.research_tools import query_docs
    docs = await query_docs("test query", "test_collection")

    assert len(docs) == 1
    assert docs[0].page_content == "Fallback doc"


@pytest.mark.asyncio
@patch("backend.tools.research_tools.GoogleSerperAPIWrapper")
async def test_serper_search(mock_wrapper_cls, monkeypatch):
    """Test web search via Serper."""
    monkeypatch.setenv("SERPER_API_KEY", "mock_key")

    mock_instance = MagicMock()
    mock_instance.aresults = AsyncMock(return_value={"organic": [{"snippet": "Search results"}]})
    mock_wrapper_cls.return_value = mock_instance

    from backend.tools.research_tools import serper_search
    result = await serper_search("API documentation")

    assert result == "Search results"
    mock_instance.aresults.assert_called_once_with("API documentation")


@pytest.mark.asyncio
async def test_serper_search_no_key(monkeypatch):
    """Test serper_search when API key is missing."""
    monkeypatch.delenv("SERPER_API_KEY", raising=False)

    from backend.tools.research_tools import serper_search
    result = await serper_search("test")

    assert "missing" in result.lower()
