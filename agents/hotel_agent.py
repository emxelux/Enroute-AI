"""Deterministic Hotelbeds availability, selection, and booking workflow."""

from __future__ import annotations

import os
from typing import Any

from langchain_core.messages import AIMessage
from langgraph.types import interrupt

from state import TravelState
from tools.hotel_tool import (
    _normalize_availability,
    book_hotel,
    cancel_hotel_booking,
    check_hotel_rate,
    change_hotel_booking,
    get_hotel_booking,
    search_hotels,
)


def _safe_error(exc: Exception) -> str:
    message = str(exc)
    for credential_name in ("HOTELBEDS_API_KEY", "HOTELBEDS_SECRET"):
        credential = os.getenv(credential_name)
        if credential:
            message = message.replace(credential, "[redacted]")
    return message or exc.__class__.__name__


def hotel_agent_node(state: TravelState) -> dict[str, Any]:
    """Search the sandbox once and save compact offers for deterministic selection."""
    if state.get("hotel_management_action"):
        return {"current_agent": "hotel_management"}
    if state.get("hotel_booked"):
        return {"current_agent": "hotel_complete"}
    if state.get("hotel_results"):
        return {"current_agent": "hotel_selection"}

    required = {
        "location": state.get("hotel_location"),
        "check-in date": state.get("hotel_check_in"),
        "check-out date": state.get("hotel_check_out"),
    }
    missing = [label for label, value in required.items() if not value]
    if missing:
        return {
            "messages": [AIMessage(content=f"I need the hotel {', '.join(missing)} before I can search.")],
            "error": f"Missing hotel information: {', '.join(missing)}",
            "current_agent": "hotel_complete",
        }

    try:
        results = search_hotels.invoke({
            "name": state["hotel_location"],
            "check_in_date": state["hotel_check_in"],
            "check_out_date": state["hotel_check_out"],
            "adults": state.get("hotel_adults") or state.get("hotel_guests") or 1,
            "children_ages": state.get("hotel_children_ages") or [],
        })
    except Exception as exc:
        safe_error = _safe_error(exc)
        return {
            "hotel_results": [],
            "error": f"Hotel search failed: {safe_error}",
            "messages": [AIMessage(content=f"I couldn't complete the Hotelbeds sandbox search: {safe_error}")],
            "current_agent": "hotel_complete",
        }

    if not results:
        return {
            "hotel_results": [],
            "messages": [AIMessage(content="Hotelbeds returned no available rooms for those dates and guests. Try another location or dates.")],
            "current_agent": "hotel_complete",
            "error": None,
        }

    display = "\n".join(
        f"{item['option_id']}. {item['hotel_name']} — {item.get('room_name') or item.get('room_code') or 'room'}; "
        f"{item.get('selling_rate', 'price unavailable')} {item.get('currency') or ''}; "
        f"{item.get('board') or 'board unspecified'}"
        for item in results
    )
    return {
        "hotel_results": results,
        "messages": [AIMessage(content=f"Available Hotelbeds sandbox options:\n{display}\n\nReply with an option number to select it.")],
        "current_agent": "hotel_selection",
        "error": None,
    }


def hotel_selection_node(state: TravelState) -> dict[str, Any]:
    """Interrupt for a stable option ID and persist the complete selected rate."""
    results = state.get("hotel_results") or []
    if state.get("hotel_selected"):
        return {"current_agent": "hotel_rate_check"}
    if not results:
        return {"current_agent": "hotel_agent"}

    question = "Which hotel option would you like? Reply with its number."
    valid = {str(item.get("option_id")): item for item in results}
    while True:
        choice = interrupt({
            "type": "hotel_selection",
            "question": question,
            "options": results,
        })
        selected = valid.get(str(choice).strip())
        if selected:
            break
        question = "That option number wasn't recognized. Reply with one of the listed numbers."

    return {
        "hotel_selected": selected,
        "messages": [AIMessage(content=f"Selected {selected['hotel_name']}. Checking the current rate and availability before proceeding.")],
        "current_agent": "hotel_rate_check",
    }


def hotel_rate_check_node(state: TravelState) -> dict[str, Any]:
    """Recheck the selected rate immediately before presenting it for confirmation."""
    selected = state.get("hotel_selected") or {}
    rate_key = selected.get("rate_key")
    if not rate_key:
        return {
            "error": "Selected hotel option has no Hotelbeds rate key.",
            "hotel_selected": None,
            "current_agent": "hotel_selection",
        }

    try:
        response = check_hotel_rate.invoke({"rate_key": rate_key})
        options = _normalize_availability(response)
        updated = next((item for item in options if item.get("rate_key") == rate_key), None)
        if updated is None:
            matching_room = [
                item for item in options
                if item.get("hotel_code") == selected.get("hotel_code")
                and item.get("room_code") == selected.get("room_code")
            ]
            if len(matching_room) == 1:
                updated = matching_room[0]
            else:
                raise ValueError("Hotelbeds did not return the selected rate as currently available.")
        updated["option_id"] = selected.get("option_id", "1")
        return {
            "hotel_rate_checked": updated,
            "hotel_selected": updated,
            "messages": [AIMessage(content="The current Hotelbeds rate has been rechecked.")],
            "current_agent": "hotel_booking_confirm",
            "error": None,
        }
    except Exception as exc:
        safe_error = _safe_error(exc)
        return {
            "hotel_rate_checked": None,
            "messages": [AIMessage(content=f"I couldn't recheck that hotel rate: {safe_error}. Please choose another option.")],
            "error": f"Hotel rate check failed: {safe_error}",
            "hotel_selected": None,
            "current_agent": "hotel_selection",
        }


def hotel_booking_confirm_node(state: TravelState) -> dict[str, Any]:
    """Require an explicit affirmative response before collecting guest details or booking."""
    selected = state.get("hotel_rate_checked") or state.get("hotel_selected")
    if not selected:
        return {"current_agent": "hotel_selection"}
    if state.get("hotel_booked"):
        return {"current_agent": "hotel_complete"}

    question = (
        f"Confirm this Hotelbeds sandbox reservation:\n\n"
        f"{selected.get('hotel_name')} — {selected.get('room_name') or selected.get('room_code')}\n"
        f"Total: {selected.get('selling_rate', 'unavailable')} {selected.get('currency') or ''}\n"
        f"Board: {selected.get('board') or 'unspecified'}\n"
        f"Cancellation policy: {selected.get('cancellation_policy') or 'not supplied'}\n\n"
        "Reply yes to continue, or no to return to the hotel options."
    )
    while True:
        answer = interrupt({"type": "hotel_booking_confirmation", "question": question, "hotel_details": selected})
        if isinstance(answer, str) and answer.strip().casefold() in {"yes", "y", "confirm"}:
            return {
                "messages": [AIMessage(content="Please provide the lead guest's name and surname, plus each guest's name, surname, and whether they are an adult or child (include each child's age). No booking is placed until the details are supplied.")],
                "current_agent": "hotel_booking",
            }
        if isinstance(answer, str) and answer.strip().casefold() in {"no", "n", "cancel"}:
            return {
                "hotel_selected": None,
                "hotel_rate_checked": None,
                "messages": [AIMessage(content="Hotel booking not placed. Choose another option if you would like to continue.")],
                "current_agent": "hotel_selection",
            }
        question = "Please reply yes to continue with this booking or no to return to the hotel options."


def hotel_booking_node(state: TravelState) -> dict[str, Any]:
    """Collect real guest details and confirm the selected Hotelbeds rate."""
    selected = state.get("hotel_rate_checked") or state.get("hotel_selected") or {}
    rate_key = selected.get("rate_key")
    if not rate_key:
        return {"messages": [AIMessage(content="No current hotel rate is selected.")], "current_agent": "hotel_selection"}
    if state.get("hotel_booked"):
        return {"current_agent": "hotel_complete"}

    guest_input = interrupt({
        "type": "hotel_guest_details",
        "question": "Provide JSON with holder_name, holder_surname, and guests (each guest has name, surname, type: AD or CH, and age for children). Use real guest details; the booking API will be called after validation.",
        "adults": state.get("hotel_adults") or state.get("hotel_guests") or 1,
        "children_ages": state.get("hotel_children_ages") or [],
    })
    if not isinstance(guest_input, dict):
        return {"messages": [AIMessage(content="Guest details must be supplied as a structured object. No booking was placed.")], "current_agent": "hotel_booking_confirm"}

    guests = guest_input.get("guests") or []
    if not guests or any(not guest.get("name") or not guest.get("surname") for guest in guests):
        return {"messages": [AIMessage(content="Each guest needs a real first and last name. No booking was placed; please provide complete guest details.")], "current_agent": "hotel_booking"}
    paxes: list[dict[str, Any]] = []
    for guest in guests:
        pax_type = str(guest.get("type", "")).upper()
        if pax_type not in {"AD", "CH"}:
            return {"messages": [AIMessage(content="Guest type must be AD or CH. No booking was placed.")], "current_agent": "hotel_booking"}
        pax = {"type": pax_type, "name": guest["name"], "surname": guest["surname"], "room_id": 1}
        if pax_type == "CH":
            age = guest.get("age")
            if not isinstance(age, int) or not 0 <= age <= 17:
                return {"messages": [AIMessage(content="Each child must have an age from 0 to 17. No booking was placed.")], "current_agent": "hotel_booking"}
            pax["age"] = age
        paxes.append(pax)

    expected_adults = state.get("hotel_adults") or state.get("hotel_guests") or 1
    expected_child_ages = state.get("hotel_children_ages") or []
    actual_child_ages = sorted(pax["age"] for pax in paxes if pax["type"] == "CH")
    if sum(pax["type"] == "AD" for pax in paxes) != expected_adults or actual_child_ages != sorted(expected_child_ages):
        return {
            "messages": [AIMessage(content="Guest counts or child ages don't match the availability search. Please provide the same party composition used for the hotel search; no booking was placed.")],
            "current_agent": "hotel_booking",
        }

    try:
        reference = str(state.get("thread_id") or "hotel")[:20]
        booking = book_hotel.invoke({
            "rate_key": rate_key,
            "holder_name": str(guest_input.get("holder_name", "")),
            "holder_surname": str(guest_input.get("holder_surname", "")),
            "guest_paxes": paxes,
            "client_reference": reference,
            "confirmed": True,
        })
    except Exception as exc:
        safe_error = _safe_error(exc)
        return {
            "error": f"Hotel booking failed: {safe_error}",
            "messages": [AIMessage(content=f"Hotelbeds couldn't confirm the reservation: {safe_error}. No successful booking was recorded.")],
            "current_agent": "hotel_booking_confirm",
        }

    booking_data = booking.get("booking", booking) if isinstance(booking, dict) else booking
    return {
        "hotel_booked": booking,
        "hotel_booking_reference": booking_data.get("reference") if isinstance(booking_data, dict) else None,
        "hotel_booking_status": booking_data.get("status") if isinstance(booking_data, dict) else None,
        "hotel_guest_details": guest_input,
        "messages": [AIMessage(content=f"Hotel reservation confirmed. Reference: {booking_data.get('reference', 'not returned') if isinstance(booking_data, dict) else 'not returned'}; status: {booking_data.get('status', 'unknown') if isinstance(booking_data, dict) else 'unknown'}.")],
        "current_agent": "hotel_complete",
        "error": None,
    }


def hotel_management_node(state: TravelState) -> dict[str, Any]:
    """Handle an existing booking by reference with explicit destructive-action gates."""
    action = (state.get("hotel_management_action") or "").casefold()
    reference = state.get("hotel_booking_reference")
    if not reference:
        return {"messages": [AIMessage(content="Please provide the Hotelbeds booking reference.")], "current_agent": "hotel_management_complete"}
    if action not in {"detail", "cancel", "change"}:
        return {"messages": [AIMessage(content="I can retrieve, cancel, or change a Hotelbeds booking. Which action do you need?")], "current_agent": "hotel_management_complete"}

    try:
        detail = get_hotel_booking.invoke({"booking_reference": reference})
    except Exception as exc:
        safe_error = _safe_error(exc)
        return {
            "error": f"Hotel booking lookup failed: {safe_error}",
            "messages": [AIMessage(content=f"I couldn't retrieve Hotelbeds booking {reference}: {safe_error}")],
            "current_agent": "hotel_management_complete",
        }
    if action == "detail":
        return {
            "hotel_booked": detail,
            "messages": [AIMessage(content=f"Hotelbeds booking details for {reference}: {detail}")],
            "current_agent": "hotel_management_complete",
            "error": None,
        }

    if action == "cancel":
        answer = interrupt({
            "type": "hotel_cancellation_confirmation",
            "question": f"I found booking {reference}. Review the booking and cancellation policy below, then reply exactly 'I CONFIRM HOTEL CANCELLATION' to proceed, or anything else to keep the booking.\n\n{detail}",
            "booking": detail,
        })
        if not isinstance(answer, str) or answer.strip() != "I CONFIRM HOTEL CANCELLATION":
            return {"messages": [AIMessage(content="Hotel cancellation was not submitted; the booking remains unchanged.")], "current_agent": "hotel_management_complete"}
        try:
            result = cancel_hotel_booking.invoke({"booking_reference": reference, "confirmation": answer.strip()})
            return {
                "hotel_booked": result,
                "hotel_booking_status": "CANCELLED",
                "messages": [AIMessage(content=f"Hotelbeds cancellation response: {result}")],
                "current_agent": "hotel_management_complete",
                "error": None,
            }
        except Exception as exc:
            safe_error = _safe_error(exc)
            return {"error": f"Hotel cancellation failed: {safe_error}", "messages": [AIMessage(content=f"Hotelbeds could not cancel booking {reference}: {safe_error}")], "current_agent": "hotel_management_complete"}

    hotel_code = state.get("hotel_change_hotel_code")
    room_code = state.get("hotel_change_room_code")
    rate_key = state.get("hotel_change_rate_key")
    if not all((hotel_code, room_code, rate_key)):
        return {"messages": [AIMessage(content="To change this booking, provide the replacement Hotelbeds hotel code, room code, and rate key. No change was submitted.")], "current_agent": "hotel_management_complete"}
    try:
        simulation = change_hotel_booking.invoke({
            "booking_reference": reference,
            "hotel_code": hotel_code,
            "room_code": room_code,
            "rate_key": rate_key,
            "mode": "SIMULATION",
            "confirmation": "",
        })
    except Exception as exc:
        safe_error = _safe_error(exc)
        return {"error": f"Hotel change simulation failed: {safe_error}", "messages": [AIMessage(content=f"Hotelbeds couldn't simulate the requested change: {safe_error}")], "current_agent": "hotel_management_complete"}
    answer = interrupt({
        "type": "hotel_change_confirmation",
        "question": f"Review the Hotelbeds change simulation. Reply exactly 'I CONFIRM HOTEL CHANGE' to apply it, or anything else to leave the booking unchanged.\n\n{simulation}",
        "simulation": simulation,
    })
    if not isinstance(answer, str) or answer.strip() != "I CONFIRM HOTEL CHANGE":
        return {"messages": [AIMessage(content="Hotel booking change was not submitted; the original booking remains unchanged.")], "current_agent": "hotel_management_complete"}
    try:
        result = change_hotel_booking.invoke({
            "booking_reference": reference,
            "hotel_code": hotel_code,
            "room_code": room_code,
            "rate_key": rate_key,
            "mode": "UPDATE",
            "confirmation": answer.strip(),
        })
        return {
            "hotel_booked": result,
            "messages": [AIMessage(content=f"Hotelbeds booking change response: {result}")],
            "current_agent": "hotel_management_complete",
            "error": None,
        }
    except Exception as exc:
        safe_error = _safe_error(exc)
        return {"error": f"Hotel booking change failed: {safe_error}", "messages": [AIMessage(content=f"Hotelbeds couldn't apply the change: {safe_error}")], "current_agent": "hotel_management_complete"}
