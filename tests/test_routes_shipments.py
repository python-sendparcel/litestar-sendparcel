"""Shipment route tests."""

from __future__ import annotations

from litestar import Litestar
from litestar.testing import TestClient
from sendparcel.registry import registry

from litestar_sendparcel.config import SendparcelConfig
from litestar_sendparcel.plugin import create_shipping_router

from conftest import DummyTestProvider, InMemoryRepo


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


def _create_no_resolver_client(
    repository: InMemoryRepo,
) -> TestClient:
    """Build a TestClient for an app WITHOUT an order resolver.

    Relies on the ``isolate_global_registry`` autouse fixture for cleanup.
    """
    registry.register(DummyTestProvider)
    config = SendparcelConfig(default_provider="test-dummy")
    router = create_shipping_router(
        config=config,
        repository=repository,  # type: ignore[arg-type]
        order_resolver=None,
    )
    app = Litestar(route_handlers=[router])
    return TestClient(app)


class TestDirectShipmentCreation:
    """HTTP tests for the direct shipment creation flow (no order_id)."""

    def test_create_shipment_direct(self, client: TestClient) -> None:
        """POST /shipments with sender/receiver/parcels creates shipment."""
        resp = client.post(
            "/shipments",
            json={
                "sender_address": {"country_code": "PL"},
                "receiver_address": {"country_code": "DE"},
                "parcels": [{"weight_kg": "1.0"}],
            },
        )
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
        assert "order_id" in resp.json()["detail"].lower()

    def test_create_shipment_empty_body_returns_500(
        self, client: TestClient
    ) -> None:
        """Empty request body returns 500 (ConfigurationError)."""
        resp = client.post("/shipments", json={})
        assert resp.status_code == 500
        assert "order_id" in resp.json()["detail"].lower()


class TestNoResolverConfigured:
    """HTTP tests when order_resolver is None."""

    def test_create_shipment_no_resolver(
        self, repository: InMemoryRepo
    ) -> None:
        """order_id provided but no resolver configured returns 500."""
        with _create_no_resolver_client(repository) as client:
            resp = client.post("/shipments", json={"order_id": "o-1"})
            assert resp.status_code == 500
            assert "resolver" in resp.json()["detail"].lower()
