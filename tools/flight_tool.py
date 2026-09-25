import os
from dotenv import load_dotenv
import requests as rt
import serpapi
from langchain.tools import tool
load_dotenv()


os.environ["DUFFEL_ACCESS_TOKEN"] = os.getenv("DUFFEL_ACCESS_TOKEN")

from Duffel.duffelpy import Duffel


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
                {"type": "children", "adult": no_of_children}
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
                {"type": "children", "adult": no_of_children}
            ]        
        )
    relevant_flights = []
    for offers in offer_request["offers"]:
        for flight in offers["slices"]:
            origin_iata = flight["origin"]["iata_code"]
            destination_iata = flight["destination"]['iata_code']

            if (origin_iata == origin_airport) and (destination_iata == destination_airport):
                relevant_flights.append(offers)
    
    