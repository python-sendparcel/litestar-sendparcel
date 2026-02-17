"""SQLAlchemy models implementing sendparcel core protocols."""

from __future__ import annotations

from decimal import Decimal

from sendparcel.types import AddressInfo, ParcelInfo
from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    pass


class Order(Base):
    """Order model implementing sendparcel Order protocol."""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(100), unique=True)

    sender_email: Mapped[str] = mapped_column(String(255))
    sender_name: Mapped[str] = mapped_column(String(255), default="")
    sender_country_code: Mapped[str] = mapped_column(String(2), default="PL")

    recipient_email: Mapped[str] = mapped_column(String(255))
    recipient_phone: Mapped[str] = mapped_column(String(50))
    recipient_name: Mapped[str] = mapped_column(String(255), default="")
    recipient_line1: Mapped[str] = mapped_column(String(500), default="")
    recipient_city: Mapped[str] = mapped_column(String(255), default="")
    recipient_postal_code: Mapped[str] = mapped_column(String(20), default="")
    recipient_country_code: Mapped[str] = mapped_column(String(2), default="PL")
    recipient_locker_code: Mapped[str] = mapped_column(String(50), default="")

    package_size: Mapped[str] = mapped_column(String(5), default="M")
    weight_kg: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), default=Decimal("1.0")
    )
    notes: Mapped[str] = mapped_column(Text, default="")

    shipments: Mapped[list[Shipment]] = relationship(
        back_populates="order", lazy="selectin"
    )

    def get_total_weight(self) -> Decimal:
        return self.weight_kg

    def get_parcels(self) -> list[ParcelInfo]:
        return [ParcelInfo(weight_kg=self.weight_kg)]

    def get_sender_address(self) -> AddressInfo:
        return AddressInfo(
            name=self.sender_name,
            email=self.sender_email,
            country_code=self.sender_country_code,
        )

    def get_receiver_address(self) -> AddressInfo:
        return AddressInfo(
            name=self.recipient_name,
            email=self.recipient_email,
            phone=self.recipient_phone,
            line1=self.recipient_line1,
            city=self.recipient_city,
            postal_code=self.recipient_postal_code,
            country_code=self.recipient_country_code,
        )


class Shipment(Base):
    """Shipment model implementing sendparcel Shipment protocol."""

    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    status: Mapped[str] = mapped_column(String(50), default="new")
    provider: Mapped[str] = mapped_column(String(100), default="")
    external_id: Mapped[str] = mapped_column(String(255), default="")
    tracking_number: Mapped[str] = mapped_column(String(255), default="")
    label_url: Mapped[str] = mapped_column(String(500), default="")

    order: Mapped[Order] = relationship(back_populates="shipments")


class ShipmentRepository:
    """Async SQLAlchemy repository implementing ShipmentRepository protocol."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, shipment_id: str) -> Shipment:
        result = await self.session.get(Shipment, int(shipment_id))
        if result is None:
            raise KeyError(f"Shipment {shipment_id} not found")
        return result

    async def create(self, **kwargs) -> Shipment:
        order_id = kwargs.pop("order_id", None)
        # Support legacy callers that pass an ``order`` object.
        order = kwargs.pop("order", None)
        if order_id is None and order is not None:
            order_id = getattr(order, "id", order)
        shipment = Shipment(
            order_id=order_id,
            status=str(kwargs.get("status", "new")),
            provider=str(kwargs.get("provider", "")),
            external_id=str(kwargs.get("external_id", "")),
            tracking_number=str(kwargs.get("tracking_number", "")),
            label_url=str(kwargs.get("label_url", "")),
        )
        self.session.add(shipment)
        await self.session.flush()
        return shipment

    async def save(self, shipment: Shipment) -> Shipment:
        self.session.add(shipment)
        await self.session.flush()
        return shipment

    async def update_status(
        self, shipment_id: str, status: str, **fields
    ) -> Shipment:
        shipment = await self.get_by_id(shipment_id)
        shipment.status = status
        for key, value in fields.items():
            if hasattr(shipment, key):
                setattr(shipment, key, value)
        await self.session.flush()
        return shipment


engine = create_async_engine("sqlite+aiosqlite:///example.db")
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    """Create all tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
