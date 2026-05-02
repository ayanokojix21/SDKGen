"""
Syntax Checker — Upgraded to use E2B Sandbox for secure, high-fidelity validation.
"""

import os
import logging
from e2b_code_interpreter import Sandbox

logger = logging.getLogger(__name__)

async def check_syntax(files: dict[str, str], language: str) -> list[dict]:
    """
    Check syntax of all generated SDK files using an isolated E2B Sandbox.
    """
    if not os.environ.get("E2B_API_KEY"):
        logger.warning("E2B_API_KEY missing, falling back to local basic checks")
        return _local_fallback_check(files, language)

    results = []
    
    # Initialize E2B Sandbox
    with Sandbox() as sandbox:
        # ── Write files to sandbox ──────────────────────────────────────────
        for filename, content in files.items():
            sandbox.files.write(filename, content)
        
        # ── Run validation based on language ────────────────────────────────
        for filename, content in files.items():
            if not content.strip():
                results.append({"file": filename, "valid": False, "errors": ["File is empty"]})
                continue

            if language == "python" and filename.endswith(".py"):
                # Use python's compile tool
                proc = sandbox.process.start(f"python3 -m py_compile {filename}")
                proc.wait()
                if proc.exit_code != 0:
                    results.append({"file": filename, "valid": False, "errors": [proc.stderr]})
                else:
                    results.append({"file": filename, "valid": True, "errors": []})

            elif language == "typescript" and filename.endswith((".ts", ".tsx")):
                # Run tsc --noEmit
                # Note: This requires typescript installed in the sandbox. 
                # E2B default sandbox usually has it, or we can install it.
                proc = sandbox.process.start(f"npx -y typescript tsc --noEmit {filename}")
                proc.wait()
                if proc.exit_code != 0:
                    results.append({"file": filename, "valid": False, "errors": [proc.stderr]})
                else:
                    results.append({"file": filename, "valid": True, "errors": []})
            else:
                results.append({"file": filename, "valid": True, "errors": []})

    return results

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
