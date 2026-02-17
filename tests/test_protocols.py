"""Tests for protocol definitions."""

from litestar_sendparcel.protocols import CallbackRetryStore


def test_callback_retry_store_has_all_methods():
    """CallbackRetryStore protocol defines the full lifecycle."""
    method_names = [
        "store_failed_callback",
        "get_due_retries",
        "mark_succeeded",
        "mark_failed",
        "mark_exhausted",
    ]
    for method_name in method_names:
        assert hasattr(CallbackRetryStore, method_name), (
            f"CallbackRetryStore missing method: {method_name}"
        )


def test_callback_retry_store_is_runtime_checkable():
    """CallbackRetryStore can be used with isinstance()."""

    class GoodStore:
        async def store_failed_callback(
            self,
            shipment_id: str,
            provider_slug: str,
            payload: dict,
            headers: dict,
        ) -> str:
            return "id"

        async def get_due_retries(self, limit: int = 10) -> list[dict]:
            return []

        async def mark_succeeded(self, retry_id: str) -> None:
            pass

        async def mark_failed(self, retry_id: str, error: str) -> None:
            pass

        async def mark_exhausted(self, retry_id: str) -> None:
            pass

    assert isinstance(GoodStore(), CallbackRetryStore)
