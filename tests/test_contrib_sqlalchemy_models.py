"""Tests for SQLAlchemy 2.0 async models."""

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from litestar_sendparcel.contrib.sqlalchemy.models import (
    Base,
    CallbackRetryModel,
    ShipmentModel,
)


@pytest.fixture
async def engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine):
    session_factory = async_sessionmaker(engine, class_=AsyncSession)
    async with session_factory() as session:
        yield session


async def test_shipment_model_create(session):
    """Can create a ShipmentModel with defaults."""
    shipment = ShipmentModel(
        order_id="order-1",
        provider="dummy",
    )
    session.add(shipment)
    await session.commit()
    await session.refresh(shipment)

    assert shipment.id is not None
    assert len(shipment.id) == 36  # UUID
    assert shipment.status == "new"
    assert shipment.external_id == ""
    assert shipment.tracking_number == ""
    assert shipment.label_url == ""


async def test_shipment_model_with_all_fields(session):
    """Can create a ShipmentModel with all fields populated."""
    shipment = ShipmentModel(
        order_id="order-2",
        provider="inpost",
        status="label_ready",
        external_id="ext-123",
        tracking_number="trk-456",
        label_url="https://labels/s-1.pdf",
    )
    session.add(shipment)
    await session.commit()
    await session.refresh(shipment)

    assert shipment.provider == "inpost"
    assert shipment.status == "label_ready"
    assert shipment.external_id == "ext-123"
    assert shipment.created_at is not None
    assert shipment.updated_at is not None


async def test_shipment_model_table_name():
    """ShipmentModel uses correct table name."""
    assert ShipmentModel.__tablename__ == "sendparcel_shipments"


async def test_callback_retry_model_create(session):
    """Can create a CallbackRetryModel with defaults."""
    retry = CallbackRetryModel(
        shipment_id="s-1",
        provider_slug="dummy",
        payload={"event": "picked_up"},
        headers={"content-type": "application/json"},
    )
    session.add(retry)
    await session.commit()
    await session.refresh(retry)

    assert retry.id is not None
    assert len(retry.id) == 36  # UUID
    assert retry.attempts == 0
    assert retry.status == "pending"
    assert retry.last_error is None
    assert retry.next_retry_at is None


async def test_callback_retry_model_table_name():
    """CallbackRetryModel uses correct table name."""
    assert CallbackRetryModel.__tablename__ == "sendparcel_callback_retries"
