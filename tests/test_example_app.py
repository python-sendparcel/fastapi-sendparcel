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
        assert "Orders" in resp.text
        assert 'name="description"' in resp.text


def test_create_order_and_view_detail(example_app) -> None:
    """Create an order via form POST and view its detail page."""
    with TestClient(example_app.app) as client:
        resp = client.post(
            "/orders",
            data={
                "description": "Test package",
                "total_weight": "2.5",
                "sender_name": "John Smith",
                "sender_email": "jan@example.com",
                "sender_phone": "+48111222333",
                "sender_line1": "1 Test St",
                "sender_city": "Warsaw",
                "sender_postal_code": "00-001",
                "recipient_name": "Jane Doe",
                "recipient_email": "anna@example.com",
                "recipient_phone": "+48444555666",
                "recipient_line1": "5 Destination St",
                "recipient_city": "Krakow",
                "recipient_postal_code": "30-001",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "Test package" in resp.text
        assert "John Smith" in resp.text
        assert "Jane Doe" in resp.text
        assert "Create shipment" in resp.text


def test_full_shipment_flow(example_app) -> None:
    """Create order, ship it, verify shipment page loads."""
    with TestClient(example_app.app) as client:
        # Create order
        resp = client.post(
            "/orders",
            data={
                "description": "Test package",
                "total_weight": "1.0",
                "sender_name": "Sender",
                "sender_email": "sender@example.com",
                "recipient_name": "Recipient",
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
        assert "Shipment created" in ship_resp.text
        assert "delivery-sim" in ship_resp.text

        # Extract shipment ID and view shipment detail
        match = re.search(r'href="/shipments/([^"]+)"', ship_resp.text)
        assert match is not None
        shipment_id = match.group(1)

        detail_resp = client.get(f"/shipments/{shipment_id}")
        assert detail_resp.status_code == 200
        assert "Shipment" in detail_resp.text
        assert "delivery-sim" in detail_resp.text


def _create_order_and_ship(client: TestClient) -> str:
    """Create an order, ship it, and return the ext_id from sim state.

    Helper used by multiple E2E tests.
    """
    from delivery_sim import _sim_shipments

    resp = client.post(
        "/orders",
        data={
            "description": "Label test package",
            "total_weight": "2.0",
            "sender_name": "Test Sender",
            "sender_email": "sender@example.com",
            "recipient_name": "Test Recipient",
            "recipient_email": "recipient@example.com",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    ship_resp = client.post(
        "/orders/1/ship",
        data={"provider": "delivery-sim"},
    )
    assert ship_resp.status_code == 200
    assert "Shipment created" in ship_resp.text

    # Get the ext_id from the in-memory simulator state
    assert len(_sim_shipments) == 1
    ext_id = next(iter(_sim_shipments))
    return ext_id


def test_full_flow_with_label_pdf_download(example_app) -> None:
    """Full E2E: create order, ship, download label PDF, verify content."""
    with TestClient(example_app.app) as client:
        ext_id = _create_order_and_ship(client)

        # Download the label PDF
        label_resp = client.get(f"/delivery-sim/label/{ext_id}")
        assert label_resp.status_code == 200
        assert label_resp.headers["content-type"] == "application/pdf"

        pdf_bytes = label_resp.content
        assert pdf_bytes.startswith(b"%PDF-1.4")
        assert b"%%EOF" in pdf_bytes


def test_label_pdf_has_correct_content_type(example_app) -> None:
    """Label download returns correct Content-Type and Content-Disposition."""
    with TestClient(example_app.app) as client:
        ext_id = _create_order_and_ship(client)

        label_resp = client.get(f"/delivery-sim/label/{ext_id}")
        assert label_resp.status_code == 200
        assert label_resp.headers["content-type"] == "application/pdf"

        content_disposition = label_resp.headers["content-disposition"]
        assert "filename=" in content_disposition
        assert ext_id in content_disposition


def test_shipment_detail_shows_tracking_info(example_app) -> None:
    """Shipment detail page shows tracking number, provider, and status."""
    from delivery_sim import _sim_shipments

    with TestClient(example_app.app) as client:
        ext_id = _create_order_and_ship(client)

        entry = _sim_shipments[ext_id]
        tracking_number = entry["tracking_number"]

        # Extract shipment ID from the ship response page
        ship_resp = client.get("/")  # navigate away first
        # Re-ship won't work; find shipment via sim state
        shipment_id = entry["shipment_id"]

        detail_resp = client.get(f"/shipments/{shipment_id}")
        assert detail_resp.status_code == 200

        # Verify tracking number (SIM-...)
        assert tracking_number in detail_resp.text
        assert tracking_number.startswith("SIM-")

        # Verify provider name
        assert "delivery-sim" in detail_resp.text

        # Verify status is displayed
        assert "label_ready" in detail_resp.text
