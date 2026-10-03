import os
from dotenv import load_dotenv

load_dotenv()

duffel_access_token = os.getenv("DUFFEL_ACCESS_TOKEN")
if duffel_access_token:
    os.environ["DUFFEL_ACCESS_TOKEN"] = duffel_access_token

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


# @tool
def search_flight(
    origin_airport:str,
    destination_airport:str,
    cabin_class:str | None,
    departure_date: str,
    return_date: str | None = None,
    no_of_adult: int = 1,
    no_of_children:int | None = 0,
    ):
    """
    Search for available flight in real-time.
    Args:
    origin_airport:str = 3 letter IATA airport code of the origin airport,
    destination_airport:str = 3 letter IATA airport code of the destination airport,
    cabin_class:str = One of ["economy", "premium_economy", "business", "first" ],
    departure_date:str = Departure date of the flight in strictly in YYYY-MM-DD format,
    return_date:str = (Optional) return date in YYYY-MM-DD format,
    no_of_adult:int= number of adults,
    no_of_children:int = number of children
    """
    if no_of_adult < 0 or no_of_children < 0:
        raise ValueError("Passenger counts cannot be negative")
    if no_of_adult + no_of_children == 0:
        raise ValueError("At least one passenger is required")

    client = Duffel()
    slices = [{
        "origin": origin_airport,
        "destination": destination_airport,
        "departure_date": departure_date,
    }]
    if return_date:
        slices.append({
            "origin": destination_airport,
            "destination": origin_airport,
            "departure_date": return_date,
        })

    passengers = ([{"type": "adult"}] * no_of_adult) + ([{"type": "child"}] * no_of_children)
    offer_request = client.create_offer_request(
        slices=slices,
        cabin_class=cabin_class,
        passengers=passengers,
    )

    relevant_flights = [
        offer
        for offer in offer_request.get("offers", [])
        if offer.get("slices")
        and offer["slices"][0].get("origin", {}).get("iata_code") == origin_airport
        and offer["slices"][0].get("destination", {}).get("iata_code") == destination_airport
    ]
    relevant_flights.sort(
        key=lambda offer: float(offer.get("total_amount") or "inf")
    )

    return [_compact_offer(offer) for offer in relevant_flights[:3]]

ans = search_flight(origin_airport = "ABV", 
destination_airport="MAN", 
cabin_class="business", departure_date="2026-10-31")

if ans:
    import json
    with open("flight_out.json", "w") as f:
        json.dump(ans, f, indent=4)