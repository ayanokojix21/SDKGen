import logging
from pathlib import Path
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from backend.llm import get_structured_llm, get_token_usage
from backend.graph.schemas import SupervisorDecision
from backend.graph.state import build_state_summary
from backend.config import settings

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

def _load_supervisor_prompt() -> str:
    prompt_path = _PROMPTS_DIR / "supervisor.txt"
    try:
        text = prompt_path.read_text(encoding="utf-8")
        logger.info("[supervisor] Loaded prompt from supervisor.txt (%d chars)", len(text))
        return text
    except FileNotFoundError:
        logger.warning("[supervisor] supervisor.txt not found — using fallback")
        return ""

_SUPERVISOR_PROMPT_FILE = _load_supervisor_prompt()

_FALLBACK_PROMPT = """
You are the Orchestrator for the SDKGen squad.
Your goal is to guide the team from API documentation to a verified SDK.

The team:
1. Researcher: Crawls docs, indexes into Vector Store, performs online search.
2. Architect: Designs the API Schema using Vector Store data.
3. Engineer: Writes the SDK code using the Schema.
4. QA Tester: Verifies the SDK against live APIs.
5. Packager: Finalizes and delivers files.

Rules:
- Route to Researcher if info is completely missing from vector store.
- Route to Architect if the schema is missing, needs fixing, or QA reports hallucinated/invalid endpoints (e.g. 404s).
- Route to Engineer if code is missing or has syntax errors in the SDK files.
- Route to QA Tester if the SDK is ready for verification.
- Route to Packager when QA recommends 'proceed' or when QA reports all tests passed.
- Use 'end' to stop the process.

CRITICAL — HTTP status codes: A POST endpoint returning 201 is CORRECT and is NOT a failure.
Any 2xx response (200-299) means the live HTTP test passed. Do NOT route to Engineer or Architect for 201 responses from POST endpoints.
"""

# Agents in the "forward" direction of the pipeline — used for reroute detection
_PIPELINE_ORDER = ["researcher", "architect", "engineer", "qa_tester", "packager", "end"]

def _is_reroute(previous_agent: str | None, next_agent: str) -> bool:
    """Detect if the supervisor is routing backwards in the pipeline."""
    if not previous_agent or previous_agent == next_agent:
        return False
    try:
        prev_idx = _PIPELINE_ORDER.index(previous_agent)
        next_idx = _PIPELINE_ORDER.index(next_agent)
        return next_idx < prev_idx  # Going backwards = reroute
    except ValueError:
        return False


async def supervisor_node(state: dict) -> dict:
    """
    Supervisor node using structured output.
    """
    structured_llm = get_structured_llm(SupervisorDecision)
    
    # Check budget
    if state.get("estimated_cost_usd", 0) > 2.0: # $2 limit
        return {
            "status": "failed",
            "failure_reason": "Budget limit exceeded ($2.00)",
            "next_agent": "end",
            "sse_events": [{
                "type": "safety_cutoff",
                "message": "Budget limit exceeded ($2.00) — stopping generation.",
            }],
        }

    # ── BUG 19 FIX: Enforce Iteration Limits BEFORE LLM Call ────────────
    iteration_count = state.get("iteration_count", 0)
    qa_iteration = state.get("qa_iteration", 0)
    engineer_iteration = state.get("engineer_iteration", 0)
    architect_iteration = state.get("architect_iteration", 0)

    max_eng = getattr(settings, "MAX_ENGINEER_ROUNDS", 4)
    max_arch = getattr(settings, "MAX_ARCHITECT_ROUNDS", 3)

    if iteration_count >= settings.MAX_ITERATIONS:
        logger.error("[supervisor] iteration_count=%d >= %d — forcing END", iteration_count, settings.MAX_ITERATIONS)
        return {"next_agent": "end", "status": "failed", "failure_reason": "Max total iterations reached"}
    
    if qa_iteration >= settings.MAX_QA_ROUNDS:
        logger.error("[supervisor] qa_iteration=%d >= %d — forcing END", qa_iteration, settings.MAX_QA_ROUNDS)
        return {"next_agent": "end", "status": "failed", "failure_reason": "Max QA rounds reached"}

    if engineer_iteration >= max_eng and state.get("next_agent") != "qa_tester":
        logger.warning("[supervisor] engineer_iteration=%d >= %d — forcing qa_tester", engineer_iteration, max_eng)
        return {
            "next_agent": "qa_tester",
            "instruction": "Max engineer retries reached. Verify what we have.",
            "iteration_count": iteration_count + 1,
            "messages": [AIMessage(content="Forcing QA Tester (max engineer retries reached)", name="supervisor")]
        }

    if architect_iteration >= max_arch and state.get("next_agent") != "engineer":
        logger.warning("[supervisor] architect_iteration=%d >= %d — forcing engineer", architect_iteration, max_arch)
        return {
            "next_agent": "engineer",
            "instruction": "Max architect retries reached. Generate code with current schema.",
            "iteration_count": iteration_count + 1,
            "messages": [AIMessage(content="Forcing Engineer (max architect retries reached)", name="supervisor")]
        }

    summary = build_state_summary(state)
    prompt_text = _SUPERVISOR_PROMPT_FILE or _FALLBACK_PROMPT
    
    # Fill known placeholders from the .txt prompt file
    prompt_text = (
        prompt_text
        .replace("{state_summary}", summary)
        .replace("{test_results}", str(state.get("test_results", "")))
    )
    
    try:
        decision: SupervisorDecision = await structured_llm.ainvoke([
            SystemMessage(content=prompt_text),
            HumanMessage(content=f"Current State:\n{summary}")
        ])
        
        # Groq/Llama sometimes returns capitalized Enum values (e.g., "Researcher")
        next_agent = decision.next_agent.lower() if decision.next_agent else "end"
        
        logger.info(f"Supervisor Decision: {next_agent} | {decision.reasoning}")

        # Detect the previous agent from recent messages
        previous_agent = None
        for msg in reversed(state.get("messages", [])):
            name = getattr(msg, "name", None)
            if name and name != "supervisor":
                previous_agent = name
                break

        sse_events = []

        # Emit reroute event if routing backwards
        if _is_reroute(previous_agent, next_agent):
            sse_events.append({
                "type": "reroute",
                "from": previous_agent,
                "to": next_agent,
                "reason": decision.reasoning,
            })

        # Always emit the standard supervisor event
        sse_events.append({
            "type": "supervisor",
            "routing_to": next_agent,
            "reasoning": decision.reasoning,
            "instruction": decision.instruction,
            "iteration": iteration_count + 1,
        })
        
        # Propagate token tracking to state (BUG 5 fix)
        token_usage = get_token_usage()

        return {
            "next_agent": next_agent,
            "instruction": decision.instruction,
            "iteration_count": iteration_count + 1,
            "messages": [AIMessage(content=f"Routing to {next_agent}: {decision.instruction}", name="supervisor")],
            "sse_events": sse_events,
            **token_usage,
        }
    except Exception as e:
        logger.error(f"Supervisor failed: {e}")
        return {
            "next_agent": "end",
            "status": "failed",
            "failure_reason": f"Supervisor error: {str(e)}",
            "sse_events": [{
                "type": "safety_cutoff",
                "message": f"Supervisor error: {str(e)}",
            }],
        }
