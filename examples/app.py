"""FastAPI example app using the built-in sendparcel dummy provider."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from fastapi import FastAPI

from fastapi_sendparcel.config import SendparcelConfig
from fastapi_sendparcel.router import create_shipping_router
from sendparcel.providers.dummy import DummyProvider
from sendparcel.registry import registry

DEFAULT_PROVIDER = DummyProvider.slug


@dataclass
class DemoOrder:
    id: str

    def get_total_weight(self) -> Decimal:
        return Decimal("1.0")

    def get_parcels(self) -> list[dict]:
        return [{"weight_kg": Decimal("1.0")}]

    def get_sender_address(self) -> dict:
        return {"country_code": "PL"}

    def get_receiver_address(self) -> dict:
        return {"country_code": "DE"}


@dataclass
class DemoShipment:
    id: str
    order: DemoOrder
    status: str
    provider: str
    external_id: str = ""
    tracking_number: str = ""
    label_url: str = ""


class InMemoryRepo:
    def __init__(self) -> None:
        self.items: dict[str, DemoShipment] = {}
        self._counter = 0

    async def get_by_id(self, shipment_id: str) -> DemoShipment:
        return self.items[shipment_id]

    async def create(self, **kwargs) -> DemoShipment:
        self._counter += 1
        shipment_id = f"s-{self._counter}"
        shipment = DemoShipment(
            id=shipment_id,
            order=kwargs["order"],
            provider=kwargs["provider"],
            status=str(kwargs["status"]),
        )
        self.items[shipment_id] = shipment
        return shipment

    async def save(self, shipment: DemoShipment) -> DemoShipment:
        self.items[shipment.id] = shipment
        return shipment

    async def update_status(
        self, shipment_id: str, status: str, **fields
    ) -> DemoShipment:
        shipment = self.items[shipment_id]
        shipment.status = status
        for key, value in fields.items():
            setattr(shipment, key, value)
        return shipment


class OrderResolver:
    async def resolve(self, order_id: str) -> DemoOrder:
        return DemoOrder(id=order_id)


registry.register(DummyProvider)

app = FastAPI(title="fastapi-sendparcel example")
app.include_router(
    create_shipping_router(
        config=SendparcelConfig(
            default_provider=DEFAULT_PROVIDER,
            providers={DEFAULT_PROVIDER: {"callback_token": "dummy-token"}},
        ),
        repository=InMemoryRepo(),
        order_resolver=OrderResolver(),
    )
)
