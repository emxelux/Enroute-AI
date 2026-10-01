from typing import Optional, Dict, Any, List
from typing_extensions import Annotated
from langgraph.graph import MessagesState
from dataclasses import field
from langgraph.graph.message import add_messages


class TravelState(MessagesState):
    messages: Annotated[list, add_messages]
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
    hotel_location: Optional[str] = None
    hotel_check_in: Optional[str] = None
    hotel_check_out: Optional[str] = None
    hotel_guests: Optional[int] = None

    hotel_results: Optional[
        List[Dict]
    ] = None

    hotel_selected: Optional[
        Dict
    ] = None

    current_agent: Optional[str] = None

    needs_flight: bool = False
    needs_hotel: bool = False

    ready_for_payment: bool = False
    trip_complete: bool = False
    final_response:str = None
    error: Optional[str] = None