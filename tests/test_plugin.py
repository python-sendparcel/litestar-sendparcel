"""Plugin tests."""

from litestar import Litestar, Router
from litestar.testing import TestClient

from litestar_sendparcel.config import SendparcelConfig
from litestar_sendparcel.exceptions import EXCEPTION_HANDLERS
from litestar_sendparcel.plugin import create_shipping_router


class _Repo:
    async def get_by_id(self, shipment_id: str):
        raise NotImplementedError

    async def create(self, **kwargs):
        raise NotImplementedError

    async def save(self, shipment):
        raise NotImplementedError

    async def update_status(self, shipment_id: str, status: str, **fields):
        raise NotImplementedError


def test_create_shipping_router_returns_router() -> None:
    router = create_shipping_router(
        config=SendparcelConfig(default_provider="dummy"),
        repository=_Repo(),
    )

    assert isinstance(router, Router)


def test_router_has_exception_handlers() -> None:
    """Router includes EXCEPTION_HANDLERS."""
    router = create_shipping_router(
        config=SendparcelConfig(default_provider="dummy"),
        repository=_Repo(),
    )
    for exc_type, handler_fn in EXCEPTION_HANDLERS.items():
        assert exc_type in router.exception_handlers
        assert router.exception_handlers[exc_type] is handler_fn


def test_router_has_route_handlers() -> None:
    """Router should include both ShipmentController and CallbackController."""
    router = create_shipping_router(
        config=SendparcelConfig(default_provider="dummy"),
        repository=_Repo(),
    )
    assert len(router.routes) > 0


def test_health_endpoint_accessible() -> None:
    """Health endpoint returns 200 with status ok."""
    router = create_shipping_router(
        config=SendparcelConfig(default_provider="dummy"),
        repository=_Repo(),
    )
    app = Litestar(route_handlers=[router])
    with TestClient(app=app) as client:
        resp = client.get("/shipments/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


def test_dependencies_include_config_and_repository() -> None:
    """Router dependencies must include config and repository."""
    router = create_shipping_router(
        config=SendparcelConfig(default_provider="dummy"),
        repository=_Repo(),
    )
    assert "config" in router.dependencies
    assert "repository" in router.dependencies
