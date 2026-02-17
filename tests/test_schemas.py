"""Schema tests."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from litestar_sendparcel.schemas import (
    CallbackResponse,
    CreateShipmentRequest,
    ShipmentResponse,
)


class TestCreateShipmentRequest:
    def test_empty_request_is_valid(self) -> None:
        """All fields are optional -- empty request is accepted."""
        req = CreateShipmentRequest()
        assert req.reference_id is None
        assert req.provider is None
        assert req.sender_address is None
        assert req.receiver_address is None
        assert req.parcels is None

    def test_reference_id_accepted(self) -> None:
        req = CreateShipmentRequest(reference_id="ref-1")
        assert req.reference_id == "ref-1"

    def test_provider_defaults_to_none(self) -> None:
        req = CreateShipmentRequest(reference_id="ref-1")
        assert req.provider is None

    def test_provider_accepted(self) -> None:
        req = CreateShipmentRequest(reference_id="ref-1", provider="inpost")
        assert req.provider == "inpost"

    def test_direct_fields_accepted(self) -> None:
        req = CreateShipmentRequest(
            sender_address={"country_code": "PL"},
            receiver_address={"country_code": "DE"},
            parcels=[{"weight_kg": 1.0}],
        )
        assert req.sender_address == {"country_code": "PL"}
        assert req.receiver_address == {"country_code": "DE"}
        assert req.parcels == [{"weight_kg": 1.0}]


class TestShipmentResponse:
    def test_all_fields_accepted(self) -> None:
        resp = ShipmentResponse(
            id="s-1",
            status="created",
            provider="dummy",
            external_id="ext-1",
            tracking_number="TRK-1",
            label_url="https://example.com/label.pdf",
        )
        assert resp.id == "s-1"
        assert resp.status == "created"

    def test_missing_field_raises(self) -> None:
        with pytest.raises(ValidationError):
            ShipmentResponse(id="s-1", status="created")

    def test_from_shipment_classmethod(self) -> None:
        @dataclass
        class FakeShipment:
            id: str = "s-1"
            status: str = "created"
            provider: str = "dummy"
            external_id: str = "ext-1"
            tracking_number: str = "TRK-1"
            label_url: str = ""

        resp = ShipmentResponse.from_shipment(FakeShipment())
        assert resp.id == "s-1"
        assert resp.provider == "dummy"
        assert resp.label_url == ""


class TestCallbackResponse:
    def test_all_fields_accepted(self) -> None:
        resp = CallbackResponse(
            provider="dummy",
            status="accepted",
            shipment_status="in_transit",
        )
        assert resp.provider == "dummy"

    def test_missing_field_raises(self) -> None:
        with pytest.raises(ValidationError):
            CallbackResponse(provider="dummy")
