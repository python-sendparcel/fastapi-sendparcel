# fastapi-sendparcel

[![PyPI](https://img.shields.io/pypi/v/fastapi-sendparcel.svg)](https://pypi.org/project/fastapi-sendparcel/)
[![Python Version](https://img.shields.io/pypi/pyversions/fastapi-sendparcel.svg)](https://pypi.org/project/fastapi-sendparcel/)
[![License](https://img.shields.io/pypi/l/fastapi-sendparcel.svg)](https://github.com/python-sendparcel/fastapi-sendparcel/blob/main/LICENSE)
[![Documentation](https://readthedocs.org/projects/fastapi-sendparcel/badge/?version=latest)](https://fastapi-sendparcel.readthedocs.io/)

**FastAPI adapter for the [python-sendparcel](https://github.com/python-sendparcel/python-sendparcel) shipping ecosystem.**

> **Alpha notice** — This package is at version **0.1.0** and its API is not yet
> stable. Breaking changes may occur in minor releases until 1.0.

---

## Features

- **Router factory** — single call to `create_shipping_router()` gives you a
  fully-configured `APIRouter` with shipment, label, status and callback
  endpoints.
- **Provider-agnostic** — plug in any shipping provider that implements the
  `python-sendparcel` provider protocol.
- **Plugin registry** — `FastAPIPluginRegistry` discovers and manages
  provider plugins with optional per-provider routers.
- **Pydantic-native configuration** — `SendparcelConfig` reads from
  environment variables with the `SENDPARCEL_` prefix.
- **Webhook callback handling** — built-in endpoint for provider status
  callbacks with automatic retry queue support.
- **SQLAlchemy contrib** — optional `[sqlalchemy]` extra provides
  `SQLAlchemyShipmentRepository`, `SQLAlchemyRetryStore`, and ready-made
  database models.
- **Exception mapping** — core `sendparcel` exceptions are automatically
  converted to appropriate HTTP status codes (400, 404, 409, 502).
- **Async-first** — fully asynchronous with `async`/`await` throughout.

## Installation

Install the base package:

```bash
pip install fastapi-sendparcel
```

If you want SQLAlchemy-backed persistence (recommended):

```bash
pip install fastapi-sendparcel[sqlalchemy]
```

> **Note:** The project uses [uv](https://docs.astral.sh/uv/) for development.
> If you are contributing, run `uv sync` instead.

## Quick Start

Below is a minimal but complete FastAPI application that wires up the shipping
router with SQLAlchemy persistence.

```python
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from fastapi_sendparcel import (
    SendparcelConfig,
    FastAPIPluginRegistry,
    create_shipping_router,
)
from fastapi_sendparcel.contrib.sqlalchemy.models import Base
from fastapi_sendparcel.contrib.sqlalchemy.repository import (
    SQLAlchemyShipmentRepository,
)
from fastapi_sendparcel.contrib.sqlalchemy.retry_store import (
    SQLAlchemyRetryStore,
)

# --- Database ---
engine = create_async_engine("sqlite+aiosqlite:///./shipments.db")
async_session = async_sessionmaker(engine, class_=AsyncSession)

# --- Sendparcel setup ---
config = SendparcelConfig(
    default_provider="my-provider",
    providers={
        "my-provider": {
            "api_key": "...",
        },
    },
)

repository = SQLAlchemyShipmentRepository(async_session)
retry_store = SQLAlchemyRetryStore(async_session)
registry = FastAPIPluginRegistry()

shipping_router = create_shipping_router(
    config=config,
    repository=repository,
    registry=registry,
    retry_store=retry_store,
)

# --- App ---
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(title="My Shipping App", lifespan=lifespan)
app.include_router(shipping_router, prefix="/api/shipping")
```

The `create_shipping_router` function accepts all its arguments as
keyword-only parameters:

| Parameter | Type | Required | Description |
|---|---|---|---|
| `config` | `SendparcelConfig` | Yes | Adapter configuration instance |
| `repository` | `ShipmentRepository` | Yes | Persistence backend for shipments |
| `registry` | `FastAPIPluginRegistry` | No | Plugin registry (auto-created if omitted) |
| `order_resolver` | `OrderResolver` | No | Maps order IDs to `Order` objects |
| `retry_store` | `CallbackRetryStore` | No | Storage for webhook retry queue |

## Configuration

`SendparcelConfig` extends Pydantic's `BaseSettings` and reads environment
variables with the `SENDPARCEL_` prefix.

| Setting | Env variable | Type | Default | Description |
|---|---|---|---|---|
| `default_provider` | `SENDPARCEL_DEFAULT_PROVIDER` | `str` | *(required)* | Slug of the default shipping provider |
| `providers` | `SENDPARCEL_PROVIDERS` | `dict[str, dict]` | `{}` | Per-provider configuration dicts |
| `retry_max_attempts` | `SENDPARCEL_RETRY_MAX_ATTEMPTS` | `int` | `5` | Max retry attempts for failed callbacks |
| `retry_backoff_seconds` | `SENDPARCEL_RETRY_BACKOFF_SECONDS` | `int` | `60` | Base backoff interval between retries |
| `retry_enabled` | `SENDPARCEL_RETRY_ENABLED` | `bool` | `True` | Enable/disable callback retry queue |

You can instantiate the config directly or let it read from the environment:

```python
# Explicit values
config = SendparcelConfig(
    default_provider="inpost",
    providers={"inpost": {"api_key": "secret"}},
)

# From environment variables
# (set SENDPARCEL_DEFAULT_PROVIDER=inpost, etc.)
config = SendparcelConfig()
```

## API Endpoints

The router created by `create_shipping_router()` exposes the following
endpoints. All paths are relative to the prefix you mount the router at
(e.g. `/api/shipping`).

| Method | Path | Description |
|---|---|---|
| `GET` | `/shipments/health` | Healthcheck — returns `{"status": "ok"}` |
| `POST` | `/shipments` | Create a new shipment from an order |
| `POST` | `/shipments/{shipment_id}/label` | Generate a shipping label |
| `GET` | `/shipments/{shipment_id}/status` | Fetch and update shipment status from the provider |
| `POST` | `/callbacks/{provider_slug}/{shipment_id}` | Handle a provider webhook callback |

### Request and Response Schemas

**`POST /shipments`** — request body:

```json
{
  "order_id": "123",
  "provider": "my-provider"
}
```

The `provider` field is optional; when omitted, `default_provider` from the
config is used.

**`ShipmentResponse`** — returned by shipment, label and status endpoints:

```json
{
  "id": "abc-def",
  "status": "label_created",
  "provider": "my-provider",
  "external_id": "EXT123",
  "tracking_number": "TRACK456",
  "label_url": "https://..."
}
```

**`CallbackResponse`** — returned by the callback endpoint:

```json
{
  "provider": "my-provider",
  "status": "accepted",
  "shipment_status": "in_transit"
}
```

### Exception Handling

The router automatically registers exception handlers that map core
`sendparcel` exceptions to HTTP responses:

| Exception | HTTP Status | Code |
|---|---|---|
| `ShipmentNotFoundError` | 404 | `not_found` |
| `InvalidCallbackError` | 400 | `invalid_callback` |
| `InvalidTransitionError` | 409 | `invalid_transition` |
| `CommunicationError` | 502 | `communication_error` |
| `SendParcelException` | 400 | `shipment_error` |

## Protocols

The adapter defines two protocols you can implement:

### `OrderResolver`

Resolves order IDs (strings from the API request) to `Order` objects
understood by the core library.

```python
from fastapi_sendparcel import OrderResolver
from sendparcel.protocols import Order


class MyOrderResolver:
    async def resolve(self, order_id: str) -> Order:
        # Load from your database, ORM, etc.
        ...
```

### `CallbackRetryStore`

Stores failed webhook callbacks for retry processing. The SQLAlchemy contrib
provides a ready-made implementation (`SQLAlchemyRetryStore`), but you can
implement this protocol with any backend (Redis, DynamoDB, etc.).

```python
from fastapi_sendparcel import CallbackRetryStore


class MyRetryStore:
    async def store_failed_callback(
        self, shipment_id: str, payload: dict, headers: dict
    ) -> str: ...

    async def get_due_retries(self, limit: int = 10) -> list[dict]: ...

    async def mark_succeeded(self, retry_id: str) -> None: ...

    async def mark_failed(self, retry_id: str, error: str) -> None: ...

    async def mark_exhausted(self, retry_id: str) -> None: ...
```

## SQLAlchemy Contrib

The optional `[sqlalchemy]` extra provides production-ready persistence
components:

- **`ShipmentModel`** — SQLAlchemy model mapped to the
  `sendparcel_shipments` table.
- **`CallbackRetryModel`** — SQLAlchemy model mapped to the
  `sendparcel_callback_retries` table.
- **`SQLAlchemyShipmentRepository`** — async repository implementing the
  `ShipmentRepository` protocol.
- **`SQLAlchemyRetryStore`** — async retry store implementing the
  `CallbackRetryStore` protocol.

Both require an `async_sessionmaker[AsyncSession]` at construction time:

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fastapi_sendparcel.contrib.sqlalchemy.repository import (
    SQLAlchemyShipmentRepository,
)
from fastapi_sendparcel.contrib.sqlalchemy.retry_store import (
    SQLAlchemyRetryStore,
)

session_factory = async_sessionmaker(engine, class_=AsyncSession)

repository = SQLAlchemyShipmentRepository(session_factory)
retry_store = SQLAlchemyRetryStore(session_factory, backoff_seconds=60)
```

## Example Project

The `example/` directory contains a full demo application with:

- Tabler-based UI with Jinja2 templates and HTMX
- Order management (create, list, detail views)
- Shipment creation and label generation
- A simulated delivery provider (`delivery_sim.py`)

### Running the example

```bash
cd example
uv sync
uv run uvicorn app:app --reload
```

Then open http://localhost:8000 in your browser.

## Supported Versions

| Dependency | Version |
|---|---|
| Python | >= 3.12 |
| FastAPI | >= 0.115.0 |
| Pydantic Settings | >= 2.0.0 |
| python-sendparcel | >= 0.1.0 |
| SQLAlchemy (optional) | >= 2.0.0 |

## Running Tests

```bash
uv sync --all-extras
uv run pytest
```

The test suite uses `pytest` with `pytest-asyncio` in auto mode.
Configuration is in `pyproject.toml`.

## Credits

Created and maintained by [Dominik Kozaczko](mailto:dominik@kozaczko.info).

This project is the FastAPI adapter for the
[python-sendparcel](https://github.com/python-sendparcel/python-sendparcel)
ecosystem.

## License

[MIT](https://github.com/python-sendparcel/fastapi-sendparcel/blob/main/LICENSE)
