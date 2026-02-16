"""Webhook retry mechanism with exponential backoff."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sendparcel.flow import ShipmentFlow
from sendparcel.protocols import ShipmentRepository

from litestar_sendparcel.config import SendparcelConfig
from litestar_sendparcel.protocols import CallbackRetryStore

logger = logging.getLogger(__name__)


def compute_next_retry_at(
    attempt: int,
    backoff_seconds: int,
) -> datetime:
    """Compute the next retry time with exponential backoff.

    delay = backoff_seconds * 2^(attempt - 1)
    """
    delay = backoff_seconds * (2 ** (attempt - 1))
    return datetime.now(tz=UTC) + timedelta(seconds=delay)


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


async def process_due_retries(
    *,
    retry_store: CallbackRetryStore,
    repository: ShipmentRepository,
    config: SendparcelConfig,
    limit: int = 10,
) -> int:
    """Process all due callback retries.

    Returns the number of retries processed.
    """
    retries = await retry_store.get_due_retries(limit=limit)
    processed = 0

    for retry in retries:
        retry_id = retry["id"]
        shipment_id = retry["shipment_id"]
        payload = retry["payload"]
        headers = retry["headers"]
        attempts = retry["attempts"]

        try:
            shipment = await repository.get_by_id(shipment_id)
        except KeyError:
            logger.error(
                "Retry %s: shipment %s not found, marking exhausted",
                retry_id,
                shipment_id,
            )
            await retry_store.mark_exhausted(retry_id)
            processed += 1
            continue

        flow = ShipmentFlow(
            repository=repository,
            config=config.providers,
        )

        try:
            await flow.handle_callback(
                shipment,
                payload,
                headers,
            )
            await retry_store.mark_succeeded(retry_id)
            logger.info(
                "Retry %s: callback for shipment %s succeeded",
                retry_id,
                shipment_id,
            )
        except Exception as exc:
            if attempts >= config.retry_max_attempts:
                await retry_store.mark_exhausted(retry_id)
                logger.warning(
                    "Retry %s: exhausted after %d attempts: %s",
                    retry_id,
                    attempts,
                    exc,
                )
            else:
                await retry_store.mark_failed(
                    retry_id,
                    error=str(exc),
                )
                logger.info(
                    "Retry %s: attempt %d failed: %s",
                    retry_id,
                    attempts,
                    exc,
                )

        processed += 1

    return processed
