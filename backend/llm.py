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


def get_llm(temperature: float = 0.0, callbacks: Optional[list] = None):
    """
    Returns the primary Gemini LLM with Groq fallbacks.
    Injects TokenTrackingCallback by default for cost tracking.
    """
    cbs = [_token_tracker]
    if callbacks:
        cbs.extend(callbacks)

    primary_llm = ChatGoogleGenerativeAI(
        model=settings.GEMINI_MODEL,
        google_api_key=settings.GOOGLE_API_KEY,
        temperature=temperature,
        max_retries=0,
        callbacks=cbs,
    )

    if not settings.GROQ_API_KEY:
        return primary_llm

    groq_models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
    fallbacks = [
        ChatGroq(model=m, api_key=settings.GROQ_API_KEY, temperature=temperature, max_retries=0)
        for m in groq_models
    ]

    return primary_llm.with_fallbacks(fallbacks)


def get_structured_llm(schema: Type[BaseModel], temperature: float = 0.0):
    """
    Returns an LLM chain that outputs a Pydantic object.
    """
    llm = get_llm(temperature=temperature)
    # Gemini 2.0 Flash supports 'json_schema' which is the most reliable
    return llm.with_structured_output(schema, method="json_schema")
