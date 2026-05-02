"""
Syntax Checker — Validates generated SDK file syntax before passing to QA.

Python files: Uses ast.parse() for reliable AST-level validation.
TypeScript files: Regex-based heuristic checks for common issues.

Called by the Engineer agent after LLM generates SDK files. If syntax errors
are found, the Engineer retries with the error details as context.
"""

import ast
import re
import logging

logger = logging.getLogger(__name__)


def check_syntax(files: dict[str, str], language: str) -> list[dict]:
    """
    Check syntax of all generated SDK files.

    Args:
        files: Dict of {filename: content} from the Engineer LLM.
        language: "python" or "typescript"

    Returns:
        List of per-file results:
        [
            {
                "file": "client.py",
                "valid": true/false,
                "errors": ["line 42: unexpected indent"]
            }
        ]
    """
    results = []

    for filename, content in files.items():
        if not content or not content.strip():
            results.append({
                "file": filename,
                "valid": False,
                "errors": ["File is empty"],
            })
            continue

        if language == "python" and filename.endswith(".py"):
            result = _check_python(filename, content)
        elif language == "typescript" and filename.endswith((".ts", ".tsx")):
            result = _check_typescript(filename, content)
        elif filename.endswith(".md"):
            result = _check_markdown(filename, content)
        else:
            # Unknown file type — skip
            result = {"file": filename, "valid": True, "errors": []}

        results.append(result)

    valid_count = sum(1 for r in results if r["valid"])
    total = len(results)
    logger.info(f"Syntax check: {valid_count}/{total} files passed ({language})")

    return results


def _check_python(filename: str, content: str) -> dict:
    """
    Validate Python syntax using ast.parse().
    This catches all syntax errors reliably.
    """
    errors = []

    try:
        ast.parse(content, filename=filename)
    except SyntaxError as e:
        line_info = f"line {e.lineno}" if e.lineno else "unknown line"
        col_info = f", col {e.offset}" if e.offset else ""
        errors.append(f"{line_info}{col_info}: {e.msg}")

        # Try to provide context
        lines = content.split("\n")
        if e.lineno and 0 < e.lineno <= len(lines):
            errors.append(f"  → {lines[e.lineno - 1].rstrip()}")

    # Additional heuristic checks beyond syntax
    errors.extend(_check_python_heuristics(content))

    return {
        "file": filename,
        "valid": len(errors) == 0,
        "errors": errors,
    }


def _check_python_heuristics(content: str) -> list[str]:
    """
    Catch common LLM-generated Python issues that ast.parse() won't flag.
    """
    errors = []
    lines = content.split("\n")

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Detect placeholder code
        if stripped == "pass" and i > 1:
            # Check if it's the only statement in a function body
            prev_lines = [l.strip() for l in lines[max(0, i-3):i-1]]
            if any(l.startswith("def ") or l.startswith("async def ") for l in prev_lines):
                errors.append(f"line {i}: Placeholder 'pass' in function body")

        if "# TODO" in stripped or "# FIXME" in stripped:
            errors.append(f"line {i}: Contains TODO/FIXME comment: '{stripped[:80]}'")

        # Detect triple-dot placeholder
        if stripped == "...":
            prev_lines = [l.strip() for l in lines[max(0, i-3):i-1]]
            if any(l.startswith("def ") or l.startswith("async def ") for l in prev_lines):
                errors.append(f"line {i}: Placeholder '...' in function body")

    # Check for missing imports that are commonly needed
    if "httpx" in content and "import httpx" not in content:
        errors.append("Uses 'httpx' but missing 'import httpx'")

    if "@dataclass" in content and "from dataclasses import" not in content:
        errors.append("Uses '@dataclass' but missing 'from dataclasses import dataclass'")

    return errors


def _check_typescript(filename: str, content: str) -> dict:
    """
    Heuristic-based TypeScript syntax validation.
    Since we can't run tsc, we check for common structural issues.
    """
    errors = []

    # Check bracket balance
    open_braces = content.count("{")
    close_braces = content.count("}")
    if open_braces != close_braces:
        errors.append(f"Unbalanced braces: {open_braces} open, {close_braces} close")

    open_parens = content.count("(")
    close_parens = content.count(")")
    if open_parens != close_parens:
        errors.append(f"Unbalanced parentheses: {open_parens} open, {close_parens} close")

    open_brackets = content.count("[")
    close_brackets = content.count("]")
    if open_brackets != close_brackets:
        errors.append(f"Unbalanced brackets: {open_brackets} open, {close_brackets} close")

    # Check for unclosed template literals
    backtick_count = content.count("`")
    if backtick_count % 2 != 0:
        errors.append(f"Odd number of backticks ({backtick_count}) — possible unclosed template literal")

    # Check for common TS issues
    lines = content.split("\n")
    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Detect 'any' type usage
        if re.search(r':\s*any\b', stripped) or re.search(r'<any>', stripped):
            errors.append(f"line {i}: Uses 'any' type — should use 'unknown' or a specific type")

        # Detect TODO/FIXME
        if "// TODO" in stripped or "// FIXME" in stripped:
            errors.append(f"line {i}: Contains TODO/FIXME comment")

        # Detect var usage
        if re.match(r'^var\s+', stripped):
            errors.append(f"line {i}: Uses 'var' — should use 'const' or 'let'")

    # Check for fetch usage in client
    if "client" in filename.lower():
        if "fetch" not in content and "axios" not in content:
            errors.append("Client file doesn't appear to use fetch or any HTTP library")

    return {
        "file": filename,
        "valid": len(errors) == 0,
        "errors": errors,
    }


def _check_markdown(filename: str, content: str) -> dict:
    """Basic markdown validation — mainly checks it's not empty/broken."""
    errors = []

    if not content.strip():
        errors.append("Markdown file is empty")
        return {"file": filename, "valid": False, "errors": errors}

    # Check for a title
    if not re.search(r'^#\s+', content, re.MULTILINE):
        errors.append("Missing top-level heading (# Title)")

    # Check for code blocks balance
    code_fences = content.count("```")
    if code_fences % 2 != 0:
        errors.append(f"Odd number of code fences ({code_fences}) — possible unclosed code block")

    return {
        "file": filename,
        "valid": len(errors) == 0,
        "errors": errors,
    }


def format_errors_for_retry(results: list[dict]) -> str:
    """
    Format syntax check results into a string suitable for LLM retry prompt.
    Only includes files with errors.
    """
    lines = ["The following syntax errors were found in your generated files:\n"]

    for result in results:
        if not result["valid"]:
            lines.append(f"## {result['file']}")
            for err in result["errors"]:
                lines.append(f"  - {err}")
            lines.append("")

    lines.append("Please fix these errors and regenerate the affected files.")
    return "\n".join(lines)
