"""Flow-backed route integration tests."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sendparcel.exceptions import CommunicationError, InvalidCallbackError
from sendparcel.provider import (
    BaseProvider,
    CancellableProvider,
    LabelProvider,
    PullStatusProvider,
    PushCallbackProvider,
)
from sendparcel.registry import registry

from fastapi_sendparcel.config import SendparcelConfig
from fastapi_sendparcel.exceptions import register_exception_handlers
from fastapi_sendparcel.router import create_shipping_router

_DIRECT_PAYLOAD = {
    "sender_address": {"country_code": "PL"},
    "receiver_address": {"country_code": "DE"},
    "parcels": [{"weight_kg": "1.0"}],
}


class DummyProvider(
    BaseProvider,
    LabelProvider,
    PushCallbackProvider,
    PullStatusProvider,
    CancellableProvider,
):
    slug = "dummy"
    display_name = "Dummy"

    async def create_shipment(
        self, *, sender_address, receiver_address, parcels, **kwargs
    ):
        return {"external_id": "ext-1", "tracking_number": "trk-1"}

    async def create_label(self, **kwargs):
        return {"format": "PDF", "url": "https://labels/s-1.pdf"}

    async def verify_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        if headers.get("x-dummy-token") != "ok":
            raise InvalidCallbackError("BAD TOKEN")

    async def handle_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        if self.shipment.may_trigger("mark_in_transit"):
            self.shipment.mark_in_transit()

    async def fetch_shipment_status(self, **kwargs):
        return {"status": self.get_setting("status_override", "in_transit")}

    async def cancel_shipment(self, **kwargs):
        return True


def _create_client(repo, retry_store):
    registry.register(DummyProvider)
    app = FastAPI()
    register_exception_handlers(app)
    router = create_shipping_router(
        config=SendparcelConfig(
            default_provider="dummy",
            providers={"dummy": {"status_override": "in_transit"}},
        ),
        repository=repo,
        retry_store=retry_store,
    )
    app.include_router(router)
    return TestClient(app)


def test_create_label_status_and_callback_flow(repository, retry_store) -> None:
    client = _create_client(repository, retry_store)

    with client:
        created = client.post("/shipments", json=_DIRECT_PAYLOAD)
        assert created.status_code == 200
        shipment_id = created.json()["id"]
        assert created.json()["status"] == "created"

        label = client.post(f"/shipments/{shipment_id}/label")
        assert label.status_code == 200
        assert label.json()["status"] == "label_ready"

        status = client.get(f"/shipments/{shipment_id}/status")
        assert status.status_code == 200
        assert status.json()["status"] == "in_transit"

        callback = client.post(
            f"/callbacks/dummy/{shipment_id}",
            headers={"x-dummy-token": "ok"},
            json={"event": "picked_up"},
        )
        assert callback.status_code == 200


def test_invalid_callback_does_not_enqueue_retry(
    repository, retry_store
) -> None:
    """InvalidCallbackError should NOT trigger retry."""
    client = _create_client(repository, retry_store)

    with client:
        created = client.post("/shipments", json=_DIRECT_PAYLOAD)
        shipment_id = created.json()["id"]
        client.post(f"/shipments/{shipment_id}/label")

        callback = client.post(
            f"/callbacks/dummy/{shipment_id}",
            headers={"x-dummy-token": "bad"},
            json={"event": "picked_up"},
        )

        assert callback.status_code == 400
        assert len(retry_store.events) == 0


class CommErrorProvider(
    BaseProvider,
    LabelProvider,
    PushCallbackProvider,
    PullStatusProvider,
    CancellableProvider,
):
    slug = "commerr"
    display_name = "CommErr"

    async def create_shipment(
        self, *, sender_address, receiver_address, parcels, **kwargs
    ):
        return {"external_id": "ext-1", "tracking_number": "trk-1"}

    async def create_label(self, **kwargs):
        return {"format": "PDF", "url": "https://labels/s.pdf"}

    async def verify_callback(self, data, headers, **kwargs):
        pass

    async def handle_callback(self, data, headers, **kwargs):
        raise CommunicationError("provider unreachable")

    async def fetch_shipment_status(self, **kwargs):
        return {"status": "in_transit"}

    async def cancel_shipment(self, **kwargs):
        return True


def _create_commerr_client(repo, retry_store):
    registry.register(CommErrorProvider)
    app = FastAPI()
    register_exception_handlers(app)
    router = create_shipping_router(
        config=SendparcelConfig(
            default_provider="commerr",
            providers={"commerr": {}},
        ),
        repository=repo,
        retry_store=retry_store,
    )
    app.include_router(router)
    return TestClient(app)


def test_communication_error_enqueues_retry_and_returns_502(
    repository, retry_store
) -> None:
    """CommunicationError (transient) should enqueue retry and return 502."""
    client = _create_commerr_client(repository, retry_store)

    with client:
        created = client.post("/shipments", json=_DIRECT_PAYLOAD)
        shipment_id = created.json()["id"]
        client.post(f"/shipments/{shipment_id}/label")

        callback = client.post(
            f"/callbacks/commerr/{shipment_id}",
            headers={},
            json={"event": "picked_up"},
        )

        assert callback.status_code == 502
        assert len(retry_store.events) == 1
        assert retry_store.events[0]["shipment_id"] == shipment_id
