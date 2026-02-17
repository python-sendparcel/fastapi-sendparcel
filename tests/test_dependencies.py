"""Dependency injection tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from sendparcel.flow import ShipmentFlow

from fastapi_sendparcel.config import SendparcelConfig
from fastapi_sendparcel.dependencies import (
    get_config,
    get_flow,
    get_repository,
    get_retry_store,
)


def _make_request(**state_attrs):
    """Create a mock request with app.state attributes."""
    request = MagicMock()
    state = SimpleNamespace(**state_attrs)
    request.app.state = state
    return request


class TestDependencies:
    def test_get_config_from_app_state(self) -> None:
        config = SendparcelConfig(default_provider="test")
        request = _make_request(sendparcel_config=config)
        result = get_config(request)
        assert result is config

    def test_get_repository_from_app_state(self) -> None:
        repo = MagicMock()
        request = _make_request(sendparcel_repository=repo)
        result = get_repository(request)
        assert result is repo

    def test_get_retry_store_returns_none_when_not_set(self) -> None:
        request = _make_request()
        result = get_retry_store(request)
        assert result is None

    def test_get_flow_creates_shipment_flow(self) -> None:
        config = SendparcelConfig(
            default_provider="test",
            providers={"test": {"key": "val"}},
        )
        repo = MagicMock()
        request = _make_request(
            sendparcel_config=config,
            sendparcel_repository=repo,
        )
        flow = get_flow(request)
        assert isinstance(flow, ShipmentFlow)
        assert flow.repository is repo
