import os
from dotenv import load_dotenv

load_dotenv()

duffel_access_token = os.getenv("DUFFEL_ACCESS_TOKEN")
if duffel_access_token:
    os.environ["DUFFEL_ACCESS_TOKEN"] = duffel_access_token

from Duffel.duffelpy import Duffel


def _compact_offer(offer: dict, offer_request_passengers: list[dict] | None = None) -> dict:
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

    result = {
        "offer_id": offer.get("id"),
        "expires_at": offer.get("expires_at"),
        "total_amount": offer.get("total_amount"),
        "total_currency": offer.get("total_currency"),
        "trip_type": trip_type,
        "slices": slices,
    }
    if offer_request_passengers:
        result["passengers"] = offer_request_passengers
    return result


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

    # Extract passenger IDs from the offer request for later booking
    offer_request_passengers = offer_request.get("passengers", [])

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

    return [_compact_offer(offer, offer_request_passengers) for offer in relevant_flights[:3]]

# ans = search_flight(origin_airport = "ABV", 
# destination_airport="MAN", 
# cabin_class="business", departure_date="2026-10-31")

# if ans:
#     import json
#     with open("flight_out.json", "w") as f:
#         json.dump(ans, f, indent=4)


def book_flight(
    offer_id: str,
    passengers: list[dict],
    payments: list[dict] | None = None,
    hold: bool = True,
    services: list[dict] | None = None,
) -> dict:
    """
    Book a flight offer using Duffel's order creation API (API v2).

    Args:
        offer_id: The ID of the offer to book
        passengers: List of passenger details. Each must include:
            - id (required): Passenger ID from the offer request
            - title: mr, mrs, ms, miss, mstr, etc.
            - given_name: First name
            - family_name: Last name
            - born_on: Date of birth (YYYY-MM-DD)
            - gender: "m", "f", or "x"
            - email: Email address
            - phone_number: E.164 format (e.g., "+1234567890")
            - identity_documents (optional): List of {type, unique_identifier, issuing_country_code, expires_on}
            - loyalty_programme_accounts (optional): List of {airline_iata_code, account_number}
        payments: Required when hold=False. List of payment objects:
            - type: "balance" | "card" | "arc_bsp_cash"
            - amount: String amount (e.g., "30.20")
            - currency: ISO 4217 code (e.g., "GBP")
            - three_d_secure_session_id: Required for card payments
        hold: If True, creates a hold order (no payment required). If False, creates instant order requiring payment.
        services: Optional ancillary services [{id, quantity}]

    Returns:
        Order details including booking reference, tickets, etc.
    """
    client = Duffel()

    # Create the order with the selected offer and passenger details
    order_request = client.create_order(
        selected_offers=[offer_id],
        passengers=passengers,
        payments=payments,
        services=services,
        hold=hold,
    )

    return order_request


def build_passenger_for_booking(
    offer_request_passenger: dict,
    passenger_details: dict,
) -> dict:
    """
    Build a passenger object for Duffel order creation.

    Args:
        offer_request_passenger: The passenger object from the offer request (must contain 'id')
        passenger_details: Dictionary with passenger details:
            - title: "mr", "mrs", "ms", "miss", "mstr"
            - given_name: First name
            - family_name: Last name
            - born_on: "YYYY-MM-DD"
            - gender: "m", "f", or "x"
            - email: Email address
            - phone_number: E.164 format
            - identity_documents (optional): List of identity document dicts
            - loyalty_programme_accounts (optional): List of loyalty programme dicts

    Returns:
        Passenger dict formatted for Duffel API v2 order creation
    """
    passenger = {
        "id": offer_request_passenger["id"],
        "title": passenger_details.get("title", "mr"),
        "given_name": passenger_details["given_name"],
        "family_name": passenger_details["family_name"],
        "born_on": passenger_details["born_on"],
        "gender": passenger_details["gender"],
        "email": passenger_details["email"],
        "phone_number": passenger_details["phone_number"],
    }

    # Add optional identity documents if provided
    if passenger_details.get("identity_documents"):
        passenger["identity_documents"] = passenger_details["identity_documents"]

    # Add optional loyalty programme accounts if provided
    if passenger_details.get("loyalty_programme_accounts"):
        passenger["loyalty_programme_accounts"] = passenger_details["loyalty_programme_accounts"]

    return passenger


def build_payment(
    payment_type: str,
    amount: str,
    currency: str,
    three_d_secure_session_id: str | None = None,
) -> dict:
    """
    Build a payment object for Duffel order creation.

    Args:
        payment_type: "balance" | "card" | "arc_bsp_cash"
        amount: Amount as string (e.g., "30.20")
        currency: ISO 4217 currency code (e.g., "GBP")
        three_d_secure_session_id: Required for card payments

    Returns:
        Payment dict formatted for Duffel API v2
    """
    payment = {
        "type": payment_type,
        "amount": amount,
        "currency": currency,
    }

    if payment_type == "card" and three_d_secure_session_id:
        payment["three_d_secure_session_id"] = three_d_secure_session_id

    return payment