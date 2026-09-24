import requests


def get_city_coordinates(city: str):
    """
    Gets the coorinates of a city or region by name,

    Args: 
    city: str = City/Region name (specify state or country, so it knows where you're talking about)
    """
    url = "https://nominatim.openstreetmap.org/search"

    params = {
        "q": city,
        "format": "json",
        "limit": 1,
    }

    headers = {
        "User-Agent": "AITravelAgent/1.0"
    }

    response = requests.get(
        url,
        params=params,
        headers=headers,
        timeout=10
    )

    response.raise_for_status()

    results = response.json()

    if not results:
        raise ValueError(f"Could not find location: {city}")

    location = results[0]

    return {
        "latitude": float(location["lat"]),
        "longitude": float(location["lon"]),
        "display_name": location["display_name"],
    }