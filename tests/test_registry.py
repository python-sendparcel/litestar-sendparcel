"""LitestarPluginRegistry tests."""

from __future__ import annotations

import pytest
from sendparcel.provider import BaseProvider
from sendparcel.registry import PluginRegistry

from litestar_sendparcel.registry import LitestarPluginRegistry


class _FakeProvider(BaseProvider):
    slug = "fake-reg"
    display_name = "Fake Reg"

    async def create_shipment(self, **kwargs):
        return {}


class TestLitestarPluginRegistry:
    def test_inherits_plugin_registry(self) -> None:
        assert issubclass(LitestarPluginRegistry, PluginRegistry)

    def test_register_and_get_by_slug(self) -> None:
        reg = LitestarPluginRegistry()
        reg.register(_FakeProvider)
        assert reg.get_by_slug("fake-reg") is _FakeProvider

    def test_get_by_slug_missing_raises(self) -> None:
        reg = LitestarPluginRegistry()
        reg._discovered = True
        with pytest.raises(KeyError):
            reg.get_by_slug("nonexistent")

    def test_register_provider_router(self) -> None:
        reg = LitestarPluginRegistry()
        sentinel = object()
        reg.register_provider_router("test-slug", sentinel)
        assert reg.get_provider_router("test-slug") is sentinel

    def test_get_provider_router_missing_returns_none(self) -> None:
        reg = LitestarPluginRegistry()
        assert reg.get_provider_router("nonexistent") is None
