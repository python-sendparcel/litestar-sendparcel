"""Tests for exception-to-HTTP-response mapping."""

from litestar import Litestar, get
from litestar.testing import TestClient
from sendparcel.exceptions import (
    CommunicationError,
    InvalidCallbackError,
    InvalidTransitionError,
    SendParcelException,
)

from litestar_sendparcel.exceptions import (
    EXCEPTION_HANDLERS,
    ConfigurationError,
    ShipmentNotFoundError,
)


def test_sendparcel_exception_returns_400():
    """SendParcelException maps to 400."""

    @get("/test")
    async def handler() -> None:
        raise SendParcelException("bad request")

    app = Litestar(
        route_handlers=[handler],
        exception_handlers=EXCEPTION_HANDLERS,
    )
    with TestClient(app) as client:
        resp = client.get("/test")
        assert resp.status_code == 400
        data = resp.json()
        assert data["detail"] == "bad request"
        assert data["code"] == "sendparcel_error"


def test_communication_error_returns_502():
    """CommunicationError maps to 502."""

    @get("/test")
    async def handler() -> None:
        raise CommunicationError("gateway down")

    app = Litestar(
        route_handlers=[handler],
        exception_handlers=EXCEPTION_HANDLERS,
    )
    with TestClient(app) as client:
        resp = client.get("/test")
        assert resp.status_code == 502
        assert resp.json()["code"] == "communication_error"


def test_invalid_callback_returns_400():
    """InvalidCallbackError maps to 400."""

    @get("/test")
    async def handler() -> None:
        raise InvalidCallbackError("bad signature")

    app = Litestar(
        route_handlers=[handler],
        exception_handlers=EXCEPTION_HANDLERS,
    )
    with TestClient(app) as client:
        resp = client.get("/test")
        assert resp.status_code == 400
        assert resp.json()["code"] == "invalid_callback"


def test_invalid_transition_returns_409():
    """InvalidTransitionError maps to 409."""

    @get("/test")
    async def handler() -> None:
        raise InvalidTransitionError("wrong state")

    app = Litestar(
        route_handlers=[handler],
        exception_handlers=EXCEPTION_HANDLERS,
    )
    with TestClient(app) as client:
        resp = client.get("/test")
        assert resp.status_code == 409
        assert resp.json()["code"] == "invalid_transition"


def test_shipment_not_found_returns_404():
    """ShipmentNotFoundError maps to 404."""

    @get("/test")
    async def handler() -> None:
        raise ShipmentNotFoundError("ship-123")

    app = Litestar(
        route_handlers=[handler],
        exception_handlers=EXCEPTION_HANDLERS,
    )
    with TestClient(app) as client:
        resp = client.get("/test")
        assert resp.status_code == 404
        data = resp.json()
        assert data["code"] == "not_found"
        assert "ship-123" in data["detail"]


def test_configuration_error_returns_500():
    """ConfigurationError maps to 500."""

    @get("/test")
    async def handler() -> None:
        raise ConfigurationError("missing order resolver")

    app = Litestar(
        route_handlers=[handler],
        exception_handlers=EXCEPTION_HANDLERS,
    )
    with TestClient(app) as client:
        resp = client.get("/test")
        assert resp.status_code == 500
        assert resp.json()["code"] == "configuration_error"


def test_exception_handlers_is_dict():
    """EXCEPTION_HANDLERS is a dict of exception types to callables."""
    assert isinstance(EXCEPTION_HANDLERS, dict)
    assert len(EXCEPTION_HANDLERS) == 6
    for exc_type, handler in EXCEPTION_HANDLERS.items():
        assert isinstance(exc_type, type)
        assert issubclass(exc_type, Exception)
        assert callable(handler)
