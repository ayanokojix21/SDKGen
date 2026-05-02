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
- Route to Researcher if info is missing or QA fails due to documentation gaps.
- Route to Architect if the schema is missing or needs fixing.
- Route to Engineer if code is missing or has syntax errors.
- Route to QA Tester if the SDK is ready for verification.
- Route to Packager only when the SDK is verified or you decide to give up.
- Use 'end' to stop the process.
"""

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
            "next_agent": "end"
        }

    summary = build_state_summary(state)
    
    try:
        decision: SupervisorDecision = await structured_llm.ainvoke([
            SystemMessage(content=SUPERVISOR_PROMPT),
            HumanMessage(content=f"Current State:\n{summary}")
        ])
        
        logger.info(f"Supervisor Decision: {decision.next_agent} | {decision.reasoning}")
        
        return {
            "next_agent": decision.next_agent,
            "instruction": decision.instruction,
            "iteration_count": state["iteration_count"] + 1,
            "messages": [AIMessage(content=f"Routing to {decision.next_agent}: {decision.instruction}", name="supervisor")],
            "sse_events": [{
                "type": "supervisor",
                "routing_to": decision.next_agent,
                "reasoning": decision.reasoning,
                "instruction": decision.instruction
            }]
        }
    except Exception as e:
        logger.error(f"Supervisor failed: {e}")
        return {
            "next_agent": "end",
            "status": "failed",
            "failure_reason": f"Supervisor error: {str(e)}"
        }
