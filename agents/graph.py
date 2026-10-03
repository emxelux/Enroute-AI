"""
Main LangGraph workflow
"""
from langgraph.graph import StateGraph, START, END
from state import TravelState
from agents.supervisor import supervisor_node
from agents.flight_agent import flight_agent_node, flight_selection_node

def create_travel_graph(checkpointer):
    graph = StateGraph(TravelState)

    # Add nodes
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("flight_agent", flight_agent_node)
    graph.add_node("flight_selection", flight_selection_node)

    # Add edges
    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        lambda state: "flight_agent" if state.get("needs_flight") else END,
        {"flight_agent": "flight_agent", END: END},
    )
    graph.add_edge("flight_agent", "flight_selection")
    graph.add_edge("flight_selection", END)

    return graph.compile(checkpointer=checkpointer)