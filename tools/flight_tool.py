import os
from dotenv import load_dotenv
import requests as rt
from langchain.tools import tool

load_dotenv()


os.environ["DUFFEL_ACCESS_TOKEN"] = os.getenv("DUFFEL_ACCESS_TOKEN")

from Duffel.duffelpy import Duffel


def _compact_offer(offer: dict) -> dict:
    """Keep only the offer and itinerary details needed for selection/booking."""
    slices = []

    for flight_slice in offer.get("slices", []):
        segments = flight_slice.get("segments", [])
        origin = flight_slice.get("origin", {})
        destination = flight_slice.get("destination", {})
        first_segment = segments[0] if segments else {}
        last_segment = segments[-1] if segments else {}
        carrier = (
            first_segment.get("operating_carrier")
            or first_segment.get("marketing_carrier")
            or {}
        )

        slices.append({
            "slice_id": flight_slice.get("id"),
            "origin": {
                "code": origin.get("iata_code"),
                "airport": origin.get("name"),
            },
            "destination": {
                "code": destination.get("iata_code"),
                "airport": destination.get("name"),
            },
            "departure": first_segment.get("departing_at"),
            "arrival": last_segment.get("arriving_at"),
            "stops": max(
                len(segments) - 1,
                sum(len(segment.get("stops", [])) for segment in segments),
            ),
            "airline": carrier.get("name"),
            "flight_numbers": [
                segment.get("marketing_carrier_flight_number")
                for segment in segments
                if segment.get("marketing_carrier_flight_number")
            ],
        })

    trip_type = {
        1: "one-way",
        2: "round-trip",
    }.get(len(slices), "multi-city")

    return {
        "offer_id": offer.get("id"),
        "expires_at": offer.get("expires_at"),
        "total_amount": offer.get("total_amount"),
        "total_currency": offer.get("total_currency"),
        "trip_type": trip_type,
        "slices": slices,
    }


@tool
def search_flight(
    origin_airport:str, 
    destination_airport:str,
    cabin_class:str,
    departure_date: str,
    no_of_adult: int = None,
    no_of_children:int = None,
    ):
    """
    Search for available flight in real-time.
    Args:
    origin_airport:str = 3 letter IATA airport code of the origin airport,
    destination_airport:str = 3 letter IATA airport code of the destination airport,
    cabin_class:str = One of ["economy", "premium_economy", "business", "first" ],
    departure_date:str = Departure date of the flight in strictly in YYYY-MM-DD format,
    no_of_adult:int= (Optional) if there is adult, number of adult,
    no_of_children:int = (Optional) if there is children onboard, number of children
    """
    client = Duffel()
    if no_of_children and no_of_adult:
        offer_request = client.create_offer_request(
            slices = [
                {"origin": origin_airport, "destination": destination_airport, "departure_date": departure_date}
            ],
            cabin_class=cabin_class,
            passengers=[
                {"type": "adult", "adult": no_of_adult},
                {"type": "child", "child": no_of_children}
            ]        
        )

    if not no_of_children and no_of_adult:
        offer_request = client.create_offer_request(
            slices = [
                {"origin": origin_airport, "destination": destination_airport, "departure_date": departure_date}
            ],
            cabin_class=cabin_class,
            passengers=[
                {"type": "adult", "adult": no_of_adult},
            ]        
        )
    if no_of_children and not no_of_adult:
        offer_request = client.create_offer_request(
            slices = [
                {"origin": origin_airport, "destination": destination_airport, "departure_date": departure_date}
            ],
            cabin_class=cabin_class,
            passengers=[
                {"type": "child", "child": no_of_children}
            ]        
        )
    relevant_flights = [
        offer
        for offer in offer_request.get("offers", [])
        if any(
            flight_slice.get("origin", {}).get("iata_code") == origin_airport
            and flight_slice.get("destination", {}).get("iata_code") == destination_airport
            for flight_slice in offer.get("slices", [])
        )
    ]
    relevant_flights.sort(
        key=lambda offer: float(offer.get("total_amount") or "inf")
    )

    return [_compact_offer(offer) for offer in relevant_flights[:3]]
