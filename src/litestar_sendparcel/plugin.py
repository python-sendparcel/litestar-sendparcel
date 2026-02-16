"""Router/plugin factory for litestar-sendparcel."""

from __future__ import annotations

from litestar import Router
from litestar.di import Provide
from sendparcel.protocols import ShipmentRepository

from litestar_sendparcel.config import SendparcelConfig
from litestar_sendparcel.exceptions import EXCEPTION_HANDLERS
from litestar_sendparcel.protocols import CallbackRetryStore, OrderResolver
from litestar_sendparcel.registry import LitestarPluginRegistry
from litestar_sendparcel.routes.callbacks import CallbackController
from litestar_sendparcel.routes.shipments import ShipmentController


def create_shipping_router(
    *,
    config: SendparcelConfig,
    repository: ShipmentRepository,
    registry: LitestarPluginRegistry | None = None,
    order_resolver: OrderResolver | None = None,
    retry_store: CallbackRetryStore | None = None,
) -> Router:
    """Create a configured Litestar router.

    Args:
        config: Shipping configuration.
        repository: Shipment persistence backend.
        registry: Plugin registry. Creates a new one if not provided.
        order_resolver: Resolves order IDs to Order objects.
        retry_store: Storage for webhook retry queue.

    Returns:
        A Litestar Router with all shipping endpoints.
    """
    actual_registry = registry or LitestarPluginRegistry()
    actual_registry.discover()

    return Router(
        path="/",
        route_handlers=[
            ShipmentController,
            CallbackController,
        ],
        dependencies={
            "config": Provide(lambda: config, sync_to_thread=False),
            "repository": Provide(lambda: repository, sync_to_thread=False),
            "registry": Provide(
                lambda: actual_registry,
                sync_to_thread=False,
            ),
            "order_resolver": Provide(
                lambda: order_resolver,
                sync_to_thread=False,
            ),
            "retry_store": Provide(lambda: retry_store, sync_to_thread=False),
        },
        exception_handlers=EXCEPTION_HANDLERS,
    )
