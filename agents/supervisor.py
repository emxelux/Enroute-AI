from typing import Annotated, Optional
import uuid

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.types import interrupt
from typing_extensions import TypedDict

from state import TravelState
from llm.provider import create_chat_model_pair, invoke_with_rate_limit_fallback
from tools.tavily_tool import tavily_search

load_dotenv()

base_llm, fallback_llm = create_chat_model_pair(
    "supervisor",
    groq_default="qwen/qwen3.8-27b",
)

with open("prompts/travel_classifier.md", "r", encoding="utf-8") as file:
    TRAVEL_CLASSIFIER_PROMPT = file.read()

with open("prompts/extraction_prompt.md", "r", encoding="utf-8") as file:
    TRAVEL_EXTRACTOR_PROMPT = file.read()


class ClassifyQuery(TypedDict):
    is_travel: Annotated[bool, ..., "Whether the request is travel-related."]


class NeedHotel(TypedDict):
    MISSING: Annotated[bool, ..., "Whether hotel requirements still need clarification."]
    needs_accomodation: Annotated[bool, ..., "Whether accommodation is needed."]


class TravelInfo(TypedDict):
    needs_flight: Annotated[bool, ..., "Whether the user needs a flight."]
    needs_hotel: NeedHotel
    flight_origin: Annotated[Optional[str], ..., "Origin airport IATA code."]
    flight_destination: Annotated[Optional[str], ..., "Destination airport IATA code."]
    flight_departure_date: Annotated[Optional[str], ..., "Flight departure date, YYYY-MM-DD."]
    flight_return_date: Annotated[Optional[str], ..., "Flight return date, YYYY-MM-DD, if applicable."]
    hotel_location: Annotated[Optional[str], ..., "Hotel location, if accommodation is needed."]
    hotel_check_in: Annotated[Optional[str], ..., "Hotel check-in date, YYYY-MM-DD."]
    hotel_check_out: Annotated[Optional[str], ..., "Hotel check-out date, YYYY-MM-DD."]
    missing_information: Annotated[Optional[str], ..., "Question requesting all missing trip details."]


def classify_travel_query(query: str) -> bool:
    messages = [
        SystemMessage(content=TRAVEL_CLASSIFIER_PROMPT),
        HumanMessage(content=query),
    ]
    classifier = base_llm.with_structured_output(ClassifyQuery)
    fallback_classifier = fallback_llm.with_structured_output(ClassifyQuery)
    response = invoke_with_rate_limit_fallback(
        classifier,
        fallback_classifier,
        messages,
    )
    return response["is_travel"]


def get_today_date() -> str:
    """Return today's date in YYYY-MM-DD format."""
    from datetime import date

    return date.today().isoformat()


def extract_travel_information(messages: list):
    extractor = create_agent(
        model=base_llm,
        tools=[get_today_date, tavily_search],
        response_format=TravelInfo,
        system_prompt=TRAVEL_EXTRACTOR_PROMPT,
    )
    fallback_extractor = create_agent(
        model=fallback_llm,
        tools=[get_today_date, tavily_search],
        response_format=TravelInfo,
        system_prompt=TRAVEL_EXTRACTOR_PROMPT,
    )
    agent_input = {"messages": messages}
    response = invoke_with_rate_limit_fallback(
        extractor,
        fallback_extractor,
        agent_input,
    )
    return response["structured_response"]


def supervisor_node(state: TravelState) -> dict:
    """Extract trip details, asking for clarification until required data exists."""
    thread_id = str(uuid.uuid4())
    conversation = list(state.get("messages", []))
    latest_message = conversation[-1] if conversation else None
    latest_query = getattr(latest_message, "content", None)
    if latest_query is None and isinstance(latest_message, dict):
        latest_query = latest_message.get("content", "")

    if not classify_travel_query(str(latest_query or "")):
        return {
            "messages": [AIMessage(content="Sorry, I'm a travel-only assistant. Please ask a travel-related question.")]
        }

    while True:
        try:
            travel_info = extract_travel_information(conversation)
        except Exception as exc:
            return {
                "error": f"Travel information extraction failed: {exc}",
                "messages": [AIMessage(content="I couldn't process those trip details. Please try again.")],
            }

        needs_flight = travel_info["needs_flight"]
        needs_hotel = travel_info["needs_hotel"]
        missing_flight = needs_flight and any(
            travel_info.get(field) in (None, "", "MISSING")
            for field in ("flight_origin", "flight_destination", "flight_departure_date")
        )
        missing_hotel = needs_hotel.get("MISSING", False)

        if not missing_flight and not missing_hotel:
            break

        answer = interrupt({
            "type": "missing_information",
            "question": travel_info.get("missing_information") or "Please provide the missing trip details.",
        })
        conversation.append(HumanMessage(content=str(answer)))

    result = {
        "messages": conversation + [AIMessage(content="Travel information extracted successfully.")],
        "needs_flight": needs_flight,
        "needs_hotel": needs_hotel["needs_accomodation"],
        "thread_id": thread_id,
    }
    if needs_flight:
        result.update({
            "flight_origin": travel_info["flight_origin"],
            "flight_destination": travel_info["flight_destination"],
            "flight_departure_date": travel_info["flight_departure_date"],
            "flight_return_date": travel_info["flight_return_date"],
        })
    if needs_hotel["needs_accomodation"]:
        result.update({
            "hotel_location": travel_info["hotel_location"],
            "hotel_check_in": travel_info["hotel_check_in"],
            "hotel_check_out": travel_info["hotel_check_out"],
        })
    return result