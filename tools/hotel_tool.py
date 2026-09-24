import os
from dotenv import load_dotenv
from langchain.tools import tool


import serpapi


load_dotenv()

@tool
def search_hotels(name: str, check_in_date: str, check_out_date:str) -> list:
    """
    Tool to search for hotels in a location or by name,
    Args: 

    name: str = City name, location, or hotel name (as specified from the query),
    check_in_date: Date to check in hotel YYYY-MM-DD format strictly,
    check_out_date: Date to check out hotel YYYY-MM-DD format strictly,
    """

    client = serpapi.Client(api_key=os.getenv("SERPAPI_KEY"))
    results = client.search({
    "engine": "google_hotels",
    "q": name,
    "check_in_date": check_in_date,
    "check_out_date": check_out_date
    })
    properties = results["properties"]
    hotels = []
    for hotel in properties:
        hotel_name = hotel["name"]
        hotel_link = hotel['Property_details_link']
        nearby_places = hotel["nearby_places"]
        ratings = hotel["ratings"]
        total_score = sum(item["stars"] * item["count"] for item in ratings)
        total_reviews = sum(item["count"] for item in ratings)
        average_rating = total_score / total_reviews if total_reviews > 0 else 0.0
        hotel_data = {
            "hotel_name": hotel_name,
            "hotel_link": hotel_link,
            "nearby_places": nearby_places,
            "hotel_rating": average_rating
        }
        hotels.append(hotel_data)
    return hotels
