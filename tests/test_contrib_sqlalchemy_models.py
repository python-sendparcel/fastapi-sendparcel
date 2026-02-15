"""SQLAlchemy model tests with real aiosqlite DB."""

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from fastapi_sendparcel.contrib.sqlalchemy.models import (
    Base,
    CallbackRetryModel,
    ShipmentModel,
)


@pytest.fixture()
async def async_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def test_callback_retry_model_has_all_columns(async_session) -> None:
    """Verify CallbackRetryModel has the correct column set."""
    mapper = inspect(CallbackRetryModel)
    column_names = {col.key for col in mapper.column_attrs}

    expected = {
        "id",
        "shipment_id",
        "payload",
        "headers",
        "attempts",
        "next_retry_at",
        "last_error",
        "status",
        "created_at",
    }
    assert column_names == expected


async def test_callback_retry_model_defaults(async_session) -> None:
    """Verify default values are set correctly."""
    retry = CallbackRetryModel(
        shipment_id="ship-1",
        payload={"event": "test"},
        headers={"x-token": "ok"},
    )
    async_session.add(retry)
    await async_session.commit()
    await async_session.refresh(retry)

    assert retry.id is not None
    assert len(retry.id) == 36  # UUID format
    assert retry.attempts == 0
    assert retry.status == "pending"
    assert retry.next_retry_at is None
    assert retry.last_error is None
    assert retry.created_at is not None


async def test_callback_retry_model_shipment_id_indexed(
    async_session,
) -> None:
    """Verify shipment_id column is indexed."""
    table = CallbackRetryModel.__table__
    indexed_columns = set()
    for idx in table.indexes:
        for col in idx.columns:
            indexed_columns.add(col.name)
    assert "shipment_id" in indexed_columns


async def test_shipment_model_still_works(async_session) -> None:
    """Verify ShipmentModel is not broken by changes."""
    shipment = ShipmentModel(
        id="ship-1",
        provider="dummy",
    )
    async_session.add(shipment)
    await async_session.commit()
    await async_session.refresh(shipment)

    assert shipment.id == "ship-1"
    assert shipment.status == "new"
    assert shipment.provider == "dummy"


async def test_shipment_model_has_timestamps_and_order_id(
    async_session,
) -> None:
    """Verify ShipmentModel has created_at, updated_at, and order_id."""
    mapper = inspect(ShipmentModel)
    column_names = {col.key for col in mapper.column_attrs}

    assert "created_at" in column_names
    assert "updated_at" in column_names
    assert "order_id" in column_names


async def test_shipment_model_order_id_indexed(async_session) -> None:
    """Verify order_id column is indexed."""
    table = ShipmentModel.__table__
    indexed_columns = set()
    for idx in table.indexes:
        for col in idx.columns:
            indexed_columns.add(col.name)
    assert "order_id" in indexed_columns


async def test_shipment_model_timestamps_default(async_session) -> None:
    """Verify timestamps are set automatically."""
    shipment = ShipmentModel(
        id="ship-ts",
        provider="dummy",
        order_id="order-1",
    )
    async_session.add(shipment)
    await async_session.commit()
    await async_session.refresh(shipment)

    assert shipment.created_at is not None
    assert shipment.updated_at is not None
    assert shipment.order_id == "order-1"
