"""Hotelbeds Booking API tools. All requests are fixed to the Hotelbeds test host."""

from __future__ import annotations

import hashlib
import os
import time
from datetime import date
from typing import Any

import bookingapi
from dotenv import load_dotenv
from geopy.geocoders import Nominatim
from langchain.tools import tool

load_dotenv()

HOTELBEDS_TEST_HOST = "https://api.test.hotelbeds.com/hotel-api"
HOTELBEDS_API_VERSION = "1.0"


def _api_client() -> bookingapi.ApiClient:
    """Create a fresh signed client; never permit configuration to select live."""
    api_key = os.getenv("HOTELBEDS_API_KEY")
    secret = os.getenv("HOTELBEDS_SECRET")
    if not api_key or not secret:
        raise RuntimeError("Set HOTELBEDS_API_KEY and HOTELBEDS_SECRET to use Hotelbeds sandbox.")

    signature = hashlib.sha256(f"{api_key}{secret}{int(time.time())}".encode()).hexdigest()
    client = bookingapi.ApiClient(host=HOTELBEDS_TEST_HOST)
    client.set_default_header("api-key", api_key)
    client.set_default_header("x-signature", signature)
    return client


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _model_dict(value: Any) -> Any:
    """Recursively convert generated Swagger models into state-safe values."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return [_model_dict(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _model_dict(item) for key, item in value.items()}
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return _model_dict(to_dict())
    return str(value)


def _location_coordinates(location: str) -> tuple[float, float]:
    geocoder = Nominatim(user_agent="ai-travel-hotel-search")
    point = geocoder.geocode(location, timeout=10)
    if point is None:
        raise ValueError(f"Couldn't resolve hotel location: {location}")
    return float(point.latitude), float(point.longitude)


def _validate_dates(check_in_date: str, check_out_date: str) -> None:
    check_in = date.fromisoformat(check_in_date)
    check_out = date.fromisoformat(check_out_date)
    if check_out <= check_in:
        raise ValueError("Hotel check-out must be after check-in.")


def _normalize_availability(response: Any) -> list[dict[str, Any]]:
    hotel_list = _field(_field(response, "hotels"), "hotels", []) or []
    single_hotel = _field(response, "hotel")
    hotels = hotel_list or ([single_hotel] if single_hotel is not None else [])
    options: list[dict[str, Any]] = []
    for hotel in hotels:
        hotel_code = _field(hotel, "code")
        rooms = _field(hotel, "rooms", _field(hotel, "room", [])) or []
        for room in rooms:
            for rate in _field(room, "rates", []) or []:
                rate_key = _field(rate, "rate_key") or _field(rate, "rateKey")
                if not rate_key:
                    continue
                policy = _field(rate, "cancellation_policy", []) or []
                options.append({
                    "option_id": str(len(options) + 1),
                    "hotel_code": hotel_code,
                    "hotel_name": _field(hotel, "name", "Unknown hotel"),
                    "destination": _field(hotel, "destination_name"),
                    "category": _field(hotel, "category_name"),
                    "latitude": _field(hotel, "latitude"),
                    "longitude": _field(hotel, "longitude"),
                    "room_code": _field(room, "code"),
                    "room_name": _field(room, "name"),
                    "rate_key": rate_key,
                    "board": _field(rate, "board_name"),
                    "selling_rate": _field(rate, "selling_rate"),
                    "currency": _field(hotel, "currency") or _field(rate, "hotel_currency"),
                    "rate_type": _field(rate, "rate_type"),
                    "payment_type": _field(rate, "payment_type"),
                    "cancellation_policy": _model_dict(policy),
                    "rate_comments": _field(rate, "rate_comments"),
                })
    return options


@tool
def search_hotels(
    name: str,
    check_in_date: str,
    check_out_date: str,
    adults: int = 1,
    children_ages: list[int] | None = None,
) -> list[dict[str, Any]]:
    """Search Hotelbeds sandbox availability for a location and stay dates."""
    _validate_dates(check_in_date, check_out_date)
    if adults < 1:
        raise ValueError("At least one adult is required.")
    ages = children_ages or []
    if any(age < 0 or age > 17 for age in ages):
        raise ValueError("Child ages must be between 0 and 17.")

    from datetime import date as date_type

    latitude, longitude = _location_coordinates(name)
    occupancy = bookingapi.ApiOccupancy(
        rooms=1,
        adults=adults,
        children=len(ages),
        pax=[bookingapi.ApiPax(type="CH", age=age, room_id=1) for age in ages] or None,
    )
    request = bookingapi.AvailabilityRQ(
        stay=bookingapi.ApiStay(
            check_in=date_type.fromisoformat(check_in_date),
            check_out=date_type.fromisoformat(check_out_date),
        ),
        geolocation=bookingapi.ApiGeoLocation(
            latitude=latitude,
            longitude=longitude,
            radius=20,
            unit="km",
        ),
        occupancies=[occupancy],
    )
    response = bookingapi.HotelsApi(api_client=_api_client()).availability(HOTELBEDS_API_VERSION, request)
    return _normalize_availability(response)


@tool
def check_hotel_rate(rate_key: str) -> dict[str, Any]:
    """Recheck a selected Hotelbeds rate before booking; prices and availability may change."""
    request = bookingapi.CheckRateRQ(
        rooms=[bookingapi.ApiBookingRoom(rate_key=rate_key)],
        upselling=True,
    )
    response = bookingapi.CheckratesApi(api_client=_api_client()).check_rate(HOTELBEDS_API_VERSION, request)
    return _model_dict(response)


@tool
def book_hotel(
    rate_key: str,
    holder_name: str,
    holder_surname: str,
    guest_paxes: list[dict[str, Any]],
    client_reference: str,
    confirmed: bool = False,
) -> dict[str, Any]:
    """Confirm a hotel reservation. Call only after the user explicitly confirms the final rate."""
    if confirmed is not True:
        raise ValueError("Booking requires explicit user confirmation.")
    if not holder_name.strip() or not holder_surname.strip():
        raise ValueError("Guest holder name and surname are required.")
    paxes = [bookingapi.ApiPax(**guest) for guest in guest_paxes]
    room = bookingapi.ApiBookingRoom(rate_key=rate_key, paxes=paxes)
    request = bookingapi.BookingRQ(
        holder=bookingapi.ApiHolder(name=holder_name, surname=holder_surname),
        client_reference=client_reference[:20],
        rooms=[room],
    )
    response = bookingapi.BookingsApi(api_client=_api_client()).booking(HOTELBEDS_API_VERSION, request)
    return _model_dict(response)


@tool
def get_hotel_booking(booking_reference: str) -> dict[str, Any]:
    """Retrieve a Hotelbeds booking by its reference."""
    response = bookingapi.BookingsApi(api_client=_api_client()).booking_detail(
        HOTELBEDS_API_VERSION, booking_reference
    )
    return _model_dict(response)


@tool
def cancel_hotel_booking(booking_reference: str, confirmation: str) -> dict[str, Any]:
    """Cancel a booking only after the user repeats the explicit cancellation phrase."""
    if confirmation.strip() != "I CONFIRM HOTEL CANCELLATION":
        raise ValueError("Cancellation requires the exact confirmation: I CONFIRM HOTEL CANCELLATION")
    response = bookingapi.BookingsApi(api_client=_api_client()).booking_cancellation(
        HOTELBEDS_API_VERSION, booking_reference
    )
    return _model_dict(response)


@tool
def change_hotel_booking(
    booking_reference: str,
    hotel_code: int,
    room_code: str,
    rate_key: str,
    mode: str,
    confirmation: str,
) -> dict[str, Any]:
    """Simulate or update a room-rate change; UPDATE requires explicit confirmation."""
    if mode not in {"SIMULATION", "UPDATE"}:
        raise ValueError("mode must be SIMULATION or UPDATE.")
    if mode == "UPDATE" and confirmation.strip() != "I CONFIRM HOTEL CHANGE":
        raise ValueError("Changing a booking requires the exact confirmation: I CONFIRM HOTEL CHANGE")
    hotel = bookingapi.ApiHotel(
        code=hotel_code,
        rooms=[bookingapi.Room(code=room_code, rates=[bookingapi.ApiRate(rate_key=rate_key)])],
    )
    request = bookingapi.BookingChangeRQ(
        booking_id=booking_reference,
        mode=mode,
        booking=bookingapi.ApiBooking(hotel=hotel),
    )
    response = bookingapi.BookingsApi(api_client=_api_client()).booking_change(
        HOTELBEDS_API_VERSION, booking_reference, request
    )
    return _model_dict(response)