# FastAPI Critical Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix critical gaps in fastapi-sendparcel: proper exception handling, complete retry lifecycle with exponential backoff, and SQLAlchemy model improvements — matching the reference fastapi-getpaid architecture.

**Architecture:** Add structured exception handlers mapped to HTTP status codes, replace the single-method CallbackRetryStore with a 5-method lifecycle protocol (store/get_due/mark_succeeded/mark_failed/mark_exhausted), implement exponential backoff retry processing, fix the callback route to only retry transient failures (CommunicationError) and not invalid callbacks, and expand SQLAlchemy models with proper fields (timestamps, UUIDs, indexes).

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Pydantic Settings, aiosqlite (for tests), pytest-asyncio

---

## Prerequisites

- Working directory: `fastapi-sendparcel/`
- Run tests: `uv run pytest tests/ -v`
- Source code: `src/fastapi_sendparcel/`
- Tests: `tests/`
- Core package `python-sendparcel` is a local editable dependency

---

## Task 1: Add exceptions module with register_exception_handlers

**Files:**
- Create: `src/fastapi_sendparcel/exceptions.py`
- Test: `tests/test_exceptions.py`

**Step 1: Write the failing test**

Create `tests/test_exceptions.py`:

```python
"""Exception handler tests."""

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sendparcel.exceptions import (
    CommunicationError,
    InvalidCallbackError,
    InvalidTransitionError,
    SendParcelException,
)

from fastapi_sendparcel.exceptions import (
    ShipmentNotFoundError,
    register_exception_handlers,
)


def _create_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    return app


def test_shipment_not_found_error_has_shipment_id() -> None:
    exc = ShipmentNotFoundError("ship-42")
    assert exc.shipment_id == "ship-42"
    assert "ship-42" in str(exc)


def test_communication_error_returns_502() -> None:
    app = _create_app()

    @app.get("/boom")
    async def boom():
        raise CommunicationError("provider timeout")

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/boom")
    assert resp.status_code == 502
    body = resp.json()
    assert body["detail"] == "provider timeout"
    assert body["code"] == "communication_error"


def test_invalid_callback_returns_400() -> None:
    app = _create_app()

    @app.get("/boom")
    async def boom():
        raise InvalidCallbackError("bad signature")

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/boom")
    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"] == "bad signature"
    assert body["code"] == "invalid_callback"


def test_invalid_transition_returns_409() -> None:
    app = _create_app()

    @app.get("/boom")
    async def boom():
        raise InvalidTransitionError("cannot cancel")

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/boom")
    assert resp.status_code == 409
    body = resp.json()
    assert body["detail"] == "cannot cancel"
    assert body["code"] == "invalid_transition"


def test_shipment_not_found_returns_404() -> None:
    app = _create_app()

    @app.get("/boom")
    async def boom():
        raise ShipmentNotFoundError("ship-99")

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/boom")
    assert resp.status_code == 404
    body = resp.json()
    assert body["detail"] == "Shipment ship-99 not found"
    assert body["code"] == "not_found"


def test_generic_sendparcel_exception_returns_400() -> None:
    app = _create_app()

    @app.get("/boom")
    async def boom():
        raise SendParcelException("something broke")

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/boom")
    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"] == "something broke"
    assert body["code"] == "shipment_error"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_exceptions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fastapi_sendparcel.exceptions'`

**Step 3: Write the implementation**

Create `src/fastapi_sendparcel/exceptions.py`:

```python
"""Exception handlers mapping sendparcel-core exceptions to HTTP responses."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sendparcel.exceptions import (
    CommunicationError,
    InvalidCallbackError,
    InvalidTransitionError,
    SendParcelException,
)


class ShipmentNotFoundError(Exception):
    """Shipment with given ID was not found."""

    def __init__(self, shipment_id: str) -> None:
        self.shipment_id = shipment_id
        super().__init__(f"Shipment {shipment_id} not found")


def register_exception_handlers(app: FastAPI) -> None:
    """Register sendparcel exception handlers on a FastAPI app.

    More specific handlers must be registered first so FastAPI
    matches them before the generic SendParcelException handler.
    """

    @app.exception_handler(CommunicationError)
    async def _communication_error(
        request: Request,
        exc: CommunicationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content={
                "detail": str(exc),
                "code": "communication_error",
            },
        )

    @app.exception_handler(InvalidCallbackError)
    async def _invalid_callback(
        request: Request,
        exc: InvalidCallbackError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={
                "detail": str(exc),
                "code": "invalid_callback",
            },
        )

    @app.exception_handler(InvalidTransitionError)
    async def _invalid_transition(
        request: Request,
        exc: InvalidTransitionError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={
                "detail": str(exc),
                "code": "invalid_transition",
            },
        )

    @app.exception_handler(ShipmentNotFoundError)
    async def _not_found(
        request: Request,
        exc: ShipmentNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={
                "detail": str(exc),
                "code": "not_found",
            },
        )

    @app.exception_handler(SendParcelException)
    async def _sendparcel_error(
        request: Request,
        exc: SendParcelException,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={
                "detail": str(exc),
                "code": "shipment_error",
            },
        )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_exceptions.py -v`
Expected: All 6 tests PASS

**Step 5: Commit**

```bash
git add src/fastapi_sendparcel/exceptions.py tests/test_exceptions.py
git commit -m "feat: add exceptions module with structured HTTP error handlers"
```

---

## Task 2: Wire exception handlers in router lifespan

**Files:**
- Modify: `src/fastapi_sendparcel/router.py` (line 30 lifespan function)
- Test: `tests/test_router.py`

**Step 1: Write the failing test**

Append to `tests/test_router.py`:

```python
from fastapi import FastAPI
from sendparcel.exceptions import CommunicationError

from fastapi_sendparcel.config import SendparcelConfig
from fastapi_sendparcel.router import create_shipping_router


def test_exception_handlers_registered_after_lifespan() -> None:
    """Exception handlers should be registered when the router lifespan runs."""
    app = FastAPI()
    router = create_shipping_router(
        config=SendparcelConfig(default_provider="dummy"),
        repository=_Repo(),
    )
    app.include_router(router)

    # Before startup, no exception handlers for CommunicationError
    with app.router.lifespan_context(app) as _:
        handlers = app.exception_handlers
        assert CommunicationError in handlers
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_router.py::test_exception_handlers_registered_after_lifespan -v`
Expected: FAIL — `AssertionError` because `register_exception_handlers` is not called

**Step 3: Write the implementation**

Modify `src/fastapi_sendparcel/router.py` — add the import and call in lifespan:

Add import at top (after existing imports):
```python
from fastapi_sendparcel.exceptions import register_exception_handlers
```

Add call inside the lifespan function, after setting app.state and before `actual_registry.discover()`:
```python
        register_exception_handlers(app)
```

The full lifespan function becomes:
```python
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        app.state.sendparcel_config = config
        app.state.sendparcel_repository = repository
        app.state.sendparcel_registry = actual_registry
        app.state.sendparcel_order_resolver = order_resolver
        app.state.sendparcel_retry_store = retry_store
        register_exception_handlers(app)
        actual_registry.discover()
        yield
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_router.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/fastapi_sendparcel/router.py tests/test_router.py
git commit -m "feat: wire exception handlers into router lifespan"
```

---

## Task 3: Fix callback route — replace bare Exception catch

**Files:**
- Modify: `src/fastapi_sendparcel/routes/callbacks.py`
- Modify: `tests/test_routes_flow.py`
- Modify: `tests/conftest.py`

The current callback route has two problems:
1. It enqueues a retry for `InvalidCallbackError` — invalid callbacks should NOT be retried (they'll fail again with the same bad data)
2. It catches bare `Exception` and returns 502 — this swallows errors that should propagate to the exception handler

The fix: catch `CommunicationError` specifically (transient failure → retry + re-raise for 502 handler), re-raise `InvalidCallbackError` without retry (400 handler picks it up), and remove the bare `except Exception`.

**Step 1: Write the failing tests**

Update `tests/conftest.py` — the `RetryStore` class needs to support the new `store_failed_callback` method alongside the old `enqueue` for backward compatibility during migration. Replace the `RetryStore` class:

```python
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
```

Update `tests/test_routes_flow.py` — change the existing `test_callback_error_enqueues_retry` and add a new test for `CommunicationError`. The existing test verifies that an `InvalidCallbackError` (bad token) enqueues a retry, but after this fix it should NOT enqueue a retry:

Replace `test_callback_error_enqueues_retry` with:

```python
def test_invalid_callback_does_not_enqueue_retry(
    repository, resolver, retry_store
) -> None:
    """InvalidCallbackError should NOT trigger retry — bad data won't improve."""
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
        assert len(retry_store.events) == 0
```

Add a new test class/function for CommunicationError. This requires a provider that raises CommunicationError. Add after the existing tests:

```python
from sendparcel.exceptions import CommunicationError


class CommErrorProvider(BaseProvider):
    slug = "commerr"
    display_name = "CommErr"

    async def create_shipment(self, **kwargs):
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


def _create_commerr_client(repo, resolver, retry_store):
    registry.register(CommErrorProvider)
    app = FastAPI()
    router = create_shipping_router(
        config=SendparcelConfig(
            default_provider="commerr",
            providers={"commerr": {}},
        ),
        repository=repo,
        order_resolver=resolver,
        retry_store=retry_store,
    )
    app.include_router(router)
    return TestClient(app)


def test_communication_error_enqueues_retry_and_returns_502(
    repository, resolver, retry_store
) -> None:
    """CommunicationError (transient) should enqueue retry and return 502."""
    client = _create_commerr_client(repository, resolver, retry_store)

    with client:
        created = client.post("/shipments", json={"order_id": "o-1"})
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
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_routes_flow.py -v`
Expected: `test_invalid_callback_does_not_enqueue_retry` FAILS (current code enqueues on InvalidCallbackError), `test_communication_error_enqueues_retry_and_returns_502` FAILS (current code catches bare Exception not CommunicationError specifically)

**Step 3: Write the implementation**

Replace the entire `src/fastapi_sendparcel/routes/callbacks.py`:

```python
"""Callback endpoints."""

from __future__ import annotations

import logging
from json import JSONDecodeError

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sendparcel.exceptions import CommunicationError, InvalidCallbackError

from fastapi_sendparcel.dependencies import (
    get_flow,
    get_repository,
    get_retry_store,
)
from fastapi_sendparcel.schemas import CallbackResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/callbacks/{provider_slug}/{shipment_id}",
    response_model=CallbackResponse,
)
async def provider_callback(
    provider_slug: str,
    shipment_id: str,
    request: Request,
    flow=Depends(get_flow),
    repository=Depends(get_repository),
    retry_store=Depends(get_retry_store),
) -> CallbackResponse:
    """Handle provider callback using core flow and retry hooks."""
    shipment = await repository.get_by_id(shipment_id)
    if str(shipment.provider) != provider_slug:
        raise InvalidCallbackError("Provider slug mismatch")

    raw_body = await request.body()
    try:
        payload = await request.json()
    except JSONDecodeError:
        payload = {}
    headers = dict(request.headers)

    try:
        updated = await flow.handle_callback(
            shipment,
            payload,
            headers,
            raw_body=raw_body,
        )
    except InvalidCallbackError:
        # Bad callback data — do NOT enqueue retry, re-raise for 400 handler
        raise
    except CommunicationError as exc:
        # Transient failure — enqueue for retry, then re-raise for 502 handler
        if retry_store is not None:
            retry_payload = dict(payload)
            retry_payload["_raw_body"] = raw_body.decode("utf-8")
            await retry_store.store_failed_callback(
                shipment_id=shipment_id,
                payload=retry_payload,
                headers=headers,
            )
            logger.warning(
                "Callback for shipment %s failed, queued for retry: %s",
                shipment_id,
                exc,
            )
        raise

    return CallbackResponse(
        provider=provider_slug,
        status="accepted",
        shipment_status=str(updated.status),
    )
```

Key changes:
- `InvalidCallbackError` is re-raised without retry (exception handler returns 400)
- `CommunicationError` is caught specifically, enqueues retry via `store_failed_callback`, then re-raises (exception handler returns 502)
- Bare `except Exception` is removed — other exceptions propagate naturally
- Provider slug mismatch now raises `InvalidCallbackError` instead of `HTTPException`
- Uses `store_failed_callback` instead of `enqueue_callback_retry`

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_routes_flow.py -v`
Expected: All tests PASS

Also run the full suite to check no regressions:
Run: `uv run pytest tests/ -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/fastapi_sendparcel/routes/callbacks.py tests/test_routes_flow.py tests/conftest.py
git commit -m "fix: only retry CommunicationError callbacks, not invalid ones"
```

---

## Task 4: Add __version__ and py.typed marker

**Files:**
- Modify: `src/fastapi_sendparcel/__init__.py`
- Create: `src/fastapi_sendparcel/py.typed`
- Test: `tests/test_package_metadata.py`

**Step 1: Write the failing test**

Create `tests/test_package_metadata.py`:

```python
"""Package metadata tests."""

from pathlib import Path


def test_version_is_available() -> None:
    from fastapi_sendparcel import __version__

    assert __version__ == "0.1.0"


def test_py_typed_marker_exists() -> None:
    marker = Path(__file__).resolve().parents[1] / "src" / "fastapi_sendparcel" / "py.typed"
    assert marker.exists(), "py.typed marker file must exist"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_package_metadata.py -v`
Expected: FAIL — `ImportError: cannot import name '__version__'` and missing py.typed

**Step 3: Write the implementation**

Add `__version__` to `src/fastapi_sendparcel/__init__.py`. Insert after the module docstring (line 1), before the imports:

```python
__version__ = "0.1.0"
```

Create `src/fastapi_sendparcel/py.typed` as an empty file (PEP 561 marker).

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_package_metadata.py -v`
Expected: All 2 tests PASS

**Step 5: Commit**

```bash
git add src/fastapi_sendparcel/__init__.py src/fastapi_sendparcel/py.typed tests/test_package_metadata.py
git commit -m "feat: add __version__ and PEP 561 py.typed marker"
```

---

## Task 5: Add lazy imports to __init__.py

**Files:**
- Modify: `src/fastapi_sendparcel/__init__.py`
- Test: `tests/test_package_metadata.py` (extend)

**Step 1: Write the failing test**

Append to `tests/test_package_metadata.py`:

```python
def test_all_exports_importable() -> None:
    import fastapi_sendparcel

    expected = {
        "CallbackRetryStore",
        "FastAPIPluginRegistry",
        "OrderResolver",
        "SendparcelConfig",
        "ShipmentNotFoundError",
        "__version__",
        "create_shipping_router",
        "register_exception_handlers",
    }
    assert set(fastapi_sendparcel.__all__) == expected

    for name in expected:
        obj = getattr(fastapi_sendparcel, name)
        assert obj is not None, f"{name} resolved to None"


def test_getattr_raises_for_unknown_attribute() -> None:
    import fastapi_sendparcel
    import pytest

    with pytest.raises(AttributeError, match="no_such_thing"):
        fastapi_sendparcel.no_such_thing
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_package_metadata.py -v`
Expected: FAIL — `__all__` doesn't match, new names not exported

**Step 3: Write the implementation**

Replace `src/fastapi_sendparcel/__init__.py` entirely:

```python
"""FastAPI adapter public API."""

from typing import TYPE_CHECKING

__version__ = "0.1.0"

__all__ = [
    "CallbackRetryStore",
    "FastAPIPluginRegistry",
    "OrderResolver",
    "SendparcelConfig",
    "ShipmentNotFoundError",
    "__version__",
    "create_shipping_router",
    "register_exception_handlers",
]

if TYPE_CHECKING:
    from fastapi_sendparcel.config import SendparcelConfig
    from fastapi_sendparcel.exceptions import (
        ShipmentNotFoundError,
        register_exception_handlers,
    )
    from fastapi_sendparcel.protocols import CallbackRetryStore, OrderResolver
    from fastapi_sendparcel.registry import FastAPIPluginRegistry
    from fastapi_sendparcel.router import create_shipping_router


def __getattr__(name: str):
    # Lazy imports to avoid loading all submodules on package import.
    if name == "SendparcelConfig":
        from fastapi_sendparcel.config import SendparcelConfig

        return SendparcelConfig
    if name == "create_shipping_router":
        from fastapi_sendparcel.router import create_shipping_router

        return create_shipping_router
    if name == "FastAPIPluginRegistry":
        from fastapi_sendparcel.registry import FastAPIPluginRegistry

        return FastAPIPluginRegistry
    if name in ("ShipmentNotFoundError", "register_exception_handlers"):
        from fastapi_sendparcel import exceptions

        return getattr(exceptions, name)
    if name in ("CallbackRetryStore", "OrderResolver"):
        from fastapi_sendparcel import protocols

        return getattr(protocols, name)
    raise AttributeError(
        f"module 'fastapi_sendparcel' has no attribute {name!r}"
    )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_package_metadata.py -v`
Expected: All 4 tests PASS

Also verify no regressions:
Run: `uv run pytest tests/ -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/fastapi_sendparcel/__init__.py tests/test_package_metadata.py
git commit -m "refactor: lazy imports and expanded public API in __init__"
```

---

## Task 6: Add routes/__init__.py

**Files:**
- Create: `src/fastapi_sendparcel/routes/__init__.py`

**Step 1: No test needed**

This is a package marker file. Verify it doesn't exist:

Run: `ls src/fastapi_sendparcel/routes/__init__.py`
Expected: `No such file or directory`

**Step 2: Create the file**

Create `src/fastapi_sendparcel/routes/__init__.py`:

```python
"""Route modules for fastapi-sendparcel."""
```

**Step 3: Run full test suite to verify no regressions**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add src/fastapi_sendparcel/routes/__init__.py
git commit -m "chore: add routes package __init__.py"
```

---

## Task 7: Expand CallbackRetryStore protocol

**Files:**
- Modify: `src/fastapi_sendparcel/protocols.py`
- Test: `tests/test_protocols.py`

**Step 1: Write the failing test**

Create `tests/test_protocols.py`:

```python
"""Protocol conformance tests."""

from fastapi_sendparcel.protocols import CallbackRetryStore


class _FullRetryStore:
    """Minimal implementation to verify protocol shape."""

    async def store_failed_callback(
        self, shipment_id: str, payload: dict, headers: dict
    ) -> str:
        return "retry-1"

    async def get_due_retries(self, limit: int = 10) -> list[dict]:
        return []

    async def mark_succeeded(self, retry_id: str) -> None:
        pass

    async def mark_failed(self, retry_id: str, error: str) -> None:
        pass

    async def mark_exhausted(self, retry_id: str) -> None:
        pass


class _IncompleteRetryStore:
    """Missing methods — should NOT satisfy protocol."""

    async def store_failed_callback(
        self, shipment_id: str, payload: dict, headers: dict
    ) -> str:
        return "retry-1"


def test_full_store_satisfies_protocol() -> None:
    assert isinstance(_FullRetryStore(), CallbackRetryStore)


def test_incomplete_store_does_not_satisfy_protocol() -> None:
    assert not isinstance(_IncompleteRetryStore(), CallbackRetryStore)


def test_protocol_has_five_methods() -> None:
    expected_methods = {
        "store_failed_callback",
        "get_due_retries",
        "mark_succeeded",
        "mark_failed",
        "mark_exhausted",
    }
    # Check the protocol defines these abstract methods
    for method_name in expected_methods:
        assert hasattr(CallbackRetryStore, method_name), (
            f"CallbackRetryStore missing method {method_name}"
        )
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_protocols.py -v`
Expected: FAIL — `_FullRetryStore` won't satisfy current 1-method protocol, `_IncompleteRetryStore` will incorrectly satisfy it

**Step 3: Write the implementation**

Replace `src/fastapi_sendparcel/protocols.py`:

```python
"""FastAPI adapter protocol extensions."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from sendparcel.protocols import Order


@runtime_checkable
class OrderResolver(Protocol):
    """Resolves order IDs to core Order objects."""

    async def resolve(self, order_id: str) -> Order: ...


@runtime_checkable
class CallbackRetryStore(Protocol):
    """Storage abstraction for the webhook retry queue."""

    async def store_failed_callback(
        self,
        shipment_id: str,
        payload: dict,
        headers: dict,
    ) -> str: ...

    async def get_due_retries(self, limit: int = 10) -> list[dict]: ...

    async def mark_succeeded(self, retry_id: str) -> None: ...

    async def mark_failed(
        self,
        retry_id: str,
        error: str,
    ) -> None: ...

    async def mark_exhausted(self, retry_id: str) -> None: ...
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_protocols.py -v`
Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add src/fastapi_sendparcel/protocols.py tests/test_protocols.py
git commit -m "feat: expand CallbackRetryStore protocol to 5-method lifecycle"
```

---

## Task 8: Implement exponential backoff in retry.py

**Files:**
- Modify: `src/fastapi_sendparcel/retry.py`
- Test: `tests/test_retry.py`

**Step 1: Write the failing test**

Create `tests/test_retry.py`:

```python
"""Retry mechanism tests."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from fastapi_sendparcel.config import SendparcelConfig
from fastapi_sendparcel.retry import compute_next_retry_at, process_due_retries


class TestComputeNextRetryAt:
    def test_attempt_1_gives_base_delay(self) -> None:
        before = datetime.now(tz=UTC)
        result = compute_next_retry_at(attempt=1, backoff_seconds=60)
        after = datetime.now(tz=UTC)

        assert before + timedelta(seconds=60) <= result <= after + timedelta(
            seconds=60
        )

    def test_attempt_2_gives_double_delay(self) -> None:
        before = datetime.now(tz=UTC)
        result = compute_next_retry_at(attempt=2, backoff_seconds=60)
        after = datetime.now(tz=UTC)

        assert before + timedelta(seconds=120) <= result <= after + timedelta(
            seconds=120
        )

    def test_attempt_3_gives_quadruple_delay(self) -> None:
        before = datetime.now(tz=UTC)
        result = compute_next_retry_at(attempt=3, backoff_seconds=60)
        after = datetime.now(tz=UTC)

        assert before + timedelta(seconds=240) <= result <= after + timedelta(
            seconds=240
        )

    def test_custom_backoff_seconds(self) -> None:
        before = datetime.now(tz=UTC)
        result = compute_next_retry_at(attempt=1, backoff_seconds=30)
        after = datetime.now(tz=UTC)

        assert before + timedelta(seconds=30) <= result <= after + timedelta(
            seconds=30
        )


class TestProcessDueRetries:
    @pytest.fixture()
    def config(self) -> SendparcelConfig:
        return SendparcelConfig(
            default_provider="dummy",
            retry_max_attempts=5,
            retry_backoff_seconds=60,
        )

    @pytest.fixture()
    def mock_retry_store(self) -> AsyncMock:
        store = AsyncMock()
        store.get_due_retries = AsyncMock(return_value=[])
        store.mark_succeeded = AsyncMock()
        store.mark_failed = AsyncMock()
        store.mark_exhausted = AsyncMock()
        return store

    @pytest.fixture()
    def mock_repository(self) -> AsyncMock:
        repo = AsyncMock()
        return repo

    async def test_no_due_retries_returns_zero(
        self, mock_retry_store, mock_repository, config
    ) -> None:
        result = await process_due_retries(
            retry_store=mock_retry_store,
            repository=mock_repository,
            config=config,
        )
        assert result == 0
        mock_retry_store.get_due_retries.assert_awaited_once_with(limit=10)

    async def test_successful_retry_marks_succeeded(
        self, mock_retry_store, mock_repository, config
    ) -> None:
        mock_retry_store.get_due_retries.return_value = [
            {
                "id": "retry-1",
                "shipment_id": "ship-1",
                "payload": {"event": "picked_up"},
                "headers": {"x-token": "ok"},
                "attempts": 1,
            },
        ]

        from tests.conftest import DemoShipment, DemoOrder

        shipment = DemoShipment(
            id="ship-1",
            order=DemoOrder(id="o-1"),
            status="label_ready",
            provider="dummy",
        )
        mock_repository.get_by_id.return_value = shipment

        result = await process_due_retries(
            retry_store=mock_retry_store,
            repository=mock_repository,
            config=config,
        )
        assert result == 1
        mock_retry_store.mark_succeeded.assert_awaited_once_with("retry-1")

    async def test_shipment_not_found_marks_exhausted(
        self, mock_retry_store, mock_repository, config
    ) -> None:
        mock_retry_store.get_due_retries.return_value = [
            {
                "id": "retry-1",
                "shipment_id": "missing-ship",
                "payload": {},
                "headers": {},
                "attempts": 0,
            },
        ]
        mock_repository.get_by_id.side_effect = KeyError("missing-ship")

        result = await process_due_retries(
            retry_store=mock_retry_store,
            repository=mock_repository,
            config=config,
        )
        assert result == 1
        mock_retry_store.mark_exhausted.assert_awaited_once_with("retry-1")

    async def test_max_attempts_exceeded_marks_exhausted(
        self, mock_retry_store, mock_repository, config
    ) -> None:
        mock_retry_store.get_due_retries.return_value = [
            {
                "id": "retry-1",
                "shipment_id": "ship-1",
                "payload": {"event": "x"},
                "headers": {},
                "attempts": 5,  # equals max_attempts
            },
        ]

        from tests.conftest import DemoShipment, DemoOrder

        shipment = DemoShipment(
            id="ship-1",
            order=DemoOrder(id="o-1"),
            status="label_ready",
            provider="dummy",
        )
        mock_repository.get_by_id.return_value = shipment

        # The flow.handle_callback will fail since no provider is registered,
        # but since attempts >= max, it should mark_exhausted
        result = await process_due_retries(
            retry_store=mock_retry_store,
            repository=mock_repository,
            config=config,
        )
        assert result == 1
        mock_retry_store.mark_exhausted.assert_awaited_once_with("retry-1")

    async def test_failed_retry_under_limit_marks_failed(
        self, mock_retry_store, mock_repository, config
    ) -> None:
        mock_retry_store.get_due_retries.return_value = [
            {
                "id": "retry-1",
                "shipment_id": "ship-1",
                "payload": {"event": "x"},
                "headers": {},
                "attempts": 2,  # under max_attempts (5)
            },
        ]

        from tests.conftest import DemoShipment, DemoOrder

        shipment = DemoShipment(
            id="ship-1",
            order=DemoOrder(id="o-1"),
            status="label_ready",
            provider="dummy",
        )
        mock_repository.get_by_id.return_value = shipment

        # flow.handle_callback will raise since no provider registered
        result = await process_due_retries(
            retry_store=mock_retry_store,
            repository=mock_repository,
            config=config,
        )
        assert result == 1
        mock_retry_store.mark_failed.assert_awaited_once()
        call_args = mock_retry_store.mark_failed.call_args
        assert call_args[0][0] == "retry-1"  # retry_id
        assert isinstance(call_args[1]["error"], str)  # error message
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_retry.py -v`
Expected: FAIL — `ImportError: cannot import name 'compute_next_retry_at'` and `'process_due_retries'`

**Step 3: Write the implementation**

Replace `src/fastapi_sendparcel/retry.py`:

```python
"""Webhook retry mechanism with exponential backoff."""

import logging
from datetime import UTC, datetime, timedelta

from sendparcel.flow import ShipmentFlow
from sendparcel.protocols import ShipmentRepository

from fastapi_sendparcel.config import SendparcelConfig
from fastapi_sendparcel.protocols import CallbackRetryStore

logger = logging.getLogger(__name__)


def compute_next_retry_at(
    attempt: int,
    backoff_seconds: int,
) -> datetime:
    """Compute the next retry time with exponential backoff.

    delay = backoff_seconds * 2^(attempt - 1)
    """
    delay = backoff_seconds * (2 ** (attempt - 1))
    return datetime.now(tz=UTC) + timedelta(seconds=delay)


async def process_due_retries(
    *,
    retry_store: CallbackRetryStore,
    repository: ShipmentRepository,
    config: SendparcelConfig,
) -> int:
    """Process all due callback retries.

    Returns the number of retries processed.
    """
    retries = await retry_store.get_due_retries(limit=10)
    processed = 0

    for retry in retries:
        retry_id = retry["id"]
        shipment_id = retry["shipment_id"]
        payload = retry["payload"]
        headers = retry["headers"]
        attempts = retry["attempts"]

        try:
            shipment = await repository.get_by_id(shipment_id)
        except KeyError:
            logger.error(
                "Retry %s: shipment %s not found, marking exhausted",
                retry_id,
                shipment_id,
            )
            await retry_store.mark_exhausted(retry_id)
            processed += 1
            continue

        flow = ShipmentFlow(
            repository=repository,
            config=config.providers,
        )
        raw_body = payload.get("_raw_body")
        callback_kwargs = (
            {"raw_body": raw_body.encode("utf-8")}
            if raw_body is not None
            else {}
        )

        try:
            await flow.handle_callback(
                shipment=shipment,
                data=payload,
                headers=headers,
                **callback_kwargs,
            )
            await retry_store.mark_succeeded(retry_id)
            logger.info(
                "Retry %s: callback for shipment %s succeeded",
                retry_id,
                shipment_id,
            )
        except Exception as exc:
            if attempts >= config.retry_max_attempts:
                await retry_store.mark_exhausted(retry_id)
                logger.warning(
                    "Retry %s: exhausted after %d attempts: %s",
                    retry_id,
                    attempts,
                    exc,
                )
            else:
                await retry_store.mark_failed(
                    retry_id,
                    error=str(exc),
                )
                logger.info(
                    "Retry %s: attempt %d failed: %s",
                    retry_id,
                    attempts,
                    exc,
                )

        processed += 1

    return processed
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_retry.py -v`
Expected: All tests PASS

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/fastapi_sendparcel/retry.py tests/test_retry.py
git commit -m "feat: implement exponential backoff retry processing"
```

---

## Task 9: Expand SendparcelConfig

**Files:**
- Modify: `src/fastapi_sendparcel/config.py`
- Test: `tests/test_config.py`

**Step 1: Write the failing test**

Create `tests/test_config.py`:

```python
"""Configuration tests."""

import os

from fastapi_sendparcel.config import SendparcelConfig


def test_default_retry_settings() -> None:
    config = SendparcelConfig(default_provider="dummy")
    assert config.retry_max_attempts == 5
    assert config.retry_backoff_seconds == 60
    assert config.retry_enabled is True


def test_env_prefix(monkeypatch) -> None:
    monkeypatch.setenv("SENDPARCEL_DEFAULT_PROVIDER", "inpost")
    monkeypatch.setenv("SENDPARCEL_RETRY_MAX_ATTEMPTS", "10")
    monkeypatch.setenv("SENDPARCEL_RETRY_ENABLED", "false")

    config = SendparcelConfig()
    assert config.default_provider == "inpost"
    assert config.retry_max_attempts == 10
    assert config.retry_enabled is False


def test_providers_default_empty() -> None:
    config = SendparcelConfig(default_provider="dummy")
    assert config.providers == {}


def test_custom_retry_settings() -> None:
    config = SendparcelConfig(
        default_provider="dummy",
        retry_max_attempts=3,
        retry_backoff_seconds=30,
        retry_enabled=False,
    )
    assert config.retry_max_attempts == 3
    assert config.retry_backoff_seconds == 30
    assert config.retry_enabled is False
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `retry_max_attempts` etc. don't exist on SendparcelConfig, no env prefix

**Step 3: Write the implementation**

Replace `src/fastapi_sendparcel/config.py`:

```python
"""FastAPI adapter configuration."""

from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SendparcelConfig(BaseSettings):
    """Runtime config for FastAPI adapter.

    Reads from environment variables with SENDPARCEL_ prefix.
    """

    model_config = SettingsConfigDict(env_prefix="SENDPARCEL_")

    default_provider: str
    providers: dict[str, dict[str, Any]] = Field(default_factory=dict)

    # Retry settings
    retry_max_attempts: int = 5
    retry_backoff_seconds: int = 60
    retry_enabled: bool = True
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: All 4 tests PASS

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/fastapi_sendparcel/config.py tests/test_config.py
git commit -m "feat: add retry settings and env prefix to SendparcelConfig"
```

---

## Task 10: Fix CallbackRetryModel

**Files:**
- Modify: `src/fastapi_sendparcel/contrib/sqlalchemy/models.py`
- Test: `tests/test_contrib_sqlalchemy_models.py`

**Step 1: Write the failing test**

Create `tests/test_contrib_sqlalchemy_models.py`:

```python
"""SQLAlchemy model tests with real aiosqlite DB."""

import uuid

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

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
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_contrib_sqlalchemy_models.py -v`
Expected: FAIL — CallbackRetryModel missing columns (shipment_id, headers, attempts, etc.)

**Step 3: Write the implementation**

Replace `src/fastapi_sendparcel/contrib/sqlalchemy/models.py`:

```python
"""SQLAlchemy shipment/retry models."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""


class ShipmentModel(Base):
    """Minimal shipment persistence model."""

    __tablename__ = "sendparcel_shipments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default="new")
    provider: Mapped[str] = mapped_column(String(64))
    external_id: Mapped[str] = mapped_column(String(128), default="")
    tracking_number: Mapped[str] = mapped_column(String(128), default="")
    label_url: Mapped[str] = mapped_column(String(512), default="")


class CallbackRetryModel(Base):
    """Webhook callback retry queue entry."""

    __tablename__ = "sendparcel_callback_retries"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    shipment_id: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    headers: Mapped[dict] = mapped_column(JSON)
    attempts: Mapped[int] = mapped_column(default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    last_error: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=UTC),
    )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_contrib_sqlalchemy_models.py -v`
Expected: All 4 tests PASS

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/fastapi_sendparcel/contrib/sqlalchemy/models.py tests/test_contrib_sqlalchemy_models.py
git commit -m "fix: expand CallbackRetryModel with full retry lifecycle fields"
```

---

## Task 11: Fix SQLAlchemyRetryStore

**Files:**
- Modify: `src/fastapi_sendparcel/contrib/sqlalchemy/retry_store.py`
- Test: `tests/test_contrib_sqlalchemy_retry_store.py`

**Step 1: Write the failing test**

Create `tests/test_contrib_sqlalchemy_retry_store.py`:

```python
"""SQLAlchemy retry store integration tests with real aiosqlite DB."""

from datetime import UTC, datetime, timedelta

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
        payload={"event": "test"},
        headers={"x-token": "ok"},
    )
    assert isinstance(retry_id, str)
    assert len(retry_id) == 36  # UUID


async def test_get_due_retries_returns_pending(retry_store) -> None:
    await retry_store.store_failed_callback(
        shipment_id="ship-1",
        payload={"event": "test"},
        headers={},
    )

    retries = await retry_store.get_due_retries(limit=10)
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
        payload={},
        headers={},
    )

    retries = await store.get_due_retries(limit=10)
    assert len(retries) == 0


async def test_mark_succeeded(retry_store) -> None:
    retry_id = await retry_store.store_failed_callback(
        shipment_id="ship-1",
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
        payload={},
        headers={},
    )
    await retry_store.mark_exhausted(retry_id)

    retries = await retry_store.get_due_retries(limit=10)
    assert len(retries) == 0


async def test_full_lifecycle(retry_store) -> None:
    """Test store → get_due → mark_failed → mark_succeeded lifecycle."""
    retry_id = await retry_store.store_failed_callback(
        shipment_id="ship-1",
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
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_contrib_sqlalchemy_retry_store.py -v`
Expected: FAIL — `SQLAlchemyRetryStore` only has `enqueue` method, missing `store_failed_callback`, `get_due_retries`, etc.

**Step 3: Write the implementation**

Replace `src/fastapi_sendparcel/contrib/sqlalchemy/retry_store.py`:

```python
"""SQLAlchemy-backed retry store for webhook callbacks."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fastapi_sendparcel.contrib.sqlalchemy.models import CallbackRetryModel
from fastapi_sendparcel.retry import compute_next_retry_at


class SQLAlchemyRetryStore:
    """Callback retry store backed by SQLAlchemy.

    Implements the CallbackRetryStore protocol.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        backoff_seconds: int = 60,
    ) -> None:
        self._session_factory = session_factory
        self._backoff_seconds = backoff_seconds

    async def store_failed_callback(
        self,
        shipment_id: str,
        payload: dict,
        headers: dict,
    ) -> str:
        """Store a failed callback for later retry."""
        async with self._session_factory() as session:
            retry = CallbackRetryModel(
                shipment_id=shipment_id,
                payload=payload,
                headers=headers,
                attempts=0,
                next_retry_at=compute_next_retry_at(
                    attempt=1,
                    backoff_seconds=self._backoff_seconds,
                ),
                status="pending",
            )
            session.add(retry)
            await session.commit()
            await session.refresh(retry)
            return retry.id

    async def get_due_retries(self, limit: int = 10) -> list[dict]:
        """Get retries that are due for processing."""
        now = datetime.now(tz=UTC)
        async with self._session_factory() as session:
            stmt = (
                select(CallbackRetryModel)
                .where(CallbackRetryModel.status == "pending")
                .where(CallbackRetryModel.next_retry_at <= now)
                .limit(limit)
            )
            result = await session.execute(stmt)
            retries = result.scalars().all()
            return [
                {
                    "id": r.id,
                    "shipment_id": r.shipment_id,
                    "payload": r.payload,
                    "headers": r.headers,
                    "attempts": r.attempts,
                }
                for r in retries
            ]

    async def mark_succeeded(self, retry_id: str) -> None:
        """Mark a retry as successfully processed."""
        async with self._session_factory() as session:
            retry = await session.get(CallbackRetryModel, retry_id)
            if retry is not None:
                retry.status = "succeeded"
                await session.commit()

    async def mark_failed(self, retry_id: str, error: str) -> None:
        """Mark a retry as failed and schedule next attempt."""
        async with self._session_factory() as session:
            retry = await session.get(CallbackRetryModel, retry_id)
            if retry is not None:
                retry.attempts += 1
                retry.last_error = error
                retry.next_retry_at = compute_next_retry_at(
                    attempt=retry.attempts + 1,
                    backoff_seconds=self._backoff_seconds,
                )
                retry.status = "pending"
                await session.commit()

    async def mark_exhausted(self, retry_id: str) -> None:
        """Mark a retry as exhausted (dead letter)."""
        async with self._session_factory() as session:
            retry = await session.get(CallbackRetryModel, retry_id)
            if retry is not None:
                retry.status = "exhausted"
                await session.commit()
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_contrib_sqlalchemy_retry_store.py -v`
Expected: All 7 tests PASS

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/fastapi_sendparcel/contrib/sqlalchemy/retry_store.py tests/test_contrib_sqlalchemy_retry_store.py
git commit -m "feat: implement full 5-method SQLAlchemy retry store"
```

---

## Task 12: Add timestamps and order_id to ShipmentModel

**Files:**
- Modify: `src/fastapi_sendparcel/contrib/sqlalchemy/models.py`
- Modify: `tests/test_contrib_sqlalchemy_models.py`

**Step 1: Write the failing test**

Append to `tests/test_contrib_sqlalchemy_models.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_contrib_sqlalchemy_models.py -v`
Expected: FAIL — ShipmentModel missing `created_at`, `updated_at`, `order_id`

**Step 3: Write the implementation**

Modify `src/fastapi_sendparcel/contrib/sqlalchemy/models.py` — update the `ShipmentModel` class to add the new fields:

```python
class ShipmentModel(Base):
    """Minimal shipment persistence model."""

    __tablename__ = "sendparcel_shipments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    order_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    status: Mapped[str] = mapped_column(String(32), default="new")
    provider: Mapped[str] = mapped_column(String(64))
    external_id: Mapped[str] = mapped_column(String(128), default="")
    tracking_number: Mapped[str] = mapped_column(String(128), default="")
    label_url: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=UTC),
        onupdate=lambda: datetime.now(tz=UTC),
    )
```

Note: The `DateTime` import is already at the top of the file from the CallbackRetryModel changes in Task 10.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_contrib_sqlalchemy_models.py -v`
Expected: All 7 tests PASS

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/fastapi_sendparcel/contrib/sqlalchemy/models.py tests/test_contrib_sqlalchemy_models.py
git commit -m "feat: add timestamps and order_id to ShipmentModel"
```

---

## Task 13: Add list_by_order to repository

**Files:**
- Modify: `src/fastapi_sendparcel/contrib/sqlalchemy/repository.py`
- Test: `tests/test_contrib_sqlalchemy_repository.py`

**Step 1: Write the failing test**

Create `tests/test_contrib_sqlalchemy_repository.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_contrib_sqlalchemy_repository.py -v`
Expected: FAIL — `SQLAlchemyShipmentRepository` has no `list_by_order` method

**Step 3: Write the implementation**

Modify `src/fastapi_sendparcel/contrib/sqlalchemy/repository.py` — add the import and method:

Add `select` is already imported. Add the `list_by_order` method at the end of the class:

```python
    async def list_by_order(self, order_id: str) -> list[ShipmentModel]:
        """List all shipments for an order."""
        async with self.session_factory() as session:
            stmt = select(ShipmentModel).where(
                ShipmentModel.order_id == order_id
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
```

Also update the `create` method to accept `order_id`:

Replace the `create` method body:
```python
    async def create(self, **kwargs) -> ShipmentModel:
        order = kwargs.pop("order", None)
        if order is not None and "order_id" not in kwargs:
            kwargs["order_id"] = str(getattr(order, "id", order))
        shipment = ShipmentModel(
            id=kwargs.get("id", ""),
            status=str(kwargs.get("status", "new")),
            provider=kwargs["provider"],
            order_id=kwargs.get("order_id", ""),
        )
        async with self.session_factory() as session:
            session.add(shipment)
            await session.commit()
            await session.refresh(shipment)
        return shipment
```

The full updated `src/fastapi_sendparcel/contrib/sqlalchemy/repository.py`:

```python
"""SQLAlchemy repository implementation."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fastapi_sendparcel.contrib.sqlalchemy.models import ShipmentModel


class SQLAlchemyShipmentRepository:
    """Shipment repository backed by SQLAlchemy async sessions."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        self.session_factory = session_factory

    async def get_by_id(self, shipment_id: str) -> ShipmentModel:
        async with self.session_factory() as session:
            result = await session.execute(
                select(ShipmentModel).where(
                    ShipmentModel.id == shipment_id
                )
            )
            shipment = result.scalar_one()
            return shipment

    async def create(self, **kwargs) -> ShipmentModel:
        order = kwargs.pop("order", None)
        if order is not None and "order_id" not in kwargs:
            kwargs["order_id"] = str(getattr(order, "id", order))
        shipment = ShipmentModel(
            id=kwargs.get("id", ""),
            status=str(kwargs.get("status", "new")),
            provider=kwargs["provider"],
            order_id=kwargs.get("order_id", ""),
        )
        async with self.session_factory() as session:
            session.add(shipment)
            await session.commit()
            await session.refresh(shipment)
        return shipment

    async def save(self, shipment: ShipmentModel) -> ShipmentModel:
        async with self.session_factory() as session:
            merged = await session.merge(shipment)
            await session.commit()
            await session.refresh(merged)
            return merged

    async def update_status(
        self, shipment_id: str, status: str, **fields
    ) -> ShipmentModel:
        async with self.session_factory() as session:
            shipment = await session.get(ShipmentModel, shipment_id)
            if shipment is None:
                raise KeyError(shipment_id)
            shipment.status = status
            for key, value in fields.items():
                if hasattr(shipment, key):
                    setattr(shipment, key, value)
            await session.commit()
            await session.refresh(shipment)
            return shipment

    async def list_by_order(self, order_id: str) -> list[ShipmentModel]:
        """List all shipments for an order."""
        async with self.session_factory() as session:
            stmt = select(ShipmentModel).where(
                ShipmentModel.order_id == order_id
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_contrib_sqlalchemy_repository.py -v`
Expected: All 3 tests PASS

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/fastapi_sendparcel/contrib/sqlalchemy/repository.py tests/test_contrib_sqlalchemy_repository.py
git commit -m "feat: add list_by_order to SQLAlchemy repository"
```

---

## Task 14: Update __all__ public API and final cleanup

**Files:**
- Verify: `src/fastapi_sendparcel/__init__.py`
- Modify: `tests/test_package_metadata.py`

**Step 1: Write the verification test**

The `__all__` was already set in Task 5. Verify the full suite passes with the final state:

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

**Step 2: Run ruff to verify code quality**

Run: `uv run ruff check src/ tests/`
Expected: No errors

Run: `uv run ruff format --check src/ tests/`
Expected: No formatting issues

**Step 3: Fix any ruff issues if present**

Run: `uv run ruff check src/ tests/ --fix`
Run: `uv run ruff format src/ tests/`

**Step 4: Final full test run**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

**Step 5: Commit (only if fixes were needed)**

```bash
git add -A
git commit -m "chore: fix linting issues from ruff"
```

---

## Summary of Changes

| Task | What | Files |
|------|------|-------|
| 1 | Exception handlers | `exceptions.py` (new), `test_exceptions.py` (new) |
| 2 | Wire handlers in lifespan | `router.py`, `test_router.py` |
| 3 | Fix callback retry logic | `routes/callbacks.py`, `conftest.py`, `test_routes_flow.py` |
| 4 | __version__ + py.typed | `__init__.py`, `py.typed` (new), `test_package_metadata.py` (new) |
| 5 | Lazy imports | `__init__.py`, `test_package_metadata.py` |
| 6 | routes/__init__.py | `routes/__init__.py` (new) |
| 7 | 5-method retry protocol | `protocols.py`, `test_protocols.py` (new) |
| 8 | Exponential backoff | `retry.py`, `test_retry.py` (new) |
| 9 | Config expansion | `config.py`, `test_config.py` (new) |
| 10 | Full CallbackRetryModel | `contrib/sqlalchemy/models.py`, `test_contrib_sqlalchemy_models.py` (new) |
| 11 | Full SQLAlchemyRetryStore | `contrib/sqlalchemy/retry_store.py`, `test_contrib_sqlalchemy_retry_store.py` (new) |
| 12 | ShipmentModel timestamps | `contrib/sqlalchemy/models.py`, `test_contrib_sqlalchemy_models.py` |
| 13 | list_by_order method | `contrib/sqlalchemy/repository.py`, `test_contrib_sqlalchemy_repository.py` (new) |
| 14 | Final cleanup | lint fixes |
