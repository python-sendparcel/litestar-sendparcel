"""Litestar example app demonstrating litestar-sendparcel integration."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path

from litestar import Litestar, Request, get, post
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.exceptions import NotFoundException
from litestar.response import Redirect, Template
from litestar.template import TemplateConfig
from sqlalchemy import func, select

from sendparcel.enums import ShipmentStatus
from sendparcel.flow import ShipmentFlow
from sendparcel.registry import registry

from delivery_sim import (
    STATUS_LABELS,
    DeliverySimProvider,
    sim_router,
)
from models import (
    Order,
    Shipment,
    ShipmentRepository,
    async_session,
    init_db,
)

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
    """Polish label for a shipment status."""
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
    """Render order list."""
    async with async_session() as session:
        result = await session.execute(select(Order).order_by(Order.id.desc()))
        orders = result.scalars().all()
    return Template(
        template_name="home.html",
        context={"orders": orders},
    )


@get("/orders/new")
async def order_new() -> Template:
    """Render new order form."""
    providers = registry.get_choices()
    return Template(
        template_name="delivery_gateway.html",
        context={"providers": providers},
    )


@post("/orders/create")
async def order_create(request: Request) -> Redirect:
    """Create a new order from form submission."""
    form = await request.form()
    package_size = str(form.get("package_size", "M"))
    weight = WEIGHT_BY_SIZE.get(package_size, Decimal("1.0"))

    async with async_session() as session:
        count_result = await session.execute(select(func.count(Order.id)))
        count = count_result.scalar() or 0
        reference = f"ZAM-{count + 1:04d}"

        order = Order(
            reference=reference,
            sender_email=str(form.get("sender_email", "")),
            sender_name=str(form.get("sender_name", "")),
            recipient_email=str(form.get("recipient_email", "")),
            recipient_phone=str(form.get("recipient_phone", "")),
            recipient_name=str(form.get("recipient_name", "")),
            recipient_line1=str(form.get("recipient_line1", "")),
            recipient_city=str(form.get("recipient_city", "")),
            recipient_postal_code=str(form.get("recipient_postal_code", "")),
            recipient_country_code="PL",
            recipient_locker_code=str(form.get("recipient_locker_code", "")),
            package_size=package_size,
            weight_kg=weight,
            notes=str(form.get("notes", "")),
        )
        session.add(order)
        await session.commit()
        return Redirect(path=f"/orders/{order.id}")


@get("/orders/{order_id:int}")
async def order_detail(order_id: int) -> Template:
    """Render order detail page."""
    async with async_session() as session:
        order = await session.get(Order, order_id)
        if order is None:
            raise NotFoundException(detail="Zamówienie nie znalezione")
    default_provider = registry.get_choices()[0][0]
    return Template(
        template_name="order_detail.html",
        context={
            "order": order,
            "default_provider": default_provider,
            "status_label": status_label,
            "status_color": status_color,
        },
    )


@post("/orders/{order_id:int}/ship")
async def order_ship(order_id: int, request: Request) -> Redirect:
    """Create a shipment for an order using sendparcel flow."""
    form = await request.form()
    provider_slug = str(form.get("provider", registry.get_choices()[0][0]))

    async with async_session() as session:
        order = await session.get(Order, order_id)
        if order is None:
            raise NotFoundException(detail="Zamówienie nie znalezione")

        repo = ShipmentRepository(session)
        flow = ShipmentFlow(repository=repo)
        shipment = await flow.create_shipment(order, provider_slug)
        try:
            shipment = await flow.create_label(shipment)
        except NotImplementedError:
            pass
        await session.commit()
        return Redirect(path=f"/shipments/{shipment.id}")


@get("/shipments/{shipment_id:int}")
async def shipment_detail(shipment_id: int) -> Template:
    """Render shipment detail page."""
    async with async_session() as session:
        shipment = await session.get(Shipment, shipment_id)
        if shipment is None:
            raise NotFoundException(detail="Przesyłka nie znaleziona")
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
        try:
            shipment = await flow.create_label(shipment)
        except NotImplementedError:
            pass
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
        order_new,
        order_create,
        order_detail,
        order_ship,
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
