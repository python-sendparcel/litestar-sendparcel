"""E2E tests: full parcel dispatch flow with label PDF verification."""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest
from litestar import Litestar
from litestar.testing import TestClient
from sendparcel.flow import ShipmentFlow
from sendparcel.registry import registry as core_registry
from sendparcel.types import AddressInfo, ParcelInfo
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Add example directory to path so its modules can be imported directly.
_example_dir = str(Path(__file__).resolve().parent.parent / "example")
if _example_dir not in sys.path:
    sys.path.insert(0, _example_dir)

from delivery_sim import (  # noqa: E402
    DeliverySimProvider,
    _build_label_pdf,
    _sim_state,
    sim_label,
)
from models import Base, Shipment, ShipmentRepository  # noqa: E402

SENDER = AddressInfo(
    name="Test Sender",
    line1="10 Origin St",
    city="Warsaw",
    postal_code="00-001",
    country_code="PL",
)
RECEIVER = AddressInfo(
    name="Test Recipient",
    email="recipient@test.example",
    phone="+48123456789",
    line1="5 Destination St",
    city="Krakow",
    postal_code="30-001",
    country_code="PL",
)
PARCELS = [ParcelInfo(weight_kg=Decimal("2.5"))]


@pytest.fixture()
async def db_session():
    """In-memory async SQLAlchemy session with example models."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture(autouse=True)
def _register_sim_provider():
    """Register DeliverySimProvider and clear simulator state."""
    core_registry.register(DeliverySimProvider)
    _sim_state.clear()
    yield
    _sim_state.clear()


class TestFullParcelDispatchFlow:
    """E2E: shipment creation -> label -> PDF verification."""

    async def test_create_shipment_and_download_label(
        self, db_session: AsyncSession
    ):
        """Full flow: create shipment, generate label, verify PDF bytes."""
        repo = ShipmentRepository(db_session)
        flow = ShipmentFlow(repository=repo)

        # Create shipment via provider
        shipment = await flow.create_shipment(
            "delivery-sim",
            sender_address=SENDER,
            receiver_address=RECEIVER,
            parcels=PARCELS,
            reference_id="SHP-0001",
        )
        assert shipment.provider == "delivery-sim"
        assert shipment.external_id.startswith("sim-")
        assert "SIM-" in shipment.tracking_number
        assert shipment.status == "created"

        # Generate label
        shipment = await flow.create_label(shipment)
        assert shipment.label_url is not None
        assert "/sim/label/" in shipment.label_url
        assert shipment.label_url.endswith(".pdf")
        assert shipment.status == "label_ready"

        # Verify PDF can be generated for this shipment
        clean_id = str(shipment.id)
        pdf_bytes = _build_label_pdf(f"Shipment label {clean_id}")
        assert pdf_bytes.startswith(b"%PDF-1.4")
        assert b"%%EOF" in pdf_bytes
        assert len(pdf_bytes) > 100

    async def test_shipment_persisted_in_database(
        self, db_session: AsyncSession
    ):
        """Shipment created via flow is retrievable from the database."""
        repo = ShipmentRepository(db_session)
        flow = ShipmentFlow(repository=repo)

        shipment = await flow.create_shipment(
            "delivery-sim",
            sender_address=SENDER,
            receiver_address=RECEIVER,
            parcels=PARCELS,
            reference_id="SHP-0002",
        )
        retrieved = await repo.get_by_id(str(shipment.id))
        assert retrieved is not None
        assert retrieved.provider == "delivery-sim"
        assert retrieved.external_id == shipment.external_id
        assert retrieved.tracking_number == shipment.tracking_number

    async def test_multiple_shipments(self, db_session: AsyncSession):
        """Multiple shipments can be created independently."""
        repo = ShipmentRepository(db_session)
        flow = ShipmentFlow(repository=repo)

        s1 = await flow.create_shipment(
            "delivery-sim",
            sender_address=SENDER,
            receiver_address=RECEIVER,
            parcels=PARCELS,
            reference_id="SHP-0003",
        )
        s2 = await flow.create_shipment(
            "delivery-sim",
            sender_address=SENDER,
            receiver_address=RECEIVER,
            parcels=PARCELS,
            reference_id="SHP-0004",
        )
        assert s1.id != s2.id
        assert s1.external_id != s2.external_id
        assert s1.tracking_number != s2.tracking_number

    async def test_sim_state_tracks_shipment(self, db_session: AsyncSession):
        """DeliverySimProvider records shipment status in _sim_state."""
        repo = ShipmentRepository(db_session)
        flow = ShipmentFlow(repository=repo)

        shipment = await flow.create_shipment(
            "delivery-sim",
            sender_address=SENDER,
            receiver_address=RECEIVER,
            parcels=PARCELS,
            reference_id="SHP-0005",
        )
        sid = str(shipment.id)
        assert sid in _sim_state
        assert _sim_state[sid] == "created"


class TestLabelPdfGeneration:
    """Unit-level tests for _build_label_pdf."""

    def test_pdf_content_structure(self):
        """Generated PDF has expected internal objects."""
        pdf_bytes = _build_label_pdf("Shipment label test-123")
        assert pdf_bytes.startswith(b"%PDF-1.4")
        assert b"%%EOF" in pdf_bytes
        assert b"/Type /Catalog" in pdf_bytes
        assert b"/Type /Page" in pdf_bytes
        assert b"Helvetica" in pdf_bytes
        assert b"Shipment label test-123" in pdf_bytes

    def test_pdf_escapes_special_characters(self):
        """Parentheses and backslashes are properly escaped."""
        pdf_bytes = _build_label_pdf("Test (special) chars\\")
        assert b"Test \\(special\\) chars\\\\" in pdf_bytes

    def test_pdf_empty_text(self):
        """Empty text produces a valid PDF."""
        pdf_bytes = _build_label_pdf("")
        assert pdf_bytes.startswith(b"%PDF-1.4")
        assert b"%%EOF" in pdf_bytes

    def test_pdf_non_trivial_size(self):
        """Generated PDF has a reasonable byte size."""
        pdf_bytes = _build_label_pdf("Label text")
        # A minimal PDF with xref table should be at least a few hundred bytes
        assert len(pdf_bytes) > 200


class TestLabelEndpoint:
    """Test the label PDF HTTP endpoint via Litestar TestClient."""

    def test_label_endpoint_returns_pdf(self):
        """GET /sim/label/{id}.pdf returns a valid PDF response."""
        app = Litestar(route_handlers=[sim_label])
        with TestClient(app=app) as client:
            response = client.get("/sim/label/42.pdf")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.content.startswith(b"%PDF-1.4")
        assert b"%%EOF" in response.content
        assert "content-disposition" in response.headers
        assert "label-42.pdf" in response.headers["content-disposition"]

    def test_label_endpoint_strips_pdf_extension(self):
        """The endpoint strips .pdf suffix so the label text contains
        the clean id only."""
        app = Litestar(route_handlers=[sim_label])
        with TestClient(app=app) as client:
            response = client.get("/sim/label/test-id.pdf")

        assert response.status_code == 200
        # Label text embeds clean id, not "test-id.pdf"
        assert b"test-id" in response.content

    def test_label_endpoint_without_pdf_suffix(self):
        """Endpoint also works when called without .pdf suffix."""
        app = Litestar(route_handlers=[sim_label])
        with TestClient(app=app) as client:
            response = client.get("/sim/label/99")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert b"99" in response.content
