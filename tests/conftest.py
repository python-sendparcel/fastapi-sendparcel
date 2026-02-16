"""Shared fixtures for fastapi-sendparcel tests."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal

import pytest
from sendparcel.registry import registry


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

    async def list_by_order(self, order_id: str) -> list[DemoShipment]:
        return [
            s
            for s in self.items.values()
            if hasattr(s.order, "id") and s.order.id == order_id
        ]


class OrderResolver:
    async def resolve(self, order_id: str) -> DemoOrder:
        return DemoOrder(id=order_id)


class RetryStore:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def store_failed_callback(
        self, shipment_id: str, payload: dict, headers: dict
    ) -> str:
        self.events.append(
            {
                "shipment_id": shipment_id,
                "payload": payload,
                "headers": headers,
            }
        )
        return f"retry-{len(self.events)}"

    async def get_due_retries(self, limit: int = 10) -> list[dict]:
        return []

    async def mark_succeeded(self, retry_id: str) -> None:
        pass

    async def mark_failed(self, retry_id: str, error: str) -> None:
        pass

    async def mark_exhausted(self, retry_id: str) -> None:
        pass


@pytest.fixture(autouse=True)
def isolate_global_registry() -> Iterator[None]:
    old = dict(registry._providers)
    old_discovered = registry._discovered
    registry._providers = {}
    registry._discovered = True
    try:
        yield
    finally:
        registry._providers = old
        registry._discovered = old_discovered


@pytest.fixture()
def repository() -> InMemoryRepo:
    return InMemoryRepo()


@pytest.fixture()
def resolver() -> OrderResolver:
    return OrderResolver()


@pytest.fixture()
def retry_store() -> RetryStore:
    return RetryStore()


@pytest.fixture()
async def async_engine():
    """Create an in-memory aiosqlite async engine."""
    sa = pytest.importorskip("sqlalchemy")  # noqa: F841
    from sqlalchemy.ext.asyncio import create_async_engine

    from fastapi_sendparcel.contrib.sqlalchemy.models import Base

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture()
async def async_session_factory(async_engine):
    """Create an async session factory bound to the in-memory engine."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )
    yield factory


@pytest.fixture()
def sqlalchemy_repository(async_session_factory):
    """Create an SQLAlchemyShipmentRepository."""
    from fastapi_sendparcel.contrib.sqlalchemy.repository import (
        SQLAlchemyShipmentRepository,
    )

    return SQLAlchemyShipmentRepository(async_session_factory)


@pytest.fixture()
def sqlalchemy_retry_store(async_session_factory):
    """Create an SQLAlchemyRetryStore."""
    from fastapi_sendparcel.contrib.sqlalchemy.retry_store import (
        SQLAlchemyRetryStore,
    )

    return SQLAlchemyRetryStore(async_session_factory)
