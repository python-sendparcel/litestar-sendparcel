# tests/test_controllers.py
"""Tests verifying Controller-based route structure."""

from litestar import Controller

from litestar_sendparcel.routes.callbacks import CallbackController
from litestar_sendparcel.routes.shipments import ShipmentController


def test_shipment_controller_is_controller():
    """ShipmentController extends Litestar Controller."""
    assert issubclass(ShipmentController, Controller)


def test_callback_controller_is_controller():
    """CallbackController extends Litestar Controller."""
    assert issubclass(CallbackController, Controller)


def test_shipment_controller_has_tags():
    """ShipmentController has tags set."""
    assert ShipmentController.tags == ["shipments"]


def test_callback_controller_has_tags():
    """CallbackController has tags set."""
    assert CallbackController.tags == ["callbacks"]
