"""
Engineer Agent — Generates SDK code from validated api_schema.

Selects the appropriate prompt (Python or TypeScript) based on the
target language, calls the LLM, then runs syntax_check on the output.
If syntax errors are found, retries once with error context.

Produces 4 files: client, models, tests, and README.
"""

import json
import logging
from pathlib import Path

from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from backend.tools.syntax_check import check_syntax, format_errors_for_retry

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).parent.parent / "prompts"
_PYTHON_PROMPT = (_PROMPT_DIR / "engineer_python.txt").read_text(encoding="utf-8")
_TYPESCRIPT_PROMPT = (_PROMPT_DIR / "engineer_typescript.txt").read_text(encoding="utf-8")

MAX_SYNTAX_RETRIES = 1


async def engineer_node(state: dict) -> dict:
    """
    Engineer agent node for the LangGraph graph.
    Generates SDK files from api_schema, with syntax checking and retry.
    """
    sse_events = []
    messages = []
    syntax_errors: list[str] = []

    api_schema = state.get("api_schema")
    language = state.get("language", "python")
    supervisor_instruction = _get_last_instruction(state.get("messages", []))
    existing_sdk_files = state.get("sdk_files")
    test_results = state.get("test_results")

    if not api_schema:
        messages.append(AIMessage(content="No API schema available.", name="engineer"))
        return {
            "sdk_files": None, "syntax_errors": [],
            "messages": messages,
            "sse_events": [{"type": "agent_warn", "message": "Engineer received empty api_schema"}],
        }

    base_prompt = _PYTHON_PROMPT if language == "python" else _TYPESCRIPT_PROMPT
    api_name = api_schema.get("api_name", "API")

    sse_events.append({
        "type": "engineer_start", "language": language,
        "endpoint_count": len(api_schema.get("endpoints", [])),
        "is_fix": existing_sdk_files is not None,
    })

    prompt = _fill_template(base_prompt, api_schema, api_name,
                            supervisor_instruction or "Generate the SDK",
                            existing_sdk_files, test_results)

    sdk_files = await _generate_with_retry(prompt, language, sse_events, syntax_errors)

    if sdk_files is None:
        messages.append(AIMessage(content="Engineer failed to generate SDK files.", name="engineer"))
        return {"sdk_files": None, "syntax_errors": syntax_errors,
                "messages": messages, "sse_events": sse_events}

    file_count = len(sdk_files)
    total_lines = sum(c.count("\n") + 1 for c in sdk_files.values())
    fix_note = f" ({len(syntax_errors)} syntax issues fixed)" if syntax_errors else ""
    summary = f"SDK generated: {file_count} files, ~{total_lines} lines of {language}{fix_note}."

    messages.append(AIMessage(content=summary, name="engineer"))
    sse_events.append({"type": "engineer_done", "file_count": file_count,
                       "total_lines": total_lines, "files": list(sdk_files.keys())})
    logger.info(f"Engineer: {summary}")

    return {"sdk_files": sdk_files, "syntax_errors": syntax_errors,
            "messages": messages, "sse_events": sse_events}


async def _generate_with_retry(prompt, language, sse_events, syntax_errors):
    """Call LLM, check syntax, retry once if errors found."""
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0.2)
    check_results = None

    for attempt in range(1 + MAX_SYNTAX_RETRIES):
        try:
            if attempt == 0:
                resp = await llm.ainvoke([
                    SystemMessage(content=prompt),
                    HumanMessage(content="Generate the SDK. Return JSON only."),
                ])
            else:
                error_ctx = format_errors_for_retry(check_results)
                resp = await llm.ainvoke([
                    SystemMessage(content=prompt),
                    HumanMessage(content=f"Fix syntax errors and regenerate.\n\n{error_ctx}"),
                ])

            sdk_files = _parse_sdk_files(resp.content)
            if sdk_files is None:
                continue

            check_results = check_syntax(sdk_files, language)
            has_errors = any(not r["valid"] for r in check_results)

            if has_errors and attempt < MAX_SYNTAX_RETRIES:
                for r in check_results:
                    if not r["valid"]:
                        syntax_errors.extend(f"{r['file']}: {e}" for e in r["errors"])
                sse_events.append({"type": "engineer_syntax_retry", "attempt": attempt + 1,
                                   "error_count": len(syntax_errors)})
                continue

            if has_errors:
                for r in check_results:
                    if not r["valid"]:
                        syntax_errors.extend(f"{r['file']}: {e}" for e in r["errors"])

            return sdk_files
        except Exception as e:
            logger.error(f"Engineer LLM call failed (attempt {attempt + 1}): {e}")
            if attempt >= MAX_SYNTAX_RETRIES:
                return None
    return None


def _fill_template(template, api_schema, api_name, instruction, existing_files, test_results):
    """Fill the prompt template with state data."""
    p = template.replace("{api_schema}", json.dumps(api_schema, indent=2))
    p = p.replace("{api_name}", api_name)
    p = p.replace("{instruction}", instruction)

    if existing_files:
        ft = ""
        for fname, content in existing_files.items():
            ft += f"\n--- {fname} ---\n{content}\n"
        p = p.replace("{existing_sdk_files}", ft)
    else:
        p = p.replace("{existing_sdk_files}", "null (first generation)")

    if test_results:
        p = p.replace("{test_results}", json.dumps(test_results, indent=2))
    else:
        p = p.replace("{test_results}", "null (no tests run yet)")
    return p


def _parse_sdk_files(content: str) -> dict | None:
    """Parse LLM response into {filename: content} dict."""
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        files = json.loads(text)
    except json.JSONDecodeError:
        logger.error(f"Failed to parse SDK files JSON: {text[:300]}...")
        return None

    if not isinstance(files, dict) or not files:
        return None

    for key, value in files.items():
        if not isinstance(value, str):
            files[key] = str(value)
    return files


def _get_last_instruction(messages: list) -> str | None:
    """Extract the last supervisor instruction from message history."""
    for msg in reversed(messages):
        if hasattr(msg, "name") and msg.name == "supervisor":
            content = msg.content
            if ":" in content:
                return content.split(":", 1)[1].strip()
            return content
    return None
