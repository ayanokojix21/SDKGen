import logging
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

from backend.config import settings

log = logging.getLogger(__name__)

def get_llm(temperature: float = 0.0):
    """
    Returns the primary Gemini LLM, configured to fall back to Groq's free models
    (llama-3.3-70b-versatile, llama-3.1-8b-instant, etc.) in a round-robin style
    if Gemini hits rate limits (429 ResourceExhausted).
    """
    
    # Primary model (Gemini)
    primary_llm = ChatGoogleGenerativeAI(
        model=settings.GEMINI_MODEL,
        google_api_key=settings.GOOGLE_API_KEY,
        temperature=temperature,
        max_retries=0, # Fail fast to trigger fallbacks
    )
    
    if not settings.GROQ_API_KEY:
        log.warning("GROQ_API_KEY not set — LLM fallbacks disabled.")
        return primary_llm

    # Fallback models (Groq Free Tier)
    # We list multiple models in order of preference. LangChain will try them
    # sequentially if the previous one fails (e.g. rate limit).
    groq_models = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "mixtral-8x7b-32768"
    ]
    
    fallbacks = []
    for model_name in groq_models:
        fallback_llm = ChatGroq(
            model=model_name,
            api_key=settings.GROQ_API_KEY,
            temperature=temperature,
            max_retries=0,
        )
        fallbacks.append(fallback_llm)
        
    return primary_llm.with_fallbacks(fallbacks)
