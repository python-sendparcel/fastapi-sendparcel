"""FastAPIPluginRegistry tests."""

from __future__ import annotations

import pytest
from sendparcel.provider import BaseProvider

from fastapi_sendparcel.registry import FastAPIPluginRegistry


class _FakeProvider(BaseProvider):
    slug = "fake"
    display_name = "Fake"

    async def create_shipment(self, **kwargs):
        return {"external_id": "ext-1"}


class _FakeRouter:
    """Simulates a provider-specific APIRouter."""

    pass


class TestFastAPIPluginRegistry:
    def test_register_provider(self) -> None:
        reg = FastAPIPluginRegistry()
        reg._discovered = True
        reg.register(_FakeProvider)
        assert reg.get_by_slug("fake") is _FakeProvider

    def test_get_by_slug(self) -> None:
        reg = FastAPIPluginRegistry()
        reg._discovered = True
        reg.register(_FakeProvider)
        result = reg.get_by_slug("fake")
        assert result is _FakeProvider

    def test_get_by_slug_not_found(self) -> None:
        reg = FastAPIPluginRegistry()
        reg._discovered = True
        with pytest.raises(KeyError):
            reg.get_by_slug("nonexistent")

    def test_register_provider_router(self) -> None:
        reg = FastAPIPluginRegistry()
        router = _FakeRouter()
        reg.register_provider_router("fake", router)
        assert reg.get_provider_router("fake") is router

    def test_get_provider_router_returns_none_when_missing(self) -> None:
        reg = FastAPIPluginRegistry()
        assert reg.get_provider_router("nonexistent") is None
