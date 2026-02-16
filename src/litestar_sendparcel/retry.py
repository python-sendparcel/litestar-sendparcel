"""Retry queue helpers for failed callbacks."""

from __future__ import annotations

import logging

from litestar_sendparcel.protocols import CallbackRetryStore

logger = logging.getLogger(__name__)


async def enqueue_callback_retry(
    store: CallbackRetryStore | None,
    *,
    provider_slug: str,
    shipment_id: str,
    payload: dict,
    headers: dict[str, str],
    reason: str,
) -> None:
    """Persist callback retry payload when a retry store is configured."""
    if store is None:
        return

    await store.store_failed_callback(
        shipment_id=shipment_id,
        provider_slug=provider_slug,
        payload=payload,
        headers=headers,
    )
    logger.warning(
        "Callback for shipment %s failed, queued for retry: %s",
        shipment_id,
        reason,
    )
