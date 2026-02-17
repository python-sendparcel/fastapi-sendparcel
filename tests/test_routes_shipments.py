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


def _create_client(repo, resolver, *, retry_store=None):
    registry.register(ShipmentTestProvider)
    app = FastAPI()
    register_exception_handlers(app)
    router_ = create_shipping_router(
        config=SendparcelConfig(
            default_provider="shiptest",
            providers={"shiptest": {}},
        ),
        repository=repo,
        order_resolver=resolver,
        retry_store=retry_store,
    )
    app.include_router(router_)
    return TestClient(app)


def _create_client_no_resolver(repo):
    """Client without an order resolver (order_resolver=None)."""
    registry.register(ShipmentTestProvider)
    app = FastAPI()
    register_exception_handlers(app)
    router_ = create_shipping_router(
        config=SendparcelConfig(
            default_provider="shiptest",
            providers={"shiptest": {}},
        ),
        repository=repo,
        order_resolver=None,
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


def test_create_shipment(repository, resolver) -> None:
    """POST /shipments returns 200 with correct fields."""
    client = _create_client(repository, resolver)

    with client:
        resp = client.post("/shipments", json={"order_id": "o-1"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "created"
        assert body["provider"] == "shiptest"
        assert body["external_id"] == "ext-1"
        assert body["tracking_number"] == "SHIP-001"


def test_create_shipment_no_resolver(repository) -> None:
    """No resolver configured + order_id returns 500 with 'resolver'."""
    client = _create_client_no_resolver(repository)

    with client:
        resp = client.post("/shipments", json={"order_id": "o-1"})

        assert resp.status_code == 500
        assert "resolver" in resp.json()["detail"].lower()


def test_create_shipment_direct(repository, resolver) -> None:
    """POST /shipments with explicit address/parcel data (no order)."""
    client = _create_client(repository, resolver)

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


def test_create_shipment_direct_no_resolver(repository) -> None:
    """Direct flow works even without an order resolver."""
    client = _create_client_no_resolver(repository)

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


def test_create_shipment_missing_fields(repository, resolver) -> None:
    """POST /shipments with neither order_id nor full address data returns 400."""
    client = _create_client(repository, resolver)

    with client:
        resp = client.post("/shipments", json={})

        assert resp.status_code == 400
        assert "order_id" in resp.json()["detail"]


def test_create_shipment_partial_address_returns_400(
    repository, resolver
) -> None:
    """Partial address data (missing parcels) returns 400."""
    client = _create_client(repository, resolver)

    with client:
        resp = client.post(
            "/shipments",
            json={
                "sender_address": {"country_code": "PL"},
                "receiver_address": {"country_code": "DE"},
            },
        )

        assert resp.status_code == 400


def test_create_label(repository, resolver) -> None:
    """POST label returns 200 with status=label_ready."""
    client = _create_client(repository, resolver)

    with client:
        created = client.post("/shipments", json={"order_id": "o-1"})
        sid = created.json()["id"]

        resp = client.post(f"/shipments/{sid}/label")

        assert resp.status_code == 200
        assert resp.json()["status"] == "label_ready"


def test_fetch_status(repository, resolver) -> None:
    """GET status after label returns in_transit."""
    client = _create_client(repository, resolver)

    with client:
        created = client.post("/shipments", json={"order_id": "o-1"})
        sid = created.json()["id"]
        client.post(f"/shipments/{sid}/label")

        resp = client.get(f"/shipments/{sid}/status")

        assert resp.status_code == 200
        assert resp.json()["status"] == "in_transit"


def test_health_endpoint(repository, resolver) -> None:
    """GET /shipments/health returns {"status": "ok"}."""
    client = _create_client(repository, resolver)

    with client:
        resp = client.get("/shipments/health")

        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


def test_default_provider_used(repository, resolver) -> None:
    """POST /shipments without provider field uses config.default_provider."""
    client = _create_client(repository, resolver)

    with client:
        resp = client.post("/shipments", json={"order_id": "o-1"})

        assert resp.status_code == 200
        assert resp.json()["provider"] == "shiptest"
