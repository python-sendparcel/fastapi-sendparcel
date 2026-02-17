# Configuration

## SendparcelConfig

The `SendparcelConfig` class is a [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) `BaseSettings` subclass. It can be configured via constructor arguments or environment variables.

```python
from fastapi_sendparcel import SendparcelConfig

config = SendparcelConfig(
    default_provider="dummy",
    providers={
        "dummy": {
            "latency_seconds": 0.1,
            "label_base_url": "https://labels.example.com",
        },
    },
)
```

### Settings reference

| Setting | Type | Default | Env var | Description |
|---------|------|---------|---------|-------------|
| `default_provider` | `str` | *(required)* | `DEFAULT_PROVIDER` | Slug of the provider to use when none is specified in the request |
| `providers` | `dict[str, dict]` | `{}` | — | Per-provider configuration dicts, keyed by provider slug |

### Provider configuration

Each provider receives its config dict via `BaseProvider.config`. Access settings with `self.get_setting(name, default)`.

Example for the built-in `DummyProvider`:

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `latency_seconds` | `float` | `0.0` | Simulated latency per API call |
| `label_base_url` | `str` | `https://dummy.local/labels` | Base URL for generated label PDFs |
| `callback_token` | `str` | `dummy-token` | Expected `x-dummy-token` header value for callback verification |
| `status_override` | `str` | *(current status)* | Override status returned by `fetch_shipment_status` |
| `cancel_success` | `bool` | `True` | Whether `cancel_shipment` succeeds |

## create_shipping_router

The router factory accepts these arguments:

```python
from fastapi_sendparcel import create_shipping_router

router = create_shipping_router(
    config=config,                    # SendparcelConfig (required)
    repository=repository,            # ShipmentRepository (required)
    registry=plugin_registry,         # FastAPIPluginRegistry (optional)
    retry_store=retry_store,          # CallbackRetryStore (optional)
)
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `config` | `SendparcelConfig` | Yes | Runtime configuration |
| `repository` | `ShipmentRepository` | Yes | Persistence backend for shipments |
| `registry` | `FastAPIPluginRegistry` | No | Plugin registry; auto-created if not provided |
| `retry_store` | `CallbackRetryStore` | No | Stores failed callbacks for retry |

## Protocols

### CallbackRetryStore

Optional, for persisting failed provider callbacks:

```python
class YourStore:
    async def enqueue(self, payload: dict) -> None: ...
```

## SQLAlchemy integration

The `fastapi_sendparcel.contrib.sqlalchemy` module provides ready-to-use implementations:

```python
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from fastapi_sendparcel.contrib.sqlalchemy.models import (
    Base,
    ShipmentModel,
)
from fastapi_sendparcel.contrib.sqlalchemy.repository import (
    SQLAlchemyShipmentRepository,
)
from fastapi_sendparcel.contrib.sqlalchemy.retry_store import (
    SQLAlchemyRetryStore,
)

engine = create_async_engine("sqlite+aiosqlite:///./app.db")
session_factory = async_sessionmaker(engine, class_=AsyncSession)

repository = SQLAlchemyShipmentRepository(session_factory)
retry_store = SQLAlchemyRetryStore(session_factory)

# Create tables
async with engine.begin() as conn:
    await conn.run_sync(Base.metadata.create_all)
```

Tables created:

| Table | Model | Description |
|-------|-------|-------------|
| `sendparcel_shipments` | `ShipmentModel` | Shipment records with status, tracking, provider info |
| `sendparcel_callback_retries` | `CallbackRetryModel` | Failed callback payloads for retry |
