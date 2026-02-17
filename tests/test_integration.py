"""End-to-end integration tests exercising the full request lifecycle."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sendparcel.exceptions import InvalidCallbackError
from sendparcel.provider import BaseProvider
from sendparcel.registry import registry

from conftest import InMemoryRepo, OrderResolver, RetryStore
from fastapi_sendparcel.config import SendparcelConfig
from fastapi_sendparcel.exceptions import register_exception_handlers
from fastapi_sendparcel.router import create_shipping_router

# ---------------------------------------------------------------------------
# Custom integration provider
# ---------------------------------------------------------------------------


class _IntegrationProvider(BaseProvider):
    """Provider for end-to-end integration tests with full lifecycle control."""

    slug = "intprovider"
    display_name = "Integration Provider"

    async def create_shipment(
        self, *, sender_address, receiver_address, parcels, **kwargs
    ):
        return {
            "external_id": f"int-ext-{self.shipment.id}",
            "tracking_number": f"INT-{self.shipment.id}",
        }

    async def create_label(self, **kwargs):
        return {
            "format": "PDF",
            "url": f"https://labels/{self.shipment.id}.pdf",
        }

    async def verify_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        if headers.get("x-int-token") != "secret":
            raise InvalidCallbackError("invalid token")

    async def handle_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        target_status = data.get("status")
        if target_status == "in_transit" and self.shipment.may_trigger(
            "mark_in_transit"
        ):
            self.shipment.mark_in_transit()
        elif target_status == "delivered" and self.shipment.may_trigger(
            "mark_delivered"
        ):
            self.shipment.mark_delivered()

    async def fetch_shipment_status(self, **kwargs):
        return {"status": self.get_setting("status_override", "in_transit")}

    async def cancel_shipment(self, **kwargs):
        return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROVIDER_CONFIG = {"status_override": "in_transit"}


def _create_app() -> tuple[FastAPI, InMemoryRepo, RetryStore]:
    """Build a fully-wired FastAPI app with in-memory fixtures."""
    repo = InMemoryRepo()
    resolver = OrderResolver()
    retry_store = RetryStore()

    registry.register(_IntegrationProvider)

    app = FastAPI()
    register_exception_handlers(app)
    router = create_shipping_router(
        config=SendparcelConfig(
            default_provider="intprovider",
            providers={"intprovider": _PROVIDER_CONFIG},
        ),
        repository=repo,
        order_resolver=resolver,
        retry_store=retry_store,
    )
    app.include_router(router)
    return app, repo, retry_store


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_create_shipment_through_api(repository, resolver, retry_store) -> None:
    """POST /shipments creates a shipment and returns correct fields."""
    app, _repo, _rs = _create_app()

    with TestClient(app) as client:
        resp = client.post("/shipments", json={"order_id": "order-1"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["provider"] == "intprovider"
        assert body["status"] == "created"
        assert body["external_id"].startswith("int-ext-")
        assert body["tracking_number"].startswith("INT-")


def test_callback_through_api(repository, resolver, retry_store) -> None:
    """Create → Label → Callback transitions shipment to in_transit."""
    app, _repo, _rs = _create_app()

    with TestClient(app) as client:
        # Create shipment
        created = client.post("/shipments", json={"order_id": "order-2"})
        sid = created.json()["id"]

        # Create label (transitions to label_ready)
        label_resp = client.post(f"/shipments/{sid}/label")
        assert label_resp.status_code == 200
        assert label_resp.json()["status"] == "label_ready"

        # Send callback with valid token to transition to in_transit
        cb_resp = client.post(
            f"/callbacks/intprovider/{sid}",
            headers={"x-int-token": "secret"},
            json={"status": "in_transit"},
        )

        assert cb_resp.status_code == 200
        cb_body = cb_resp.json()
        assert cb_body["provider"] == "intprovider"
        assert cb_body["status"] == "accepted"
        assert cb_body["shipment_status"] == "in_transit"


def test_label_and_status_through_api(
    repository, resolver, retry_store
) -> None:
    """Create → Label → fetch_status verifies correct transitions."""
    app, _repo, _rs = _create_app()

    with TestClient(app) as client:
        # Create shipment
        created = client.post("/shipments", json={"order_id": "order-3"})
        assert created.status_code == 200
        sid = created.json()["id"]
        assert created.json()["status"] == "created"

        # Create label
        label_resp = client.post(f"/shipments/{sid}/label")
        assert label_resp.status_code == 200
        assert label_resp.json()["status"] == "label_ready"
        assert "labels" in label_resp.json()["label_url"]

        # Fetch status — provider returns in_transit via status_override
        status_resp = client.get(f"/shipments/{sid}/status")
        assert status_resp.status_code == 200
        assert status_resp.json()["status"] == "in_transit"


def test_full_lifecycle(repository, resolver, retry_store) -> None:
    """Full lifecycle: Create, Label, Status, Callback, Health."""
    app, _repo, _rs = _create_app()

    with TestClient(app) as client:
        # 1. Create shipment
        created = client.post("/shipments", json={"order_id": "order-4"})
        assert created.status_code == 200
        sid = created.json()["id"]
        assert created.json()["status"] == "created"

        # 2. Create label
        label_resp = client.post(f"/shipments/{sid}/label")
        assert label_resp.status_code == 200
        assert label_resp.json()["status"] == "label_ready"

        # 3. Fetch status — transitions to in_transit
        status_resp = client.get(f"/shipments/{sid}/status")
        assert status_resp.status_code == 200
        assert status_resp.json()["status"] == "in_transit"

        # 4. Callback — deliver the shipment
        cb_resp = client.post(
            f"/callbacks/intprovider/{sid}",
            headers={"x-int-token": "secret"},
            json={"status": "delivered"},
        )
        assert cb_resp.status_code == 200
        assert cb_resp.json()["shipment_status"] == "delivered"

        # 5. Health check still works
        health_resp = client.get("/shipments/health")
        assert health_resp.status_code == 200
        assert health_resp.json() == {"status": "ok"}
