"""
Supervisor Agent - Entry point for all user queries.
Classifies intent and routes to appropriate sub-agents.
"""
from typing import Literal
from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.types import Command

from state import TravelState
from llm.flight_llm import flight_llm
from llm.hotel_llm import hotel_llm
from tools.tavily_tool import tavily_search
from typing_extensions import TypedDict, Annotated

# Initialize the supervisor LLM

class ClassifyQuery(TypedDict):
    is_travel: Annotated[bool, ..., "Is the query a travel related topic or not"]


c_llm = init_chat_model("groq:llama-3.1-8b-instant")
supervisor_llm = init_chat_model("groq:openai/gpt-oss-120b")
classifier_llm = c_llm.with_structured_output(ClassifyQuery)

with open("prompts/classifier.md", "f") as f:
    TRAVEL_CLASSIFIER_PROMPT = f.read()

with open("prompts/supervisor_prompt.md") as f:
    SUPERVISOR_PROMPT = f.read()


def classify_travel_query(query: str) -> bool:
    """Classify if query is travel-related."""
    messages = [
        SystemMessage(content=TRAVEL_CLASSIFIER_PROMPT),
        HumanMessage(content=query)
    ]
    response = supervisor_llm.invoke(messages)
    return response["is_travel"]


def supervisor_node(state: TravelState) -> Command[Literal["flight_agent", "hotel_agent", "payment_agent", "__end__"]]:
    """
    Supervisor node - routes to appropriate agent based on trip state.
    """
    # Get the last user message
    messages = state.get("messages", [])
    last_user_msg = None
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_user_msg = msg.content
            break

    if not last_user_msg:
        return Command(goto="__end__", update={"messages": [AIMessage(content="How can I help you with your travel plans?")]})

    # First, classify if travel-related
    if not classify_travel_query(last_user_msg):
        return Command(
            goto="__end__",
            update={
                "messages": [AIMessage(content="I'm a travel-only assistant. I can help you with flights, hotels, and trip planning. For other questions, please use a general-purpose assistant.")]
            }
        )

    # Build context for supervisor decision
    needs_flight = state.get("needs_flight", False)
    needs_hotel = state.get("needs_hotel", False)
    flight_booked = state.get("flight_selected") is not None
    hotel_booked = state.get("hotel_selected") is not None
    user_country = state.get("user_country", "US")

    # Determine what's needed from the query
    # This is a simplified version - in production, use LLM to parse
    flight_details_complete = all([
        state.get("flight_origin"),
        state.get("flight_destination"),
        state.get("flight_departure_date"),
    ])

    hotel_details_complete = all([
        state.get("hotel_location"),
        state.get("hotel_check_in"),
        state.get("hotel_check_out"),
    ])

    # Decision logic
    if not flight_booked and needs_flight and not flight_details_complete:
        return Command(
            goto="flight_agent",
            update={"current_agent": "flight_agent"}
        )

    if not hotel_booked and needs_hotel and not hotel_details_complete:
        return Command(
            goto="hotel_agent",
            update={"current_agent": "hotel_agent"}
        )

    if needs_flight and not flight_booked and flight_details_complete:
        return Command(
            goto="flight_agent",
            update={"current_agent": "flight_agent"}
        )

    if needs_hotel and not hotel_booked and hotel_details_complete:
        return Command(
            goto="hotel_agent",
            update={"current_agent": "hotel_agent"}
        )

    # Both booked or not needed - go to payment
    if (flight_booked or not needs_flight) and (hotel_booked or not needs_hotel):
        return Command(
            goto="payment_agent",
            update={"current_agent": "payment_agent", "ready_for_payment": True}
        )

    # Need clarification
    clarification_msg = _generate_clarification_message(state)
    return Command(
        goto="__end__",
        update={"messages": [AIMessage(content=clarification_msg)]}
    )


def _generate_clarification_message(state: TravelState) -> str:
    """Generate a clarification message based on missing information."""
    missing = []

    if state.get("needs_flight") and not state.get("flight_selected"):
        if not state.get("flight_origin"):
            missing.append("departure city/airport")
        if not state.get("flight_destination"):
            missing.append("destination city/airport")
        if not state.get("flight_departure_date"):
            missing.append("departure date")
        if not state.get("flight_passengers"):
            missing.append("number of passengers")

    if state.get("needs_hotel") and not state.get("hotel_selected"):
        if not state.get("hotel_location"):
            missing.append("hotel location/city")
        if not state.get("hotel_check_in"):
            missing.append("check-in date")
        if not state.get("hotel_check_out"):
            missing.append("check-out date")

    if missing:
        return f"I need a few more details to help you: {', '.join(missing)}. Could you please provide these?"

    return "Let me help you with that. What would you like to do next?"