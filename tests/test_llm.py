"""Tests for backend/llm.py — LLM initialization and token tracking."""
import pytest
from pydantic import BaseModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult


class DummySchema(BaseModel):
    name: str


def test_get_llm_instantiation(monkeypatch):
    """Test that get_llm returns a valid language model."""
    monkeypatch.setenv("GOOGLE_API_KEY", "test_key")
    # Also patch the cached settings since they're read at import time
    import backend.config
    monkeypatch.setattr(backend.config.settings, "GOOGLE_API_KEY", "test_key")
    monkeypatch.setattr(backend.config.settings, "GROQ_API_KEY", "")

    # Mock the LLM to prevent network calls during initialization
    from unittest.mock import MagicMock
    
    def mock_init(*args, **kwargs):
        mock = MagicMock()
        mock.temperature = kwargs.get("temperature", 0.5)
        mock.callbacks = kwargs.get("callbacks", [])
        return mock
        
    monkeypatch.setattr("backend.llm.ChatGoogleGenerativeAI", mock_init)

    from backend.llm import get_llm, TokenTrackingCallback
    llm = get_llm(temperature=0.5)

    assert llm is not None
    assert llm.temperature == 0.5
    # Callbacks should contain TokenTrackingCallback
    assert llm.callbacks is not None
    assert any(isinstance(cb, TokenTrackingCallback) for cb in llm.callbacks)


def test_get_structured_llm_instantiation(monkeypatch):
    """Test that get_structured_llm binds a schema."""
    monkeypatch.setenv("GOOGLE_API_KEY", "test_key")
    import backend.config
    monkeypatch.setattr(backend.config.settings, "GOOGLE_API_KEY", "test_key")
    monkeypatch.setattr(backend.config.settings, "GROQ_API_KEY", "")

    from unittest.mock import MagicMock
    mock_llm_class = MagicMock()
    mock_llm_class.return_value.with_structured_output.return_value = MagicMock()
    monkeypatch.setattr("backend.llm.ChatGoogleGenerativeAI", mock_llm_class)

    from backend.llm import get_structured_llm
    llm = get_structured_llm(DummySchema)

    assert llm is not None


@pytest.mark.asyncio
async def test_token_tracking_callback():
    """Test that the callback calculates tokens and cost correctly."""
    from backend.llm import TokenTrackingCallback
    callback = TokenTrackingCallback()

    mock_message = AIMessage(
        content="Test response",
        usage_metadata={
            "input_tokens": 1000,
            "output_tokens": 500,
            "total_tokens": 1500,
        },
    )

    gen = ChatGeneration(message=mock_message)
    # LLMResult.generations is List[List[Generation]]
    res = LLMResult(generations=[[gen]])

    await callback.on_llm_end(response=res)

    assert callback.total_tokens == 1500
    # 1000 * 0.10/1M + 500 * 0.40/1M = 0.0001 + 0.0002 = 0.0003
    assert callback.total_cost_usd == pytest.approx(0.0003, abs=1e-6)


@pytest.mark.asyncio
async def test_token_tracking_callback_no_usage():
    """Test that callback handles messages without usage_metadata."""
    from backend.llm import TokenTrackingCallback
    callback = TokenTrackingCallback()

    mock_message = AIMessage(content="No metadata")
    gen = ChatGeneration(message=mock_message)
    res = LLMResult(generations=[[gen]])

    await callback.on_llm_end(response=res)

    assert callback.total_tokens == 0
    assert callback.total_cost_usd == 0.0
