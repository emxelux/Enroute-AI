"""
Main LangGraph workflow
"""
from langgraph.graph import StateGraph, START, END
from state import TravelState
from agents.supervisor import supervisor_node
from agents.flight_agent import (
    flight_agent_node,
    flight_selection_node,
    flight_booking_confirm_node,
    flight_booking_node,
)
from agents.hotel_agent import (
    hotel_agent_node,
    hotel_selection_node,
    hotel_rate_check_node,
    hotel_booking_confirm_node,
    hotel_booking_node,
    hotel_management_node,
)


def _after_flight(state):
    return "hotel_agent" if state.get("needs_hotel") else END

def create_travel_graph(checkpointer):
    graph = StateGraph(TravelState)

    # Add nodes
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("flight_agent", flight_agent_node)
    graph.add_node("flight_selection", flight_selection_node)
    graph.add_node("flight_booking_confirm", flight_booking_confirm_node)
    graph.add_node("flight_booking", flight_booking_node)
    graph.add_node("hotel_agent", hotel_agent_node)
    graph.add_node("hotel_selection", hotel_selection_node)
    graph.add_node("hotel_rate_check", hotel_rate_check_node)
    graph.add_node("hotel_booking_confirm", hotel_booking_confirm_node)
    graph.add_node("hotel_booking", hotel_booking_node)
    graph.add_node("hotel_management", hotel_management_node)

    # Add edges
    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        lambda state: (
            "flight_agent" if state.get("needs_flight")
            else "hotel_agent" if state.get("needs_hotel") or state.get("hotel_management_action")
            else END
        ),
        {"flight_agent": "flight_agent", "hotel_agent": "hotel_agent", END: END},
    )
    graph.add_edge("flight_agent", "flight_selection")
    graph.add_conditional_edges(
        "flight_selection",
        lambda state: (
            _after_flight(state)
            if state.get("current_agent") == "flight_complete"
            else state.get("current_agent", "flight_booking_confirm")
        ),
        {
            "flight_booking_confirm": "flight_booking_confirm",
            "flight_agent": "flight_agent",
            "hotel_agent": "hotel_agent",
            END: END,
        },
    )
    graph.add_conditional_edges(
        "flight_booking_confirm",
        lambda state: (
            _after_flight(state)
            if state.get("current_agent") == "flight_complete"
            else state.get("current_agent", "flight_booking")
        ),
        {
            "flight_booking": "flight_booking",
            "flight_selection": "flight_selection",
            "hotel_agent": "hotel_agent",
            END: END,
        },
    )
    graph.add_conditional_edges(
        "flight_booking",
        _after_flight,
        {"hotel_agent": "hotel_agent", END: END},
    )

    graph.add_conditional_edges(
        "hotel_agent",
        lambda state: state.get("current_agent", "hotel_selection"),
        {
            "hotel_selection": "hotel_selection",
            "hotel_management": "hotel_management",
            "hotel_complete": END,
        },
    )
    graph.add_edge("hotel_management", END)
    graph.add_conditional_edges(
        "hotel_selection",
        lambda state: state.get("current_agent", "hotel_rate_check"),
        {
            "hotel_rate_check": "hotel_rate_check",
            "hotel_agent": "hotel_agent",
            "hotel_complete": END,
        },
    )
    graph.add_conditional_edges(
        "hotel_rate_check",
        lambda state: state.get("current_agent", "hotel_booking_confirm"),
        {
            "hotel_booking_confirm": "hotel_booking_confirm",
            "hotel_selection": "hotel_selection",
        },
    )
    graph.add_conditional_edges(
        "hotel_booking_confirm",
        lambda state: state.get("current_agent", "hotel_booking"),
        {
            "hotel_booking": "hotel_booking",
            "hotel_selection": "hotel_selection",
            "hotel_complete": END,
        },
    )
    graph.add_conditional_edges(
        "hotel_booking",
        lambda state: state.get("current_agent", "hotel_complete"),
        {
            "hotel_booking": "hotel_booking",
            "hotel_booking_confirm": "hotel_booking_confirm",
            "hotel_selection": "hotel_selection",
            "hotel_complete": END,
        },
    )

    return graph.compile(checkpointer=checkpointer)