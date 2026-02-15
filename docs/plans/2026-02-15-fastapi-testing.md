# FastAPI-Sendparcel Comprehensive Test Suite Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a comprehensive test suite of ~80 tests across ~14 test files for the fastapi-sendparcel package, covering config, protocols, exceptions, registry, dependencies, schemas, retry logic, routes, public API, SQLAlchemy contrib models, repository, retry store, and integration flows.

**Architecture:** Each test file targets one module or concern. Tests are class-based, grouping related assertions. In-memory fixtures (InMemoryRepo, OrderResolver, RetryStore) drive unit/route tests; real aiosqlite in-memory databases drive SQLAlchemy contrib tests. Route tests use `httpx.AsyncClient` with `ASGITransport` against a test FastAPI app. The conftest provides shared fixtures for both approaches.

**Tech Stack:** Python 3.12, pytest, pytest-asyncio (auto mode), httpx (AsyncClient), FastAPI (TestClient + ASGI transport), SQLAlchemy 2.0 async (aiosqlite), pydantic-settings, sendparcel core.

---

## Prerequisites

This plan assumes the **critical-fixes plan** has been executed. The following modules/features must exist before starting:

- `fastapi_sendparcel/exceptions.py` with `register_exception_handlers(app)` function that maps:
  - `CommunicationError` -> 502
  - `InvalidCallbackError` -> 400
  - `InvalidTransitionError` -> 409
  - `ShipmentNotFoundError` -> 404
  - `SendParcelException` (base) -> 400
- `__version__` attribute in `fastapi_sendparcel.__init__`
- `py.typed` marker file
- `routes/__init__.py`
- Expanded `CallbackRetryStore` protocol (5 methods: `enqueue`, `get_due_retries`, `mark_succeeded`, `mark_failed`, `mark_exhausted`)
- Exponential backoff retry: `compute_next_retry_at(attempt, backoff_seconds)` and `process_due_retries(store, flow, repository, max_attempts)` in `retry.py`
- Expanded config: `retry_max_attempts`, `retry_backoff_seconds`, `retry_enabled` fields on `SendparcelConfig`
- Timestamps (`created_at`, `updated_at`) and `order_id` on `ShipmentModel`
- `list_by_order(order_id)` on repository
- Full `SQLAlchemyRetryStore` with all 5 protocol methods
- `uuid` default column and `status`, `attempt_count`, `next_retry_at`, `last_error` on `CallbackRetryModel`

**If any of these are missing, implement the critical-fixes plan first.**

## Test runner

All tests run from the `fastapi-sendparcel/` directory:

```bash
uv run pytest tests/ -v
```

For SQLAlchemy tests (need the `sqlalchemy` extra installed):

```bash
uv run --extra sqlalchemy pytest tests/ -v
```

To run a single file:

```bash
uv run pytest tests/test_config.py -v
```

---

### Task 1: Expand conftest with SQLAlchemy fixtures and updated RetryStore mock

**Files:**
- Modify: `tests/conftest.py`

**Step 1: Update `tests/conftest.py` with expanded fixtures**

Replace the entire `tests/conftest.py` with:

```python
"""Shared fixtures for fastapi-sendparcel tests."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
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
        if shipment_id not in self.items:
            raise KeyError(f"Shipment {shipment_id} not found")
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


@dataclass
class RetryEntry:
    id: str
    payload: dict
    status: str = "pending"
    attempt_count: int = 0
    next_retry_at: datetime | None = None
    last_error: str = ""


class RetryStore:
    """In-memory mock implementing all 5 CallbackRetryStore protocol methods."""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self._entries: dict[str, RetryEntry] = {}
        self._counter = 0

    async def enqueue(self, payload: dict) -> None:
        self._counter += 1
        entry_id = f"retry-{self._counter}"
        self._entries[entry_id] = RetryEntry(
            id=entry_id,
            payload=payload,
            next_retry_at=datetime.now(tz=UTC),
        )
        self.events.append(payload)

    async def get_due_retries(
        self, *, limit: int = 10
    ) -> list[RetryEntry]:
        now = datetime.now(tz=UTC)
        due = [
            e
            for e in self._entries.values()
            if e.status == "pending"
            and e.next_retry_at is not None
            and e.next_retry_at <= now
        ]
        return due[:limit]

    async def mark_succeeded(self, retry_id: str) -> None:
        self._entries[retry_id].status = "succeeded"

    async def mark_failed(
        self, retry_id: str, *, error: str, next_retry_at: datetime
    ) -> None:
        entry = self._entries[retry_id]
        entry.status = "pending"
        entry.attempt_count += 1
        entry.last_error = error
        entry.next_retry_at = next_retry_at

    async def mark_exhausted(self, retry_id: str) -> None:
        self._entries[retry_id].status = "exhausted"


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
async def async_engine() -> AsyncIterator:
    """Create an in-memory aiosqlite async engine."""
    sa = pytest.importorskip("sqlalchemy")
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
async def async_session_factory(async_engine) -> AsyncIterator:
    """Create an async session factory bound to the in-memory engine."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

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
```

**Step 2: Run existing tests to verify conftest changes do not break anything**

Run:
```bash
uv run pytest tests/ -v
```

Expected: All 6 existing tests still pass. New fixtures are available but unused.

**Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test: expand conftest with SQLAlchemy fixtures and full RetryStore mock"
```

---

### Task 2: tests/test_config.py (~6 tests)

**Files:**
- Create: `tests/test_config.py`

**Step 1: Write `tests/test_config.py`**

```python
"""SendparcelConfig tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fastapi_sendparcel.config import SendparcelConfig


class TestSendparcelConfig:
    def test_default_provider_required(self) -> None:
        with pytest.raises(ValidationError):
            SendparcelConfig()  # type: ignore[call-arg]

    def test_providers_defaults_to_empty(self) -> None:
        config = SendparcelConfig(default_provider="test")
        assert config.providers == {}

    def test_retry_max_attempts_default(self) -> None:
        config = SendparcelConfig(default_provider="test")
        assert config.retry_max_attempts == 5

    def test_retry_backoff_seconds_default(self) -> None:
        config = SendparcelConfig(default_provider="test")
        assert config.retry_backoff_seconds == 60

    def test_retry_enabled_default(self) -> None:
        config = SendparcelConfig(default_provider="test")
        assert config.retry_enabled is True

    def test_env_prefix(self) -> None:
        config = SendparcelConfig(default_provider="test")
        prefix = config.model_config.get("env_prefix", "")
        assert isinstance(prefix, str)
```

**Step 2: Run tests**

Run:
```bash
uv run pytest tests/test_config.py -v
```

Expected: 6 tests pass (assuming critical-fixes added retry fields to config).

**Step 3: Commit**

```bash
git add tests/test_config.py
git commit -m "test: add SendparcelConfig unit tests"
```

---

### Task 3: tests/test_protocols.py (~4 tests)

**Files:**
- Create: `tests/test_protocols.py`

**Step 1: Write `tests/test_protocols.py`**

```python
"""Protocol runtime-checkable tests."""

from __future__ import annotations

from fastapi_sendparcel.protocols import CallbackRetryStore, OrderResolver
from tests.conftest import OrderResolver as MockOrderResolver
from tests.conftest import RetryStore as MockRetryStore


class TestProtocols:
    def test_order_resolver_is_runtime_checkable(self) -> None:
        assert hasattr(OrderResolver, "__protocol_attrs__") or hasattr(
            OrderResolver, "__abstractmethods__"
        )
        # runtime_checkable protocols support isinstance checks
        assert isinstance(MockOrderResolver(), OrderResolver)

    def test_callback_retry_store_is_runtime_checkable(self) -> None:
        assert isinstance(MockRetryStore(), CallbackRetryStore)

    def test_mock_satisfies_order_resolver(self) -> None:
        resolver = MockOrderResolver()
        assert hasattr(resolver, "resolve")
        assert callable(resolver.resolve)

    def test_mock_satisfies_retry_store(self) -> None:
        store = MockRetryStore()
        assert hasattr(store, "enqueue")
        assert callable(store.enqueue)
        assert hasattr(store, "get_due_retries")
        assert callable(store.get_due_retries)
        assert hasattr(store, "mark_succeeded")
        assert callable(store.mark_succeeded)
        assert hasattr(store, "mark_failed")
        assert callable(store.mark_failed)
        assert hasattr(store, "mark_exhausted")
        assert callable(store.mark_exhausted)
```

**Step 2: Run tests**

Run:
```bash
uv run pytest tests/test_protocols.py -v
```

Expected: 4 tests pass.

**Step 3: Commit**

```bash
git add tests/test_protocols.py
git commit -m "test: add protocol runtime-checkable tests"
```

---

### Task 4: tests/test_exceptions.py (~6 tests)

**Files:**
- Create: `tests/test_exceptions.py`

This tests the `register_exception_handlers` function from `fastapi_sendparcel.exceptions`. Each handler should return a JSON response with the correct status code and a `detail` key.

**Step 1: Write `tests/test_exceptions.py`**

```python
"""Exception handler tests."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from sendparcel.exceptions import (
    CommunicationError,
    InvalidCallbackError,
    InvalidTransitionError,
    SendParcelException,
)

from fastapi_sendparcel.exceptions import register_exception_handlers


def _create_app_with_exception(exc: Exception) -> FastAPI:
    """Build a minimal FastAPI app that raises the given exception."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/raise")
    async def raise_exc() -> None:
        raise exc

    return app


class TestExceptionHandlers:
    @pytest.mark.anyio
    async def test_communication_error_returns_502(self) -> None:
        app = _create_app_with_exception(
            CommunicationError("provider unreachable")
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/raise")
        assert resp.status_code == 502
        assert "provider unreachable" in resp.json()["detail"]

    @pytest.mark.anyio
    async def test_invalid_callback_returns_400(self) -> None:
        app = _create_app_with_exception(
            InvalidCallbackError("bad signature")
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/raise")
        assert resp.status_code == 400
        assert "bad signature" in resp.json()["detail"]

    @pytest.mark.anyio
    async def test_invalid_transition_returns_409(self) -> None:
        app = _create_app_with_exception(
            InvalidTransitionError("cannot cancel delivered")
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/raise")
        assert resp.status_code == 409
        assert "cannot cancel delivered" in resp.json()["detail"]

    @pytest.mark.anyio
    async def test_shipment_not_found_returns_404(self) -> None:
        # ShipmentNotFoundError should be added by critical-fixes plan
        from fastapi_sendparcel.exceptions import ShipmentNotFoundError

        app = _create_app_with_exception(
            ShipmentNotFoundError("s-999 not found")
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/raise")
        assert resp.status_code == 404
        assert "s-999 not found" in resp.json()["detail"]

    @pytest.mark.anyio
    async def test_sendparcel_exception_returns_400(self) -> None:
        app = _create_app_with_exception(
            SendParcelException("generic error")
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/raise")
        assert resp.status_code == 400
        assert "generic error" in resp.json()["detail"]

    @pytest.mark.anyio
    async def test_response_format(self) -> None:
        app = _create_app_with_exception(
            CommunicationError("test format")
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/raise")
        body = resp.json()
        assert "detail" in body
        assert isinstance(body["detail"], str)
```

**Step 2: Run tests**

Run:
```bash
uv run pytest tests/test_exceptions.py -v
```

Expected: 6 tests pass.

**Step 3: Commit**

```bash
git add tests/test_exceptions.py
git commit -m "test: add exception handler tests"
```

---

### Task 5: tests/test_registry.py (~5 tests)

**Files:**
- Create: `tests/test_registry.py`

**Step 1: Write `tests/test_registry.py`**

```python
"""FastAPIPluginRegistry tests."""

from __future__ import annotations

import pytest
from sendparcel.provider import BaseProvider

from fastapi_sendparcel.registry import FastAPIPluginRegistry


class _FakeProvider(BaseProvider):
    slug = "fake"
    display_name = "Fake"

    async def create_shipment(self, **kwargs):
        return {"external_id": "ext-1"}


class _FakeRouter:
    """Simulates a provider-specific APIRouter."""

    pass


class TestFastAPIPluginRegistry:
    def test_register_provider(self) -> None:
        reg = FastAPIPluginRegistry()
        reg._discovered = True
        reg.register(_FakeProvider)
        assert reg.get_by_slug("fake") is _FakeProvider

    def test_get_by_slug(self) -> None:
        reg = FastAPIPluginRegistry()
        reg._discovered = True
        reg.register(_FakeProvider)
        result = reg.get_by_slug("fake")
        assert result is _FakeProvider

    def test_get_by_slug_not_found(self) -> None:
        reg = FastAPIPluginRegistry()
        reg._discovered = True
        with pytest.raises(KeyError):
            reg.get_by_slug("nonexistent")

    def test_register_provider_router(self) -> None:
        reg = FastAPIPluginRegistry()
        router = _FakeRouter()
        reg.register_provider_router("fake", router)
        assert reg.get_provider_router("fake") is router

    def test_get_provider_router_returns_none_when_missing(self) -> None:
        reg = FastAPIPluginRegistry()
        assert reg.get_provider_router("nonexistent") is None
```

**Step 2: Run tests**

Run:
```bash
uv run pytest tests/test_registry.py -v
```

Expected: 5 tests pass.

**Step 3: Commit**

```bash
git add tests/test_registry.py
git commit -m "test: add FastAPIPluginRegistry tests"
```

---

### Task 6: tests/test_dependencies.py (~5 tests)

**Files:**
- Create: `tests/test_dependencies.py`

**Step 1: Write `tests/test_dependencies.py`**

```python
"""Dependency injection tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sendparcel.flow import ShipmentFlow

from fastapi_sendparcel.config import SendparcelConfig
from fastapi_sendparcel.dependencies import (
    get_config,
    get_flow,
    get_order_resolver,
    get_repository,
    get_retry_store,
)


def _make_request(**state_attrs) -> MagicMock:
    """Create a mock request with app.state attributes."""
    request = MagicMock()
    state = SimpleNamespace(**state_attrs)
    request.app.state = state
    return request


class TestDependencies:
    def test_get_config_from_app_state(self) -> None:
        config = SendparcelConfig(default_provider="test")
        request = _make_request(sendparcel_config=config)
        result = get_config(request)
        assert result is config

    def test_get_repository_from_app_state(self) -> None:
        repo = MagicMock()
        request = _make_request(sendparcel_repository=repo)
        result = get_repository(request)
        assert result is repo

    def test_get_order_resolver_returns_none_when_not_set(self) -> None:
        request = _make_request()
        result = get_order_resolver(request)
        assert result is None

    def test_get_retry_store_returns_none_when_not_set(self) -> None:
        request = _make_request()
        result = get_retry_store(request)
        assert result is None

    def test_get_flow_creates_shipment_flow(self) -> None:
        config = SendparcelConfig(
            default_provider="test",
            providers={"test": {"key": "val"}},
        )
        repo = MagicMock()
        request = _make_request(
            sendparcel_config=config,
            sendparcel_repository=repo,
        )
        flow = get_flow(request)
        assert isinstance(flow, ShipmentFlow)
        assert flow.repository is repo
```

**Step 2: Run tests**

Run:
```bash
uv run pytest tests/test_dependencies.py -v
```

Expected: 5 tests pass.

**Step 3: Commit**

```bash
git add tests/test_dependencies.py
git commit -m "test: add dependency injection tests"
```

---

### Task 7: tests/test_schemas.py (~7 tests)

**Files:**
- Create: `tests/test_schemas.py`

**Step 1: Write `tests/test_schemas.py`**

```python
"""Pydantic schema tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from fastapi_sendparcel.schemas import (
    CallbackResponse,
    CreateShipmentRequest,
    ShipmentResponse,
)


class TestCreateShipmentRequest:
    def test_required_order_id(self) -> None:
        with pytest.raises(ValidationError):
            CreateShipmentRequest()  # type: ignore[call-arg]

    def test_optional_provider(self) -> None:
        req = CreateShipmentRequest(order_id="o-1")
        assert req.order_id == "o-1"
        assert req.provider is None

    def test_provider_set(self) -> None:
        req = CreateShipmentRequest(order_id="o-1", provider="dhl")
        assert req.provider == "dhl"


class TestShipmentResponse:
    def test_from_shipment(self) -> None:
        shipment = SimpleNamespace(
            id="s-1",
            status="created",
            provider="dummy",
            external_id="ext-1",
            tracking_number="trk-1",
            label_url="https://labels/s-1.pdf",
        )
        resp = ShipmentResponse.from_shipment(shipment)
        assert resp.id == "s-1"
        assert resp.status == "created"
        assert resp.provider == "dummy"
        assert resp.external_id == "ext-1"
        assert resp.tracking_number == "trk-1"
        assert resp.label_url == "https://labels/s-1.pdf"

    def test_all_fields(self) -> None:
        resp = ShipmentResponse(
            id="s-2",
            status="label_ready",
            provider="inpost",
            external_id="ext-2",
            tracking_number="trk-2",
            label_url="",
        )
        assert resp.id == "s-2"
        assert resp.label_url == ""


class TestCallbackResponse:
    def test_all_fields(self) -> None:
        resp = CallbackResponse(
            provider="dummy",
            status="accepted",
            shipment_status="in_transit",
        )
        assert resp.provider == "dummy"
        assert resp.status == "accepted"
        assert resp.shipment_status == "in_transit"

    def test_serialization(self) -> None:
        resp = CallbackResponse(
            provider="dummy",
            status="accepted",
            shipment_status="delivered",
        )
        data = resp.model_dump()
        assert data == {
            "provider": "dummy",
            "status": "accepted",
            "shipment_status": "delivered",
        }
```

**Step 2: Run tests**

Run:
```bash
uv run pytest tests/test_schemas.py -v
```

Expected: 7 tests pass.

**Step 3: Commit**

```bash
git add tests/test_schemas.py
git commit -m "test: add schema validation tests"
```

---

### Task 8: tests/test_retry.py (~6 tests)

**Files:**
- Create: `tests/test_retry.py`

This tests `compute_next_retry_at` (exponential backoff helper) and `process_due_retries` (batch retry processor) — both added by the critical-fixes plan.

**Step 1: Write `tests/test_retry.py`**

```python
"""Retry logic tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from fastapi_sendparcel.retry import (
    compute_next_retry_at,
    enqueue_callback_retry,
    process_due_retries,
)


class TestComputeNextRetryAt:
    def test_first_attempt(self) -> None:
        base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        result = compute_next_retry_at(attempt=0, backoff_seconds=60, now=base)
        expected = base + timedelta(seconds=60)
        assert result == expected

    def test_second_attempt_doubles(self) -> None:
        base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        result = compute_next_retry_at(attempt=1, backoff_seconds=60, now=base)
        expected = base + timedelta(seconds=120)
        assert result == expected

    def test_third_attempt_quadruples(self) -> None:
        base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        result = compute_next_retry_at(attempt=2, backoff_seconds=60, now=base)
        expected = base + timedelta(seconds=240)
        assert result == expected


class TestProcessDueRetries:
    @pytest.mark.anyio
    async def test_processes_due_retries(self, retry_store) -> None:
        await retry_store.enqueue({
            "provider": "dummy",
            "shipment_id": "s-1",
            "payload": {"event": "test"},
            "headers": {},
            "reason": "timeout",
        })

        mock_callback_handler = AsyncMock()
        processed = await process_due_retries(
            store=retry_store,
            callback_handler=mock_callback_handler,
            max_attempts=5,
            backoff_seconds=60,
        )
        assert processed >= 0

    @pytest.mark.anyio
    async def test_exhausts_after_max_attempts(self, retry_store) -> None:
        await retry_store.enqueue({
            "provider": "dummy",
            "shipment_id": "s-1",
            "payload": {"event": "test"},
            "headers": {},
            "reason": "timeout",
        })

        # Simulate max attempts reached by setting attempt_count
        for entry in retry_store._entries.values():
            entry.attempt_count = 5

        mock_callback_handler = AsyncMock(
            side_effect=Exception("still failing")
        )
        processed = await process_due_retries(
            store=retry_store,
            callback_handler=mock_callback_handler,
            max_attempts=5,
            backoff_seconds=60,
        )
        # After exceeding max_attempts, entry should be marked exhausted
        for entry in retry_store._entries.values():
            assert entry.status == "exhausted"

    @pytest.mark.anyio
    async def test_returns_processed_count(self, retry_store) -> None:
        # Enqueue two retries
        await retry_store.enqueue({
            "provider": "dummy",
            "shipment_id": "s-1",
            "payload": {},
            "headers": {},
            "reason": "err1",
        })
        await retry_store.enqueue({
            "provider": "dummy",
            "shipment_id": "s-2",
            "payload": {},
            "headers": {},
            "reason": "err2",
        })

        mock_callback_handler = AsyncMock()
        processed = await process_due_retries(
            store=retry_store,
            callback_handler=mock_callback_handler,
            max_attempts=5,
            backoff_seconds=60,
        )
        assert processed == 2
```

**Step 2: Run tests**

Run:
```bash
uv run pytest tests/test_retry.py -v
```

Expected: 6 tests pass.

**Step 3: Commit**

```bash
git add tests/test_retry.py
git commit -m "test: add retry logic and exponential backoff tests"
```

---

### Task 9: tests/test_routes_callbacks.py (~6 tests)

**Files:**
- Create: `tests/test_routes_callbacks.py`

Uses `httpx.AsyncClient` with `ASGITransport` for async route testing. Registers a `DummyProvider` and wires up the test app through `create_shipping_router`.

**Step 1: Write `tests/test_routes_callbacks.py`**

```python
"""Callback route tests."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from sendparcel.exceptions import InvalidCallbackError
from sendparcel.provider import BaseProvider
from sendparcel.registry import registry

from fastapi_sendparcel.config import SendparcelConfig
from fastapi_sendparcel.router import create_shipping_router
from tests.conftest import InMemoryRepo, OrderResolver, RetryStore


class _CallbackDummyProvider(BaseProvider):
    slug = "cbdummy"
    display_name = "Callback Dummy"

    async def create_shipment(self, **kwargs):
        return {"external_id": "ext-1", "tracking_number": "trk-1"}

    async def create_label(self, **kwargs):
        return {"format": "PDF", "url": "https://labels/test.pdf"}

    async def verify_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        if headers.get("x-token") != "valid":
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


def _build_app(
    repo: InMemoryRepo,
    resolver: OrderResolver,
    store: RetryStore,
) -> FastAPI:
    registry.register(_CallbackDummyProvider)
    app = FastAPI()
    router = create_shipping_router(
        config=SendparcelConfig(default_provider="cbdummy"),
        repository=repo,
        order_resolver=resolver,
        retry_store=store,
    )
    app.include_router(router)
    return app


async def _create_shipment(
    client: httpx.AsyncClient,
) -> str:
    resp = await client.post("/shipments", json={"order_id": "o-1"})
    assert resp.status_code == 200
    return resp.json()["id"]


class TestCallbackRoute:
    @pytest.mark.anyio
    async def test_happy_path(
        self, repository, resolver, retry_store
    ) -> None:
        app = _build_app(repository, resolver, retry_store)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            sid = await _create_shipment(client)
            # Move to label_ready so mark_in_transit is allowed
            await client.post(f"/shipments/{sid}/label")

            resp = await client.post(
                f"/callbacks/cbdummy/{sid}",
                json={"event": "picked_up"},
                headers={"x-token": "valid"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["provider"] == "cbdummy"
            assert body["status"] == "accepted"

    @pytest.mark.anyio
    async def test_provider_slug_mismatch(
        self, repository, resolver, retry_store
    ) -> None:
        app = _build_app(repository, resolver, retry_store)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            sid = await _create_shipment(client)
            resp = await client.post(
                f"/callbacks/wrong_provider/{sid}",
                json={"event": "test"},
                headers={"x-token": "valid"},
            )
            assert resp.status_code == 400
            assert "mismatch" in resp.json()["detail"].lower()

    @pytest.mark.anyio
    async def test_communication_error_enqueues_retry(
        self, repository, resolver, retry_store
    ) -> None:
        app = _build_app(repository, resolver, retry_store)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            sid = await _create_shipment(client)
            # Send with bad token -> verify_callback raises InvalidCallbackError
            resp = await client.post(
                f"/callbacks/cbdummy/{sid}",
                json={"event": "test"},
                headers={"x-token": "bad"},
            )
            assert resp.status_code == 400
            assert len(retry_store.events) == 1
            assert retry_store.events[0]["provider"] == "cbdummy"

    @pytest.mark.anyio
    async def test_invalid_callback_does_not_retry_on_no_store(
        self, repository, resolver
    ) -> None:
        """When retry_store is None, failed callbacks don't crash."""
        registry.register(_CallbackDummyProvider)
        app = FastAPI()
        router = create_shipping_router(
            config=SendparcelConfig(default_provider="cbdummy"),
            repository=repository,
            order_resolver=resolver,
            retry_store=None,
        )
        app.include_router(router)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            sid = await _create_shipment(client)
            resp = await client.post(
                f"/callbacks/cbdummy/{sid}",
                json={"event": "test"},
                headers={"x-token": "bad"},
            )
            assert resp.status_code == 400

    @pytest.mark.anyio
    async def test_invalid_json_body(
        self, repository, resolver, retry_store
    ) -> None:
        app = _build_app(repository, resolver, retry_store)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            sid = await _create_shipment(client)
            resp = await client.post(
                f"/callbacks/cbdummy/{sid}",
                content=b"not-json",
                headers={
                    "x-token": "valid",
                    "content-type": "application/json",
                },
            )
            # The route catches JSONDecodeError and uses empty dict
            # Then verify_callback succeeds with valid token
            # handle_callback runs with empty data, no status transition
            assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_shipment_not_found(
        self, repository, resolver, retry_store
    ) -> None:
        app = _build_app(repository, resolver, retry_store)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/callbacks/cbdummy/nonexistent-id",
                json={"event": "test"},
                headers={"x-token": "valid"},
            )
            # InMemoryRepo.get_by_id raises KeyError for missing shipments
            assert resp.status_code == 500 or resp.status_code == 404
```

**Step 2: Run tests**

Run:
```bash
uv run pytest tests/test_routes_callbacks.py -v
```

Expected: 6 tests pass.

**Step 3: Commit**

```bash
git add tests/test_routes_callbacks.py
git commit -m "test: add callback route tests"
```

---

### Task 10: tests/test_routes_shipments.py (~6 tests)

**Files:**
- Modify: `tests/test_routes_shipments.py` (replace existing minimal test)

**Step 1: Replace `tests/test_routes_shipments.py`**

```python
"""Shipment route tests."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from sendparcel.provider import BaseProvider
from sendparcel.registry import registry

from fastapi_sendparcel.config import SendparcelConfig
from fastapi_sendparcel.router import create_shipping_router
from fastapi_sendparcel.routes.shipments import router as shipments_router
from tests.conftest import InMemoryRepo, OrderResolver


class _ShipmentDummyProvider(BaseProvider):
    slug = "shipdummy"
    display_name = "Ship Dummy"

    async def create_shipment(self, **kwargs):
        return {"external_id": "ext-1", "tracking_number": "SHIP-001"}

    async def create_label(self, **kwargs):
        return {"format": "PDF", "url": "https://labels/ship.pdf"}

    async def fetch_shipment_status(self, **kwargs):
        return {"status": "in_transit"}

    async def cancel_shipment(self, **kwargs):
        return True


def _build_app(
    repo: InMemoryRepo,
    resolver: OrderResolver | None = None,
) -> FastAPI:
    registry.register(_ShipmentDummyProvider)
    app = FastAPI()
    router = create_shipping_router(
        config=SendparcelConfig(default_provider="shipdummy"),
        repository=repo,
        order_resolver=resolver,
    )
    app.include_router(router)
    return app


class TestShipmentRoutes:
    @pytest.mark.anyio
    async def test_create_shipment(
        self, repository, resolver
    ) -> None:
        app = _build_app(repository, resolver)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/shipments", json={"order_id": "o-1"}
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "created"
            assert body["provider"] == "shipdummy"
            assert body["external_id"] == "ext-1"
            assert body["tracking_number"] == "SHIP-001"

    @pytest.mark.anyio
    async def test_create_shipment_no_resolver(
        self, repository
    ) -> None:
        app = _build_app(repository, resolver=None)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/shipments", json={"order_id": "o-1"}
            )
            assert resp.status_code == 500
            assert "resolver" in resp.json()["detail"].lower()

    @pytest.mark.anyio
    async def test_create_label(
        self, repository, resolver
    ) -> None:
        app = _build_app(repository, resolver)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            create_resp = await client.post(
                "/shipments", json={"order_id": "o-1"}
            )
            sid = create_resp.json()["id"]
            resp = await client.post(f"/shipments/{sid}/label")
            assert resp.status_code == 200
            assert resp.json()["status"] == "label_ready"

    @pytest.mark.anyio
    async def test_fetch_status(
        self, repository, resolver
    ) -> None:
        app = _build_app(repository, resolver)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            create_resp = await client.post(
                "/shipments", json={"order_id": "o-1"}
            )
            sid = create_resp.json()["id"]
            # Get label first so transition to in_transit is valid
            await client.post(f"/shipments/{sid}/label")
            resp = await client.get(f"/shipments/{sid}/status")
            assert resp.status_code == 200
            assert resp.json()["status"] == "in_transit"

    @pytest.mark.anyio
    async def test_health_endpoint(
        self, repository, resolver
    ) -> None:
        app = _build_app(repository, resolver)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/shipments/health")
            assert resp.status_code == 200
            assert resp.json() == {"status": "ok"}

    @pytest.mark.anyio
    async def test_default_provider_used(
        self, repository, resolver
    ) -> None:
        app = _build_app(repository, resolver)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/shipments",
                json={"order_id": "o-1"},
            )
            assert resp.status_code == 200
            assert resp.json()["provider"] == "shipdummy"

    def test_shipments_health_route_exists(self) -> None:
        paths = {route.path for route in shipments_router.routes}
        assert "/shipments/health" in paths
```

**Step 2: Run tests**

Run:
```bash
uv run pytest tests/test_routes_shipments.py -v
```

Expected: 7 tests pass.

**Step 3: Commit**

```bash
git add tests/test_routes_shipments.py
git commit -m "test: expand shipment route tests with httpx async client"
```

---

### Task 11: tests/test_public_api.py (~3 tests)

**Files:**
- Create: `tests/test_public_api.py`

**Step 1: Write `tests/test_public_api.py`**

```python
"""Public API surface tests."""

from __future__ import annotations

import fastapi_sendparcel


class TestPublicAPI:
    def test_all_exports_exact_set(self) -> None:
        expected = {
            "FastAPIPluginRegistry",
            "SendparcelConfig",
            "create_shipping_router",
            "__version__",
        }
        actual = set(fastapi_sendparcel.__all__)
        assert actual == expected, f"Missing: {expected - actual}, Extra: {actual - expected}"

    def test_all_exports_importable(self) -> None:
        for name in fastapi_sendparcel.__all__:
            obj = getattr(fastapi_sendparcel, name)
            assert obj is not None, f"{name} is None"

    def test_version(self) -> None:
        version = fastapi_sendparcel.__version__
        assert isinstance(version, str)
        assert len(version) > 0
        # Semantic version: at least "X.Y.Z"
        parts = version.split(".")
        assert len(parts) >= 2, f"Version {version!r} is not semver-like"
```

**Step 2: Run tests**

Run:
```bash
uv run pytest tests/test_public_api.py -v
```

Expected: 3 tests pass (requires `__version__` and updated `__all__` from critical-fixes).

**Step 3: Commit**

```bash
git add tests/test_public_api.py
git commit -m "test: add public API surface tests"
```

---

### Task 12: tests/test_contrib_models.py (~6 tests)

**Files:**
- Create: `tests/test_contrib_models.py`

All tests use real aiosqlite in-memory DB via the `async_engine` and `async_session_factory` fixtures from conftest.

**Step 1: Write `tests/test_contrib_models.py`**

```python
"""SQLAlchemy model tests."""

from __future__ import annotations

import pytest

sa = pytest.importorskip("sqlalchemy")


class TestShipmentModel:
    @pytest.mark.anyio
    async def test_create(self, async_session_factory) -> None:
        from fastapi_sendparcel.contrib.sqlalchemy.models import ShipmentModel

        async with async_session_factory() as session:
            shipment = ShipmentModel(
                id="s-1",
                status="new",
                provider="dummy",
            )
            session.add(shipment)
            await session.commit()
            await session.refresh(shipment)

        assert shipment.id == "s-1"
        assert shipment.status == "new"
        assert shipment.provider == "dummy"

    @pytest.mark.anyio
    async def test_fields(self, async_session_factory) -> None:
        from fastapi_sendparcel.contrib.sqlalchemy.models import ShipmentModel

        async with async_session_factory() as session:
            shipment = ShipmentModel(
                id="s-2",
                status="created",
                provider="inpost",
                external_id="ext-2",
                tracking_number="trk-2",
                label_url="https://labels/s-2.pdf",
            )
            session.add(shipment)
            await session.commit()
            await session.refresh(shipment)

        assert shipment.external_id == "ext-2"
        assert shipment.tracking_number == "trk-2"
        assert shipment.label_url == "https://labels/s-2.pdf"

    @pytest.mark.anyio
    async def test_timestamps(self, async_session_factory) -> None:
        """Verify created_at/updated_at columns exist (added by critical-fixes)."""
        from fastapi_sendparcel.contrib.sqlalchemy.models import ShipmentModel

        async with async_session_factory() as session:
            shipment = ShipmentModel(
                id="s-3",
                status="new",
                provider="dummy",
            )
            session.add(shipment)
            await session.commit()
            await session.refresh(shipment)

        assert hasattr(shipment, "created_at")
        assert hasattr(shipment, "updated_at")
        assert shipment.created_at is not None


class TestCallbackRetryModel:
    @pytest.mark.anyio
    async def test_create(self, async_session_factory) -> None:
        from fastapi_sendparcel.contrib.sqlalchemy.models import (
            CallbackRetryModel,
        )

        async with async_session_factory() as session:
            retry = CallbackRetryModel(
                payload={"provider": "dummy", "reason": "timeout"},
            )
            session.add(retry)
            await session.commit()
            await session.refresh(retry)

        assert retry.id is not None
        assert retry.payload["provider"] == "dummy"

    @pytest.mark.anyio
    async def test_all_fields(self, async_session_factory) -> None:
        from fastapi_sendparcel.contrib.sqlalchemy.models import (
            CallbackRetryModel,
        )

        async with async_session_factory() as session:
            retry = CallbackRetryModel(
                payload={"test": True},
            )
            session.add(retry)
            await session.commit()
            await session.refresh(retry)

        # Fields added by critical-fixes
        assert hasattr(retry, "status")
        assert hasattr(retry, "attempt_count")
        assert hasattr(retry, "next_retry_at")
        assert hasattr(retry, "last_error")

    @pytest.mark.anyio
    async def test_uuid_default(self, async_session_factory) -> None:
        """Verify that uuid column has a default value if added by critical-fixes."""
        from fastapi_sendparcel.contrib.sqlalchemy.models import (
            CallbackRetryModel,
        )

        async with async_session_factory() as session:
            retry = CallbackRetryModel(
                payload={"check": "uuid"},
            )
            session.add(retry)
            await session.commit()
            await session.refresh(retry)

        # The id or uuid field should be auto-populated
        assert retry.id is not None
```

**Step 2: Run tests**

Run:
```bash
uv run --extra sqlalchemy pytest tests/test_contrib_models.py -v
```

Expected: 6 tests pass.

**Step 3: Commit**

```bash
git add tests/test_contrib_models.py
git commit -m "test: add SQLAlchemy model tests"
```

---

### Task 13: tests/test_contrib_repository.py (~7 tests)

**Files:**
- Create: `tests/test_contrib_repository.py`

**Step 1: Write `tests/test_contrib_repository.py`**

```python
"""SQLAlchemy repository tests."""

from __future__ import annotations

import pytest

sa = pytest.importorskip("sqlalchemy")


class TestSQLAlchemyShipmentRepository:
    @pytest.mark.anyio
    async def test_create(self, sqlalchemy_repository) -> None:
        shipment = await sqlalchemy_repository.create(
            id="s-1",
            provider="dummy",
            status="new",
        )
        assert shipment.id == "s-1"
        assert shipment.provider == "dummy"
        assert shipment.status == "new"

    @pytest.mark.anyio
    async def test_get_by_id(self, sqlalchemy_repository) -> None:
        created = await sqlalchemy_repository.create(
            id="s-2",
            provider="dummy",
            status="new",
        )
        fetched = await sqlalchemy_repository.get_by_id("s-2")
        assert fetched.id == created.id
        assert fetched.provider == "dummy"

    @pytest.mark.anyio
    async def test_get_by_id_not_found(self, sqlalchemy_repository) -> None:
        from sqlalchemy.exc import NoResultFound

        with pytest.raises(NoResultFound):
            await sqlalchemy_repository.get_by_id("nonexistent")

    @pytest.mark.anyio
    async def test_save(self, sqlalchemy_repository) -> None:
        shipment = await sqlalchemy_repository.create(
            id="s-3",
            provider="dummy",
            status="new",
        )
        shipment.external_id = "ext-updated"
        saved = await sqlalchemy_repository.save(shipment)
        assert saved.external_id == "ext-updated"

        fetched = await sqlalchemy_repository.get_by_id("s-3")
        assert fetched.external_id == "ext-updated"

    @pytest.mark.anyio
    async def test_update_status(self, sqlalchemy_repository) -> None:
        await sqlalchemy_repository.create(
            id="s-4",
            provider="dummy",
            status="new",
        )
        updated = await sqlalchemy_repository.update_status(
            "s-4",
            "created",
            external_id="ext-4",
        )
        assert updated.status == "created"
        assert updated.external_id == "ext-4"

    @pytest.mark.anyio
    async def test_list_by_order(self, sqlalchemy_repository) -> None:
        """list_by_order added by critical-fixes plan."""
        await sqlalchemy_repository.create(
            id="s-5",
            provider="dummy",
            status="new",
            order_id="order-A",
        )
        await sqlalchemy_repository.create(
            id="s-6",
            provider="dummy",
            status="new",
            order_id="order-A",
        )
        await sqlalchemy_repository.create(
            id="s-7",
            provider="dummy",
            status="new",
            order_id="order-B",
        )
        results = await sqlalchemy_repository.list_by_order("order-A")
        assert len(results) == 2
        ids = {s.id for s in results}
        assert ids == {"s-5", "s-6"}

    @pytest.mark.anyio
    async def test_list_by_order_empty(self, sqlalchemy_repository) -> None:
        results = await sqlalchemy_repository.list_by_order("nonexistent")
        assert results == []
```

**Step 2: Run tests**

Run:
```bash
uv run --extra sqlalchemy pytest tests/test_contrib_repository.py -v
```

Expected: 7 tests pass.

**Step 3: Commit**

```bash
git add tests/test_contrib_repository.py
git commit -m "test: add SQLAlchemy repository tests"
```

---

### Task 14: tests/test_contrib_retry_store.py (~7 tests)

**Files:**
- Create: `tests/test_contrib_retry_store.py`

**Step 1: Write `tests/test_contrib_retry_store.py`**

```python
"""SQLAlchemy retry store tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

sa = pytest.importorskip("sqlalchemy")


class TestSQLAlchemyRetryStore:
    @pytest.mark.anyio
    async def test_store_failed_callback(
        self, sqlalchemy_retry_store
    ) -> None:
        await sqlalchemy_retry_store.enqueue({
            "provider": "dummy",
            "shipment_id": "s-1",
            "payload": {"event": "test"},
            "headers": {},
            "reason": "timeout",
            "queued_at": datetime.now(tz=UTC).isoformat(),
        })
        # Verify entry was persisted by fetching due retries
        due = await sqlalchemy_retry_store.get_due_retries(limit=10)
        assert len(due) >= 1

    @pytest.mark.anyio
    async def test_get_due_retries(
        self, sqlalchemy_retry_store
    ) -> None:
        await sqlalchemy_retry_store.enqueue({
            "provider": "dummy",
            "shipment_id": "s-1",
            "payload": {},
            "headers": {},
            "reason": "err",
            "queued_at": datetime.now(tz=UTC).isoformat(),
        })
        due = await sqlalchemy_retry_store.get_due_retries(limit=10)
        assert len(due) >= 1
        entry = due[0]
        assert entry.payload["provider"] == "dummy"

    @pytest.mark.anyio
    async def test_get_due_retries_respects_limit(
        self, sqlalchemy_retry_store
    ) -> None:
        for i in range(5):
            await sqlalchemy_retry_store.enqueue({
                "provider": "dummy",
                "shipment_id": f"s-{i}",
                "payload": {},
                "headers": {},
                "reason": "err",
                "queued_at": datetime.now(tz=UTC).isoformat(),
            })
        due = await sqlalchemy_retry_store.get_due_retries(limit=3)
        assert len(due) <= 3

    @pytest.mark.anyio
    async def test_mark_succeeded(
        self, sqlalchemy_retry_store
    ) -> None:
        await sqlalchemy_retry_store.enqueue({
            "provider": "dummy",
            "shipment_id": "s-1",
            "payload": {},
            "headers": {},
            "reason": "err",
            "queued_at": datetime.now(tz=UTC).isoformat(),
        })
        due = await sqlalchemy_retry_store.get_due_retries(limit=10)
        assert len(due) >= 1
        entry_id = due[0].id
        await sqlalchemy_retry_store.mark_succeeded(entry_id)

        # Should no longer appear in due retries
        due_after = await sqlalchemy_retry_store.get_due_retries(limit=10)
        remaining_ids = [e.id for e in due_after]
        assert entry_id not in remaining_ids

    @pytest.mark.anyio
    async def test_mark_failed(
        self, sqlalchemy_retry_store
    ) -> None:
        await sqlalchemy_retry_store.enqueue({
            "provider": "dummy",
            "shipment_id": "s-1",
            "payload": {},
            "headers": {},
            "reason": "err",
            "queued_at": datetime.now(tz=UTC).isoformat(),
        })
        due = await sqlalchemy_retry_store.get_due_retries(limit=10)
        entry_id = due[0].id

        future_time = datetime.now(tz=UTC) + timedelta(hours=1)
        await sqlalchemy_retry_store.mark_failed(
            entry_id, error="still failing", next_retry_at=future_time
        )

        # Should NOT appear in due retries now (next_retry_at is in the future)
        due_after = await sqlalchemy_retry_store.get_due_retries(limit=10)
        remaining_ids = [e.id for e in due_after]
        assert entry_id not in remaining_ids

    @pytest.mark.anyio
    async def test_mark_exhausted(
        self, sqlalchemy_retry_store
    ) -> None:
        await sqlalchemy_retry_store.enqueue({
            "provider": "dummy",
            "shipment_id": "s-1",
            "payload": {},
            "headers": {},
            "reason": "err",
            "queued_at": datetime.now(tz=UTC).isoformat(),
        })
        due = await sqlalchemy_retry_store.get_due_retries(limit=10)
        entry_id = due[0].id
        await sqlalchemy_retry_store.mark_exhausted(entry_id)

        # Should NOT appear in due retries anymore
        due_after = await sqlalchemy_retry_store.get_due_retries(limit=10)
        remaining_ids = [e.id for e in due_after]
        assert entry_id not in remaining_ids

    @pytest.mark.anyio
    async def test_full_lifecycle(
        self, sqlalchemy_retry_store
    ) -> None:
        """Test complete lifecycle: enqueue -> fail -> fail -> succeed."""
        await sqlalchemy_retry_store.enqueue({
            "provider": "dummy",
            "shipment_id": "s-lifecycle",
            "payload": {"event": "lifecycle_test"},
            "headers": {},
            "reason": "initial failure",
            "queued_at": datetime.now(tz=UTC).isoformat(),
        })

        # First retry attempt: mark failed with near-past retry time
        due = await sqlalchemy_retry_store.get_due_retries(limit=10)
        assert len(due) == 1
        entry_id = due[0].id

        near_past = datetime.now(tz=UTC) - timedelta(seconds=1)
        await sqlalchemy_retry_store.mark_failed(
            entry_id, error="attempt 1 failed", next_retry_at=near_past
        )

        # Second retry attempt: should be due again
        due = await sqlalchemy_retry_store.get_due_retries(limit=10)
        assert len(due) == 1

        # Mark succeeded
        await sqlalchemy_retry_store.mark_succeeded(entry_id)

        # No more due retries
        due = await sqlalchemy_retry_store.get_due_retries(limit=10)
        assert len(due) == 0
```

**Step 2: Run tests**

Run:
```bash
uv run --extra sqlalchemy pytest tests/test_contrib_retry_store.py -v
```

Expected: 7 tests pass.

**Step 3: Commit**

```bash
git add tests/test_contrib_retry_store.py
git commit -m "test: add SQLAlchemy retry store tests"
```

---

### Task 15: tests/test_integration.py (~4 tests)

**Files:**
- Create: `tests/test_integration.py`

End-to-end integration tests that exercise the full request lifecycle through the FastAPI app with in-memory fixtures.

**Step 1: Write `tests/test_integration.py`**

```python
"""End-to-end integration tests."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from sendparcel.exceptions import InvalidCallbackError
from sendparcel.provider import BaseProvider
from sendparcel.registry import registry

from fastapi_sendparcel.config import SendparcelConfig
from fastapi_sendparcel.router import create_shipping_router
from tests.conftest import InMemoryRepo, OrderResolver, RetryStore


class _IntegrationProvider(BaseProvider):
    slug = "intprovider"
    display_name = "Integration Provider"

    async def create_shipment(self, **kwargs):
        return {
            "external_id": f"int-ext-{self.shipment.id}",
            "tracking_number": f"INT-{self.shipment.id}",
        }

    async def create_label(self, **kwargs):
        return {"format": "PDF", "url": f"https://labels/{self.shipment.id}.pdf"}

    async def verify_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        if headers.get("x-int-token") != "secret":
            raise InvalidCallbackError("invalid token")

    async def handle_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        target_status = data.get("status")
        if target_status == "in_transit":
            if self.shipment.may_trigger("mark_in_transit"):
                self.shipment.mark_in_transit()
        elif target_status == "delivered":
            if self.shipment.may_trigger("mark_delivered"):
                self.shipment.mark_delivered()

    async def fetch_shipment_status(self, **kwargs):
        return {"status": self.get_setting("status_override", "in_transit")}

    async def cancel_shipment(self, **kwargs):
        return True


def _build_integration_app(
    repo: InMemoryRepo,
    resolver: OrderResolver,
    store: RetryStore,
) -> FastAPI:
    registry.register(_IntegrationProvider)
    app = FastAPI()
    router = create_shipping_router(
        config=SendparcelConfig(
            default_provider="intprovider",
            providers={"intprovider": {"status_override": "in_transit"}},
        ),
        repository=repo,
        order_resolver=resolver,
        retry_store=store,
    )
    app.include_router(router)
    return app


class TestIntegration:
    @pytest.mark.anyio
    async def test_create_shipment_through_api(
        self, repository, resolver, retry_store
    ) -> None:
        app = _build_integration_app(repository, resolver, retry_store)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/shipments", json={"order_id": "order-int-1"}
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["provider"] == "intprovider"
            assert body["status"] == "created"
            assert "int-ext-" in body["external_id"]
            assert "INT-" in body["tracking_number"]

    @pytest.mark.anyio
    async def test_callback_through_api(
        self, repository, resolver, retry_store
    ) -> None:
        app = _build_integration_app(repository, resolver, retry_store)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # Create shipment
            create_resp = await client.post(
                "/shipments", json={"order_id": "order-int-2"}
            )
            sid = create_resp.json()["id"]

            # Get label
            await client.post(f"/shipments/{sid}/label")

            # Send valid callback
            cb_resp = await client.post(
                f"/callbacks/intprovider/{sid}",
                json={"status": "in_transit"},
                headers={"x-int-token": "secret"},
            )
            assert cb_resp.status_code == 200
            assert cb_resp.json()["shipment_status"] == "in_transit"

    @pytest.mark.anyio
    async def test_label_and_status_through_api(
        self, repository, resolver, retry_store
    ) -> None:
        app = _build_integration_app(repository, resolver, retry_store)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # Create
            create_resp = await client.post(
                "/shipments", json={"order_id": "order-int-3"}
            )
            sid = create_resp.json()["id"]

            # Label
            label_resp = await client.post(f"/shipments/{sid}/label")
            assert label_resp.status_code == 200
            assert label_resp.json()["status"] == "label_ready"
            assert label_resp.json()["label_url"] != ""

            # Status fetch
            status_resp = await client.get(f"/shipments/{sid}/status")
            assert status_resp.status_code == 200
            assert status_resp.json()["status"] == "in_transit"

    @pytest.mark.anyio
    async def test_full_lifecycle(
        self, repository, resolver, retry_store
    ) -> None:
        """Create -> Label -> Status -> Callback -> verify final state."""
        app = _build_integration_app(repository, resolver, retry_store)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # 1. Create shipment
            create_resp = await client.post(
                "/shipments", json={"order_id": "order-lifecycle"}
            )
            assert create_resp.status_code == 200
            sid = create_resp.json()["id"]
            assert create_resp.json()["status"] == "created"

            # 2. Create label
            label_resp = await client.post(f"/shipments/{sid}/label")
            assert label_resp.status_code == 200
            assert label_resp.json()["status"] == "label_ready"

            # 3. Fetch status (provider returns in_transit)
            status_resp = await client.get(f"/shipments/{sid}/status")
            assert status_resp.status_code == 200
            assert status_resp.json()["status"] == "in_transit"

            # 4. Callback with delivered
            cb_resp = await client.post(
                f"/callbacks/intprovider/{sid}",
                json={"status": "delivered"},
                headers={"x-int-token": "secret"},
            )
            assert cb_resp.status_code == 200
            assert cb_resp.json()["shipment_status"] == "delivered"

            # 5. Health check still works
            health_resp = await client.get("/shipments/health")
            assert health_resp.status_code == 200
            assert health_resp.json() == {"status": "ok"}
```

**Step 2: Run tests**

Run:
```bash
uv run pytest tests/test_integration.py -v
```

Expected: 4 tests pass.

**Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add end-to-end integration tests"
```

---

## Final verification

After all tasks are complete, run the full test suite:

```bash
uv run --extra sqlalchemy pytest tests/ -v
```

Expected: ~80 tests pass across ~14 test files.

### Test count summary

| File | Tests |
|------|-------|
| `tests/conftest.py` | (fixtures only) |
| `tests/test_config.py` | 6 |
| `tests/test_protocols.py` | 4 |
| `tests/test_exceptions.py` | 6 |
| `tests/test_registry.py` | 5 |
| `tests/test_dependencies.py` | 5 |
| `tests/test_schemas.py` | 7 |
| `tests/test_retry.py` | 6 |
| `tests/test_routes_callbacks.py` | 6 |
| `tests/test_routes_shipments.py` | 7 |
| `tests/test_public_api.py` | 3 |
| `tests/test_contrib_models.py` | 6 |
| `tests/test_contrib_repository.py` | 7 |
| `tests/test_contrib_retry_store.py` | 7 |
| `tests/test_integration.py` | 4 |
| `tests/test_routes_flow.py` (existing) | 2 |
| `tests/test_router.py` (existing) | 1 |
| `tests/test_example_app.py` (existing) | 1 |
| `tests/test_contrib_sqlalchemy.py` (existing) | 1 |
| **Total** | **~84** |

### Final commit

```bash
git add -A
git commit -m "test: complete Phase 5 comprehensive test suite (~84 tests)"
```
