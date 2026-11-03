from __future__ import annotations

import hashlib
import os
import unittest
from unittest.mock import Mock, patch

from tools import hotel_tool
from agents import hotel_agent


class HotelbedsToolTests(unittest.TestCase):
    def test_signature_matches_hotelbeds_sha256_formula(self) -> None:
        expected = hashlib.sha256(b"keysecret12345").hexdigest()
        self.assertEqual(
            hotel_tool.generate_hotelbeds_signature("key", "secret", timestamp=12345),
            expected,
        )

    def test_request_is_signed_and_fixed_to_sandbox(self) -> None:
        with patch.dict(os.environ, {"HOTELBEDS_API_KEY": "test-key", "HOTELBEDS_SECRET": "test-secret"}), patch.object(
            hotel_tool.time, "time", return_value=12345
        ), patch.object(hotel_tool.requests, "request", return_value=Mock(content=b'{"ok":true}', json=lambda: {"ok": True})) as request:
            result = hotel_tool._api_request("GET", "bookings/ref-1")

        args, kwargs = request.call_args
        self.assertEqual(args, ("GET", "https://api.test.hotelbeds.com/hotel-api/1.0/bookings/ref-1"))
        self.assertEqual(kwargs["headers"]["Api-key"], "test-key")
        self.assertEqual(
            kwargs["headers"]["X-Signature"],
            hashlib.sha256(b"test-keytest-secret12345").hexdigest(),
        )
        self.assertEqual(kwargs["timeout"], hotel_tool.HOTELBEDS_TIMEOUT_SECONDS)
        self.assertEqual(result, {"ok": True})

    def test_client_requires_both_credentials(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "HOTELBEDS_API_KEY"):
                hotel_tool._api_request("GET", "bookings/ref-1")

    def test_date_validation(self) -> None:
        with self.assertRaises(ValueError):
            hotel_tool._validate_dates("2026-10-10", "2026-10-10")
        with self.assertRaises(ValueError):
            hotel_tool._validate_dates("not-a-date", "2026-10-11")

    def test_search_builds_rest_availability_request_and_normalizes_results(self) -> None:
        response = {"hotels": {"hotels": [{
            "code": 22,
            "name": "Test Hotel",
            "currency": "EUR",
            "rooms": [{
                "code": "DBL",
                "name": "Double room",
                "rates": [{"rateKey": "rk-1", "sellingRate": 99.5, "boardName": "Breakfast"}],
            }],
        }]}}
        with patch.object(hotel_tool, "_location_coordinates", return_value=(51.5, -0.1)), patch.object(
            hotel_tool, "_api_request", return_value=response
        ) as api_request:
            options = hotel_tool.search_hotels.func(
                "London", "2026-11-02", "2026-11-05", adults=2, children_ages=[8]
            )

        api_request.assert_called_once_with("POST", "hotels", json={
            "stay": {"checkIn": "2026-11-02", "checkOut": "2026-11-05"},
            "geolocation": {"latitude": 51.5, "longitude": -0.1, "radius": 20, "unit": "km"},
            "occupancies": [{
                "rooms": 1,
                "adults": 2,
                "children": 1,
                "paxes": [{"type": "CH", "age": 8, "roomId": 1}],
            }],
        })
        self.assertEqual(options[0]["hotel_code"], 22)
        self.assertEqual(options[0]["rate_key"], "rk-1")
        self.assertEqual(options[0]["selling_rate"], 99.5)
        self.assertEqual(options[0]["currency"], "EUR")

    def test_search_rejects_invalid_child_age(self) -> None:
        with self.assertRaisesRegex(ValueError, "Child ages"):
            hotel_tool.search_hotels.func("London", "2026-11-02", "2026-11-05", children_ages=[18])

    def test_normalizer_reads_single_hotel_checkrate_response(self) -> None:
        response = {"hotel": {
            "code": 5,
            "name": "Rechecked Hotel",
            "rooms": [{"rates": [{"rateKey": "fresh", "sellingRate": 120}]}],
        }}
        options = hotel_tool._normalize_availability(response)
        self.assertEqual(options[0]["hotel_name"], "Rechecked Hotel")
        self.assertEqual(options[0]["rate_key"], "fresh")

    def test_booking_requires_explicit_confirmation(self) -> None:
        with self.assertRaisesRegex(ValueError, "explicit user confirmation"):
            hotel_tool.book_hotel.func("rate", "Ada", "Lovelace", [], "ref", confirmed=False)

    def test_cancellation_requires_exact_confirmation(self) -> None:
        with self.assertRaisesRegex(ValueError, "exact confirmation"):
            hotel_tool.cancel_hotel_booking.func("ref", "yes")

    def test_update_requires_confirmation_but_simulation_does_not(self) -> None:
        with self.assertRaisesRegex(ValueError, "exact confirmation"):
            hotel_tool.change_hotel_booking.func("ref", 10, "DBL", "rate-2", "UPDATE", "yes")

    def test_empty_rate_recheck_does_not_preserve_stale_offer(self) -> None:
        state = {"hotel_selected": {"rate_key": "stale", "hotel_code": 10, "room_code": "DBL"}}
        with patch.object(hotel_agent, "check_hotel_rate") as check_rate:
            check_rate.invoke.return_value = {"hotel": None}
            result = hotel_agent.hotel_rate_check_node(state)
        self.assertIsNone(result["hotel_selected"])
        self.assertEqual(result["current_agent"], "hotel_selection")
        self.assertIsNone(result["hotel_rate_checked"])

    def test_booking_confirmation_builds_expected_rest_request(self) -> None:
        with patch.object(hotel_tool, "_api_request", return_value={"booking": {"reference": "ref-1"}}) as api_request:
            hotel_tool.book_hotel.func(
                "rate-1",
                "Ada",
                "Lovelace",
                [{"type": "AD", "name": "Ada", "surname": "Lovelace", "room_id": 1}],
                "client-ref",
                confirmed=True,
            )
        api_request.assert_called_once_with("POST", "bookings", json={
            "holder": {"name": "Ada", "surname": "Lovelace"},
            "clientReference": "client-ref",
            "rooms": [{"rateKey": "rate-1", "paxes": [{
                "type": "AD", "name": "Ada", "surname": "Lovelace", "roomId": 1,
            }]}],
        })

    def test_change_simulation_uses_rest_mode(self) -> None:
        with patch.object(hotel_tool, "_api_request", return_value={"booking": {"reference": "ref-1"}}) as api_request:
            hotel_tool.change_hotel_booking.func("ref-1", 10, "DBL", "rate-2", "SIMULATION", "")
        api_request.assert_called_once_with("PUT", "bookings/ref-1", json={
            "mode": "SIMULATION",
            "booking": {"hotel": {"code": 10, "rooms": [{
                "code": "DBL", "rates": [{"rateKey": "rate-2"}],
            }]}},
        })

    def test_booking_detail_uses_supplied_reference(self) -> None:
        with patch.object(hotel_tool, "_api_request", return_value={"booking": {"reference": "hb-ref"}}) as api_request:
            result = hotel_tool.get_hotel_booking.func("hb-ref")
        api_request.assert_called_once_with("GET", "bookings/hb-ref")
        self.assertEqual(result["booking"]["reference"], "hb-ref")

    def test_cancellation_calls_rest_only_after_exact_confirmation(self) -> None:
        with patch.object(hotel_tool, "_api_request", return_value={"status": "CANCELLED"}) as api_request:
            result = hotel_tool.cancel_hotel_booking.func("hb-ref", "I CONFIRM HOTEL CANCELLATION")
        api_request.assert_called_once_with(
            "DELETE", "bookings/hb-ref", params={"cancellationFlag": "CANCELLATION"}
        )
        self.assertEqual(result["status"], "CANCELLED")


if __name__ == "__main__":
    unittest.main()
