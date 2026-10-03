
from typing import Any

from langchain_core.messages import AIMessage
from langgraph.types import interrupt

from state import TravelState
from tools.flight_tool import search_flight


def _passenger_count(passengers: dict[str, Any] | None, *keys: str, default: int = 0) -> int:
    if not passengers:
        return default
    for key in keys:
        if key in passengers and passengers[key] is not None:
            return int(passengers[key])
    return default


def _format_flight_option(index: int, flight: dict[str, Any]) -> str:
    itinerary = []
    for slice_info in flight.get("slices", []):
        origin = slice_info.get("origin", {}).get("code", "?")
        destination = slice_info.get("destination", {}).get("code", "?")
        
        itinerary.append(
            f"{origin} → {destination} | "
            f"{slice_info.get('departure') or 'time unavailable'}–"
            f"{slice_info.get('arrival') or 'time unavailable'} | "
            f"{slice_info.get('stops', 0)} stop(s)"
        )

    price = flight.get("total_amount", "?")
    currency = flight.get("total_currency", "")
    airline = next(
        (part.get("airline") for part in flight.get("slices", []) if part.get("airline")),
        "Airline unavailable",
    )
    offer_id = flight.get("offer_id", "unavailable")
    return (
        f"{index}. {airline} — {price} {currency}\n"
        f"   {'; '.join(itinerary)}\n"
        f"   Offer ID: {offer_id}"
    )


def flight_agent_node(state: TravelState) -> dict[str, Any]:
    """Search Duffel for flights and save the options before asking the user."""
    if state.get("flight_selected"):
        return {"current_agent": "flight_complete"}

    existing_results = state.get("flight_results")
    if existing_results is not None:
        return {"current_agent": "flight_selection"}

    required = {
        "origin": state.get("flight_origin"),
        "destination": state.get("flight_destination"),
        "departure date": state.get("flight_departure_date"),
    }
    missing = [label for label, value in required.items() if not value]
    if missing:
        return {
            "messages": [AIMessage(content=f"I need the flight {', '.join(missing)} before I can search.")],
            "error": f"Missing flight information: {', '.join(missing)}",
            "current_agent": "flight_agent",
        }

    passengers = state.get("flight_passengers")
    adults = _passenger_count(passengers, "adults", "adult", default=1)
    children = _passenger_count(passengers, "children", "child", default=0)
    try:
        results = search_flight(
            origin_airport=state["flight_origin"],
            destination_airport=state["flight_destination"],
            cabin_class=state.get("flight_cabin_class") or "economy",
            departure_date=state["flight_departure_date"],
            return_date=state.get("flight_return_date"),
            no_of_adult=adults,
            no_of_children=children,
        )
    except Exception as exc:
        return {
            "flight_results": [],
            "error": f"Flight search failed: {exc}",
            "messages": [AIMessage(content="I couldn't complete the flight search. Please check the trip details and try again.")],
            "current_agent": "flight_agent",
        }

    results = results or []
    if not results:
        return {
            "flight_results": [],
            "messages": [AIMessage(content="I couldn't find any flights for those trip details. Please try different dates or airports.")],
            "current_agent": "flight_agent",
        }

    options = "\n\n".join(
        _format_flight_option(index, flight)
        for index, flight in enumerate(results, start=1)
    )
    return {
        "flight_results": results,
        "messages": [AIMessage(content=f"Here are the available flights:\n\n{options}\n\nChoose a flight by its number or offer ID.")],
        "current_agent": "flight_selection",
        "error": None,
    }


def _selected_flight(selection: Any, results: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not isinstance(selection, str):
        selection = str(selection)
    choice = selection.strip()
    if not choice:
        return None

    for flight in results:
        if choice.casefold() == str(flight.get("offer_id", "")).casefold():
            return flight

    # Accept a numbered option, optionally phrased as "flight 2" or "option 2".
    import re

    match = re.fullmatch(r"(?:flight|option)?\s*(\d+)", choice, flags=re.IGNORECASE)
    if match:
        index = int(match.group(1)) - 1
        if 0 <= index < len(results):
            return results[index]
    return None


def flight_selection_node(state: TravelState) -> dict[str, Any]:
    """Pause for the user's choice and store the chosen offer in flight_selected."""
    if state.get("flight_selected"):
        return {"current_agent": "flight_complete"}

    results = state.get("flight_results") or []
    if not results:
        return {"current_agent": "flight_agent"}

    question = "Which flight would you like? Reply with its number or offer ID."
    while True:
        selection = interrupt({
            "type": "flight_selection",
            "question": question,
            "options": results,
        })
        selected = _selected_flight(selection, results)
        if selected is not None:
            break
        question = "That didn't match an option. Please reply with a listed flight number or offer ID."

    return {
        "flight_selected": selected,
        "messages": [AIMessage(content=f"Flight {selected.get('offer_id', '')} selected.")],
        "current_agent": "flight_complete",
    }
