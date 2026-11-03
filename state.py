from typing import List, Optional, Dict, Any
from typing_extensions import TypedDict
from langgraph.graph import MessagesState


class TravelState(MessagesState):
    """
    State for the Travel Agent workflow.
    Inherits from MessagesState to get message handling.
    """
    # User context
    user_id: Optional[str] = None
    user_country: Optional[str] = None  # For currency conversion

    # Trip details collected
    trip_details: Dict[str, Any] = {}

    # Flight specific
    flight_origin: Optional[str] = None
    flight_destination: Optional[str] = None
    flight_departure_date: Optional[str] = None
    flight_return_date: Optional[str] = None
    flight_cabin_class: Optional[str] = None
    flight_passengers: Optional[Dict[str, int]] = None  # {"adults": 2, "children": 1}
    flight_results: Optional[List[Dict]] = None
    flight_selected: Optional[Dict] = None

    # Hotel specific
    hotel_location: Optional[str] = None
    hotel_check_in: Optional[str] = None
    hotel_check_out: Optional[str] = None
    hotel_guests: Optional[int] = None
    hotel_results: Optional[List[Dict]] = None
    hotel_selected: Optional[Dict] = None

    # Workflow control
    current_agent: Optional[str] = None  # "supervisor", "flight", "hotel", "payment"
    needs_flight: bool = False
    needs_hotel: bool = False
    ready_for_payment: bool = False
    trip_complete: bool = False

    # Error handling
    error: Optional[str] = None