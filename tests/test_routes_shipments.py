"""Shipment route tests."""

from __future__ import annotations

from litestar.testing import TestClient


class TestShipmentsHealthRoute:
    def test_health_returns_ok(self, client: TestClient) -> None:
        resp = client.get("/shipments/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestCreateShipmentRoute:
    def test_create_shipment_returns_201(self, client: TestClient) -> None:
        resp = client.post("/shipments", json={"order_id": "order-1"})
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
            json={"order_id": "o-2", "provider": "test-dummy"},
        )
        assert resp.status_code == 201
        assert resp.json()["provider"] == "test-dummy"


class TestCreateLabelRoute:
    def test_create_label_returns_201(self, client: TestClient) -> None:
        created = client.post("/shipments", json={"order_id": "o-1"})
        shipment_id = created.json()["id"]
        resp = client.post(f"/shipments/{shipment_id}/label")
        assert resp.status_code == 201
        assert resp.json()["status"] == "label_ready"

    def test_create_label_sets_label_url(self, client: TestClient) -> None:
        created = client.post("/shipments", json={"order_id": "o-1"})
        shipment_id = created.json()["id"]
        resp = client.post(f"/shipments/{shipment_id}/label")
        assert resp.json()["label_url"] != ""


class TestFetchStatusRoute:
    def test_fetch_status_returns_200(self, client: TestClient) -> None:
        created = client.post("/shipments", json={"order_id": "o-1"})
        shipment_id = created.json()["id"]
        client.post(f"/shipments/{shipment_id}/label")
        resp = client.get(f"/shipments/{shipment_id}/status")
        assert resp.status_code == 200
        assert "status" in resp.json()
