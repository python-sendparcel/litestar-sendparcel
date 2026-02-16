"""Litestar adapter protocol extensions."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from sendparcel.protocols import Order


@runtime_checkable
class OrderResolver(Protocol):
    """Resolves order IDs to core Order objects."""

    async def resolve(self, order_id: str) -> Order: ...


@runtime_checkable
class CallbackRetryStore(Protocol):
    """Storage abstraction for failed callback retries."""

    async def store_failed_callback(
        self,
        shipment_id: str,
        provider_slug: str,
        payload: dict,
        headers: dict,
    ) -> str: ...
