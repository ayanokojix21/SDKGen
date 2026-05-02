"""
Syntax Checker — Validates generated SDK code.
Uses local Python compile() for Python files.
Falls back to basic checks for other languages.
"""

import ast
import logging

logger = logging.getLogger(__name__)


async def check_syntax(files: dict[str, str], language: str) -> list[dict]:
    """
    Check syntax of all generated SDK files.
    Uses Python's built-in ast.parse for Python files (fast, no external deps).
    """
    results = []

    for filename, content in files.items():
        if not content or not content.strip():
            results.append({"file": filename, "valid": False, "errors": ["File is empty"]})
            continue

        if language == "python" and filename.endswith(".py"):
            try:
                ast.parse(content, filename=filename)
                results.append({"file": filename, "valid": True, "errors": []})
            except SyntaxError as e:
                error_msg = f"Line {e.lineno}: {e.msg}"
                results.append({"file": filename, "valid": False, "errors": [error_msg]})

        elif language == "typescript" and filename.endswith((".ts", ".tsx")):
            # Basic bracket/brace balance check for TypeScript
            errors = _check_brackets(content, filename)
            results.append({
                "file": filename,
                "valid": len(errors) == 0,
                "errors": errors,
            })

        else:
            # Non-code files (README.md, etc.) — always valid
            results.append({"file": filename, "valid": True, "errors": []})

    return results


def _check_brackets(content: str, filename: str) -> list[str]:
    """Basic bracket/brace/paren balance check."""
    stack = []
    pairs = {')': '(', ']': '[', '}': '{'}
    errors = []

    for i, ch in enumerate(content):
        if ch in '([{':
            stack.append((ch, i))
        elif ch in ')]}':
            if not stack:
                errors.append(f"Unmatched '{ch}' at position {i}")
            elif stack[-1][0] != pairs[ch]:
                errors.append(f"Mismatched '{ch}' at position {i}")
            else:
                stack.pop()

    for ch, pos in stack:
        errors.append(f"Unclosed '{ch}' at position {pos}")

    return errors

import tempfile
import subprocess

def _local_fallback_check(files: dict[str, str], language: str) -> list[dict]:
    """Basic local checks if E2B is unavailable."""
    results = []
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Write files to tempdir
        for filename, content in files.items():
            filepath = os.path.join(tmpdir, filename)
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
                
        # Validate
        for filename, content in files.items():
            filepath = os.path.join(tmpdir, filename)
            if not content.strip():
                results.append({"file": filename, "valid": False, "errors": ["File is empty"]})
                continue
                
            if language == "python" and filename.endswith(".py"):
                proc = subprocess.run(
                    ["python", "-m", "py_compile", filepath],
                    capture_output=True,
                    text=True
                )
                if proc.returncode != 0:
                    err_msg = proc.stderr.strip() or proc.stdout.strip()
                    results.append({"file": filename, "valid": False, "errors": [err_msg]})
                else:
                    results.append({"file": filename, "valid": True, "errors": []})
                    
            elif language == "typescript" and filename.endswith((".ts", ".tsx")):
                proc = subprocess.run(
                    ["npx", "-y", "typescript", "tsc", "--noEmit", filepath],
                    capture_output=True,
                    text=True,
                    shell=True
                )
                if proc.returncode != 0:
                    err_msg = proc.stderr.strip() or proc.stdout.strip()
                    results.append({"file": filename, "valid": False, "errors": [err_msg]})
                else:
                    results.append({"file": filename, "valid": True, "errors": []})
            else:
                results.append({"file": filename, "valid": True, "errors": []})
                
    return results

def format_errors_for_retry(results: list[dict]) -> str:
    lines = ["The following syntax errors were found in your generated files:\n"]
    for result in results:
        if not result["valid"]:
            lines.append(f"## {result['file']}\n" + "\n".join(f"  - {e}" for e in result["errors"]))
    return "\n".join(lines)
