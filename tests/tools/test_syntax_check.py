"""Tests for backend/tools/syntax_check.py."""
import pytest
from unittest.mock import patch, MagicMock
from backend.tools.syntax_check import check_syntax, format_errors_for_retry


@pytest.fixture
def mock_sandbox():
    """Mock the E2B Sandbox context manager."""
    with patch("backend.tools.syntax_check.Sandbox") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value.__enter__.return_value = mock_instance

        mock_instance.files.write = MagicMock()

        mock_proc = MagicMock()
        mock_proc.exit_code = 0
        mock_proc.stderr = ""
        mock_instance.process.start.return_value = mock_proc

        yield mock_instance


@pytest.mark.asyncio
async def test_check_syntax_python_success(mock_sandbox, monkeypatch):
    monkeypatch.setenv("E2B_API_KEY", "test_key")

    files = {"test.py": "print('hello')"}
    results = await check_syntax(files, "python")

    assert len(results) == 1
    assert results[0]["file"] == "test.py"
    assert results[0]["valid"] is True

    mock_sandbox.files.write.assert_called_with("test.py", "print('hello')")
    mock_sandbox.process.start.assert_called_with("python3 -m py_compile test.py")


@pytest.mark.asyncio
async def test_check_syntax_python_failure(mock_sandbox, monkeypatch):
    monkeypatch.setenv("E2B_API_KEY", "test_key")

    mock_proc = MagicMock()
    mock_proc.exit_code = 1
    mock_proc.stderr = "SyntaxError: invalid syntax"
    mock_sandbox.process.start.return_value = mock_proc

    files = {"test.py": "print 'hello'"}
    results = await check_syntax(files, "python")

    assert results[0]["valid"] is False
    assert "SyntaxError" in results[0]["errors"][0]


@pytest.mark.asyncio
async def test_check_syntax_empty_file(mock_sandbox, monkeypatch):
    monkeypatch.setenv("E2B_API_KEY", "test_key")

    files = {"empty.py": "  "}
    results = await check_syntax(files, "python")

    assert results[0]["valid"] is False
    assert "empty" in results[0]["errors"][0].lower()


@pytest.mark.asyncio
async def test_check_syntax_fallback(monkeypatch):
    """Test when E2B_API_KEY is not set."""
    monkeypatch.delenv("E2B_API_KEY", raising=False)

    files = {"test.py": "print('hello')"}
    results = await check_syntax(files, "python")

    assert len(results) == 1
    assert results[0]["valid"] is True


def test_format_errors_for_retry():
    results = [
        {"file": "good.py", "valid": True, "errors": []},
        {"file": "bad.py", "valid": False, "errors": ["Line 1: SyntaxError"]},
    ]
    formatted = format_errors_for_retry(results)

    assert "bad.py" in formatted
    assert "Line 1: SyntaxError" in formatted
    assert "good.py" not in formatted
