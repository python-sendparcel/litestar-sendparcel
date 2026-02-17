"""Simulated delivery provider with control panel routes."""

from __future__ import annotations

from typing import ClassVar
from uuid import uuid4

from litestar import Response, Router, get, post
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
    display_name: ClassVar[str] = "Delivery Simulator"
    supported_countries: ClassVar[list[str]] = ["PL"]
    supported_services: ClassVar[list[str]] = ["standard"]
    user_selectable: ClassVar[bool] = False

    async def create_shipment(
        self,
        *,
        sender_address=None,
        receiver_address=None,
        parcels=None,
        **kwargs,
    ) -> ShipmentCreateResult:
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

# Human-readable status labels
STATUS_LABELS: dict[str, str] = {
    ShipmentStatus.NEW: "New",
    ShipmentStatus.CREATED: "Created",
    ShipmentStatus.LABEL_READY: "Label ready",
    ShipmentStatus.IN_TRANSIT: "In transit",
    ShipmentStatus.OUT_FOR_DELIVERY: "Out for delivery",
    ShipmentStatus.DELIVERED: "Delivered",
    ShipmentStatus.CANCELLED: "Cancelled",
    ShipmentStatus.FAILED: "Failed",
    ShipmentStatus.RETURNED: "Returned",
}


def get_sim_status(shipment_id: str) -> str:
    """Get current simulator status for a shipment."""
    return _sim_state.get(shipment_id, ShipmentStatus.NEW)


def get_next_statuses(current: str) -> list[str]:
    """Get list of allowed next statuses from current."""
    return _NEXT_STATUSES.get(current, [])


# --- PDF label generation helpers ---


def _pdf_escape(value: str) -> str:
    """Escape special PDF string characters."""
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_label_pdf(text: str) -> bytes:
    """Generate a minimal valid PDF with the given text."""
    stream = (f"BT /F1 14 Tf 72 760 Td ({_pdf_escape(text)}) Tj ET").encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R "
            b"/MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 5 0 R >> >> "
            b"/Contents 4 0 R >>"
        ),
        (
            b"<< /Length "
            + str(len(stream)).encode("ascii")
            + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for off in offsets:
        pdf.extend(f"{off:010} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} "
            f"/Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(pdf)


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


@get("/sim/label/{shipment_id:str}")
async def sim_label(shipment_id: str) -> Response:
    """Return a generated PDF label for a simulated shipment."""
    # Strip .pdf extension if present (URL pattern is /sim/label/{id}.pdf)
    clean_id = shipment_id.removesuffix(".pdf")
    label_text = f"Shipment label {clean_id}"
    pdf_bytes = _build_label_pdf(label_text)
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="label-{clean_id}.pdf"'
        },
    )


sim_router = Router(
    path="/",
    route_handlers=[sim_panel, sim_advance, sim_label],
)
