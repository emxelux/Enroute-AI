"""
Minimal Duffel API client built on `requests` (targets API version v2).

    pip install requests

    from duffel_client import Duffel
    duffel = Duffel()                      # reads DUFFEL_ACCESS_TOKEN
    res = duffel.create_offer_request(
        slices=[{"origin": "LOS", "destination": "LHR", "departure_date": "2026-11-10"}],
        passengers=[{"type": "adult"}],
    )
    offers = res["offers"]

Conventions
- Every method returns the unwrapped `data` payload as plain dicts / lists.
- list_* methods return a generator that follows the `meta.after` cursor.
- Errors raise DuffelError (with .status, .errors, .request_id).
- Money-moving calls (create_order, create_payment, confirm_*) are NOT guarded here;
  put a human confirmation step in front of them if an LLM agent is calling this.
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, Iterator, List, Optional

import requests

BASE_URL = "https://api.duffel.com/"
DEFAULT_VERSION = "v2"
_RETRY_STATUSES = {429, 502, 503, 504}


class DuffelError(Exception):
    def __init__(self, status: int, errors: List[dict], request_id: Optional[str] = None, raw: Any = None):
        self.status = status
        self.errors = errors or []
        self.request_id = request_id
        self.raw = raw
        first = self.errors[0] if self.errors else {}
        self.type = first.get("type")
        self.code = first.get("code")
        self.title = first.get("title")
        self.message = first.get("message") or str(raw)
        super().__init__(f"[{status}] {self.type}: {self.title}: {self.message}")


class Duffel:
    def __init__(
        self,
        access_token: Optional[str] = None,
        api_version: str = DEFAULT_VERSION,
        base_url: str = BASE_URL,
        timeout: float = 60.0,  # offer searches can take up to ~20s+ on the API side
        max_retries: int = 3,
        session: Optional[requests.Session] = None,
    ):
        token = access_token or os.environ.get("DUFFEL_ACCESS_TOKEN")
        if not token:
            raise ValueError("Provide access_token or set DUFFEL_ACCESS_TOKEN")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Duffel-Version": api_version,
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Accept-Encoding": "gzip",
            }
        )

    # ------------------------------------------------------------------ core
    def _request(self, method: str, path: str, params: Optional[dict] = None, body: Optional[dict] = None) -> dict:
        """Send a request, retry transient failures, return the full JSON envelope."""
        url = f"{self.base_url}{path}"
        payload = {"data": body} if body is not None else None
        attempt = 0
        while True:
            resp = self.session.request(method, url, params=_clean(params), json=payload, timeout=self.timeout)
            # Retry rate limits for any method (request was rejected, not processed).
            # Retry 5xx only for GET so we never double-submit an order or payment.
            retryable = resp.status_code == 429 or (resp.status_code in _RETRY_STATUSES and method == "GET")
            if retryable and attempt < self.max_retries:
                time.sleep(min(2 ** attempt, 8))
                attempt += 1
                continue
            break

        if resp.status_code == 204 or not resp.content:
            return {}
        try:
            js = resp.json()
        except ValueError:
            raise DuffelError(resp.status_code, [], resp.headers.get("x-request-id"), resp.text)
        if not resp.ok:
            raise DuffelError(resp.status_code, js.get("errors", []), resp.headers.get("x-request-id"), js)
        return js

    def _data(self, method: str, path: str, params: Optional[dict] = None, body: Optional[dict] = None):
        return self._request(method, path, params, body).get("data")

    def _paginate(self, path: str, params: Optional[dict] = None, limit: int = 50) -> Iterator[dict]:
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        params = dict(params or {}, limit=limit)
        while True:
            js = self._request("GET", path, params)
            for item in js.get("data", []):
                yield item
            after = (js.get("meta") or {}).get("after")
            if not after:
                return
            params["after"] = after

    # ---------------------------------------------------------------- search
    def create_offer_request(
        self,
        slices: List[dict],
        passengers: List[dict],
        cabin_class: Optional[str] = None,  # economy | premium_economy | business | first
        max_connections: Optional[int] = None,
        return_offers: bool = True,
        supplier_timeout: Optional[int] = None,  # ms; API default is 20000
    ) -> dict:
        """POST /air/offer_requests: the flight search."""
        body: Dict[str, Any] = {"slices": slices, "passengers": passengers}
        if cabin_class:
            body["cabin_class"] = cabin_class
        if max_connections is not None:
            body["max_connections"] = max_connections
        params = {"return_offers": str(return_offers).lower(), "supplier_timeout": supplier_timeout}
        return self._data("POST", "/air/offer_requests", params, body)

    def get_offer_request(self, offer_request_id: str) -> dict:
        return self._data("GET", f"/air/offer_requests/{offer_request_id}")

    def list_offer_requests(self, limit: int = 50) -> Iterator[dict]:
        return self._paginate("/air/offer_requests", limit=limit)

    def list_offers(
        self,
        offer_request_id: str,
        sort: Optional[str] = None,  # e.g. total_amount, total_duration (prefix - to reverse)
        max_connections: Optional[int] = None,
        limit: int = 50,
    ) -> Iterator[dict]:
        params = {"offer_request_id": offer_request_id, "sort": sort, "max_connections": max_connections}
        return self._paginate("/air/offers", params, limit)

    def get_offer(self, offer_id: str, return_available_services: bool = False) -> dict:
        params = {"return_available_services": "true"} if return_available_services else None
        return self._data("GET", f"/air/offers/{offer_id}", params)

    def update_offer_passenger(
        self,
        offer_id: str,
        offer_passenger_id: str,
        given_name: Optional[str] = None,
        family_name: Optional[str] = None,
        loyalty_programme_accounts: Optional[List[dict]] = None,  # [{airline_iata_code, account_number}]
    ) -> dict:
        body = _clean(
            {
                "given_name": given_name,
                "family_name": family_name,
                "loyalty_programme_accounts": loyalty_programme_accounts,
            }
        )
        return self._data("PATCH", f"/air/offers/{offer_id}/passengers/{offer_passenger_id}", body=body)

    def get_seat_maps(self, offer_id: str) -> List[dict]:
        return self._data("GET", "/air/seat_maps", {"offer_id": offer_id})

    # ------------------------------------------- multi-step (partial) search
    def create_partial_offer_request(
        self, slices: List[dict], passengers: List[dict], cabin_class: Optional[str] = None,
        max_connections: Optional[int] = None,
    ) -> dict:
        body: Dict[str, Any] = {"slices": slices, "passengers": passengers}
        if cabin_class:
            body["cabin_class"] = cabin_class
        if max_connections is not None:
            body["max_connections"] = max_connections
        return self._data("POST", "/air/partial_offer_requests", body=body)

    def get_partial_offer_request(self, partial_offer_request_id: str, selected_partial_offer: Optional[List[str]] = None) -> dict:
        params = {"selected_partial_offer[]": selected_partial_offer} if selected_partial_offer else None
        return self._data("GET", f"/air/partial_offer_requests/{partial_offer_request_id}", params)

    def get_partial_offer_request_fares(self, partial_offer_request_id: str, selected_partial_offers: List[str]) -> dict:
        params = {"selected_partial_offers[]": selected_partial_offers}
        return self._data("GET", f"/air/partial_offer_requests/{partial_offer_request_id}/fares", params)

    # ----------------------------------------------------------------- orders
    def create_order(
        self,
        selected_offers: List[str],  # exactly one offer id
        passengers: List[dict],      # each needs the passenger `id` from the offer request
        payments: Optional[List[dict]] = None,  # [{type, amount, currency}]; type: balance | arc_bsp_cash
        services: Optional[List[dict]] = None,  # [{id, quantity}]
        metadata: Optional[dict] = None,
        hold: bool = False,  # True = hold order (no payments), pay later with create_payment
    ) -> dict:
        """POST /air/orders. Note: v2 removed `passengers[].type`, do not send it."""
        if len(selected_offers) != 1:
            raise ValueError("selected_offers must contain exactly one offer id")
        body: Dict[str, Any] = {
            "type": "hold" if hold else "instant",
            "selected_offers": selected_offers,
            "passengers": passengers,
        }
        if not hold:
            if not payments:
                raise ValueError("payments are required unless hold=True")
            body["payments"] = payments
        if services:
            body["services"] = services
        if metadata:
            body["metadata"] = metadata
        return self._data("POST", "/air/orders", body=body)

    def get_order(self, order_id: str) -> dict:
        return self._data("GET", f"/air/orders/{order_id}")

    def list_orders(self, awaiting_payment: bool = False, sort: Optional[str] = None, limit: int = 50) -> Iterator[dict]:
        if sort not in (None, "pay_by", "-pay_by"):
            raise ValueError("sort must be 'pay_by' or '-pay_by'")
        params = {"awaiting_payment": "true" if awaiting_payment else None, "sort": sort}
        return self._paginate("/air/orders", params, limit)

    def update_order(self, order_id: str, metadata: dict) -> dict:
        return self._data("PATCH", f"/air/orders/{order_id}", body={"metadata": metadata})

    def create_payment(self, order_id: str, payment: dict) -> dict:
        """Pay for a hold order. payment = {type, amount, currency}."""
        return self._data("POST", "/air/payments", body={"order_id": order_id, "payment": payment})

    # ---------------------------------------------------------- cancellations
    def create_order_cancellation(self, order_id: str) -> dict:
        """Step 1: creates a pending cancellation; inspect refund_amount (may be null in v2)."""
        return self._data("POST", "/air/order_cancellations", body={"order_id": order_id})

    def confirm_order_cancellation(self, cancellation_id: str) -> dict:
        """Step 2: irreversible."""
        return self._data("POST", f"/air/order_cancellations/{cancellation_id}/actions/confirm")

    def get_order_cancellation(self, cancellation_id: str) -> dict:
        return self._data("GET", f"/air/order_cancellations/{cancellation_id}")

    def list_order_cancellations(self, order_id: Optional[str] = None, limit: int = 50) -> Iterator[dict]:
        return self._paginate("/air/order_cancellations", {"order_id": order_id}, limit)

    # ---------------------------------------------------------------- changes
    def create_order_change_request(self, order_id: str, slices: Dict[str, List[dict]]) -> dict:
        """slices = {"remove": [{"slice_id": ...}], "add": [{origin, destination, departure_date, cabin_class}]}"""
        return self._data("POST", "/air/order_change_requests", body={"order_id": order_id, "slices": slices})

    def get_order_change_request(self, request_id: str) -> dict:
        return self._data("GET", f"/air/order_change_requests/{request_id}")

    def list_order_change_offers(
        self, order_change_request_id: str, sort: Optional[str] = None,
        max_connections: Optional[int] = None, limit: int = 50,
    ) -> Iterator[dict]:
        params = {"order_change_request_id": order_change_request_id, "sort": sort, "max_connections": max_connections}
        return self._paginate("/air/order_change_offers", params, limit)

    def get_order_change_offer(self, offer_id: str) -> dict:
        return self._data("GET", f"/air/order_change_offers/{offer_id}")

    def create_order_change(self, selected_order_change_offer: str) -> dict:
        return self._data("POST", "/air/order_changes",
                          body={"selected_order_change_offer": selected_order_change_offer})

    def confirm_order_change(self, order_change_id: str, payment: dict) -> dict:
        """payment = {type, amount, currency}; a negative change_total_amount is refunded to your balance."""
        return self._data("POST", f"/air/order_changes/{order_change_id}/actions/confirm", body=payment)

    def get_order_change(self, order_change_id: str) -> dict:
        return self._data("GET", f"/air/order_changes/{order_change_id}")

    # ------------------------------------------------------- Duffel Payments
    def create_payment_intent(self, amount: str, currency: str) -> dict:
        """Returns a client_token used by your front end to collect card details."""
        return self._data("POST", "/payments/payment_intents", body={"amount": amount, "currency": currency})

    def get_payment_intent(self, payment_intent_id: str) -> dict:
        return self._data("GET", f"/payments/payment_intents/{payment_intent_id}")

    def confirm_payment_intent(self, payment_intent_id: str) -> dict:
        return self._data("POST", f"/payments/payment_intents/{payment_intent_id}/actions/confirm")

    # ------------------------------------------------------------------ links
    def create_link_session(
        self, reference: str, success_url: str, failure_url: str, abandonment_url: str, **options: Any
    ) -> dict:
        """options: logo_url, primary_color, secondary_color, checkout_display_text, traveller_currency,
        markup_rate, markup_amount + markup_currency (amount and currency must be given together)."""
        if ("markup_amount" in options) != ("markup_currency" in options):
            raise ValueError("markup_amount and markup_currency must be supplied together")
        body = {"reference": reference, "success_url": success_url, "failure_url": failure_url,
                "abandonment_url": abandonment_url, **options}
        return self._data("POST", "/links/sessions", body=body)

    # --------------------------------------------------------------- webhooks
    def create_webhook(self, url: str, events: List[str]) -> dict:
        return self._data("POST", "/air/webhooks", body={"url": url, "events": events})

    def update_webhook(self, webhook_id: str, active: bool) -> dict:
        return self._data("PATCH", f"/air/webhooks/{webhook_id}", body={"active": active})

    def ping_webhook(self, webhook_id: str) -> None:
        self._request("POST", f"/air/webhooks/{webhook_id}/actions/ping")

    # -------------------------------------------------------- reference data
    def get_airport(self, airport_id: str) -> dict:
        return self._data("GET", f"/air/airports/{airport_id}")

    def list_airports(self, limit: int = 50) -> Iterator[dict]:
        return self._paginate("/air/airports", limit=limit)

    def get_airline(self, airline_id: str) -> dict:
        return self._data("GET", f"/air/airlines/{airline_id}")

    def list_airlines(self, limit: int = 50) -> Iterator[dict]:
        return self._paginate("/air/airlines", limit=limit)

    def get_aircraft(self, aircraft_id: str) -> dict:
        return self._data("GET", f"/air/aircraft/{aircraft_id}")

    def list_aircraft(self, limit: int = 50) -> Iterator[dict]:
        return self._paginate("/air/aircraft", limit=limit)

    def suggest_places(self, query: str) -> List[dict]:
        """GET /places/suggestions: city/airport lookup by free text (not in the old library)."""
        return self._data("GET", "/places/suggestions", {"query": query})


def _clean(d: Optional[dict]) -> Optional[dict]:
    """Drop None values so optional params are simply omitted."""
    return None if d is None else {k: v for k, v in d.items() if v is not None}