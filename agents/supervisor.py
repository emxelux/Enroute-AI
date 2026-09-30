"""
Supervisor Agent
----------------
Entry point for travel-related user queries.

Responsibilities:
1. Understand the user's travel request.
2. Extract structured travel information.
3. Update TravelState.
4. Detect missing high-level information.
5. Ask the user for missing information when necessary.
6. Route to the appropriate domain agent.

The supervisor does NOT perform flight/hotel searches.
Those responsibilities belong to the domain agents.
"""

from typing import Optional, Literal

from langchain.chat_models import init_chat_model
from langchain_core.messages import (
    SystemMessage,
    HumanMessage,
    AIMessage,
)
from langgraph.types import Command, interrupt
from typing_extensions import TypedDict

from state import TravelState


base_llm = init_chat_model(
    "groq:llama-3.1-8b-instant"
)

with open("prompts/travel_classifier.md", "r", encoding="utf-8") as f:
    TRAVEL_CLASSIFIER_PROMPT = f.read()

with open("prompts/supervisor_prompt.md", "r", encoding="utf-8") as f:
    SUPERVISOR_PROMPT = f.read()

class ClassifyQuery(TypedDict):
    is_travel: bool


class TravelExtraction(TypedDict):
    needs_flight: bool
    needs_hotel: bool
    origin_country: Optional[str]
    flight_origin: Optional[str]
    flight_destination: Optional[str]
    flight_departure_date: Optional[str]
    flight_return_date: Optional[str]
    flight_cabin_class: Optional[str]
    adults: Optional[int]
    children: Optional[int]
    infants: Optional[int]
    hotel_location: Optional[str]
    hotel_check_in: Optional[str]
    hotel_check_out: Optional[str]
    hotel_guests: Optional[int]



classifier_llm = base_llm.with_structured_output(
    ClassifyQuery
)

travel_extractor_llm = base_llm.with_structured_output(
    TravelExtraction
)

def classify_travel_query(query: str) -> bool:
    """
    Determine whether the user's message is travel-related.
    """

    messages = [
        SystemMessage(
            content=TRAVEL_CLASSIFIER_PROMPT
        ),
        HumanMessage(
            content=query
        ),
    ]

    response = classifier_llm.invoke(messages)

    return response["is_travel"]


def extract_travel_information(
    query: str,
) -> TravelExtraction:
    """
    Extract all relevant travel information from the
    user's latest message in a single LLM call.
    """

    messages = [
        SystemMessage(
            content=SUPERVISOR_PROMPT
        ),
        HumanMessage(
            content=query
        ),
    ]

    response = travel_extractor_llm.invoke(messages)

    return response


def build_state_update(
    extraction: TravelExtraction,
) -> dict:
    """
    Convert the structured LLM extraction into a LangGraph
    state update.

    Only non-null values are written to the state.
    This prevents the latest message from accidentally
    overwriting previously collected information with None.
    """

    update = {
        "needs_flight": extraction["needs_flight"],
        "needs_hotel": extraction["needs_hotel"],
    }

    if extraction["origin_country"]:
        update["user_country"] = extraction["origin_country"]


    if extraction["flight_origin"]:
        update["flight_origin"] = extraction["flight_origin"]

    if extraction["flight_destination"]:
        update["flight_destination"] = (
            extraction["flight_destination"]
        )

    if extraction["flight_departure_date"]:
        update["flight_departure_date"] = (
            extraction["flight_departure_date"]
        )

    if extraction["flight_return_date"]:
        update["flight_return_date"] = (
            extraction["flight_return_date"]
        )

    if extraction["flight_cabin_class"]:
        update["flight_cabin_class"] = (
            extraction["flight_cabin_class"]
        )

    passenger_information = {}

    if extraction["adults"] is not None:
        passenger_information["adults"] = extraction["adults"]

    if extraction["children"] is not None:
        passenger_information["children"] = (
            extraction["children"]
        )

    if extraction["infants"] is not None:
        passenger_information["infants"] = (
            extraction["infants"]
        )

    if passenger_information:
        update["flight_passengers"] = passenger_information


    if extraction["hotel_location"]:
        update["hotel_location"] = (
            extraction["hotel_location"]
        )

    if extraction["hotel_check_in"]:
        update["hotel_check_in"] = (
            extraction["hotel_check_in"]
        )

    if extraction["hotel_check_out"]:
        update["hotel_check_out"] = (
            extraction["hotel_check_out"]
        )

    if extraction["hotel_guests"] is not None:
        update["hotel_guests"] = (
            extraction["hotel_guests"]
        )

    return update



def get_missing_information(
    state: TravelState,
) -> list:
    """
    Determine whether the current travel state is missing
    information required before domain agents can work.
    """

    missing = []

    # ========================================================
    # Flight
    # ========================================================

    if state.get("needs_flight"):

        if not state.get("flight_origin"):
            missing.append("flight departure location")

        if not state.get("flight_destination"):
            missing.append("flight destination")

        if not state.get("flight_departure_date"):
            missing.append("flight departure date")

        passengers = state.get("flight_passengers")

        if not passengers:
            missing.append("number of passengers")

    # ========================================================
    # Hotel
    # ========================================================

    if state.get("needs_hotel"):

        if not state.get("hotel_location"):
            missing.append("hotel location")

        if not state.get("hotel_check_in"):
            missing.append("hotel check-in date")

        if not state.get("hotel_check_out"):
            missing.append("hotel check-out date")

        if not state.get("hotel_guests"):
            missing.append("number of hotel guests")

    return missing



def request_missing_information(
    missing: list[str],
):
    """
    Pause the graph and ask the user for missing information.
    """

    question = (
        "I need a few more details before I can continue:\n\n"
        + "\n".join(
            f"- {item}"
            for item in missing
        )
        + "\n\nPlease provide the missing information."
    )

    response = interrupt({
        "type": "missing_travel_information",
        "missing": missing,
        "question": question,
    })

    return response



def determine_next_agent(
    state: TravelState,
) -> Literal[
    "flight_agent",
    "hotel_agent",
    "payment_agent",
    "__end__",
]:
    """
    Decide which agent should execute next.

    This function only looks at state.
    It does not call an LLM.
    """

    needs_flight = state.get("needs_flight", False)
    needs_hotel = state.get("needs_hotel", False)

    flight_done = (
        not needs_flight
        or state.get("flight_selected") is not None
    )

    hotel_done = (
        not needs_hotel
        or state.get("hotel_selected") is not None
    )

    
    if flight_done and hotel_done:

        if needs_flight or needs_hotel:
            return "payment_agent"

        return "__end__"

    if needs_flight and not state.get("flight_selected"):
        return "flight_agent"

  
    if needs_hotel and not state.get("hotel_selected"):
        return "hotel_agent"

    return "__end__"


def supervisor_node(state: TravelState):
    messages = state.get("messages", [])

    if not messages:
        return Command(
            goto="__end__",
            update={
                "error": "No user message found."
            },
        )

  
    user_query = None

    for message in reversed(messages):

        if isinstance(message, HumanMessage):
            user_query = message.content
            break

    if not user_query:
        return Command(
            goto="__end__",
            update={
                "error": "No user message found."
            },
        )

    is_travel = classify_travel_query(
        user_query
    )

    if not is_travel:

        return Command(
            goto="__end__",
            update={
                "messages": [
                    AIMessage(
                        content=(
                            "I'm a travel-only assistant. "
                            "I can help with flights, hotels, "
                            "and trip planning."
                        )
                    )
                ]
            },
        )

    extraction = extract_travel_information(
        user_query
    )

    state_update = build_state_update(
        extraction
    )

   
    validation_state = {
        **state,
        **state_update,
    }

    missing = get_missing_information(
        validation_state
    )

    if missing:

        response = request_missing_information(
            missing
        )

        return Command(
            goto="supervisor",
            update={
                **state_update,
                "messages": [
                    HumanMessage(
                        content=str(response)
                    )
                ],
            },
        )

    next_agent = determine_next_agent(
        validation_state
    )

    state_update["current_agent"] = next_agent

    return Command(
        goto=next_agent,
        update=state_update,
    )