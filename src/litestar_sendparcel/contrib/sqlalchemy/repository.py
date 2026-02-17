"""SQLAlchemy 2.0 async ShipmentRepository implementation."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from litestar_sendparcel.contrib.sqlalchemy.models import ShipmentModel


class SQLAlchemyShipmentRepository:
    """Shipment repository backed by SQLAlchemy async sessions.

    Implements the ShipmentRepository protocol from sendparcel.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def get_by_id(self, shipment_id: str) -> ShipmentModel:
        """Get a shipment by ID. Raises KeyError if not found."""
        async with self._session_factory() as session:
            result = await session.get(ShipmentModel, shipment_id)
            if result is None:
                raise KeyError(shipment_id)
            session.expunge(result)
            return result

    async def create(self, **kwargs) -> ShipmentModel:
        """Create a new shipment record."""
        # Ensure status is a string
        if "status" in kwargs:
            kwargs["status"] = str(kwargs["status"])
        async with self._session_factory() as session:
            shipment = ShipmentModel(**kwargs)
            session.add(shipment)
            await session.commit()
            await session.refresh(shipment)
            session.expunge(shipment)
            return shipment

    async def save(self, shipment: ShipmentModel) -> ShipmentModel:
        """Save an existing shipment (merge and commit)."""
        async with self._session_factory() as session:
            merged = await session.merge(shipment)
            await session.commit()
            await session.refresh(merged)
            session.expunge(merged)
            return merged

    async def update_status(
        self,
        shipment_id: str,
        status: str,
        **fields,
    ) -> ShipmentModel:
        """Update shipment status and optional extra fields."""
        async with self._session_factory() as session:
            shipment = await session.get(ShipmentModel, shipment_id)
            if shipment is None:
                raise KeyError(shipment_id)
            shipment.status = status
            for key, value in fields.items():
                if hasattr(shipment, key):
                    setattr(shipment, key, value)
            await session.commit()
            await session.refresh(shipment)
            session.expunge(shipment)
            return shipment

    async def list_by_reference(self, reference_id: str) -> list[ShipmentModel]:
        """List all shipments for a reference."""
        async with self._session_factory() as session:
            stmt = select(ShipmentModel).where(
                ShipmentModel.reference_id == reference_id
            )
            result = await session.execute(stmt)
            shipments = list(result.scalars().all())
            for s in shipments:
                session.expunge(s)
            return shipments
