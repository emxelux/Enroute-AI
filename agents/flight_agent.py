
from typing import Any

from langchain_core.messages import AIMessage
from langgraph.types import interrupt

from state import TravelState
from tools.flight_tool import search_flight, book_flight, build_passenger_for_booking, build_payment


def _passenger_count(passengers: dict[str, Any] | None, *keys: str, default: int = 0) -> int:
    if not passengers:
        return default
    for key in keys:
        if key in passengers and passengers[key] is not None:
            return int(passengers[key])
    return default


def _format_flight_options(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Map each offer ID to its full flight record."""
    return {
        str(offer_id): flight
        for flight in results
        if (offer_id := flight.get("offer_id")) is not None
    }




def flight_agent_node(state: TravelState) -> dict[str, Any]:
    """Search Duffel for flights and save the options before asking the user."""
    if state.get("flight_selected"):
        return {"current_agent": "flight_complete"}

    existing_results = state.get("flight_results")
    if existing_results:
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

    options = _format_flight_options(results)
    if not options:
        return {
            "flight_results": [],
            "messages": [AIMessage(content="The flight search returned no flights with offer IDs. Please try again.")],
            "current_agent": "flight_agent",
        }

    offer_ids = "\n".join(options)
    return {
        "flight_results": results,
        "messages": [AIMessage(content=f"Here are the available flight offer IDs:\n{offer_ids}")],
        "current_agent": "flight_selection",
        "error": None,
    }

def _selected_flight(
    selection: Any,
    options: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if not isinstance(selection, str):
        selection = str(selection)
    choice = selection.strip().casefold()
    if not choice:
        return None

    for offer_id, flight in options.items():
        if choice == offer_id.casefold():
            return flight
    return None

def flight_selection_node(state: TravelState) -> dict[str, Any]:
    """Pause for the user's offer ID and store the matching flight record."""
    if state.get("flight_selected"):
        return {"current_agent": "flight_booking_confirm"}

    results = state.get("flight_results") or []
    options = _format_flight_options(results)
    if not options:
        return {"current_agent": "flight_agent"}

    question = "Which flight would you like? Reply with its offer ID."
    while True:
        selection = interrupt({
            "type": "flight_selection",
            "question": question,
            "options": options,
        })
        selected = _selected_flight(selection, options)
        if selected is not None:
            break
        question = "That offer ID didn't match. Please reply with one of the listed offer IDs."

    return {
        "flight_selected": selected,
        "messages": [AIMessage(content=f"Flight {selected.get('offer_id', '')} selected.")],
        "current_agent": "flight_booking_confirm",
    }


def _format_flight_for_confirmation(flight: dict[str, Any]) -> str:
    """Format flight details for user confirmation."""
    slices = flight.get("slices", [])
    slice_strs = []
    for s in slices:
        slice_strs.append(
            f"{s['origin']['code']} → {s['destination']['code']} | "
            f"Dep: {s['departure']} | Arr: {s['arrival']} | "
            f"Airline: {s.get('airline', 'N/A')} | "
            f"Stops: {s.get('stops', 0)}"
        )
    return (
        f"Offer ID: {flight.get('offer_id')}\n"
        f"Trip Type: {flight.get('trip_type')}\n"
        f"Total: {flight.get('total_amount')} {flight.get('total_currency')}\n"
        f"Expires: {flight.get('expires_at')}\n"
        f"Slices:\n" + "\n".join(slice_strs)
    )


def flight_booking_confirm_node(state: TravelState) -> dict[str, Any]:
    """Ask user to confirm before booking the selected flight."""
    if state.get("flight_booked"):
        return {"current_agent": "flight_complete"}

    selected = state.get("flight_selected")
    if not selected:
        return {"current_agent": "flight_selection"}

    flight_details = _format_flight_for_confirmation(selected)
    question = (
        f"Please confirm you want to book this flight:\n\n"
        f"{flight_details}\n\n"
        f"Reply 'yes' to confirm or 'no' to cancel."
    )

    while True:
        confirmation = interrupt({
            "type": "flight_booking_confirmation",
            "question": question,
            "flight_details": selected,
        })
        if isinstance(confirmation, str):
            choice = confirmation.strip().casefold()
            if choice in ("yes", "y", "confirm"):
                return {
                    "messages": [AIMessage(content="Booking your flight...")],
                    "current_agent": "flight_booking",
                }
            elif choice in ("no", "n", "cancel"):
                return {
                    "messages": [AIMessage(content="Flight booking cancelled.")],
                    "flight_selected": None,
                    "current_agent": "flight_selection",
                }

        question = "Please reply 'yes' to confirm or 'no' to cancel."


def _build_passengers(state: TravelState) -> list[dict]:
    """Build passenger list from state for booking using Duffel API v2 format.

    Note: Duffel API v2 requires `passengers[].id` from the offer request.
    Required fields: id, title, given_name, family_name, born_on, gender, email, phone_number
    Gender must be one of: "m", "f", "x"
    """
    selected = state.get("flight_selected") or {}
    offer_passengers = selected.get("passengers") or []
    passengers = state.get("flight_passengers") or {}
    adults = passengers.get("adults", 1)
    children = passengers.get("children", 0)
    total_passengers = adults + children

    # For now, create placeholder passengers - in production these would come from user input
    passenger_list = []
    for i in range(total_passengers):
        # Get the passenger ID from the offer request (REQUIRED for v2)
        offer_pax = offer_passengers[i] if i < len(offer_passengers) else {}
        pax_id = offer_pax.get("id")
        is_adult = i < adults

        if not pax_id:
            raise ValueError(f"Missing passenger ID from offer request for passenger index {i}")

        # Build passenger details (in production, these would come from user input)
        passenger_details = {
            "title": "mr" if is_adult else "miss",
            "given_name": "Adult" if is_adult else "Child",
            "family_name": "Passenger",
            "born_on": "1990-01-01" if is_adult else "2015-01-01",
            "gender": "m" if is_adult else "f",  # Duffel v2 uses "m", "f", "x"
            "email": "traveler@example.com" if is_adult else "child@example.com",
            "phone_number": "+442080160508",
        }

        # Use the helper function to build properly formatted passenger
        passenger = build_passenger_for_booking(offer_pax, passenger_details)
        passenger_list.append(passenger)

    return passenger_list


def flight_booking_node(state: TravelState) -> dict[str, Any]:
    """Book the selected flight using Duffel's order creation API (v2).

    Creates a hold order by default (no immediate payment required).
    Payment can be added later via the payments endpoint if needed.
    """
    if state.get("flight_booked"):
        return {"current_agent": "flight_complete"}

    selected = state.get("flight_selected")
    if not selected:
        return {
            "messages": [AIMessage(content="No flight selected for booking.")],
            "current_agent": "flight_selection",
        }

    offer_id = selected.get("offer_id")
    if not offer_id:
        return {
            "messages": [AIMessage(content="Selected flight is missing offer ID.")],
            "current_agent": "flight_selection",
        }

    try:
        passengers = _build_passengers(state)

        # Create a hold order (pay later) by default
        # In production, you might want to check offer.payment_requirements.requires_instant_payment
        order = book_flight(
            offer_id=offer_id,
            passengers=passengers,
            hold=True,  # Creates a hold order - no payment required upfront
        )

        return {
            "flight_booked": order,
            "flight_order": order,
            "messages": [
                AIMessage(content=(
                    f"✅ Flight booked successfully (hold order)!\n"
                    f"Booking Reference: {order.get('booking_reference', 'N/A')}\n"
                    f"Order ID: {order.get('id', 'N/A')}\n"
                    f"Status: {order.get('status', 'N/A')}\n"
                    f"Payment Required By: {order.get('payment_required_by', 'N/A')}"
                ))
            ],
            "current_agent": "flight_complete",
            "error": None,
        }
    except Exception as exc:
        return {
            "messages": [AIMessage(content=f"Booking failed: {exc}")],
            "error": f"Flight booking failed: {exc}",
            "current_agent": "flight_booking_confirm",
        }