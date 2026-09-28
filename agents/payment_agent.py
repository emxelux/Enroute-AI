"""
Payment Agent - Handles payment processing for booked travel.
Placeholder for now - integrate with Duffel Payments, Stripe, etc.
"""
from typing import Literal
from langchain_core.messages import SystemMessage, AIMessage
from langgraph.types import Command

from state import TravelState


PAYMENT_AGENT_PROMPT = """You are the Payment Agent. Process payment for the user's booked travel.

Current booking:
- Flight: {flight_details}
- Hotel: {hotel_details}
- Total estimated cost: {total_cost}
- User country: {user_country}

Instructions:
1. Present the total cost in user's currency
2. Ask for payment confirmation
3. Process payment (integrate with payment provider)
4. Confirm booking completion

For now, this is a placeholder. In production, integrate with:
- Duffel Payments
- Stripe
- Or other payment provider"""


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

    # For now, just inform user and mark complete
    message = AIMessage(content=(
        f"Your trip is ready for payment:\n"
        f"✈️ Flight: {flight_details}\n"
        f"🏨 Hotel: {hotel_details}\n\n"
        f"Payment integration coming soon. Your booking details have been saved."
    ))

    return Command(
        goto="__end__",
        update={
            "messages": [system_msg, message],
            "trip_complete": True,
            "current_agent": "complete"
        }
    )