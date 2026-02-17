"""Callback route tests — edge cases not covered by test_routes_flow.py."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sendparcel.exceptions import CommunicationError, InvalidCallbackError
from sendparcel.provider import BaseProvider
from sendparcel.registry import registry

from fastapi_sendparcel.config import SendparcelConfig
from fastapi_sendparcel.exceptions import register_exception_handlers
from fastapi_sendparcel.router import create_shipping_router

# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


class CallbackTestProvider(BaseProvider):
    """Provider that verifies callbacks via x-test-token header."""

    slug = "cbtest"
    display_name = "Callback Test"

    async def create_shipment(
        self, *, sender_address, receiver_address, parcels, **kwargs
    ):
        return {"external_id": "ext-cb", "tracking_number": "TRK-CB"}

    async def create_label(self, **kwargs):
        return {"format": "PDF", "url": "https://labels/cb.pdf"}

    async def verify_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        if headers.get("x-test-token") != "valid":
            raise InvalidCallbackError("bad token")

    async def handle_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        if self.shipment.may_trigger("mark_in_transit"):
            self.shipment.mark_in_transit()

    async def fetch_shipment_status(self, **kwargs):
        return {"status": "in_transit"}

    async def cancel_shipment(self, **kwargs):
        return True


class CommErrorCallbackProvider(BaseProvider):
    """Provider whose handle_callback always raises CommunicationError."""

    slug = "cberr"
    display_name = "CB CommErr"

    async def create_shipment(
        self, *, sender_address, receiver_address, parcels, **kwargs
    ):
        return {"external_id": "ext-cberr", "tracking_number": "TRK-CBERR"}

    async def create_label(self, **kwargs):
        return {"format": "PDF", "url": "https://labels/cberr.pdf"}

    async def verify_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        pass  # accept all

    async def handle_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        raise CommunicationError("provider down")

    async def fetch_shipment_status(self, **kwargs):
        return {"status": "in_transit"}

    async def cancel_shipment(self, **kwargs):
        return True


# ---------------------------------------------------------------------------
# Client helpers
# ---------------------------------------------------------------------------


def _create_client(
    repo, resolver, retry_store=None, *, provider_cls=CallbackTestProvider
):
    registry.register(provider_cls)
    app = FastAPI()
    register_exception_handlers(app)
    router = create_shipping_router(
        config=SendparcelConfig(
            default_provider=provider_cls.slug,
            providers={provider_cls.slug: {}},
        ),
        repository=repo,
        order_resolver=resolver,
        retry_store=retry_store,
    )
    app.include_router(router)
    return TestClient(app)


def _prepare_shipment(client):
    """Create a shipment and generate a label so callback transitions work."""
    created = client.post("/shipments", json={"order_id": "o-1"})
    sid = created.json()["id"]
    client.post(f"/shipments/{sid}/label")
    return sid


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_provider_slug_mismatch(repository, resolver) -> None:
    """Wrong provider slug returns 400 with 'mismatch'."""
    client = _create_client(repository, resolver)

    with client:
        sid = _prepare_shipment(client)

        resp = client.post(
            f"/callbacks/wrong_provider/{sid}",
            headers={"x-test-token": "valid"},
            json={"event": "test"},
        )

        assert resp.status_code == 400
        body = resp.json()
        assert "mismatch" in body["detail"].lower()


def test_callback_no_retry_store(repository, resolver) -> None:
    """InvalidCallbackError with no retry_store returns 400."""
    client = _create_client(repository, resolver, retry_store=None)

    with client:
        sid = _prepare_shipment(client)

        resp = client.post(
            f"/callbacks/cbtest/{sid}",
            headers={"x-test-token": "bad"},
            json={"event": "test"},
        )

        assert resp.status_code == 400
        assert "bad token" in resp.json()["detail"].lower()


def test_callback_invalid_json_body(repository, resolver) -> None:
    """Non-JSON body falls back to empty dict; succeeds with valid token."""
    client = _create_client(repository, resolver)

    with client:
        sid = _prepare_shipment(client)

        resp = client.post(
            f"/callbacks/cbtest/{sid}",
            headers={
                "x-test-token": "valid",
                "content-type": "application/json",
            },
            content=b"not-json",
        )

        assert resp.status_code == 200


def test_callback_shipment_not_found(repository, resolver) -> None:
    """POST callback for nonexistent shipment ID raises KeyError (unhandled)."""
    client = _create_client(repository, resolver)

    with client, pytest.raises(KeyError):
        client.post(
            "/callbacks/cbtest/nonexistent-id",
            headers={"x-test-token": "valid"},
            json={"event": "test"},
        )


def test_callback_happy_path_returns_correct_format(
    repository, resolver
) -> None:
    """Verify response body has provider, status, shipment_status keys."""
    client = _create_client(repository, resolver)

    with client:
        sid = _prepare_shipment(client)

        resp = client.post(
            f"/callbacks/cbtest/{sid}",
            headers={"x-test-token": "valid"},
            json={"event": "picked_up"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["provider"] == "cbtest"
        assert body["status"] == "accepted"
        assert "shipment_status" in body


def test_callback_communication_error_status_code(
    repository, resolver, retry_store
) -> None:
    """CommunicationError from handle_callback returns 502."""
    client = _create_client(
        repository,
        resolver,
        retry_store=retry_store,
        provider_cls=CommErrorCallbackProvider,
    )

    with client:
        sid = _prepare_shipment(client)

        resp = client.post(
            f"/callbacks/cberr/{sid}",
            headers={},
            json={"event": "test"},
        )

        assert resp.status_code == 502
        assert "communication_error" in resp.json().get("code", "")
