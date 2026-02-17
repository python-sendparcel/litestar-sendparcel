"""Callback route tests."""

from __future__ import annotations

from litestar.testing import TestClient


_DIRECT_PAYLOAD = {
    "sender_address": {"country_code": "PL"},
    "receiver_address": {"country_code": "DE"},
    "parcels": [{"weight_kg": "1.0"}],
}


class TestCallbackRoute:
    """Test POST /callbacks/{provider_slug}/{shipment_id}."""

    def _create_shipment(self, client: TestClient) -> str:
        """Helper: create a shipment and return its ID."""
        resp = client.post("/shipments", json=_DIRECT_PAYLOAD)
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    def test_callback_happy_path(self, client: TestClient) -> None:
        shipment_id = self._create_shipment(client)
        # Create label first so FSM allows mark_in_transit
        client.post(f"/shipments/{shipment_id}/label")

        resp = client.post(
            f"/callbacks/test-dummy/{shipment_id}",
            json={"event": "picked_up"},
            headers={"x-test-token": "valid"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["provider"] == "test-dummy"
        assert body["status"] == "accepted"

    def test_callback_invalid_token_returns_400(
        self, client: TestClient
    ) -> None:
        shipment_id = self._create_shipment(client)
        resp = client.post(
            f"/callbacks/test-dummy/{shipment_id}",
            json={"event": "test"},
            headers={"x-test-token": "WRONG"},
        )
        assert resp.status_code == 400

    def test_callback_provider_mismatch_returns_400(
        self, client: TestClient
    ) -> None:
        shipment_id = self._create_shipment(client)
        resp = client.post(
            f"/callbacks/wrong-provider/{shipment_id}",
            json={"event": "test"},
            headers={"x-test-token": "valid"},
        )
        assert resp.status_code == 400

    def test_callback_missing_shipment_returns_404(
        self, client: TestClient
    ) -> None:
        resp = client.post(
            "/callbacks/test-dummy/nonexistent-id",
            json={"event": "test"},
            headers={"x-test-token": "valid"},
        )
        assert resp.status_code == 404

    def test_callback_response_includes_shipment_status(
        self, client: TestClient
    ) -> None:
        shipment_id = self._create_shipment(client)
        client.post(f"/shipments/{shipment_id}/label")

        resp = client.post(
            f"/callbacks/test-dummy/{shipment_id}",
            json={"event": "transit"},
            headers={"x-test-token": "valid"},
        )
        assert resp.status_code == 201
        assert "shipment_status" in resp.json()

    def test_callback_invalid_token_does_not_enqueue_retry(
        self, client: TestClient, retry_store
    ) -> None:
        """InvalidCallbackError is NOT retried - only CommunicationError is."""
        shipment_id = self._create_shipment(client)
        client.post(
            f"/callbacks/test-dummy/{shipment_id}",
            json={"event": "test"},
            headers={"x-test-token": "WRONG"},
        )
        assert len(retry_store.events) == 0
