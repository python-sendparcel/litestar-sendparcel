"""Simulated delivery provider with control panel routes."""

from __future__ import annotations

from typing import ClassVar
from uuid import uuid4

from litestar import Router, get, post
from litestar.response import Template
from sendparcel.enums import ShipmentStatus
from sendparcel.provider import BaseProvider
from sendparcel.types import (
    LabelInfo,
    ShipmentCreateResult,
    ShipmentStatusResponse,
)

# In-memory store for simulator state keyed by shipment.id
_sim_state: dict[str, str] = {}


class DeliverySimProvider(BaseProvider):
    """Simulated delivery provider for the example app."""

    slug: ClassVar[str] = "delivery-sim"
    display_name: ClassVar[str] = "Symulator Dostawy"
    supported_countries: ClassVar[list[str]] = ["PL"]
    supported_services: ClassVar[list[str]] = ["standard"]

    async def create_shipment(self, **kwargs) -> ShipmentCreateResult:
        shipment_id = str(self.shipment.id)
        tracking = f"SIM-{uuid4().hex[:8].upper()}"
        _sim_state[shipment_id] = ShipmentStatus.CREATED
        return ShipmentCreateResult(
            external_id=f"sim-{shipment_id}",
            tracking_number=tracking,
        )

    async def create_label(self, **kwargs) -> LabelInfo:
        shipment_id = str(self.shipment.id)
        return LabelInfo(
            format="PDF",
            url=f"/sim/label/{shipment_id}.pdf",
        )

    async def fetch_shipment_status(self, **kwargs) -> ShipmentStatusResponse:
        shipment_id = str(self.shipment.id)
        current = _sim_state.get(shipment_id, str(self.shipment.status))
        return ShipmentStatusResponse(status=current)

    async def cancel_shipment(self, **kwargs) -> bool:
        shipment_id = str(self.shipment.id)
        _sim_state[shipment_id] = ShipmentStatus.CANCELLED
        return True


# --- Status progression helpers ---

# Allowed forward transitions for the control panel
_NEXT_STATUSES: dict[str, list[str]] = {
    ShipmentStatus.CREATED: [
        ShipmentStatus.LABEL_READY,
        ShipmentStatus.CANCELLED,
        ShipmentStatus.FAILED,
    ],
    ShipmentStatus.LABEL_READY: [
        ShipmentStatus.IN_TRANSIT,
        ShipmentStatus.CANCELLED,
        ShipmentStatus.FAILED,
    ],
    ShipmentStatus.IN_TRANSIT: [
        ShipmentStatus.OUT_FOR_DELIVERY,
        ShipmentStatus.DELIVERED,
        ShipmentStatus.RETURNED,
        ShipmentStatus.FAILED,
    ],
    ShipmentStatus.OUT_FOR_DELIVERY: [
        ShipmentStatus.DELIVERED,
        ShipmentStatus.RETURNED,
        ShipmentStatus.FAILED,
    ],
}

# Polish labels for statuses
STATUS_LABELS: dict[str, str] = {
    ShipmentStatus.NEW: "Nowa",
    ShipmentStatus.CREATED: "Utworzona",
    ShipmentStatus.LABEL_READY: "Etykieta gotowa",
    ShipmentStatus.IN_TRANSIT: "W transporcie",
    ShipmentStatus.OUT_FOR_DELIVERY: "W doręczeniu",
    ShipmentStatus.DELIVERED: "Doręczona",
    ShipmentStatus.CANCELLED: "Anulowana",
    ShipmentStatus.FAILED: "Błąd",
    ShipmentStatus.RETURNED: "Zwrócona",
}


def get_sim_status(shipment_id: str) -> str:
    """Get current simulator status for a shipment."""
    return _sim_state.get(shipment_id, ShipmentStatus.NEW)


def get_next_statuses(current: str) -> list[str]:
    """Get list of allowed next statuses from current."""
    return _NEXT_STATUSES.get(current, [])


# --- Litestar routes for the simulator control panel ---


@get("/sim/panel/{shipment_id:int}")
async def sim_panel(shipment_id: int) -> Template:
    """Render simulator control panel partial (HTMX target)."""
    sid = str(shipment_id)
    current = get_sim_status(sid)
    next_options = get_next_statuses(current)
    return Template(
        template_name="partials/sim_panel.html",
        context={
            "shipment_id": shipment_id,
            "current_status": current,
            "current_label": STATUS_LABELS.get(current, current),
            "next_options": [
                {"value": s, "label": STATUS_LABELS.get(s, s)}
                for s in next_options
            ],
        },
    )


@post("/sim/advance/{shipment_id:int}")
async def sim_advance(shipment_id: int, data: dict) -> Template:
    """Advance simulator status for a shipment (HTMX)."""
    sid = str(shipment_id)
    new_status = data.get("status", "")
    current = get_sim_status(sid)
    allowed = get_next_statuses(current)
    if new_status in allowed:
        _sim_state[sid] = new_status

    current = get_sim_status(sid)
    next_options = get_next_statuses(current)
    return Template(
        template_name="partials/sim_panel.html",
        context={
            "shipment_id": shipment_id,
            "current_status": current,
            "current_label": STATUS_LABELS.get(current, current),
            "next_options": [
                {"value": s, "label": STATUS_LABELS.get(s, s)}
                for s in next_options
            ],
        },
    )


sim_router = Router(
    path="/",
    route_handlers=[sim_panel, sim_advance],
)
