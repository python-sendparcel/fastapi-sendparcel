"""Flow-backed route integration tests."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sendparcel.exceptions import InvalidCallbackError
from sendparcel.provider import BaseProvider
from sendparcel.registry import registry

from fastapi_sendparcel.config import SendparcelConfig
from fastapi_sendparcel.router import create_shipping_router


class DummyProvider(BaseProvider):
    slug = "dummy"
    display_name = "Dummy"

    async def create_shipment(self, **kwargs):
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


def _create_client(repo, resolver, retry_store):
    registry.register(DummyProvider)
    app = FastAPI()
    router = create_shipping_router(
        config=SendparcelConfig(
            default_provider="dummy",
            providers={"dummy": {"status_override": "in_transit"}},
        ),
        repository=repo,
        order_resolver=resolver,
        retry_store=retry_store,
    )
    app.include_router(router)
    return TestClient(app)


def test_create_label_status_and_callback_flow(
    repository, resolver, retry_store
) -> None:
    client = _create_client(repository, resolver, retry_store)

    with client:
        created = client.post("/shipments", json={"order_id": "o-1"})
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


def test_callback_error_enqueues_retry(
    repository, resolver, retry_store
) -> None:
    client = _create_client(repository, resolver, retry_store)

    with client:
        created = client.post("/shipments", json={"order_id": "o-1"})
        shipment_id = created.json()["id"]
        client.post(f"/shipments/{shipment_id}/label")

        callback = client.post(
            f"/callbacks/dummy/{shipment_id}",
            headers={"x-dummy-token": "bad"},
            json={"event": "picked_up"},
        )

        assert callback.status_code == 400
        assert len(retry_store.events) == 1
