# src/litestar_sendparcel/__init__.py
"""Litestar framework adapter for sendparcel shipping processing."""

from typing import TYPE_CHECKING

__version__ = "0.1.0"

__all__ = [
    "CallbackResponse",
    "CallbackRetryStore",
    "ConfigurationError",
    "CreateShipmentRequest",
    "LitestarPluginRegistry",
    "SendparcelConfig",
    "ShipmentNotFoundError",
    "ShipmentResponse",
    "__version__",
    "create_shipping_router",
]

if TYPE_CHECKING:
    from litestar_sendparcel.config import SendparcelConfig
    from litestar_sendparcel.exceptions import (
        ConfigurationError,
        ShipmentNotFoundError,
    )
    from litestar_sendparcel.plugin import create_shipping_router
    from litestar_sendparcel.protocols import CallbackRetryStore
    from litestar_sendparcel.registry import LitestarPluginRegistry
    from litestar_sendparcel.schemas import (
        CallbackResponse,
        CreateShipmentRequest,
        ShipmentResponse,
    )


def __getattr__(name: str):
    # Lazy imports to avoid loading all submodules on package import.
    if name == "SendparcelConfig":
        from litestar_sendparcel.config import SendparcelConfig

        return SendparcelConfig
    if name == "create_shipping_router":
        from litestar_sendparcel.plugin import create_shipping_router

        return create_shipping_router
    if name == "LitestarPluginRegistry":
        from litestar_sendparcel.registry import LitestarPluginRegistry

        return LitestarPluginRegistry
    if name == "ShipmentNotFoundError":
        from litestar_sendparcel.exceptions import ShipmentNotFoundError

        return ShipmentNotFoundError
    if name == "ConfigurationError":
        from litestar_sendparcel.exceptions import ConfigurationError

        return ConfigurationError
    if name == "CallbackRetryStore":
        from litestar_sendparcel import protocols

        return getattr(protocols, name)
    if name in (
        "CreateShipmentRequest",
        "ShipmentResponse",
        "CallbackResponse",
    ):
        from litestar_sendparcel import schemas

        return getattr(schemas, name)
    raise AttributeError(
        f"module 'litestar_sendparcel' has no attribute {name!r}"
    )
