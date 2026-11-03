from datetime import date
import unittest
from unittest.mock import Mock, patch

from langchain_core.messages import AIMessage, HumanMessage

from agents import supervisor
from agents.supervisor import (
    _deterministic_travel_information,
    _hotel_preference,
    _mentioned_dates,
    supplement_travel_information,
)


class SupervisorHotelIntentTests(unittest.TestCase):
    def test_this_weekday_and_next_weekday_dates(self) -> None:
        dates = _mentioned_dates(
            "travel this Wednesday and return by next week Sunday",
            date(2026, 10, 19),
        )
        self.assertEqual(dates, [date(2026, 10, 21), date(2026, 11, 1)])

    def test_explicit_hotel_request_is_detected(self) -> None:
        self.assertIs(
            _hotel_preference([HumanMessage(content="I also need a hotel in New York")]),
            True,
        )

    def test_explicit_hotel_decline_is_detected(self) -> None:
        self.assertIs(
            _hotel_preference([HumanMessage(content="No hotel, flights only")]),
            False,
        )

    def test_missing_hotel_choice_requires_confirmation(self) -> None:
        messages = [
            HumanMessage(content="Book a flight to New York"),
            AIMessage(content="Would you also like hotel accommodation?"),
            HumanMessage(content="yes"),
        ]
        self.assertIs(_hotel_preference(messages), True)

    def test_requested_hotel_uses_flight_stay_dates_by_default(self) -> None:
        travel_info = {
            "needs_flight": True,
            "needs_hotel": {"MISSING": False, "needs_accomodation": True},
            "flight_origin": "LOS",
            "flight_destination": "JFK",
            "flight_departure_date": "2026-10-21",
            "flight_return_date": "2026-11-01",
            "hotel_location": "New York",
        }
        result = supplement_travel_information(
            travel_info,
            [HumanMessage(content="I need a hotel in New York")],
        )
        self.assertEqual(result["hotel_check_in"], "2026-10-21")
        self.assertEqual(result["hotel_check_out"], "2026-11-01")

    def test_flight_and_hotel_request_extracts_without_llm(self) -> None:
        query = (
            "I want to travel from Lagos to New York on this Wednesday "
            "and I'll be back by next week Sunday; I need flight and hotel"
        )
        result = _deterministic_travel_information([HumanMessage(content=query)])
        self.assertTrue(result["needs_flight"])
        self.assertEqual(result["needs_hotel"]["needs_accomodation"], True)
        self.assertEqual(result["flight_origin"], "LOS")
        self.assertEqual(result["flight_destination"], "JFK")
        self.assertEqual(result["flight_departure_date"], "2026-10-21")
        self.assertEqual(result["flight_return_date"], "2026-11-01")
        self.assertEqual(result["hotel_location"], "New York")
        self.assertEqual(result["hotel_check_in"], "2026-10-21")
        self.assertEqual(result["hotel_check_out"], "2026-11-01")

    def test_extractor_falls_back_after_provider_schema_error(self) -> None:
        broken_agent = Mock()
        broken_agent.invoke.side_effect = RuntimeError(
            "structured output schema validation failed"
        )
        query = "Travel from Lagos to New York this Wednesday; I need a hotel"
        messages = [HumanMessage(content=query)]
        with patch.object(supervisor, "create_agent", return_value=broken_agent):
            result = supervisor.extract_travel_information(messages)
        self.assertTrue(result["needs_flight"])
        self.assertEqual(result["flight_origin"], "LOS")
        self.assertEqual(result["flight_destination"], "JFK")
        self.assertEqual(result["flight_departure_date"], "2026-10-21")

    def test_deterministic_date_supplement_overrides_model_guess(self) -> None:
        travel_info = {
            "needs_flight": True,
            "needs_hotel": {"MISSING": False, "needs_accomodation": False},
            "flight_departure_date": "2026-10-25",
            "flight_return_date": "2026-10-25",
        }
        result = supplement_travel_information(
            travel_info,
            [HumanMessage(content="Travel this Wednesday and return next week Sunday")],
        )
        self.assertEqual(result["flight_departure_date"], "2026-10-21")
        self.assertEqual(result["flight_return_date"], "2026-11-01")


if __name__ == "__main__":
    unittest.main()
