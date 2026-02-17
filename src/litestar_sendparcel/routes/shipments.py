"""Shipment endpoints."""

from __future__ import annotations

import logging
from typing import Annotated, ClassVar

from litestar import Controller, get, post
from litestar.params import Dependency
from sendparcel.flow import ShipmentFlow
from sendparcel.protocols import ShipmentRepository

from litestar_sendparcel.config import SendparcelConfig
from litestar_sendparcel.exceptions import (
    ConfigurationError,
    ShipmentNotFoundError,
)
from litestar_sendparcel.schemas import CreateShipmentRequest, ShipmentResponse

logger = logging.getLogger(__name__)


class ShipmentController(Controller):
    """Shipment CRUD endpoints."""

    path = "/shipments"
    tags: ClassVar[list[str]] = ["shipments"]

    @get("/health")
    async def shipments_health(self) -> dict[str, str]:
        """Healthcheck endpoint for shipment routes."""
        return {"status": "ok"}

    @post("/")
    async def create_shipment(
        self,
        data: CreateShipmentRequest,
        config: Annotated[SendparcelConfig, Dependency(skip_validation=True)],
        repository: Annotated[
            ShipmentRepository, Dependency(skip_validation=True)
        ],
    ) -> ShipmentResponse:
        """Create a shipment via ShipmentFlow.

        Requires ``sender_address``, ``receiver_address``, and ``parcels``.
        Optionally accepts ``reference_id`` for external reference tracking.
        """
        provider_slug = data.provider or config.default_provider
        flow = ShipmentFlow(repository=repository, config=config.providers)

        if (
            data.sender_address is not None
            and data.receiver_address is not None
            and data.parcels is not None
        ):
            shipment = await flow.create_shipment(
                provider_slug,
                sender_address=data.sender_address,
                receiver_address=data.receiver_address,
                parcels=data.parcels,
            )
        else:
            raise ConfigurationError(
                "Provide 'sender_address', 'receiver_address', and 'parcels'"
            )

        return ShipmentResponse.from_shipment(shipment)

    @post("/{shipment_id:str}/label")
    async def create_label(
        self,
        shipment_id: str,
        config: Annotated[SendparcelConfig, Dependency(skip_validation=True)],
        repository: Annotated[
            ShipmentRepository, Dependency(skip_validation=True)
        ],
    ) -> ShipmentResponse:
        """Create shipment label via provider."""
        flow = ShipmentFlow(repository=repository, config=config.providers)
        try:
            shipment = await repository.get_by_id(shipment_id)
        except KeyError as exc:
            raise ShipmentNotFoundError(shipment_id) from exc
        shipment = await flow.create_label(shipment)
        return ShipmentResponse.from_shipment(shipment)

    @get("/{shipment_id:str}/status")
    async def fetch_status(
        self,
        shipment_id: str,
        config: Annotated[SendparcelConfig, Dependency(skip_validation=True)],
        repository: Annotated[
            ShipmentRepository, Dependency(skip_validation=True)
        ],
    ) -> ShipmentResponse:
        """Fetch and persist latest provider shipment status."""
        flow = ShipmentFlow(repository=repository, config=config.providers)
        try:
            shipment = await repository.get_by_id(shipment_id)
        except KeyError as exc:
            raise ShipmentNotFoundError(shipment_id) from exc
        shipment = await flow.fetch_and_update_status(shipment)
        return ShipmentResponse.from_shipment(shipment)
