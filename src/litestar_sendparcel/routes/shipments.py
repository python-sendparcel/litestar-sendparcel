"""Shipment endpoints."""

from __future__ import annotations

from litestar import get, post
from litestar.exceptions import HTTPException
from sendparcel.flow import ShipmentFlow
from sendparcel.protocols import ShipmentRepository

from litestar_sendparcel.config import SendparcelConfig
from litestar_sendparcel.protocols import OrderResolver
from litestar_sendparcel.schemas import CreateShipmentRequest, ShipmentResponse


@get("/shipments/health")
async def shipments_health() -> dict[str, str]:
    """Healthcheck endpoint for shipment routes."""
    return {"status": "ok"}


@post("/shipments")
async def create_shipment(
    data: CreateShipmentRequest,
    config: SendparcelConfig,
    repository: ShipmentRepository,
    order_resolver: OrderResolver | None,
) -> ShipmentResponse:
    """Create a shipment via ShipmentFlow."""
    if order_resolver is None:
        raise HTTPException(
            status_code=500,
            detail="Order resolver not configured",
        )

    provider_slug = data.provider or config.default_provider
    order = await order_resolver.resolve(data.order_id)
    flow = ShipmentFlow(repository=repository, config=config.providers)
    shipment = await flow.create_shipment(order, provider_slug)
    return ShipmentResponse.from_shipment(shipment)


@post("/shipments/{shipment_id:str}/label")
async def create_label(
    shipment_id: str,
    config: SendparcelConfig,
    repository: ShipmentRepository,
) -> ShipmentResponse:
    """Create shipment label via provider."""
    flow = ShipmentFlow(repository=repository, config=config.providers)
    shipment = await repository.get_by_id(shipment_id)
    shipment = await flow.create_label(shipment)
    return ShipmentResponse.from_shipment(shipment)


@get("/shipments/{shipment_id:str}/status")
async def fetch_status(
    shipment_id: str,
    config: SendparcelConfig,
    repository: ShipmentRepository,
) -> ShipmentResponse:
    """Fetch and persist latest provider shipment status."""
    flow = ShipmentFlow(repository=repository, config=config.providers)
    shipment = await repository.get_by_id(shipment_id)
    shipment = await flow.fetch_and_update_status(shipment)
    return ShipmentResponse.from_shipment(shipment)
