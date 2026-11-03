from HotelBeds.hotel import HotelBeds



def search_hotels(
    location: str, 
    check_in: str, 
    check_out: str, 
    rooms: int = 1, 
    adults: int = 1, 
    children: int = 0, 
    child_ages: list[int] = None, 
    radius_km: int = 50
    ) -> list[dict]:
    """Search for hotels using the provided information and return result"""
    hotel_bed =  HotelBeds()
    result = hotel_bed.check_availability(location, check_in, check_out, rooms, adults, children, child_ages, radius_km)
    hotels = result.get("hotels", {}).get("hotels", [])
    hotel_rates = []
    for hotel in hotels:
        for room in hotel.get("rooms", []):
            for rate in room.get("rates", []):
                hotel_rates.append({
                    "hotel_id": hotel.get("code"),
                    "hotel_name": hotel.get("name"),
                    "rate_key": rate.get("rateKey"),
                    "total_amount": rate.get("net"),
                    "currency": hotel.get("currency"),
                    "room_type": room.get("name"),
                    "board_type": rate.get("board", {}).get("name"),
                    "cancellation_policy": rate.get("cancellationPolicies", []),
                })
    return hotel_rates
    # return result
# if __name__ == "__main__":
#     import json

#     with open("hotel_out.json", "w") as f:
#         json.dump(
#             search_hotels(
#                 "Manchester, United Kingdom",
#                 "2026-11-01",
#                 "2026-11-05",
#                 rooms=1,
#                 adults=2,
#                 children=1,
#                 child_ages=[5],
#                 radius_km=50,
#             ),
#             f,
#             indent=4,
#         )