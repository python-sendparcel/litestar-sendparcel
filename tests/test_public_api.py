# tests/test_public_api.py
"""Tests for public API surface."""

from pathlib import Path


def test_version_is_set():
    """Package exposes __version__."""
    import litestar_sendparcel

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
