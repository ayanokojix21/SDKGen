"""Tests for backend/tools/syntax_check.py."""
import pytest
from backend.tools.syntax_check import check_syntax, format_errors_for_retry


@pytest.mark.asyncio
async def test_check_syntax_python_success():
    """Valid Python code should pass syntax check."""
    files = {"test.py": "print('hello')\nx = 42\n"}
    results = await check_syntax(files, "python")

    assert len(results) == 1
    assert results[0]["file"] == "test.py"
    assert results[0]["valid"] is True
    assert results[0]["errors"] == []


@pytest.mark.asyncio
async def test_check_syntax_python_failure():
    """Invalid Python syntax should be caught by ast.parse."""
    files = {"test.py": "def foo(\n  print('hello')\n"}
    results = await check_syntax(files, "python")

    assert results[0]["valid"] is False
    assert len(results[0]["errors"]) > 0


@pytest.mark.asyncio
async def test_check_syntax_empty_file():
    """Empty files should be flagged as invalid."""
    files = {"empty.py": "  "}
    results = await check_syntax(files, "python")

    assert results[0]["valid"] is False
    assert "empty" in results[0]["errors"][0].lower()


@pytest.mark.asyncio
async def test_check_syntax_fallback():
    """Non-.py files should always pass (README, etc.)."""
    files = {"README.md": "# Hello\nThis is a readme."}
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
