"""Shipment route tests."""

from litestar_sendparcel.routes.shipments import shipments_health


def test_shipments_health_handler_name() -> None:
    assert shipments_health.handler_name == "shipments_health"
