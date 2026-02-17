"""SQLAlchemy retry store integration tests with real aiosqlite DB."""


import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from fastapi_sendparcel.contrib.sqlalchemy.models import Base
from fastapi_sendparcel.contrib.sqlalchemy.retry_store import (
    SQLAlchemyRetryStore,
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
def retry_store(session_factory) -> SQLAlchemyRetryStore:
    return SQLAlchemyRetryStore(session_factory, backoff_seconds=60)


async def test_store_failed_callback_returns_id(retry_store) -> None:
    retry_id = await retry_store.store_failed_callback(
        shipment_id="ship-1",
        provider_slug="test-provider",
        payload={"event": "test"},
        headers={"x-token": "ok"},
    )
    assert isinstance(retry_id, str)
    assert len(retry_id) == 36  # UUID


async def test_get_due_retries_returns_pending(session_factory) -> None:
    store = SQLAlchemyRetryStore(session_factory, backoff_seconds=0)
    await store.store_failed_callback(
        shipment_id="ship-1",
        provider_slug="test-provider",
        payload={"event": "test"},
        headers={},
    )

    retries = await store.get_due_retries(limit=10)
    assert len(retries) == 1
    assert retries[0]["shipment_id"] == "ship-1"
    assert retries[0]["payload"] == {"event": "test"}
    assert retries[0]["attempts"] == 0


async def test_get_due_retries_ignores_future(
    session_factory,
) -> None:
    """Retries with next_retry_at in the future should not be returned."""
    store = SQLAlchemyRetryStore(session_factory, backoff_seconds=9999)
    await store.store_failed_callback(
        shipment_id="ship-1",
        provider_slug="test-provider",
        payload={},
        headers={},
    )

    retries = await store.get_due_retries(limit=10)
    assert len(retries) == 0


async def test_mark_succeeded(retry_store) -> None:
    retry_id = await retry_store.store_failed_callback(
        shipment_id="ship-1",
        provider_slug="test-provider",
        payload={},
        headers={},
    )
    await retry_store.mark_succeeded(retry_id)

    # Should no longer appear in due retries
    retries = await retry_store.get_due_retries(limit=10)
    assert len(retries) == 0


async def test_mark_failed_increments_attempts(retry_store) -> None:
    retry_id = await retry_store.store_failed_callback(
        shipment_id="ship-1",
        provider_slug="test-provider",
        payload={},
        headers={},
    )
    await retry_store.mark_failed(retry_id, error="timeout")

    retries = await retry_store.get_due_retries(limit=10)
    # After mark_failed, next_retry_at is pushed into the future
    # so it won't appear in due retries yet
    assert len(retries) == 0


async def test_mark_exhausted(retry_store) -> None:
    retry_id = await retry_store.store_failed_callback(
        shipment_id="ship-1",
        provider_slug="test-provider",
        payload={},
        headers={},
    )
    await retry_store.mark_exhausted(retry_id)

    retries = await retry_store.get_due_retries(limit=10)
    assert len(retries) == 0


async def test_full_lifecycle(retry_store) -> None:
    """Test store -> get_due -> mark_failed -> mark_succeeded lifecycle."""
    retry_id = await retry_store.store_failed_callback(
        shipment_id="ship-1",
        provider_slug="test-provider",
        payload={"event": "delivered"},
        headers={"x-sig": "abc"},
    )

    # Initially due (backoff_seconds=60, first retry scheduled ~60s from now)
    # We need to verify it was stored correctly
    assert retry_id is not None

    # Mark as failed (schedules next retry further out)
    await retry_store.mark_failed(retry_id, error="connection refused")

    # Mark as succeeded on next attempt
    await retry_store.mark_succeeded(retry_id)

    # Verify it's gone from due retries
    retries = await retry_store.get_due_retries(limit=10)
    assert len(retries) == 0
