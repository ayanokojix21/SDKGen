"""
Research Tools — Vector Store operations and live web search.

Provides:
  - chunk_and_index(): Splits content into chunks and stores in MongoDB Atlas.
  - query_docs():      Performs vector search + optional Cohere reranking.
  - serper_search():   Live Google search via Serper.dev.
"""

import asyncio
import logging
import os
from typing import List

from pymongo import MongoClient
from langchain_mongodb import MongoDBAtlasVectorSearch
from langchain_nomic import NomicEmbeddings
from langchain_cohere import CohereRerank
from langchain_classic.retrievers import ContextualCompressionRetriever
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.utilities import GoogleSerperAPIWrapper
from langchain_core.documents import Document

from backend.config import settings

logger = logging.getLogger(__name__)

# ── Singleton MongoClient — reused across all calls to avoid connection leaks ──
_mongo_client: MongoClient | None = None


def _get_mongo_client() -> MongoClient:
    """
    Returns a singleton MongoClient instance.
    Creating a new MongoClient per call was causing connection pool exhaustion
    (BUG 7 — each call opened a new TCP connection that was never closed).
    """
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoClient(settings.MONGODB_URI)
        logger.info("[research_tools] Initialized singleton MongoClient")
    return _mongo_client


def get_vector_store(collection_name: str):
    """
    Returns a MongoDBAtlasVectorSearch instance for a specific job collection.
    Reuses the singleton MongoClient to avoid connection leaks.
    """
    client = _get_mongo_client()
    db = client["sdkgen_research"]
    collection = db[collection_name]

    # Pass the API key explicitly so it doesn't depend on env var casing
    embeddings = NomicEmbeddings(
        model="nomic-embed-text-v1.5",
        nomic_api_key=settings.NOMIC_API_KEY,
    )

    return MongoDBAtlasVectorSearch(
        collection=collection,
        embedding=embeddings,
        index_name="vector_index",  # Must be created in Atlas UI
    )


async def chunk_and_index(url: str, content: str, collection_name: str):
    """
    Splits content into chunks and stores them in MongoDB Atlas.
    Runs synchronous MongoDB/embedding operations in a thread pool to avoid
    blocking the asyncio event loop (BUG 8).
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=100,
        add_start_index=True,
    )

    docs = [Document(page_content=content, metadata={"source": url})]
    chunks = text_splitter.split_documents(docs)

    # Run the synchronous add_documents in a thread to avoid blocking the
    # FastAPI event loop and freezing all active SSE streams.
    vector_store = get_vector_store(collection_name)
    await asyncio.to_thread(vector_store.add_documents, chunks)
    logger.info("Indexed %d chunks for %s", len(chunks), url)


async def query_docs(query: str, collection_name: str, k: int = 100) -> List[Document]:
    """
    Performs vector search + optional Cohere reranking.
    Runs retrieval in a thread pool since the underlying MongoDB call is synchronous.
    """
    vector_store = get_vector_store(collection_name)
    base_retriever = vector_store.as_retriever(search_kwargs={"k": k})

    if not settings.COHERE_API_KEY:
        logger.warning("COHERE_API_KEY missing, skipping rerank")
        return await asyncio.to_thread(base_retriever.invoke, query)

    compressor = CohereRerank(model="rerank-english-v3.0")
    compression_retriever = ContextualCompressionRetriever(
        base_compressor=compressor,
        base_retriever=base_retriever,
    )

    return await asyncio.to_thread(compression_retriever.invoke, query)


async def serper_search(query: str) -> str:
    """
    Performs a live Google search via Serper.dev.
    """
    if not settings.SERPER_API_KEY or settings.SERPER_API_KEY.startswith("your_"):
        return "Serper API key not configured. Cannot perform online research."

    search = GoogleSerperAPIWrapper(serper_api_key=settings.SERPER_API_KEY)
    try:
        results = await search.aresults(query)
        # Safely extract snippets from organic results or answer box
        snippets = []
        if "answerBox" in results and "snippet" in results["answerBox"]:
            snippets.append(results["answerBox"]["snippet"])
        if "organic" in results:
            snippets.extend([
                res.get("snippet", "")
                for res in results["organic"]
                if "snippet" in res
            ])

        if not snippets:
            return "Search completed but no relevant organic snippets were found."

        return "\n\n".join(snippets)
    except Exception as e:
        logger.error("Serper search failed: %s", e)
        return f"Search failed: {str(e)}"
