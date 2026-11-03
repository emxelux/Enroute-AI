import hashlib
import os
import time
from typing import Optional

import requests
from dotenv import load_dotenv
from utils import get_city_coordinates

load_dotenv()

BASE_URL = "https://api.test.hotelbeds.com"
API_PREFIX = "/hotel-api/1.0"
TIMEOUT = 30  # seconds


class HotelBeds:
    def __init__(self, api_key: Optional[str] = None, secret: Optional[str] = None):
        self.api_key = api_key or os.getenv("HOTELBEDS_API_KEY")
        self.secret = secret or os.getenv("HOTELBEDS_SECRET")
        if not self.api_key or not self.secret:
            raise ValueError("HOTELBEDS_API_KEY and HOTELBEDS_SECRET are required")

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _get_headers(self) -> dict:
        """Fresh headers (and a fresh signature) for EVERY request."""
        timestamp = int(time.time())
        signature = hashlib.sha256(
            f"{self.api_key}{self.secret}{timestamp}".encode("utf-8")
        ).hexdigest()
        return {
            "Api-key": self.api_key,
            "X-Signature": signature,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, **kwargs) -> dict:
        response = requests.request(
            method,
            f"{BASE_URL}{API_PREFIX}{path}",
            headers=self._get_headers(),  # new signature each call
            timeout=TIMEOUT,
            **kwargs,
        )
        if response.status_code not in (200, 201):
            raise Exception(response.text)
        return response.json()

    @staticmethod
    def _get_coordinates(location: str) -> dict:
        coordinates = get_city_coordinates(location)
        return {
            "latitude": coordinates["latitude"],
            "longitude": coordinates["longitude"],
        }

    @staticmethod
    def _split_counts(rooms: int, adults: int, children: int) -> list[tuple[int, int]]:
        """Distribute adults/children across rooms -> [(adults, children), ...].

        Adults are spread evenly (earlier rooms get the remainder); children are
        spread evenly the same way. Every room must end up with >= 1 adult.
        """
        if rooms < 1:
            raise ValueError("rooms must be >= 1")
        if adults < rooms:
            raise ValueError(
                f"Need at least one adult per room ({adults} adults for {rooms} rooms)"
            )
        a_base, a_extra = divmod(adults, rooms)
        c_base, c_extra = divmod(children, rooms)
        return [
            (a_base + (1 if i < a_extra else 0), c_base + (1 if i < c_extra else 0))
            for i in range(rooms)
        ]

    # ------------------------------------------------------------------ #
    # Availability
    # ------------------------------------------------------------------ #
    def check_availability(
        self,
        location: str,
        check_in: str,
        check_out: str,
        rooms: int = 1,
        adults: int = 1,
        children: int = 0,
        child_ages: Optional[list[int]] = None,
        radius_km: int = 50,
    ) -> dict:
        child_ages = child_ages or []
        if len(child_ages) != children:
            raise ValueError(
                f"children={children} but {len(child_ages)} child_ages provided"
            )

        coordinates = self._get_coordinates(location)

        # HotelBeds needs the children's ages in `paxes`.
        if children == 0:
            occupancies = [{"rooms": rooms, "adults": adults, "children": 0}]
        else:
            # Per-room occupancies so each child's age sits in the right room.
            occupancies, ages = [], iter(child_ages)
            for room_adults, room_children in self._split_counts(rooms, adults, children):
                occupancies.append(
                    {
                        "rooms": 1,
                        "adults": room_adults,
                        "children": room_children,
                        "paxes": [
                            {"type": "CH", "age": next(ages)}
                            for _ in range(room_children)
                        ],
                    }
                )

        payload = {
            "stay": {"checkIn": check_in, "checkOut": check_out},
            "occupancies": occupancies,
            "geolocation": {
                **coordinates,
                "radius": radius_km,
                "unit": "km",
            },
        }
        return self._request("POST", "/hotels", json=payload)

    # ------------------------------------------------------------------ #
    # CheckRate
    # ------------------------------------------------------------------ #
    def check_rate(self, rate_key: str) -> dict:
        """Re-validate price/availability before booking.

        Use the rateKey returned HERE (it can differ from the search one)
        when you call book_hotel.
        """
        payload = {"rooms": [{"rateKey": rate_key}]}
        return self._request("POST", "/checkrates", json=payload)

    # ------------------------------------------------------------------ #
    # Booking
    # ------------------------------------------------------------------ #
    def _build_paxes(
        self, guests: list[dict], rooms: int, adults: int, children: int
    ) -> list[dict]:
        if len(guests) != adults + children:
            raise ValueError(
                f"Expected {adults + children} guests (adults={adults} + "
                f"children={children}), got {len(guests)}"
            )

        for g in guests:
            if g.get("type") not in ("AD", "CH"):
                raise ValueError(f"Guest type must be 'AD' or 'CH': {g}")
            if not g.get("name") or not g.get("surname"):
                raise ValueError(f"Guest needs name and surname: {g}")
            if g["type"] == "CH" and g.get("age") is None:
                raise ValueError(f"Children require an age: {g}")

        adult_guests = [g for g in guests if g["type"] == "AD"]
        child_guests = [g for g in guests if g["type"] == "CH"]
        if len(adult_guests) != adults or len(child_guests) != children:
            raise ValueError(
                f"Guest types don't match: got {len(adult_guests)} AD / "
                f"{len(child_guests)} CH, expected {adults} AD / {children} CH"
            )

        # Respect explicit roomId on every guest, otherwise split automatically.
        if all("roomId" in g for g in guests):
            room_of = {id(g): g["roomId"] for g in guests}
        else:
            room_of = {}
            a_iter, c_iter = iter(adult_guests), iter(child_guests)
            for room_id, (ra, rc) in enumerate(
                self._split_counts(rooms, adults, children), start=1
            ):
                for _ in range(ra):
                    room_of[id(next(a_iter))] = room_id
                for _ in range(rc):
                    room_of[id(next(c_iter))] = room_id

        paxes = []
        for g in guests:
            pax = {
                "roomId": room_of[id(g)],
                "type": g["type"],
                "name": g["name"],
                "surname": g["surname"],
            }
            if g["type"] == "CH":
                pax["age"] = g["age"]
            paxes.append(pax)
        return sorted(paxes, key=lambda p: p["roomId"])

    def book_hotel(
        self,
        rate_key: str,
        holder: dict,
        guests: list[dict],
        rooms: int = 1,
        adults: int = 1,
        children: int = 0,
        client_reference: str = "IntegrationAgency",
        remark: str = "",
        tolerance: float = 2,
    ) -> dict:
        if not holder.get("name") or not holder.get("surname"):
            raise ValueError("holder needs 'name' and 'surname'")

        paxes = self._build_paxes(guests, rooms, adults, children)

        payload = {
            "holder": {"name": holder["name"], "surname": holder["surname"]},
            "rooms": [{"rateKey": rate_key, "paxes": paxes}],
            "clientReference": client_reference,
            "remark": remark,
            "tolerance": tolerance,
        }
        return self._request("POST", "/bookings", json=payload)

    # ------------------------------------------------------------------ #
    # Booking management
    # ------------------------------------------------------------------ #
    def get_booking(self, booking_reference: str) -> dict:
        return self._request("GET", f"/bookings/{booking_reference}")

    def cancel_booking(self, booking_reference: str, simulate: bool = False) -> dict:
        """Cancel a booking. simulate=True only returns the cancellation cost."""
        flag = "SIMULATION" if simulate else "CANCELLATION"
        return self._request(
            "DELETE",
            f"/bookings/{booking_reference}",
            params={"cancellationFlag": flag},
        )
