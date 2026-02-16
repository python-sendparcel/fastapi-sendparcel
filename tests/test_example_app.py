"""Tests for the new example app."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sendparcel.registry import registry as global_registry
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_example_mod: ModuleType | None = None


def _load_example_modules() -> ModuleType:
    """Load example app modules once, caching the result."""
    global _example_mod  # noqa: PLW0603
    if _example_mod is not None:
        return _example_mod

    example_dir = Path(__file__).resolve().parents[1] / "example"

    sys_path_entry = str(example_dir)
    if sys_path_entry not in sys.path:
        sys.path.insert(0, sys_path_entry)

    with patch.dict("os.environ", {}, clear=False):
        models_spec = importlib.util.spec_from_file_location(
            "models", example_dir / "models.py"
        )
        assert models_spec is not None and models_spec.loader is not None
        models_mod = importlib.util.module_from_spec(models_spec)
        sys.modules["models"] = models_mod
        models_spec.loader.exec_module(models_mod)

        delivery_spec = importlib.util.spec_from_file_location(
            "delivery_sim", example_dir / "delivery_sim.py"
        )
        assert delivery_spec is not None and delivery_spec.loader is not None
        delivery_mod = importlib.util.module_from_spec(delivery_spec)
        sys.modules["delivery_sim"] = delivery_mod
        delivery_spec.loader.exec_module(delivery_mod)

        app_spec = importlib.util.spec_from_file_location(
            "example_app", example_dir / "app.py"
        )
        assert app_spec is not None and app_spec.loader is not None
        app_mod = importlib.util.module_from_spec(app_spec)
        sys.modules["example_app"] = app_mod
        app_spec.loader.exec_module(app_mod)

    _example_mod = app_mod
    return app_mod


@pytest.fixture()
def example_app():
    """Provide the example app with a fresh in-memory database per test."""
    app_mod = _load_example_modules()

    # Create fresh in-memory engine for test isolation
    test_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    test_session = async_sessionmaker(test_engine, class_=AsyncSession)

    # Override database components
    original_engine = app_mod.engine
    original_session = app_mod.async_session
    original_repo_sf = app_mod.repository.session_factory
    original_retry_sf = app_mod.retry_store._session_factory
    original_resolver_sf = app_mod.order_resolver._session_factory

    app_mod.engine = test_engine
    app_mod.async_session = test_session
    app_mod.repository.session_factory = test_session
    app_mod.retry_store._session_factory = test_session
    app_mod.order_resolver._session_factory = test_session

    # Clear the in-memory delivery simulator state between tests
    from delivery_sim import DeliverySimProvider, _sim_shipments

    _sim_shipments.clear()

    # Register provider in the global registry so ShipmentFlow can find it
    global_registry.register(DeliverySimProvider)

    yield app_mod

    # Restore originals
    app_mod.engine = original_engine
    app_mod.async_session = original_session
    app_mod.repository.session_factory = original_repo_sf
    app_mod.retry_store._session_factory = original_retry_sf
    app_mod.order_resolver._session_factory = original_resolver_sf


def test_home_page_loads(example_app) -> None:
    """Home page renders with Tabler CSS and order form."""
    with TestClient(example_app.app) as client:
        resp = client.get("/")
        assert resp.status_code == 200
        assert "tabler" in resp.text.lower()
        assert "Zamówienia" in resp.text
        assert 'name="description"' in resp.text


def test_create_order_and_view_detail(example_app) -> None:
    """Create an order via form POST and view its detail page."""
    with TestClient(example_app.app) as client:
        resp = client.post(
            "/orders",
            data={
                "description": "Testowa paczka",
                "total_weight": "2.5",
                "sender_name": "Jan Kowalski",
                "sender_email": "jan@example.com",
                "sender_phone": "+48111222333",
                "sender_line1": "ul. Testowa 1",
                "sender_city": "Warszawa",
                "sender_postal_code": "00-001",
                "recipient_name": "Anna Nowak",
                "recipient_email": "anna@example.com",
                "recipient_phone": "+48444555666",
                "recipient_line1": "ul. Docelowa 5",
                "recipient_city": "Kraków",
                "recipient_postal_code": "30-001",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "Testowa paczka" in resp.text
        assert "Jan Kowalski" in resp.text
        assert "Anna Nowak" in resp.text
        assert "Nadaj przesyłkę" in resp.text


def test_full_shipment_flow(example_app) -> None:
    """Create order, ship it, verify shipment page loads."""
    with TestClient(example_app.app) as client:
        # Create order
        resp = client.post(
            "/orders",
            data={
                "description": "Paczka testowa",
                "total_weight": "1.0",
                "sender_name": "Nadawca",
                "sender_email": "sender@example.com",
                "recipient_name": "Odbiorca",
                "recipient_email": "recipient@example.com",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200

        # Ship the order
        ship_resp = client.post(
            "/orders/1/ship",
            data={"provider": "delivery-sim"},
        )
        assert ship_resp.status_code == 200
        assert "Przesyłka utworzona" in ship_resp.text
        assert "delivery-sim" in ship_resp.text

        # Extract shipment ID and view shipment detail
        match = re.search(r'href="/shipments/([^"]+)"', ship_resp.text)
        assert match is not None
        shipment_id = match.group(1)

        detail_resp = client.get(f"/shipments/{shipment_id}")
        assert detail_resp.status_code == 200
        assert "Przesyłka" in detail_resp.text
        assert "delivery-sim" in detail_resp.text
