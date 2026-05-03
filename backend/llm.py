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
    "google/gemma-4-31b-it": {"input": 0.00, "output": 0.00},  # Self-hosted
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79},
    "openai/gpt-oss-120b": {"input": 0.59, "output": 0.79},
    "qwen/qwen3-32b": {"input": 0.59, "output": 0.79},
    "meta-llama/llama-4-scout-17b-16e-instruct": {"input": 0.05, "output": 0.08},
    "llama-3.1-8b-instant": {"input": 0.05, "output": 0.08},
    "openai/gpt-oss-20b": {"input": 0.05, "output": 0.08},
}


class TokenTrackingCallback(AsyncCallbackHandler):
    """
    Callback handler to track token usage and estimated cost.
    Aggregates across all LLM calls within a generation run.
    """
    def __init__(self):
        self.total_tokens = 0
        self.total_cost_usd = 0.0

    async def on_chat_model_start(self, *args, **kwargs) -> None:
        """Required by LangChain — no-op for tracking."""

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


def _build_gemma_llm(temperature: float = 0.0, callbacks: Optional[list] = None):
    """Build the self-deployed Gemma 4 LLM (Vertex AI Model Garden)."""
    from backend.llm_gemma import ChatGemmaVertexAI

    return ChatGemmaVertexAI(
        project=settings.GEMMA_PROJECT,
        location=settings.GEMMA_LOCATION,
        endpoint_id=settings.GEMMA_ENDPOINT_ID,
        dedicated_dns=settings.GEMMA_DEDICATED_DNS,
        model_name=settings.GEMMA_MODEL_NAME,
        temperature=temperature,
        max_tokens=4096,
        callbacks=callbacks or [],
    )


def get_llm(temperature: float = 0.0, callbacks: Optional[list] = None):
    """
    Returns the primary LLM with fallbacks.
    Priority:
      1. Groq (llama-3.3-70b-versatile) — fast, reliable native tool calling
      2. Self-deployed Gemma 4 (Vertex AI) — fallback
      3. Gemini (gemini-2.0-flash) — Google AI Studio fallback
    """
    cbs = [_token_tracker]
    if callbacks:
        cbs.extend(callbacks)

    models = []
    groq_instances = []

    # 1. Primary: Groq models (fast, reliable, native tool calling)
    if settings.GROQ_API_KEY:
        groq_models = [
            "llama-3.3-70b-versatile",
            "meta-llama/llama-4-scout-17b-16e-instruct",
            "qwen/qwen3-32b",
            "llama-3.1-8b-instant",
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
        ]
        for model_name in groq_models:
            groq_instances.append(
                ChatGroq(
                    model=model_name,
                    api_key=settings.GROQ_API_KEY,
                    temperature=temperature,
                    max_retries=2,
                    callbacks=cbs,
                )
            )
        log.info("[llm] Groq (llama-3.3-70b) added as primary LLM")
        
        # Round-robin: 5 full cycles of all Groq models
        for _ in range(5):
            models.extend(groq_instances)

    # 2. Fallback: Self-deployed Gemma 4
    if settings.GEMMA_ENDPOINT_ID:
        try:
            models.append(_build_gemma_llm(temperature, cbs))
            log.info("[llm] Gemma 4 (Vertex AI) added as fallback LLM")
        except Exception as e:
            log.warning("[llm] Failed to init Gemma 4: %s — skipping", e)

    # 3. Fallback: Gemini
    if settings.GOOGLE_API_KEY:
        models.append(
            ChatGoogleGenerativeAI(
                model=settings.GEMINI_MODEL,
                google_api_key=settings.GOOGLE_API_KEY,
                temperature=temperature,
                max_retries=0,
            )
        )

    if not models:
        raise EnvironmentError(
            "No LLM configured. Set GROQ_API_KEY, GEMMA_ENDPOINT_ID, or GOOGLE_API_KEY."
        )

    primary = models[0]
    fallbacks = models[1:]
    return primary.with_fallbacks(fallbacks) if fallbacks else primary


def get_structured_llm(schema: Type[BaseModel], temperature: float = 0.0):
    """
    Returns an LLM chain that outputs a Pydantic object.
    Each model in the fallback chain has structured output applied individually,
    so fallbacks also return properly typed Pydantic objects.

    Groq uses native tool calling via with_structured_output() — most reliable.
    Gemma 4 uses JSON prompt injection — less reliable, used as fallback.
    """
    cbs = [_token_tracker]
    structured_models = []
    groq_structured_instances = []

    # 1. Primary: Groq models (native tool calling — MOST RELIABLE for structured output)
    if settings.GROQ_API_KEY:
        groq_models = [
            "llama-3.3-70b-versatile",
            "meta-llama/llama-4-scout-17b-16e-instruct",
            "qwen/qwen3-32b",
            "llama-3.1-8b-instant",
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
        ]
        for model_name in groq_models:
            llm = ChatGroq(
                model=model_name,
                api_key=settings.GROQ_API_KEY,
                temperature=temperature,
                max_retries=2,
                callbacks=cbs,
            )
            groq_structured_instances.append(llm.with_structured_output(schema))
        log.info("[llm] Groq structured output added as primary")
        
        # Round-robin: 5 full cycles of all Groq structured models
        for _ in range(5):
            structured_models.extend(groq_structured_instances)

    # 2. Fallback: Self-deployed Gemma 4 (JSON prompt injection)
    if settings.GEMMA_ENDPOINT_ID:
        try:
            gemma = _build_gemma_llm(temperature, cbs)
            structured_models.append(gemma.with_structured_output(schema))
            log.info("[llm] Gemma 4 structured output added as fallback")
        except Exception as e:
            log.warning("[llm] Failed to init Gemma 4 structured: %s — skipping", e)

    # 3. Fallback: Gemini (native tool calling)
    if settings.GOOGLE_API_KEY:
        gemini = ChatGoogleGenerativeAI(
            model=settings.GEMINI_MODEL,
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=temperature,
            max_retries=0,
        )
        structured_models.append(gemini.with_structured_output(schema))

    if not structured_models:
        raise EnvironmentError(
            "No LLM configured for structured output. "
            "Set GROQ_API_KEY, GEMMA_ENDPOINT_ID, or GOOGLE_API_KEY."
        )

    primary = structured_models[0]
    fallbacks = structured_models[1:]
    return primary.with_fallbacks(fallbacks) if fallbacks else primary
