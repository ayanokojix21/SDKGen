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

def get_vector_store(collection_name: str):
    """
    Returns a MongoDBAtlasVectorSearch instance for a specific job collection.
    """
    client = MongoClient(settings.MONGODB_URI)
    db = client["sdkgen_research"]
    collection = db[collection_name]
    
    # Lazy initialization to prevent import crashes if NOMIC_API_KEY is missing
    embeddings = NomicEmbeddings(model="nomic-embed-text-v1.5")
    
    return MongoDBAtlasVectorSearch(
        collection=collection,
        embedding=embeddings,
        index_name="vector_index", # Must be created in Atlas UI
    )

async def chunk_and_index(url: str, content: str, collection_name: str):
    """
    Splits content into chunks and stores them in MongoDB Atlas.
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=100,
        add_start_index=True
    )
    
    docs = [Document(page_content=content, metadata={"source": url})]
    chunks = text_splitter.split_documents(docs)
    
    vector_store = get_vector_store(collection_name)
    vector_store.add_documents(chunks)
    logger.info(f"Indexed {len(chunks)} chunks for {url}")

async def query_docs(query: str, collection_name: str, k: int = 100) -> List[Document]:
    """
    Performs vector search + Cohere reranking.
    """
    vector_store = get_vector_store(collection_name)
    base_retriever = vector_store.as_retriever(search_kwargs={"k": k})
    
    if not os.environ.get("COHERE_API_KEY"):
        logger.warning("COHERE_API_KEY missing, skipping rerank")
        return await base_retriever.ainvoke(query)

    compressor = CohereRerank(model="rerank-english-v3.0")
    compression_retriever = ContextualCompressionRetriever(
        base_compressor=compressor, 
        base_retriever=base_retriever
    )
    
    return await compression_retriever.ainvoke(query)

async def serper_search(query: str) -> str:
    """
    Performs a live Google search via Serper.dev.
    """
    if not os.environ.get("SERPER_API_KEY"):
        return "Serper API key missing. Cannot perform online research."
    
    search = GoogleSerperAPIWrapper()
    try:
        results = await search.aresults(query)
        # Safely extract snippets from organic results or answer box
        snippets = []
        if "answerBox" in results and "snippet" in results["answerBox"]:
            snippets.append(results["answerBox"]["snippet"])
        if "organic" in results:
            snippets.extend([res.get("snippet", "") for res in results["organic"] if "snippet" in res])
            
        if not snippets:
            return "Search completed but no relevant organic snippets were found."
            
        return "\n\n".join(snippets)
    except Exception as e:
        logger.error(f"Serper search failed: {e}")
        return f"Search failed: {str(e)}"
