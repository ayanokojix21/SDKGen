import logging
from typing import Type, Any, Optional
from pydantic import BaseModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_core.outputs import LLMResult
from langchain_core.callbacks import AsyncCallbackHandler

from backend.config import settings

log = logging.getLogger(__name__)

# Approximate costs per 1M tokens (USD)
COSTS = {
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79},
    "openai/gpt-oss-120b": {"input": 0.59, "output": 0.79},
    "qwen/qwen3-32b": {"input": 0.59, "output": 0.79},
    "meta-llama/llama-4-scout-17b-16e-instruct": {"input": 0.05, "output": 0.08},
    "llama-3.1-8b-instant": {"input": 0.05, "output": 0.08},
}


class TokenTrackingCallback(AsyncCallbackHandler):
    """
    Callback handler to track token usage and estimated cost.
    Aggregates across all LLM calls within a generation run.
    """
    def __init__(self):
        self.total_tokens = 0
        self.total_cost_usd = 0.0

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        for gen_list in response.generations:
            for gen in gen_list if isinstance(gen_list, list) else [gen_list]:
                # ChatGeneration has a .message attribute
                msg = getattr(gen, "message", None)
                if msg is None:
                    continue
                usage = getattr(msg, "usage_metadata", None)
                if usage:
                    input_tokens = usage.get("input_tokens", 0)
                    output_tokens = usage.get("output_tokens", 0)
                    model_name = (response.llm_output or {}).get("model_name", "unknown")

                    self.total_tokens += (input_tokens + output_tokens)

                    cost_config = COSTS.get(model_name, COSTS["gemini-2.0-flash"])
                    self.total_cost_usd += (input_tokens * cost_config["input"] / 1_000_000)
                    self.total_cost_usd += (output_tokens * cost_config["output"] / 1_000_000)


# Module-level callback instance for cost tracking across all calls
_token_tracker = TokenTrackingCallback()


def get_token_usage() -> dict:
    """
    Returns the current accumulated token usage and estimated cost.
    Called by agent nodes to propagate tracking data into the LangGraph state,
    which enables the Supervisor's $2 budget guard to function.
    """
    return {
        "total_tokens": _token_tracker.total_tokens,
        "estimated_cost_usd": round(_token_tracker.total_cost_usd, 6),
    }


def get_llm(temperature: float = 0.0, callbacks: Optional[list] = None):
    """
    Returns the primary LLM with fallbacks.
    Primary: Groq (llama-3.3-70b-versatile) — fast, free tier available.
    Fallback: Gemini (gemini-2.0-flash) — when Groq is unavailable.
    """
    cbs = [_token_tracker]
    if callbacks:
        cbs.extend(callbacks)

    # Primary: Groq
    if settings.GROQ_API_KEY:
        # Best 5 models from GroqCloud in fallback order for resilient execution
        groq_models = [
            "llama-3.3-70b-versatile",
            "openai/gpt-oss-120b",
            "qwen/qwen3-32b",
            "meta-llama/llama-4-scout-17b-16e-instruct",
            "llama-3.1-8b-instant"
        ]

        primary_llm = ChatGroq(
            model=groq_models[0],
            api_key=settings.GROQ_API_KEY,
            temperature=temperature,
            max_retries=1,
            callbacks=cbs,
        )

        fallbacks = []

        # Groq model fallbacks
        for model_name in groq_models[1:]:
            fallbacks.append(
                ChatGroq(
                    model=model_name,
                    api_key=settings.GROQ_API_KEY,
                    temperature=temperature,
                    max_retries=1,
                    callbacks=cbs,  # Track tokens on fallbacks too (BUG 23 fix)
                )
            )

        # Fallback 2: Gemini (if key exists)
        if settings.GOOGLE_API_KEY:
            fallbacks.append(
                ChatGoogleGenerativeAI(
                    model=settings.GEMINI_MODEL,
                    google_api_key=settings.GOOGLE_API_KEY,
                    temperature=temperature,
                    max_retries=0,
                )
            )

        return primary_llm.with_fallbacks(fallbacks) if fallbacks else primary_llm

    # No Groq key — use Gemini as primary (original behavior)
    return ChatGoogleGenerativeAI(
        model=settings.GEMINI_MODEL,
        google_api_key=settings.GOOGLE_API_KEY,
        temperature=temperature,
        max_retries=0,
        callbacks=cbs,
    )


def get_structured_llm(schema: Type[BaseModel], temperature: float = 0.0):
    """
    Returns an LLM chain that outputs a Pydantic object.
    Each model in the fallback chain has structured output applied individually,
    so fallbacks also return properly typed Pydantic objects.
    """
    cbs = [_token_tracker]

    if settings.GROQ_API_KEY:
        groq_models = [
            "llama-3.3-70b-versatile",
            "openai/gpt-oss-120b",
            "qwen/qwen3-32b",
            "meta-llama/llama-4-scout-17b-16e-instruct",
            "llama-3.1-8b-instant",
        ]

        # Build structured LLMs for each Groq model
        structured_models = []
        for i, model_name in enumerate(groq_models):
            llm = ChatGroq(
                model=model_name,
                api_key=settings.GROQ_API_KEY,
                temperature=temperature,
                max_retries=1,
                callbacks=cbs,  
            )
            structured_models.append(llm.with_structured_output(schema))

        # Add Gemini as final fallback if available
        if settings.GOOGLE_API_KEY:
            gemini = ChatGoogleGenerativeAI(
                model=settings.GEMINI_MODEL,
                google_api_key=settings.GOOGLE_API_KEY,
                temperature=temperature,
                max_retries=0,
            )
            structured_models.append(gemini.with_structured_output(schema))

        primary = structured_models[0]
        fallbacks = structured_models[1:]

        return primary.with_fallbacks(fallbacks) if fallbacks else primary

    # No Groq key — use Gemini
    gemini = ChatGoogleGenerativeAI(
        model=settings.GEMINI_MODEL,
        google_api_key=settings.GOOGLE_API_KEY,
        temperature=temperature,
        max_retries=0,
        callbacks=cbs,
    )
    return gemini.with_structured_output(schema)
