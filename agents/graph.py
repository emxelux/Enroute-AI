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


def create_postgres_checkpointer():
    """Create PostgreSQL checkpointer for production."""
    import os
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")
    return PostgresSaver.from_conn_string(database_url)


# For development/testing
travel_graph = create_travel_graph()


def run_travel_agent(user_message: str, thread_id: str = "default", user_id: str = None, user_country: str = "US"):
    """
    Run the travel agent with a user message.

    Args:
        user_message: User's input
        thread_id: Conversation thread ID
        user_id: User ID from authentication
        user_country: User's country for currency conversion

    Returns:
        Final state after processing
    """
    from langchain_core.messages import HumanMessage

    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "messages": [HumanMessage(content=user_message)],
        "user_id": user_id,
        "user_country": user_country,
    }

    result = travel_graph.invoke(initial_state, config=config)
    return result


if __name__ == "__main__":
    # Test the graph
    print("Testing travel agent graph...")
    result = run_travel_agent("I want to fly from Lagos to Abuja next Friday")
    print(f"Messages: {result.get('messages', [])}")
    print(f"Current agent: {result.get('current_agent')}")
    print(f"Needs flight: {result.get('needs_flight')}")
    print(f"Flight origin: {result.get('flight_origin')}")