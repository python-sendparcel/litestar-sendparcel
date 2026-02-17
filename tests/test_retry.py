# tests/test_retry.py
"""Tests for the webhook retry mechanism."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from litestar_sendparcel.config import SendparcelConfig
from litestar_sendparcel.retry import compute_next_retry_at, process_due_retries


@pytest.fixture
def mock_retry_store():
    store = AsyncMock()
    store.get_due_retries = AsyncMock(return_value=[])
    store.mark_succeeded = AsyncMock()
    store.mark_failed = AsyncMock()
    store.mark_exhausted = AsyncMock()
    return store


@pytest.fixture
def mock_repo():
    return AsyncMock()


@pytest.fixture
def config():
    return SendparcelConfig(
        default_provider="dummy",
        providers={"dummy": {}},
        retry_max_attempts=3,
        retry_backoff_seconds=10,
    )


def test_compute_backoff():
    """Backoff increases exponentially."""
    base = 10
    t1 = compute_next_retry_at(attempt=1, backoff_seconds=base)
    t2 = compute_next_retry_at(attempt=2, backoff_seconds=base)
    t3 = compute_next_retry_at(attempt=3, backoff_seconds=base)

    now = datetime.now(tz=UTC)
    assert t1 > now
    assert t2 > t1
    assert t3 > t2


def test_compute_backoff_first_attempt():
    """First attempt backoff is base_seconds."""
    now = datetime.now(tz=UTC)
    result = compute_next_retry_at(attempt=1, backoff_seconds=60)
    expected_min = now + timedelta(seconds=55)
    expected_max = now + timedelta(seconds=65)
    assert expected_min < result < expected_max


async def test_process_retries_empty(mock_retry_store, mock_repo, config):
    """No retries to process — does nothing."""
    processed = await process_due_retries(
        retry_store=mock_retry_store,
        repository=mock_repo,
        config=config,
    )
    assert processed == 0


async def test_process_retries_success(mock_retry_store, mock_repo, config):
    """Successful retry marks as succeeded."""
    shipment = AsyncMock()
    shipment.id = "s-1"
    shipment.provider = "dummy"
    mock_repo.get_by_id = AsyncMock(return_value=shipment)

    mock_retry_store.get_due_retries = AsyncMock(
        return_value=[
            {
                "id": "retry-1",
                "shipment_id": "s-1",
                "provider_slug": "dummy",
                "payload": {"event": "picked_up"},
                "headers": {},
                "attempts": 1,
            }
        ]
    )

    with patch("litestar_sendparcel.retry.ShipmentFlow") as mock_flow_cls:
        instance = AsyncMock()
        mock_flow_cls.return_value = instance
        instance.handle_callback = AsyncMock()

        processed = await process_due_retries(
            retry_store=mock_retry_store,
            repository=mock_repo,
            config=config,
        )

    assert processed == 1
    mock_retry_store.mark_succeeded.assert_called_once_with("retry-1")


async def test_process_retries_failure_under_max(
    mock_retry_store, mock_repo, config
):
    """Failed retry under max_attempts marks as failed."""
    shipment = AsyncMock()
    shipment.id = "s-1"
    shipment.provider = "dummy"
    mock_repo.get_by_id = AsyncMock(return_value=shipment)

    mock_retry_store.get_due_retries = AsyncMock(
        return_value=[
            {
                "id": "retry-1",
                "shipment_id": "s-1",
                "provider_slug": "dummy",
                "payload": {"event": "picked_up"},
                "headers": {},
                "attempts": 1,
            }
        ]
    )

    with patch("litestar_sendparcel.retry.ShipmentFlow") as mock_flow_cls:
        instance = AsyncMock()
        mock_flow_cls.return_value = instance
        instance.handle_callback = AsyncMock(
            side_effect=Exception("still failing")
        )

        processed = await process_due_retries(
            retry_store=mock_retry_store,
            repository=mock_repo,
            config=config,
        )

    assert processed == 1
    mock_retry_store.mark_failed.assert_called_once()


async def test_process_retries_exhausted(mock_retry_store, mock_repo, config):
    """Failed retry at max_attempts marks as exhausted."""
    shipment = AsyncMock()
    shipment.id = "s-1"
    shipment.provider = "dummy"
    mock_repo.get_by_id = AsyncMock(return_value=shipment)

    mock_retry_store.get_due_retries = AsyncMock(
        return_value=[
            {
                "id": "retry-1",
                "shipment_id": "s-1",
                "provider_slug": "dummy",
                "payload": {"event": "picked_up"},
                "headers": {},
                "attempts": 3,
            }
        ]
    )

    with patch("litestar_sendparcel.retry.ShipmentFlow") as mock_flow_cls:
        instance = AsyncMock()
        mock_flow_cls.return_value = instance
        instance.handle_callback = AsyncMock(
            side_effect=Exception("still failing")
        )

        processed = await process_due_retries(
            retry_store=mock_retry_store,
            repository=mock_repo,
            config=config,
        )

    assert processed == 1
    mock_retry_store.mark_exhausted.assert_called_once_with("retry-1")


async def test_process_retries_shipment_not_found(
    mock_retry_store, mock_repo, config
):
    """Retry for missing shipment is marked exhausted."""
    mock_repo.get_by_id = AsyncMock(side_effect=KeyError("s-1"))

    mock_retry_store.get_due_retries = AsyncMock(
        return_value=[
            {
                "id": "retry-1",
                "shipment_id": "s-1",
                "provider_slug": "dummy",
                "payload": {},
                "headers": {},
                "attempts": 1,
            }
        ]
    )

    processed = await process_due_retries(
        retry_store=mock_retry_store,
        repository=mock_repo,
        config=config,
    )

    assert processed == 1
    mock_retry_store.mark_exhausted.assert_called_once_with("retry-1")
