"""
Main LangGraph workflow
"""
from langgraph.graph import StateGraph, START, END
from state import TravelState
from agents.supervisor import supervisor_node
from agents.flight_agent import flight_agent_node, flight_tools_node

def create_travel_graph(checkpointer):
    graph = StateGraph(TravelState)

    # Add nodes
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("flight_agent", flight_agent_node)
    graph.add_node("flight_tools", flight_tools_node)

    # Add edges
    graph.add_edge(START, "supervisor")
    graph.add_edge("supervisor", "flight_agent")
    # graph.add_edge("flight_agent", "flight_tools")
    # graph.add_edge("flight_tools", "flight_agent")
    graph.add_edge("flight_agent", "supervisor")
    graph.add_edge("supervisor", END)

    return graph.compile(checkpointer=checkpointer)