"""SQLAlchemy repository integration tests with real aiosqlite DB."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from fastapi_sendparcel.contrib.sqlalchemy.models import Base
from fastapi_sendparcel.contrib.sqlalchemy.repository import (
    SQLAlchemyShipmentRepository,
)


@pytest.fixture()
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture()
def repository(session_factory) -> SQLAlchemyShipmentRepository:
    return SQLAlchemyShipmentRepository(session_factory)


async def test_list_by_order_returns_matching_shipments(
    repository,
) -> None:
    await repository.create(id="s-1", provider="dummy", order_id="order-A")
    await repository.create(id="s-2", provider="dummy", order_id="order-A")
    await repository.create(id="s-3", provider="dummy", order_id="order-B")

    results = await repository.list_by_order("order-A")
    assert len(results) == 2
    assert {r.id for r in results} == {"s-1", "s-2"}


async def test_list_by_order_empty(repository) -> None:
    results = await repository.list_by_order("nonexistent")
    assert results == []


async def test_create_and_get_by_id(repository) -> None:
    created = await repository.create(
        id="s-1", provider="dummy", order_id="order-1"
    )
    assert created.id == "s-1"

    fetched = await repository.get_by_id("s-1")
    assert fetched.id == "s-1"
    assert fetched.provider == "dummy"
