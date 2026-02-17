"""Shipment route tests."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sendparcel.provider import BaseProvider
from sendparcel.registry import registry

from fastapi_sendparcel.config import SendparcelConfig
from fastapi_sendparcel.exceptions import register_exception_handlers
from fastapi_sendparcel.router import create_shipping_router
from fastapi_sendparcel.routes.shipments import router

# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class ShipmentTestProvider(BaseProvider):
    """Deterministic provider for shipment route tests."""

    slug = "shiptest"
    display_name = "Shipment Test"

    async def create_shipment(
        self, *, sender_address, receiver_address, parcels, **kwargs
    ):
        return {"external_id": "ext-1", "tracking_number": "SHIP-001"}

    async def create_label(self, **kwargs):
        return {"format": "PDF", "url": "https://labels/ship.pdf"}

    async def fetch_shipment_status(self, **kwargs):
        return {"status": "in_transit"}

    async def cancel_shipment(self, **kwargs):
        return True


# ---------------------------------------------------------------------------
# Client helpers
# ---------------------------------------------------------------------------


def _create_client(repo, *, retry_store=None):
    registry.register(ShipmentTestProvider)
    app = FastAPI()
    register_exception_handlers(app)
    router_ = create_shipping_router(
        config=SendparcelConfig(
            default_provider="shiptest",
            providers={"shiptest": {}},
        ),
        repository=repo,
        retry_store=retry_store,
    )
    app.include_router(router_)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_shipments_health_route_exists() -> None:
    """Original test — route is registered in the sub-router."""
    paths = {route.path for route in router.routes}
    assert "/shipments/health" in paths


def test_create_shipment_direct(repository) -> None:
    """POST /shipments with explicit address/parcel data."""
    client = _create_client(repository)

    with client:
        resp = client.post(
            "/shipments",
            json={
                "sender_address": {"country_code": "PL"},
                "receiver_address": {"country_code": "DE"},
                "parcels": [{"weight_kg": "1.0"}],
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "created"
        assert body["provider"] == "shiptest"
        assert body["external_id"] == "ext-1"
        assert body["tracking_number"] == "SHIP-001"


def test_create_shipment_missing_fields(repository) -> None:
    """POST /shipments with neither full address data returns 400."""
    client = _create_client(repository)

    with client:
        resp = client.post("/shipments", json={})

        assert resp.status_code == 400
        assert "sender_address" in resp.json()["detail"]


def test_create_shipment_partial_address_returns_400(repository) -> None:
    """Partial address data (missing parcels) returns 400."""
    client = _create_client(repository)

    with client:
        resp = client.post(
            "/shipments",
            json={
                "sender_address": {"country_code": "PL"},
                "receiver_address": {"country_code": "DE"},
            },
        )

        assert resp.status_code == 400


def test_create_label(repository) -> None:
    """POST label returns 200 with status=label_ready."""
    client = _create_client(repository)

    with client:
        created = client.post(
            "/shipments",
            json={
                "sender_address": {"country_code": "PL"},
                "receiver_address": {"country_code": "DE"},
                "parcels": [{"weight_kg": "1.0"}],
            },
        )
        sid = created.json()["id"]

        resp = client.post(f"/shipments/{sid}/label")

        assert resp.status_code == 200
        assert resp.json()["status"] == "label_ready"


def test_fetch_status(repository) -> None:
    """GET status after label returns in_transit."""
    client = _create_client(repository)

    with client:
        created = client.post(
            "/shipments",
            json={
                "sender_address": {"country_code": "PL"},
                "receiver_address": {"country_code": "DE"},
                "parcels": [{"weight_kg": "1.0"}],
            },
        )
        sid = created.json()["id"]
        client.post(f"/shipments/{sid}/label")

        resp = client.get(f"/shipments/{sid}/status")

        assert resp.status_code == 200
        assert resp.json()["status"] == "in_transit"


def test_health_endpoint(repository) -> None:
    """GET /shipments/health returns {"status": "ok"}."""
    client = _create_client(repository)

    with client:
        resp = client.get("/shipments/health")

        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


def test_default_provider_used(repository) -> None:
    """POST /shipments without provider field uses config.default_provider."""
    client = _create_client(repository)

    with client:
        resp = client.post(
            "/shipments",
            json={
                "sender_address": {"country_code": "PL"},
                "receiver_address": {"country_code": "DE"},
                "parcels": [{"weight_kg": "1.0"}],
            },
        )

        assert resp.status_code == 200
        assert resp.json()["provider"] == "shiptest"
