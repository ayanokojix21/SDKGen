import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import backend.llm


@pytest.fixture
def mock_state() -> dict:
    """Provides a valid initial state for tests — matches SDKJobState keys."""
    return {
        "job_id": "test_job_123",
        "target_url": "https://api.example.com",
        "language": "python",
        "page_content": "Example API documentation content here",
        "page_links": [{"text": "API Docs", "href": "/docs"}],
        "instruction": "Build an SDK for this API",
        "messages": [],
        "total_tokens": 0,
        "estimated_cost_usd": 0.0,
        "crawl_plan": None,
        "crawled_pages": None,
        "vector_store_collection": "job_test_job_123",
        "research_summary": None,
        "api_schema": None,
        "schema_fixes": [],
        "sdk_files": None,
        "syntax_errors": [],
        "test_results": None,
        "qa_iteration": 0,
        "final_files": None,
        "narration_text": None,
        "next_agent": "supervisor",
        "iteration_count": 0,
        "status": "running",
        "failure_reason": None,
        "sse_events": [],
    }


@pytest.fixture
def mock_api_schema() -> dict:
    """Provides a valid API schema for testing agents."""
    return {
        "api_name": "TestAPI",
        "base_url": "https://api.example.com/v1",
        "auth": {"type": "bearer", "location": "header", "key_name": "Authorization", "example": "Bearer token"},
        "endpoints": [
            {
                "name": "get_users",
                "method": "GET",
                "path": "/users",
                "description": "Get all users",
                "path_params": [],
                "query_params": [],
                "request_body": None,
                "response_schema": None,
            }
        ],
    }


@pytest.fixture
def mock_sdk_files() -> dict:
    """Provides sample generated SDK files."""
    return {
        "client.py": "class Client:\n    pass",
        "models.py": "from pydantic import BaseModel\nclass User(BaseModel):\n    id: int",
    }


@pytest.fixture
def mock_llm(monkeypatch):
    """Mocks the standard LLM invoke."""
    mock = MagicMock()
    mock.ainvoke = AsyncMock(return_value=MagicMock(content="Mock LLM response"))
    _original = backend.llm.get_llm
    monkeypatch.setattr(backend.llm, "get_llm", lambda **kwargs: mock)
    return mock


@pytest.fixture
def mock_structured_llm(monkeypatch):
    """
    Mocks get_structured_llm globally — patches the backend.llm module so that
    ALL callers (supervisor, architect, engineer, etc.) who imported via
    `from backend.llm import get_structured_llm` get the mock.

    Uses monkeypatch on the module object + re-injects into already-imported modules.
    """
    mock = MagicMock()
    mock.ainvoke = AsyncMock()

    factory = lambda schema=None, **kwargs: mock

    # Patch the canonical source
    monkeypatch.setattr(backend.llm, "get_structured_llm", factory)

    # Re-inject into modules that already did `from backend.llm import get_structured_llm`
    import importlib
    for mod_path in [
        "backend.agents.supervisor",
        "backend.agents.architect",
        "backend.agents.engineer",
        "backend.agents.qa_tester",
        "backend.agents.researcher",
        "backend.tools.select_pages",
    ]:
        try:
            mod = importlib.import_module(mod_path)
            if hasattr(mod, "get_structured_llm"):
                monkeypatch.setattr(mod, "get_structured_llm", factory)
        except ImportError:
            pass

    return mock
