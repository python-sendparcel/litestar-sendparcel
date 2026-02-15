"""Plugin tests."""

from litestar import Router

from litestar_sendparcel.config import SendparcelConfig
from litestar_sendparcel.plugin import create_shipping_router


class _Repo:
    async def get_by_id(self, shipment_id: str):
        raise NotImplementedError

    async def create(self, **kwargs):
        raise NotImplementedError

    async def save(self, shipment):
        raise NotImplementedError

    async def update_status(self, shipment_id: str, status: str, **fields):
        raise NotImplementedError


def test_create_shipping_router_returns_router() -> None:
    router = create_shipping_router(
        config=SendparcelConfig(default_provider="dummy"),
        repository=_Repo(),
    )

    assert isinstance(router, Router)
