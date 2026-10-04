from typing import Optional, Dict, Any, List
from typing_extensions import Annotated
from langgraph.graph import MessagesState
from dataclasses import field
from langgraph.graph.message import add_messages


class TravelState(MessagesState):
    messages: Annotated[list, add_messages]
    thread_id: Optional[str] = None
    user_country: Optional[str] = None
    user_query: Optional[str] = None
    trip_details: Dict[str, Any] = field(
        default_factory=dict
    )
    flight_origin: Optional[str] = None
    flight_destination: Optional[str] = None
    flight_departure_date: Optional[str] = None
    flight_return_date: Optional[str] = None
    flight_cabin_class: Optional[str] = None

    flight_passengers: Optional[
        Dict[str, int]
    ] = None

    flight_results: Optional[
        List[Dict]
    ] = None

    flight_selected: Optional[
        Dict
    ] = None

    flight_booked: Optional[
        Dict
    ] = None

    flight_order: Optional[
        Dict
    ] = None

    hotel_location: Optional[str] = None
    hotel_check_in: Optional[str] = None
    hotel_check_out: Optional[str] = None
    hotel_guests: Optional[int] = None
    hotel_adults: Optional[int] = None
    hotel_children_ages: Optional[List[int]] = None

    hotel_results: Optional[
        List[Dict]
    ] = None

    hotel_selected: Optional[
        Dict
    ] = None

    hotel_rate_checked: Optional[Dict] = None
    hotel_guest_details: Optional[Dict[str, Any]] = None
    hotel_booked: Optional[Dict[str, Any]] = None
    hotel_booking_reference: Optional[str] = None
    hotel_booking_status: Optional[str] = None
    hotel_management_action: Optional[str] = None
    hotel_change_hotel_code: Optional[int] = None
    hotel_change_room_code: Optional[str] = None
    hotel_change_rate_key: Optional[str] = None

    current_agent: Optional[str] = None

    needs_flight: bool = False
    needs_hotel: bool = False

    ready_for_payment: bool = False
    trip_complete: bool = False
    final_response:str = None
    error: Optional[str] = None