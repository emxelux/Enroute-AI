from functools import lru_cache

import airportsdata
import requests


@lru_cache(maxsize=1)
def _airports_by_city() -> dict[str, list[dict]]:
    """Load local airport coordinates, grouped by city for offline lookups."""
    airports = airportsdata.load("IATA")
    by_city: dict[str, list[dict]] = {}
    for airport in airports.values():
        city = airport.get("city")
        if city and airport.get("lat") is not None and airport.get("lon") is not None:
            by_city.setdefault(city.casefold(), []).append(airport)
    return by_city


def _coordinates_from_airport_data(city: str) -> dict | None:
    """Use the main airport as a local city-coordinate proxy when available."""
    candidates = _airports_by_city().get(city.casefold(), [])
    if not candidates:
        return None

    def rank(airport: dict) -> tuple[int, int, float]:
        name = airport.get("name", "").casefold()
        city_name = city.casefold()
        return (
            2 if "international" in name else 1 if name == f"{city_name} airport" else 0,
            1 if "airport" in name else 0,
            float(airport.get("elevation") or 0),
        )

    airport = max(candidates, key=rank)
    return {
        "latitude": float(airport["lat"]),
        "longitude": float(airport["lon"]),
        "display_name": airport.get("name", city),
    }


def get_city_coordinates(city: str):
    """
    Gets the coorinates of a city or region by name,

    Args: 
    city: str = City/Region name (specify state or country, so it knows where you're talking about)
    """
    # Prefer local airport coordinates for city-level searches. This avoids
    # making hotel availability depend on the public geocoder being reachable.
    city_name = city.split(",", 1)[0].strip()
    local_coordinates = _coordinates_from_airport_data(city_name)
    if local_coordinates:
        return local_coordinates

    url = "https://nominatim.openstreetmap.org/search"

    params = {
        "q": city,
        "format": "json",
        "limit": 1,
    }

    headers = {
        "User-Agent": "AITravelAgent/1.0"
    }

    try:
        response = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=5,
        )
    except requests.RequestException as exc:
        raise ConnectionError(
            f"Could not geocode {city!r}: the online geocoder is unavailable and "
            "no local airport coordinates matched the city."
        ) from exc

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