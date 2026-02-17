"""Shipment route tests."""

from __future__ import annotations

from litestar import Litestar
from litestar.testing import TestClient
from sendparcel.registry import registry

from litestar_sendparcel.config import SendparcelConfig
from litestar_sendparcel.plugin import create_shipping_router

from conftest import DummyTestProvider, InMemoryRepo


_DIRECT_PAYLOAD = {
    "sender_address": {"country_code": "PL"},
    "receiver_address": {"country_code": "DE"},
    "parcels": [{"weight_kg": "1.0"}],
}


class TestShipmentsHealthRoute:
    def test_health_returns_ok(self, client: TestClient) -> None:
        resp = client.get("/shipments/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestCreateShipmentRoute:
    def test_create_shipment_returns_201(self, client: TestClient) -> None:
        resp = client.post("/shipments", json=_DIRECT_PAYLOAD)
        assert resp.status_code == 201
        body = resp.json()
        assert "id" in body
        assert body["status"] == "created"
        assert body["provider"] == "test-dummy"

    def test_create_shipment_with_explicit_provider(
        self, client: TestClient
    ) -> None:
        resp = client.post(
            "/shipments",
            json={**_DIRECT_PAYLOAD, "provider": "test-dummy"},
        )
        assert resp.status_code == 201
        assert resp.json()["provider"] == "test-dummy"


class TestCreateLabelRoute:
    def test_create_label_returns_201(self, client: TestClient) -> None:
        created = client.post("/shipments", json=_DIRECT_PAYLOAD)
        shipment_id = created.json()["id"]
        resp = client.post(f"/shipments/{shipment_id}/label")
        assert resp.status_code == 201
        assert resp.json()["status"] == "label_ready"

    def test_create_label_sets_label_url(self, client: TestClient) -> None:
        created = client.post("/shipments", json=_DIRECT_PAYLOAD)
        shipment_id = created.json()["id"]
        resp = client.post(f"/shipments/{shipment_id}/label")
        assert resp.json()["label_url"] != ""


class TestFetchStatusRoute:
    def test_fetch_status_returns_200(self, client: TestClient) -> None:
        created = client.post("/shipments", json=_DIRECT_PAYLOAD)
        shipment_id = created.json()["id"]
        client.post(f"/shipments/{shipment_id}/label")
        resp = client.get(f"/shipments/{shipment_id}/status")
        assert resp.status_code == 200
        assert "status" in resp.json()


class TestDirectShipmentCreation:
    """HTTP tests for the direct shipment creation flow."""

    def test_create_shipment_direct(self, client: TestClient) -> None:
        """POST /shipments with sender/receiver/parcels creates shipment."""
        resp = client.post("/shipments", json=_DIRECT_PAYLOAD)
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "created"
        assert body["provider"] == "test-dummy"

    def test_create_shipment_partial_direct_fields_returns_500(
        self, client: TestClient
    ) -> None:
        """Partial direct fields (missing parcels) returns 500."""
        resp = client.post(
            "/shipments",
            json={
                "sender_address": {"country_code": "PL"},
                "receiver_address": {"country_code": "DE"},
            },
        )
        assert resp.status_code == 500

    def test_create_shipment_empty_body_returns_500(
        self, client: TestClient
    ) -> None:
        """Empty request body returns 500 (ConfigurationError)."""
        resp = client.post("/shipments", json={})
        assert resp.status_code == 500
