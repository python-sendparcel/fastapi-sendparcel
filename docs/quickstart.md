# Quickstart

## Installation

Install `fastapi-sendparcel` with your preferred package manager:

::::{tab-set}

:::{tab-item} uv
```bash
uv add fastapi-sendparcel
```
:::

:::{tab-item} pip
```bash
pip install fastapi-sendparcel
```
:::

::::

For SQLAlchemy support (recommended):

```bash
uv add "fastapi-sendparcel[sqlalchemy]"
```

## Minimal example

```python
from fastapi import FastAPI
from fastapi_sendparcel import (
    SendparcelConfig,
    create_shipping_router,
)
from fastapi_sendparcel.contrib.sqlalchemy.models import Base
from fastapi_sendparcel.contrib.sqlalchemy.repository import (
    SQLAlchemyShipmentRepository,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

engine = create_async_engine("sqlite+aiosqlite:///./shipments.db")
async_session = async_sessionmaker(engine, class_=AsyncSession)
repository = SQLAlchemyShipmentRepository(async_session)

config = SendparcelConfig(
    default_provider="dummy",
    providers={},
)

shipping_router = create_shipping_router(
    config=config,
    repository=repository,
)

app = FastAPI()
app.include_router(shipping_router, prefix="/api/shipping")
```

This gives you:

- `POST /api/shipping/shipments` — create a shipment
- `POST /api/shipping/shipments/{id}/label` — generate a label
- `GET /api/shipping/shipments/{id}/status` — fetch shipment status
- `POST /api/shipping/callbacks/{provider}/{shipment_id}` — receive provider callbacks
- `GET /api/shipping/shipments/health` — healthcheck

## Running the example app

A full working example with a web UI is included in the `example/` directory:

```bash
cd example
uv sync
uv run uvicorn app:app --reload
```

Open [http://localhost:8000](http://localhost:8000) to see the demo with:

- Order creation and management
- Shipment creation via a simulated delivery provider
- Real-time status tracking with delivery simulation
- Tabler UI with HTMX interactions

## Next steps

- {doc}`configuration` — full settings reference
- {doc}`api` — API module documentation
