from langgraph.graph import StateGraph, END
from backend.graph.state import SDKJobState
from backend.graph.router import route_next

# Import agent nodes
from backend.agents.supervisor import supervisor_node
from backend.agents.researcher import researcher_node
from backend.agents.architect import architect_node
from backend.agents.engineer import engineer_node
from backend.agents.qa_tester import qa_tester_node
from backend.agents.packager import packager_node

def create_graph() -> StateGraph:
    """Creates and compiles the LangGraph StateMachine."""
    graph = StateGraph(SDKJobState)

    # Add nodes
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("researcher", researcher_node)
    graph.add_node("architect", architect_node)
    graph.add_node("engineer", engineer_node)
    graph.add_node("qa_tester", qa_tester_node)
    graph.add_node("packager", packager_node)

    # Set entry point
    graph.set_entry_point("supervisor")

    # Every agent reports back to Supervisor
    graph.add_edge("researcher", "supervisor")
    graph.add_edge("architect", "supervisor")
    graph.add_edge("engineer", "supervisor")
    graph.add_edge("qa_tester", "supervisor")
    
    # Packager is the final deterministic step
    graph.add_edge("packager", END)

    # Supervisor routes via conditional edge
    graph.add_conditional_edges(
        "supervisor",
        route_next,
        {
            "researcher": "researcher",
            "architect":  "architect",
            "engineer":   "engineer",
            "qa_tester":  "qa_tester",
            "packager":   "packager",
            "end":        END,
        }
    )

    return graph.compile()
