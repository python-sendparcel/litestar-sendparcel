# tests/test_routes_shipments.py
"""Shipment route tests."""

from litestar import Controller

from litestar_sendparcel.routes.shipments import ShipmentController


def test_shipment_controller_is_controller() -> None:
    assert issubclass(ShipmentController, Controller)


def test_shipment_controller_path() -> None:
    assert ShipmentController.path == "/shipments"
