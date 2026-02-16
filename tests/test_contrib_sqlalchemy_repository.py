"""Tests for SQLAlchemy ShipmentRepository implementation."""

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from litestar_sendparcel.contrib.sqlalchemy.models import Base
from litestar_sendparcel.contrib.sqlalchemy.repository import (
    SQLAlchemyShipmentRepository,
)


@pytest.fixture
async def engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession)


@pytest.fixture
def repo(session_factory):
    return SQLAlchemyShipmentRepository(session_factory=session_factory)


async def test_create_shipment(repo):
    """Repository creates a shipment."""
    shipment = await repo.create(
        order_id="order-1",
        provider="dummy",
        status="new",
    )
    assert shipment.id is not None
    assert shipment.order_id == "order-1"
    assert shipment.status == "new"
    assert shipment.provider == "dummy"


async def test_get_by_id(repo):
    """Repository retrieves a shipment by ID."""
    created = await repo.create(
        order_id="order-1",
        provider="dummy",
        status="new",
    )
    fetched = await repo.get_by_id(created.id)
    assert fetched.id == created.id
    assert fetched.order_id == "order-1"


async def test_get_by_id_not_found(repo):
    """KeyError when shipment not found."""
    with pytest.raises(KeyError):
        await repo.get_by_id("nonexistent")


async def test_save_shipment(repo):
    """Repository saves updated shipment fields."""
    shipment = await repo.create(
        order_id="order-1",
        provider="dummy",
        status="new",
    )
    shipment.external_id = "ext-123"
    saved = await repo.save(shipment)
    assert saved.external_id == "ext-123"

    fetched = await repo.get_by_id(shipment.id)
    assert fetched.external_id == "ext-123"


async def test_update_status(repo):
    """Repository updates shipment status."""
    shipment = await repo.create(
        order_id="order-1",
        provider="dummy",
        status="new",
    )
    updated = await repo.update_status(
        shipment.id, "label_ready", external_id="ext-456"
    )
    assert updated.status == "label_ready"
    assert updated.external_id == "ext-456"


async def test_list_by_order(repo):
    """Repository lists shipments for an order."""
    await repo.create(
        order_id="order-1",
        provider="dummy",
        status="new",
    )
    await repo.create(
        order_id="order-1",
        provider="inpost",
        status="new",
    )
    await repo.create(
        order_id="order-2",
        provider="dummy",
        status="new",
    )

    shipments = await repo.list_by_order("order-1")
    assert len(shipments) == 2
    assert all(s.order_id == "order-1" for s in shipments)


async def test_list_by_order_empty(repo):
    """Empty list when no shipments for order."""
    shipments = await repo.list_by_order("nonexistent")
    assert shipments == []
