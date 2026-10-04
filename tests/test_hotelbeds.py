from __future__ import annotations

import hashlib
import os
import unittest
from datetime import date
from unittest.mock import Mock, patch

import bookingapi

from tools import hotel_tool
from agents import hotel_agent


class HotelbedsToolTests(unittest.TestCase):
    def test_client_is_signed_and_fixed_to_sandbox(self) -> None:
        with patch.dict(os.environ, {"HOTELBEDS_API_KEY": "test-key", "HOTELBEDS_SECRET": "test-secret"}), patch.object(
            hotel_tool.time, "time", return_value=12345
        ):
            client = hotel_tool._api_client()

        self.assertEqual(client.host, hotel_tool.HOTELBEDS_TEST_HOST)
        self.assertEqual(client.default_headers["api-key"], "test-key")
        self.assertEqual(
            client.default_headers["x-signature"],
            hashlib.sha256(b"test-keytest-secret12345").hexdigest(),
        )
        self.assertNotIn("api.hotelbeds.com/hotel-api", client.host.replace("api.test.hotelbeds.com/hotel-api", ""))

    def test_client_requires_both_credentials(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "HOTELBEDS_API_KEY"):
                hotel_tool._api_client()

    def test_date_validation(self) -> None:
        with self.assertRaises(ValueError):
            hotel_tool._validate_dates("2026-10-10", "2026-10-10")
        with self.assertRaises(ValueError):
            hotel_tool._validate_dates("not-a-date", "2026-10-11")

    def test_search_builds_sandbox_availability_request_and_normalizes_results(self) -> None:
        response = {"hotels": {"hotels": [{
            "code": 22,
            "name": "Test Hotel",
            "currency": "EUR",
            "rooms": [{
                "code": "DBL",
                "name": "Double room",
                "rates": [{"rate_key": "rk-1", "selling_rate": 99.5, "board_name": "Breakfast"}],
            }],
        }]}}
        api = Mock()
        api.availability.return_value = response
        with patch.object(hotel_tool, "_location_coordinates", return_value=(51.5, -0.1)), patch.object(
            hotel_tool, "_api_client", return_value=Mock()
        ), patch.object(hotel_tool.bookingapi, "HotelsApi", return_value=api):
            options = hotel_tool.search_hotels.func(
                "London", "2026-11-02", "2026-11-05", adults=2, children_ages=[8]
            )

        request = api.availability.call_args.args[1]
        self.assertEqual(request.stay.check_in, date(2026, 11, 2))
        self.assertEqual(request.stay.check_out, date(2026, 11, 5))
        self.assertEqual(request.geolocation.latitude, 51.5)
        self.assertEqual(request.geolocation.longitude, -0.1)
        self.assertEqual(request.occupancies[0].adults, 2)
        self.assertEqual(request.occupancies[0].children, 1)
        self.assertEqual(request.occupancies[0].pax[0].type, "CH")
        self.assertEqual(options[0]["hotel_code"], 22)
        self.assertEqual(options[0]["rate_key"], "rk-1")
        self.assertEqual(options[0]["selling_rate"], 99.5)
        self.assertEqual(options[0]["currency"], "EUR")

    def test_search_rejects_invalid_child_age(self) -> None:
        with self.assertRaisesRegex(ValueError, "Child ages"):
            hotel_tool.search_hotels.func("London", "2026-11-02", "2026-11-05", children_ages=[18])

    def test_normalizer_reads_single_hotel_checkrate_response(self) -> None:
        response = {"hotel": bookingapi.ApiHotel(
            code=5,
            name="Rechecked Hotel",
            rooms=[bookingapi.Room(rates=[bookingapi.ApiRate(rate_key="fresh", selling_rate=120)])],
        )}
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

    def test_booking_confirmation_builds_expected_sdk_request(self) -> None:
        response = {"booking": {"reference": "ref-1", "status": "CONFIRMED"}}
        api = Mock()
        api.booking.return_value = response
        with patch.object(hotel_tool, "_api_client", return_value=Mock()), patch.object(
            hotel_tool.bookingapi, "BookingsApi", return_value=api
        ):
            hotel_tool.book_hotel.func(
                "rate-1",
                "Ada",
                "Lovelace",
                [{"type": "AD", "name": "Ada", "surname": "Lovelace", "room_id": 1}],
                "client-ref",
                confirmed=True,
            )
        request = api.booking.call_args.args[1]
        self.assertEqual(request.rooms[0].rate_key, "rate-1")
        self.assertEqual(request.rooms[0].paxes[0].name, "Ada")
        self.assertEqual(request.holder.name, "Ada")
        self.assertEqual(request.client_reference, "client-ref")

    def test_change_simulation_uses_sdk_mode(self) -> None:
        api = Mock()
        api.booking_change.return_value = {"booking": {"reference": "ref-1"}}
        with patch.object(hotel_tool, "_api_client", return_value=Mock()), patch.object(
            hotel_tool.bookingapi, "BookingsApi", return_value=api
        ):
            hotel_tool.change_hotel_booking.func("ref-1", 10, "DBL", "rate-2", "SIMULATION", "")
        request = api.booking_change.call_args.args[2]
        self.assertEqual(request.booking_id, "ref-1")
        self.assertEqual(request.mode, "SIMULATION")
        self.assertEqual(request.booking.hotel.rooms[0].rates[0].rate_key, "rate-2")

    def test_booking_detail_uses_supplied_reference(self) -> None:
        api = Mock()
        api.booking_detail.return_value = {"booking": {"reference": "hb-ref"}}
        with patch.object(hotel_tool, "_api_client", return_value=Mock()), patch.object(
            hotel_tool.bookingapi, "BookingsApi", return_value=api
        ):
            result = hotel_tool.get_hotel_booking.func("hb-ref")
        api.booking_detail.assert_called_once_with("1.0", "hb-ref")
        self.assertEqual(result["booking"]["reference"], "hb-ref")

    def test_cancellation_calls_sdk_only_after_exact_confirmation(self) -> None:
        api = Mock()
        api.booking_cancellation.return_value = {"status": "CANCELLED"}
        with patch.object(hotel_tool, "_api_client", return_value=Mock()), patch.object(
            hotel_tool.bookingapi, "BookingsApi", return_value=api
        ):
            result = hotel_tool.cancel_hotel_booking.func("hb-ref", "I CONFIRM HOTEL CANCELLATION")
        api.booking_cancellation.assert_called_once_with("1.0", "hb-ref")
        self.assertEqual(result["status"], "CANCELLED")


if __name__ == "__main__":
    unittest.main()
