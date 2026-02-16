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
    def test_order_id_required(self) -> None:
        with pytest.raises(ValidationError):
            CreateShipmentRequest()

    def test_provider_defaults_to_none(self) -> None:
        req = CreateShipmentRequest(order_id="o-1")
        assert req.provider is None

    def test_provider_accepted(self) -> None:
        req = CreateShipmentRequest(order_id="o-1", provider="inpost")
        assert req.provider == "inpost"


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
