"""Litestar example app demonstrating litestar-sendparcel integration."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from decimal import Decimal
from pathlib import Path

from delivery_sim import (
    STATUS_LABELS,
    DeliverySimProvider,
    sim_router,
)
from litestar import Litestar, Request, get, post
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.exceptions import NotFoundException
from litestar.response import Redirect, Template
from litestar.template import TemplateConfig
from models import (
    Shipment,
    ShipmentRepository,
    async_session,
    init_db,
)
from sendparcel.enums import ShipmentStatus
from sendparcel.flow import ShipmentFlow
from sendparcel.registry import registry
from sendparcel.types import AddressInfo, ParcelInfo
from sqlalchemy import func, select

TEMPLATES_DIR = Path(__file__).parent / "templates"

# --- Register the simulator provider ---
registry.register(DeliverySimProvider)

# --- Weight presets ---
WEIGHT_BY_SIZE: dict[str, Decimal] = {
    "S": Decimal("0.5"),
    "M": Decimal("1.0"),
    "L": Decimal("2.5"),
}


# --- Template helpers ---
def status_label(status: str) -> str:
    """Human-readable label for a shipment status."""
    return STATUS_LABELS.get(status, status)


def status_color(status: str) -> str:
    """Tabler badge color for a shipment status."""
    colors: dict[str, str] = {
        ShipmentStatus.NEW: "secondary",
        ShipmentStatus.CREATED: "info",
        ShipmentStatus.LABEL_READY: "cyan",
        ShipmentStatus.IN_TRANSIT: "blue",
        ShipmentStatus.OUT_FOR_DELIVERY: "indigo",
        ShipmentStatus.DELIVERED: "success",
        ShipmentStatus.CANCELLED: "warning",
        ShipmentStatus.FAILED: "danger",
        ShipmentStatus.RETURNED: "orange",
    }
    return colors.get(status, "secondary")


# --- Lifespan: init DB ---
@asynccontextmanager
async def lifespan(app: Litestar) -> AsyncGenerator[None, None]:
    await init_db()
    yield


# --- Route handlers ---


@get("/")
async def home() -> Template:
    """Render shipment list."""
    async with async_session() as session:
        result = await session.execute(
            select(Shipment).order_by(Shipment.id.desc())
        )
        shipments = result.scalars().all()
    return Template(
        template_name="home.html",
        context={
            "shipments": shipments,
            "status_label": status_label,
            "status_color": status_color,
        },
    )


@get("/shipments/new")
async def shipment_new() -> Template:
    """Render new shipment form."""
    providers = registry.get_choices()
    return Template(
        template_name="delivery_gateway.html",
        context={"providers": providers},
    )


@post("/shipments/create")
async def shipment_create(request: Request) -> Redirect:
    """Create a new shipment from form submission."""
    form = await request.form()
    package_size = str(form.get("package_size", "M"))
    weight = WEIGHT_BY_SIZE.get(package_size, Decimal("1.0"))
    provider_slug = str(form.get("provider", registry.get_choices()[0][0]))

    sender_address = AddressInfo(
        name=str(form.get("sender_name", "")),
        line1=str(form.get("sender_line1", "")),
        city=str(form.get("sender_city", "")),
        postal_code=str(form.get("sender_postal_code", "")),
        country_code="PL",
    )
    receiver_address = AddressInfo(
        name=str(form.get("recipient_name", "")),
        email=str(form.get("recipient_email", "")),
        phone=str(form.get("recipient_phone", "")),
        line1=str(form.get("recipient_line1", "")),
        city=str(form.get("recipient_city", "")),
        postal_code=str(form.get("recipient_postal_code", "")),
        country_code="PL",
    )
    parcels = [ParcelInfo(weight_kg=weight)]

    async with async_session() as session:
        count_result = await session.execute(select(func.count(Shipment.id)))
        count = count_result.scalar() or 0
        reference_id = f"SHP-{count + 1:04d}"

        repo = ShipmentRepository(session)
        flow = ShipmentFlow(repository=repo)
        shipment = await flow.create_shipment(
            provider_slug,
            sender_address=sender_address,
            receiver_address=receiver_address,
            parcels=parcels,
            reference_id=reference_id,
        )

        # Store address and parcel data on the example model
        shipment.sender_name = str(form.get("sender_name", ""))
        shipment.sender_street = str(form.get("sender_line1", ""))
        shipment.sender_city = str(form.get("sender_city", ""))
        shipment.sender_postal_code = str(form.get("sender_postal_code", ""))
        shipment.receiver_name = str(form.get("recipient_name", ""))
        shipment.receiver_street = str(form.get("recipient_line1", ""))
        shipment.receiver_city = str(form.get("recipient_city", ""))
        shipment.receiver_postal_code = str(
            form.get("recipient_postal_code", "")
        )
        shipment.weight = weight

        with suppress(NotImplementedError):
            shipment = await flow.create_label(shipment)
        await session.commit()
        return Redirect(path=f"/shipments/{shipment.id}")


@get("/shipments/{shipment_id:int}")
async def shipment_detail(shipment_id: int) -> Template:
    """Render shipment detail page."""
    async with async_session() as session:
        shipment = await session.get(Shipment, shipment_id)
        if shipment is None:
            raise NotFoundException(detail="Shipment not found")
    return Template(
        template_name="shipment_detail.html",
        context={
            "shipment": shipment,
            "status_label": status_label,
            "status_color": status_color,
        },
    )


@post("/shipments/{shipment_id:int}/create-label")
async def shipment_create_label(shipment_id: int) -> Redirect:
    """Generate label for shipment."""
    async with async_session() as session:
        repo = ShipmentRepository(session)
        flow = ShipmentFlow(repository=repo)
        shipment = await repo.get_by_id(str(shipment_id))
        with suppress(NotImplementedError):
            shipment = await flow.create_label(shipment)
        await session.commit()
    return Redirect(path=f"/shipments/{shipment_id}")


@get("/shipments/{shipment_id:int}/refresh-status")
async def shipment_refresh_status(shipment_id: int) -> Template:
    """HTMX endpoint: fetch latest status and return badge HTML."""
    async with async_session() as session:
        repo = ShipmentRepository(session)
        flow = ShipmentFlow(repository=repo)
        shipment = await repo.get_by_id(str(shipment_id))
        shipment = await flow.fetch_and_update_status(shipment)
        await session.commit()

        return Template(
            template_name="partials/status_badge.html",
            context={
                "shipment": shipment,
                "status_label": status_label,
                "status_color": status_color,
            },
        )


# --- Litestar app ---

app = Litestar(
    route_handlers=[
        home,
        shipment_new,
        shipment_create,
        shipment_detail,
        shipment_create_label,
        shipment_refresh_status,
        sim_router,
    ],
    template_config=TemplateConfig(
        engine=JinjaTemplateEngine,
        directory=TEMPLATES_DIR,
    ),
    lifespan=[lifespan],
    debug=True,
)
