"""
Main LangGraph workflow - wires together supervisor, flight, hotel, and payment agents.
"""
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.memory import MemorySaver

from state import TravelState
from agents.supervisor import supervisor_node, classify_travel_query
from agents.flight_agent import flight_agent_node, flight_tools_node
from agents.hotel_agent import hotel_agent_node, hotel_tools_node
from agents.payment_agent import payment_agent_node


def create_travel_graph(checkpointer=None):
    """
    Create the travel agent workflow graph.

    Args:
        checkpointer: LangGraph checkpointer (PostgresSaver for production, MemorySaver for dev)

    Returns:
        Compiled graph
    """
    graph = StateGraph(TravelState)

    # Add nodes
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("flight_agent", flight_agent_node)
    graph.add_node("flight_tools", flight_tools_node)
    graph.add_node("hotel_agent", hotel_agent_node)
    graph.add_node("hotel_tools", hotel_tools_node)
    graph.add_node("payment_agent", payment_agent_node)

    # Add edges
    graph.add_edge(START, "supervisor")

    # Supervisor routes to agents - handled by Command in supervisor_node
    # Flight agent -> tools -> flight_agent (loop) or supervisor
    graph.add_edge("flight_tools", "flight_agent")
    # Hotel agent -> tools -> hotel_agent (loop) or supervisor
    graph.add_edge("hotel_tools", "hotel_agent")
    # Payment agent -> END (handled by Command in payment_agent_node)

    # Compile with checkpointer
    if checkpointer is None:
        checkpointer = MemorySaver()

    return graph.compile(checkpointer=checkpointer)