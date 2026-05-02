import logging
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from backend.llm import get_structured_llm
from backend.graph.schemas import SupervisorDecision
from backend.graph.state import build_state_summary

logger = logging.getLogger(__name__)

SUPERVISOR_PROMPT = """
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
- Route to Architect if the schema is missing, needs fixing, or QA reports hallucinated/invalid endpoints (e.g. 404s). If 'Architect Iteration' >= 2, stop retrying and route to Engineer instead.
- Route to Engineer if code is missing or has syntax errors in the SDK files. If 'Engineer Iteration' >= 3, stop retrying and route to QA instead.
- Route to QA Tester if the SDK is ready for verification (no syntax errors, or engineer has retried enough times).
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

    summary = build_state_summary(state)
    
    try:
        decision: SupervisorDecision = await structured_llm.ainvoke([
            SystemMessage(content=SUPERVISOR_PROMPT),
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
            "iteration": state["iteration_count"] + 1,
        })
        
        return {
            "next_agent": next_agent,
            "instruction": decision.instruction,
            "iteration_count": state["iteration_count"] + 1,
            "messages": [AIMessage(content=f"Routing to {next_agent}: {decision.instruction}", name="supervisor")],
            "sse_events": sse_events,
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
