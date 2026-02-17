"""Shared fixtures for litestar-sendparcel tests."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal

import pytest
from litestar import Litestar
from litestar.testing import TestClient
from sendparcel.exceptions import InvalidCallbackError
from sendparcel.provider import BaseProvider
from sendparcel.registry import registry

from litestar_sendparcel.config import SendparcelConfig
from litestar_sendparcel.plugin import create_shipping_router


@dataclass
class DemoOrder:
    id: str

    def get_total_weight(self) -> Decimal:
        return Decimal("1.0")

    def get_parcels(self) -> list[dict]:
        return [{"weight_kg": Decimal("1.0")}]

    def get_sender_address(self) -> dict:
        return {"country_code": "PL"}

    def get_receiver_address(self) -> dict:
        return {"country_code": "DE"}


@dataclass
class DemoShipment:
    id: str
    status: str
    provider: str
    order_id: str = ""
    external_id: str = ""
    tracking_number: str = ""
    label_url: str = ""


class InMemoryRepo:
    def __init__(self) -> None:
        self.items: dict[str, DemoShipment] = {}
        self._counter = 0

    async def get_by_id(self, shipment_id: str) -> DemoShipment:
        return self.items[shipment_id]

    async def create(self, **kwargs) -> DemoShipment:
        self._counter += 1
        shipment_id = f"s-{self._counter}"
        shipment = DemoShipment(
            id=shipment_id,
            order_id=str(kwargs.get("order_id", "")),
            provider=kwargs["provider"],
            status=str(kwargs["status"]),
        )
        self.items[shipment_id] = shipment
        return shipment

    async def save(self, shipment: DemoShipment) -> DemoShipment:
        self.items[shipment.id] = shipment
        return shipment

    async def update_status(
        self, shipment_id: str, status: str, **fields
    ) -> DemoShipment:
        shipment = self.items[shipment_id]
        shipment.status = status
        for key, value in fields.items():
            setattr(shipment, key, value)
        return shipment

    async def list_by_order(self, order_id: str) -> list[DemoShipment]:
        return [s for s in self.items.values() if s.order_id == order_id]


class OrderResolver:
    async def resolve(self, order_id: str) -> DemoOrder:
        return DemoOrder(id=order_id)


class RetryStore:
    def __init__(self) -> None:
        self.events: list[dict] = []
        self._counter = 0

    async def enqueue(self, payload: dict) -> None:
        self.events.append(payload)

    async def store_failed_callback(
        self,
        shipment_id: str,
        provider_slug: str,
        payload: dict,
        headers: dict,
    ) -> str:
        self._counter += 1
        retry_id = f"retry-{self._counter}"
        self.events.append(
            {
                "id": retry_id,
                "shipment_id": shipment_id,
                "provider_slug": provider_slug,
                "payload": payload,
                "headers": headers,
                "reason": "stored",
            }
        )
        return retry_id

    async def get_due_retries(self, limit: int = 10) -> list[dict]:
        return []

    async def mark_succeeded(self, retry_id: str) -> None:
        pass

    async def mark_failed(self, retry_id: str, error: str) -> None:
        pass

    async def mark_exhausted(self, retry_id: str) -> None:
        pass


class DummyTestProvider(BaseProvider):
    """Deterministic provider for HTTP route tests."""

    slug = "test-dummy"
    display_name = "Test Dummy"

    async def create_shipment(
        self, *, sender_address, receiver_address, parcels, **kwargs
    ):
        return {"external_id": "ext-1", "tracking_number": "TRK-1"}

    async def create_label(self, **kwargs):
        return {"format": "PDF", "url": "https://labels.test/s.pdf"}

    async def verify_callback(self, data, headers, **kwargs):
        if headers.get("x-test-token") != "valid":
            raise InvalidCallbackError("Invalid token")

    async def handle_callback(self, data, headers, **kwargs):
        if self.shipment.may_trigger("mark_in_transit"):
            self.shipment.mark_in_transit()

    async def fetch_shipment_status(self, **kwargs):
        return {"status": "in_transit"}

    async def cancel_shipment(self, **kwargs):
        return True


@pytest.fixture(autouse=True)
def isolate_global_registry() -> Iterator[None]:
    old = dict(registry._providers)
    old_discovered = registry._discovered
    registry._providers = {}
    registry._discovered = True
    try:
        yield
    finally:
        registry._providers = old
        registry._discovered = old_discovered


@pytest.fixture()
def repository() -> InMemoryRepo:
    return InMemoryRepo()


@pytest.fixture()
def resolver() -> OrderResolver:
    return OrderResolver()


@pytest.fixture()
def retry_store() -> RetryStore:
    return RetryStore()


@pytest.fixture()
def config() -> SendparcelConfig:
    return SendparcelConfig(default_provider="test-dummy")


@pytest.fixture()
def test_app(
    repository: InMemoryRepo,
    resolver: OrderResolver,
    retry_store: RetryStore,
    config: SendparcelConfig,
) -> Litestar:
    registry.register(DummyTestProvider)
    router = create_shipping_router(
        config=config,
        repository=repository,
        order_resolver=resolver,
        retry_store=retry_store,
    )
    return Litestar(route_handlers=[router])


@pytest.fixture()
def client(test_app: Litestar) -> Iterator[TestClient]:
    with TestClient(app=test_app) as tc:
        yield tc


# ---------------------------------------------------------------------------
# SQLAlchemy fixtures (conditional)
# ---------------------------------------------------------------------------

_HAS_SQLALCHEMY = False
try:
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    _HAS_SQLALCHEMY = True
except ImportError:
    pass

if _HAS_SQLALCHEMY:

    @pytest.fixture()
    async def async_engine():
        engine = create_async_engine("sqlite+aiosqlite://", echo=False)
        yield engine
        await engine.dispose()

    @pytest.fixture()
    async def async_session_factory(async_engine):
        return async_sessionmaker(
            async_engine, class_=AsyncSession, expire_on_commit=False
        )

    @pytest.fixture()
    async def async_session(async_session_factory):
        async with async_session_factory() as session:
            yield session
