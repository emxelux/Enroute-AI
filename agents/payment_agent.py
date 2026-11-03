"""Payment stage guard for travel selections that have not been booked."""
from typing import Literal
from langchain_core.messages import SystemMessage, AIMessage
from langgraph.types import Command

from state import TravelState


PAYMENT_AGENT_PROMPT = """You are the Payment Agent. The application cannot process payments yet.

Current selection (not a confirmed booking):
- Flight: {flight_details}
- Hotel: {hotel_details}
- Total estimated cost: {total_cost}
- User country: {user_country}

Do not claim a booking or payment was completed. Clearly tell the user that
the selection is retained but no reservation or charge was made."""


def payment_agent_node(state: TravelState) -> Command[Literal["supervisor", "__end__"]]:
    """
    Payment agent node - processes payment.
    """
    flight_selected = state.get("flight_selected")
    hotel_selected = state.get("hotel_selected")
    user_country = state.get("user_country", "US")

    flight_details = "Not booked"
    hotel_details = "Not booked"

    if flight_selected:
        flight_details = f"{flight_selected.get('airline', 'Unknown')} - {flight_selected.get('origin', '')} to {flight_selected.get('destination', '')}"

    if hotel_selected:
        hotel_details = hotel_selected.get("hotel_name", "Unknown hotel")

    system_msg = SystemMessage(content=PAYMENT_AGENT_PROMPT.format(
        flight_details=flight_details,
        hotel_details=hotel_details,
        total_cost="TBD (integrate pricing)",
        user_country=user_country
    ))

    message = AIMessage(content=(
        f"Your travel selections are saved, but the trip is not booked:\n"
        f"✈️ Flight: {flight_details}\n"
        f"🏨 Hotel: {hotel_details}\n\n"
        "No reservation or payment was made. Booking and payment processing "
        "are not available in this app yet."
    ))

    return Command(
        goto="__end__",
        update={
            "messages": [system_msg, message],
            "trip_complete": False,
            "ready_for_payment": False,
            "current_agent": "payment_unavailable"
        }
    )