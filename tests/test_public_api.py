# tests/test_public_api.py
"""Tests for public API surface."""

from pathlib import Path

import litestar_sendparcel


def test_version_is_set():
    """Package exposes __version__."""
    assert hasattr(litestar_sendparcel, "__version__")
    assert litestar_sendparcel.__version__ == "0.1.0"


def test_py_typed_marker_exists():
    """PEP 561 py.typed marker file exists."""
    marker = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "litestar_sendparcel"
        / "py.typed"
    )
    assert marker.exists()


def test_all_exports_are_importable():
    """Every name in __all__ is importable."""
    for name in litestar_sendparcel.__all__:
        attr = getattr(litestar_sendparcel, name)
        assert attr is not None, f"{name} resolved to None"


def test_lazy_import_config():
    """SendparcelConfig is lazily importable."""
    cls = litestar_sendparcel.SendparcelConfig
    assert cls.__name__ == "SendparcelConfig"


def test_lazy_import_router_factory():
    """create_shipping_router is lazily importable."""
    fn = litestar_sendparcel.create_shipping_router
    assert callable(fn)


def test_lazy_import_exceptions():
    """Exception classes are lazily importable."""
    assert litestar_sendparcel.ShipmentNotFoundError is not None
    assert litestar_sendparcel.ConfigurationError is not None


def test_lazy_import_protocols():
    """Protocol classes are lazily importable."""
    assert litestar_sendparcel.OrderResolver is not None
    assert litestar_sendparcel.CallbackRetryStore is not None


def test_lazy_import_schemas():
    """Schema classes are lazily importable."""
    assert litestar_sendparcel.CreateShipmentRequest is not None
    assert litestar_sendparcel.ShipmentResponse is not None
    assert litestar_sendparcel.CallbackResponse is not None


def test_getattr_raises_for_unknown():
    """Unknown attribute raises AttributeError."""
    import pytest

    with pytest.raises(AttributeError, match="no_such_attribute"):
        litestar_sendparcel.no_such_attribute  # noqa: B018
