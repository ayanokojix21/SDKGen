"""
<<<<<<< HEAD
backend/agents/supervisor.py
─────────────────────────────
The Supervisor LLM node — the only node that makes routing decisions.

Responsibilities
─────────────────
1. Read current state via build_state_summary()
2. Call Gemini with the supervisor prompt (loaded from prompts/supervisor.txt)
3. Parse the strict JSON response → {next_agent, instruction, reasoning}
4. Emit a supervisor SSE event (routing decision visible in the UI)
5. Return a partial state update: {next_agent, instruction, iteration_count, messages, sse_events}

Safety
──────
• 3 retries with exponential backoff (2s → 4s → 8s) for Gemini rate limits
• If JSON parse fails → retry with stricter prompt injection
• If retries exhausted → emit failure event and set status=failed
• Never mutates state directly — always returns a dict with the delta
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from backend.config import settings
from backend.graph.state import build_state_summary, emit_sse

log = logging.getLogger(__name__)

# ── Load supervisor prompt once at import time ────────────────────────────────
_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "supervisor.txt"

def _load_supervisor_prompt() -> str:
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        log.warning("supervisor.txt not found — using built-in fallback prompt")
        return _FALLBACK_PROMPT

_FALLBACK_PROMPT = """\
You are the Supervisor of an SDK generation squad.
Your agents: researcher, architect, engineer, qa_tester, packager.

ROUTING RULES (follow in order):
1. knowledge_base is None → researcher
2. api_schema is None → architect
3. sdk_files is None → engineer
4. test_results is None → qa_tester
5. test_results has failures → engineer (code bug) or researcher (docs missing)
6. All tests passed → packager
7. iteration_count >= 15 OR qa_iteration >= 4 → set status=failed, route to end
8. Same agent called 3+ times for same unresolved issue → set status=failed, route to end

Respond ONLY with this exact JSON. No preamble. No explanation.
{
  "next_agent": "<researcher|architect|engineer|qa_tester|packager|end>",
  "instruction": "<specific, actionable instruction for that agent>",
  "reasoning": "<one sentence: why this agent, why now>"
}

STATE SUMMARY:
{state_summary}
"""

_STRICT_SUFFIX = (
    "\n\nIMPORTANT: Your previous response was not valid JSON. "
    "Reply with ONLY the JSON object. No markdown. No explanation. No backticks."
)

# ── LLM singleton ─────────────────────────────────────────────────────────────
_llm = ChatGoogleGenerativeAI(
    model=settings.GEMINI_MODEL,
    google_api_key=settings.GOOGLE_API_KEY,
    temperature=0,          # deterministic routing
    max_retries=0,          # we handle retries ourselves
)


# ──────────────────────────────────────────────────────────────────────────────
# Supervisor node
# ──────────────────────────────────────────────────────────────────────────────

async def supervisor_node(state: dict) -> dict:
    """
    LangGraph node — called every time the Supervisor needs to make a routing decision.
    Returns a partial state update dict.
    """
    iteration_count: int = state.get("iteration_count", 0) + 1
    log.info("[supervisor] iteration=%d", iteration_count)

    # ── Hard safety ceiling (also enforced in router.py, double-safety here) ──
    if iteration_count > settings.MAX_ITERATIONS:
        return _fail(state, "iteration_count ceiling reached", iteration_count)
    if state.get("qa_iteration", 0) >= settings.MAX_QA_ROUNDS:
        return _fail(state, "qa_iteration ceiling reached", iteration_count)

    # ── Build prompt ──────────────────────────────────────────────────────────
    base_prompt = _load_supervisor_prompt()
    state_summary = build_state_summary(state)
    
    test_results_str = "None"
    if state.get("test_results"):
        test_results_str = json.dumps(state["test_results"], indent=2)
        
    full_prompt = base_prompt.replace("{state_summary}", state_summary)
    full_prompt = full_prompt.replace("{test_results}", test_results_str)

    # ── Gemini call with retry / exponential backoff ──────────────────────────
    routing: dict = {}
    last_error: str = ""

    for attempt in range(1, settings.SUPERVISOR_RETRIES + 1):
        prompt_text = full_prompt if attempt == 1 else full_prompt + _STRICT_SUFFIX
        try:
            response = await _llm.ainvoke([
                SystemMessage(content="You are a precise routing controller. Output JSON only."),
                HumanMessage(content=prompt_text),
            ])
            raw = _extract_text(response)
            routing = _parse_json(raw)
            break  # success
        except json.JSONDecodeError as exc:
            last_error = f"JSON parse error (attempt {attempt}): {exc}"
            log.warning("[supervisor] %s — raw=%r", last_error, raw[:200])
        except Exception as exc:
            last_error = f"LLM error (attempt {attempt}): {exc}"
            log.warning("[supervisor] %s", last_error)

        if attempt < settings.SUPERVISOR_RETRIES:
            backoff = 2 ** attempt          # 2s, 4s, 8s
            log.info("[supervisor] retrying in %ds…", backoff)
            await asyncio.sleep(backoff)
    else:
        # All retries failed
        return _fail(state, f"Supervisor LLM failed after {settings.SUPERVISOR_RETRIES} retries: {last_error}", iteration_count)

    # ── Validate routing fields ───────────────────────────────────────────────
    valid_agents = {"researcher", "architect", "engineer", "qa_tester", "packager", "end"}
    next_agent   = routing.get("next_agent", "end")
    instruction  = routing.get("instruction", "")
    reasoning    = routing.get("reasoning", "")

    if next_agent not in valid_agents:
        log.warning("[supervisor] invalid next_agent=%r — defaulting to end", next_agent)
        next_agent = "end"

    # ── Detect reroute (QA failure → different agent) ─────────────────────────
    prev_next = state.get("next_agent", "")
    is_reroute = (
        state.get("test_results") is not None
        and any(not r.get("passed") for r in (state.get("test_results") or []))
        and next_agent in ("researcher", "engineer")
    )

    # ── Build SSE event ───────────────────────────────────────────────────────
    sse_kwargs = dict(
        routing_to=next_agent,
        reasoning=reasoning,
        iteration=iteration_count,
    )
    if is_reroute:
        sse_kwargs["reroute"] = True
        sse_kwargs["reroute_from"] = "qa_tester"
        log.info("[supervisor] REROUTE → %s (QA failures detected)", next_agent)

    sse_update = emit_sse("supervisor", **sse_kwargs)

    # ── Append supervisor message to conversation ─────────────────────────────
    supervisor_msg = AIMessage(
        content=json.dumps(routing),
        name="supervisor",
    )

    log.info("[supervisor] routing → %s | reason: %s", next_agent, reasoning[:80])

    return {
        "next_agent":      next_agent,
        "instruction":     instruction,
        "iteration_count": iteration_count,
        "messages":        [supervisor_msg],
        **sse_update,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _extract_text(response) -> str:
    """Safely extract string content from LangChain AIMessage."""
    content = response.content
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        # Gemini sometimes returns [{"type":"text","text":"..."}]
        parts = [p["text"] for p in content if isinstance(p, dict) and "text" in p]
        return " ".join(parts).strip()
    return str(content).strip()


def _parse_json(raw: str) -> dict:
    """Strip markdown fences and parse JSON."""
    # Remove ```json ... ``` fences if present
    cleaned = re.sub(r"^```[a-z]*\n?", "", raw, flags=re.MULTILINE)
    cleaned = re.sub(r"\n?```$", "", cleaned, flags=re.MULTILINE)
    return json.loads(cleaned.strip())


def _fail(state: dict, reason: str, iteration_count: int) -> dict:
    """Return a failure state update with appropriate SSE event."""
    log.error("[supervisor] FAIL — %s", reason)
    sse_update = emit_sse("supervisor_fail", reason=reason, iteration=iteration_count)
    return {
        "status":          "failed",
        "failure_reason":  reason,
        "next_agent":      "end",
        "iteration_count": iteration_count,
        **sse_update,
    }
=======
Supervisor Agent — Routing brain of the Docs-to-Code pipeline.

The Supervisor is a lightweight LLM call that reads the current job state
and decides which agent should run next. It does NOT do any real work —
it only routes.

Called after every other agent finishes. The graph loops:
  agent → supervisor → (next agent) → supervisor → ...
until the Supervisor routes to "packager" (terminal) or safety ceilings hit.
"""

import json
import logging
from pathlib import Path

from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from backend.graph.state import build_state_summary

logger = logging.getLogger(__name__)

# Load prompt once at module level
_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "supervisor.txt"
_SUPERVISOR_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")


async def supervisor_node(state: dict) -> dict:
    """
    Supervisor agent node for the LangGraph graph.

    Reads state summary, calls LLM for routing decision,
    returns updated next_agent + iteration_count.
    """
    sse_events = []
    messages = []

    state_summary = build_state_summary(state)
    iteration_count = state.get("iteration_count", 0) + 1

    # Format test results for the prompt
    test_results = state.get("test_results")
    test_results_str = json.dumps(test_results, indent=2) if test_results else "null"

    # Fill prompt template
    prompt = _SUPERVISOR_PROMPT.replace("{state_summary}", state_summary)
    prompt = prompt.replace("{test_results}", test_results_str)

    try:
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            temperature=0.0,
        )

        response = await llm.ainvoke([
            SystemMessage(content=prompt),
            HumanMessage(content="Decide which agent runs next."),
        ])

        decision = _parse_decision(response.content)

    except Exception as e:
        logger.error(f"Supervisor LLM call failed: {e}")
        # Fallback: deterministic routing based on state
        decision = _fallback_route(state)

    next_agent = decision.get("next_agent", "packager")
    instruction = decision.get("instruction", "")
    reasoning = decision.get("reasoning", "")

    # Validate the agent name
    valid_agents = {"researcher", "architect", "engineer", "qa_tester", "packager"}
    if next_agent not in valid_agents:
        logger.warning(f"Supervisor chose invalid agent '{next_agent}', defaulting to 'packager'")
        next_agent = "packager"
        reasoning = f"Invalid agent '{next_agent}' was chosen — defaulting to packager"

    logger.info(f"Supervisor → {next_agent} (iteration {iteration_count}): {reasoning}")

    # Build message for the conversation history
    msg_content = f"Routing to {next_agent}: {instruction}"
    messages.append(AIMessage(content=msg_content, name="supervisor"))

    sse_events.append({
        "type": "supervisor_decision",
        "next_agent": next_agent,
        "instruction": instruction,
        "reasoning": reasoning,
        "iteration": iteration_count,
    })

    return {
        "next_agent": next_agent,
        "iteration_count": iteration_count,
        "messages": messages,
        "sse_events": sse_events,
    }


def _parse_decision(content: str) -> dict:
    """Parse the Supervisor LLM response into a routing decision."""
    text = content.strip()

    # Strip markdown fences
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        decision = json.loads(text)
    except json.JSONDecodeError:
        logger.error(f"Failed to parse supervisor JSON: {text[:300]}...")
        return {"next_agent": "packager", "instruction": "", "reasoning": "JSON parse failure — stopping"}

    # Validate required fields
    if "next_agent" not in decision:
        decision["next_agent"] = "packager"
    if "instruction" not in decision:
        decision["instruction"] = ""
    if "reasoning" not in decision:
        decision["reasoning"] = ""

    return decision


def _fallback_route(state: dict) -> dict:
    """
    Deterministic fallback when the Supervisor LLM fails.
    Mirrors the routing rules from supervisor.txt.
    """
    if state.get("knowledge_base") is None:
        return {"next_agent": "researcher", "instruction": "Build the knowledge base", "reasoning": "Fallback: no knowledge_base"}
    if state.get("api_schema") is None:
        return {"next_agent": "architect", "instruction": "Generate the API schema", "reasoning": "Fallback: no api_schema"}
    if state.get("sdk_files") is None:
        return {"next_agent": "engineer", "instruction": "Generate the SDK files", "reasoning": "Fallback: no sdk_files"}
    if state.get("test_results") is None:
        return {"next_agent": "qa_tester", "instruction": "Run QA tests", "reasoning": "Fallback: no test_results"}

    # Check test results
    test_results = state.get("test_results", [])
    if isinstance(test_results, list):
        has_failures = any(
            t.get("status") == "fail"
            for t in test_results
            if isinstance(t, dict)
        )
        if has_failures:
            return {"next_agent": "engineer", "instruction": "Fix test failures", "reasoning": "Fallback: test failures exist"}

    return {"next_agent": "packager", "instruction": "Package the SDK", "reasoning": "Fallback: all steps complete"}
>>>>>>> a8306fd (feat: implement multi-agent system with supervisor, engineer, architect, and qa-tester roles, including syntax validation tools and updated prompt templates.)
