from backend.graph.state import SDKJobState

def route_next(state: SDKJobState) -> str:
    """
    Pure function — reads state.next_agent set by Supervisor LLM.
    Hard safety overrides take priority over LLM decision.
    """
    if state["status"] == "failed":
        return "end"
    
    # Safety ceiling: stop graph runaway loops
    if state["iteration_count"] >= 15:
        # We would log a failure here in production
        return "end"
        
    # Safety ceiling: stop endless QA loops
    if state["qa_iteration"] >= 4:
        # QA has looped 4 times — something is fundamentally broken
        return "end"
        
    return state.get("next_agent", "end")
