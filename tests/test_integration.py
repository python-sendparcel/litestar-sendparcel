"""Full integration tests: Litestar app with in-memory repo."""

from __future__ import annotations

from litestar.testing import TestClient


class TestFullShipmentFlow:
    """End-to-end tests through the Litestar HTTP layer."""

    def test_create_label_status_flow(self, client: TestClient) -> None:
        """Create shipment, create label, fetch status -- full happy path."""
        # Step 1: Create shipment
        created = client.post("/shipments", json={"order_id": "int-o-1"})
        assert created.status_code == 201
        shipment_id = created.json()["id"]
        assert created.json()["status"] == "created"
        assert created.json()["provider"] == "test-dummy"

        # Step 2: Create label
        label = client.post(f"/shipments/{shipment_id}/label")
        assert label.status_code == 201
        assert label.json()["status"] == "label_ready"
        assert label.json()["label_url"] != ""

        # Step 3: Fetch status
        status = client.get(f"/shipments/{shipment_id}/status")
        assert status.status_code == 200
        assert "status" in status.json()

    def test_create_label_callback_flow(self, client: TestClient) -> None:
        """Create, label, then callback -- verify status progresses."""
        created = client.post("/shipments", json={"order_id": "int-o-2"})
        shipment_id = created.json()["id"]

        client.post(f"/shipments/{shipment_id}/label")

        callback = client.post(
            f"/callbacks/test-dummy/{shipment_id}",
            json={"event": "picked_up"},
            headers={"x-test-token": "valid"},
        )
        assert callback.status_code == 201
        assert callback.json()["shipment_status"] == "in_transit"

    def test_invalid_callback_returns_400_no_retry(
        self, client: TestClient, retry_store
    ) -> None:
        """Bad callback token returns 400 and does NOT enqueue retry."""
        created = client.post("/shipments", json={"order_id": "int-o-3"})
        shipment_id = created.json()["id"]

        resp = client.post(
            f"/callbacks/test-dummy/{shipment_id}",
            json={"event": "test"},
            headers={"x-test-token": "INVALID"},
        )
        assert resp.status_code == 400
        # InvalidCallbackError is NOT retried
        assert len(retry_store.events) == 0

    def test_health_always_available(self, client: TestClient) -> None:
        """Health endpoint should work without any prior state."""
        resp = client.get("/shipments/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
