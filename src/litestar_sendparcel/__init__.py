"""Litestar adapter public API."""

__version__ = "0.1.0"

from litestar_sendparcel.config import SendparcelConfig
from litestar_sendparcel.plugin import create_shipping_router
from litestar_sendparcel.registry import LitestarPluginRegistry

__all__ = [
    "LitestarPluginRegistry",
    "SendparcelConfig",
    "__version__",
    "create_shipping_router",
]
