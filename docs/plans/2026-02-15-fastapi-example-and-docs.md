# Example App Rewrite + Documentation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the monolithic 428-line inline-HTML example app with a clean, Jinja2-templated Tabler+HTMX demo featuring a simulated delivery provider with HTTP callbacks, backed by SQLAlchemy/aiosqlite; then add Sphinx documentation with quickstart, configuration reference, and API autodoc.

**Architecture:** The example app is restructured into separate modules — `models.py` (SQLAlchemy order model implementing the `Order` protocol via `AddressInfo`/`ParcelInfo` TypedDicts), `delivery_sim.py` (a fake delivery provider that exposes its own FastAPI routes and sends HTTP callbacks back to the main app), and `app.py` (FastAPI app composing the library's `create_shipping_router` with Jinja2 template views). Templates use Tabler CSS from CDN + HTMX for dynamic interactions. Sphinx docs live in `docs/` at the package root and are built with furo+myst-parser for `.md` source files.

**Tech Stack:** Python 3.12+, FastAPI, Jinja2, SQLAlchemy (async + aiosqlite), HTMX, Tabler CSS, Sphinx (furo + myst-parser + autodoc)

---

## Prerequisite Assumptions

- The critical-fixes and testing plans have already been executed.
- The library's `create_shipping_router`, `SendparcelConfig`, `FastAPIPluginRegistry`, `SQLAlchemyShipmentRepository`, `SQLAlchemyRetryStore`, `ShipmentModel`, `CallbackRetryModel`, and `Base` from `contrib.sqlalchemy` all work as currently implemented.
- The `sendparcel` core protocols (`Order`, `Shipment`, `ShipmentRepository`), `BaseProvider`, `ShipmentFlow`, `DummyProvider`, `ShipmentStatus`, FSM callbacks, and `PluginRegistry` all work as currently implemented.
- `uv` is the dependency manager (lockfile: `uv.lock`).

## Key Codebase References

| What | Where |
|---|---|
| Core `Order` protocol | `python-sendparcel/src/sendparcel/protocols.py:10-16` |
| `AddressInfo` / `ParcelInfo` TypedDicts | `python-sendparcel/src/sendparcel/types.py:7-28` |
| `BaseProvider` ABC | `python-sendparcel/src/sendparcel/provider.py:14-55` |
| `ShipmentFlow` orchestrator | `python-sendparcel/src/sendparcel/flow.py:15-131` |
| `ShipmentStatus` enum | `python-sendparcel/src/sendparcel/enums.py:6-17` |
| FSM transitions & callbacks | `python-sendparcel/src/sendparcel/fsm.py:7-106` |
| `DummyProvider` reference impl | `python-sendparcel/src/sendparcel/providers/dummy.py:17-77` |
| `create_shipping_router` factory | `fastapi-sendparcel/src/fastapi_sendparcel/router.py:18-42` |
| `SendparcelConfig` | `fastapi-sendparcel/src/fastapi_sendparcel/config.py:9-13` |
| `FastAPIPluginRegistry` | `fastapi-sendparcel/src/fastapi_sendparcel/registry.py:6-17` |
| SQLAlchemy `ShipmentModel` + `Base` | `fastapi-sendparcel/src/fastapi_sendparcel/contrib/sqlalchemy/models.py` |
| `SQLAlchemyShipmentRepository` | `fastapi-sendparcel/src/fastapi_sendparcel/contrib/sqlalchemy/repository.py` |
| `SQLAlchemyRetryStore` | `fastapi-sendparcel/src/fastapi_sendparcel/contrib/sqlalchemy/retry_store.py` |
| Shipments route (POST /shipments) | `fastapi-sendparcel/src/fastapi_sendparcel/routes/shipments.py` |
| Callbacks route (POST /callbacks) | `fastapi-sendparcel/src/fastapi_sendparcel/routes/callbacks.py` |
| Dependencies (get_flow, get_repository, etc.) | `fastapi-sendparcel/src/fastapi_sendparcel/dependencies.py` |
| Old example app (to be deleted) | `fastapi-sendparcel/examples/app.py` |
| Old example test (to be rewritten) | `fastapi-sendparcel/tests/test_example_app.py` |

---

## Task 1: Create example project structure with pyproject.toml and README

**Files:**
- Create: `example/pyproject.toml`
- Create: `example/README.md`
- Create: `example/templates/` (empty directory, created by writing base.html in Task 4)

**Step 1: Create `example/pyproject.toml`**

```toml
[project]
name = "fastapi-sendparcel-example"
version = "0.1.0"
description = "Example app demonstrating fastapi-sendparcel with Tabler + HTMX"
requires-python = ">=3.12"
dependencies = [
    "fastapi-sendparcel",
    "fastapi>=0.115.0",
    "jinja2>=3.1.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "aiosqlite>=0.20.0",
    "uvicorn[standard]>=0.30.0",
    "httpx>=0.27.0",
]

[tool.uv.sources]
fastapi-sendparcel = { path = "..", editable = true }
```

**Step 2: Create `example/README.md`**

```markdown
# fastapi-sendparcel — przykładowa aplikacja

Demonstracja użycia `fastapi-sendparcel` z Tabler UI, HTMX i SQLAlchemy.

## Uruchomienie

```bash
cd example
uv sync
uv run uvicorn app:app --reload
```

Otwórz http://localhost:8000 w przeglądarce.

## Struktura

- `app.py` — główna aplikacja FastAPI z widokami HTML
- `models.py` — model zamówienia (SQLAlchemy) implementujący protokół `Order`
- `delivery_sim.py` — symulator dostawcy przesyłek z endpointami HTTP
- `templates/` — szablony Jinja2 z Tabler CSS i HTMX
```

**Step 3: Commit**

```bash
git add example/pyproject.toml example/README.md
git commit -m "feat(example): scaffold example project with pyproject.toml and README"
```

---

## Task 2: Create SQLAlchemy order model

**Files:**
- Create: `example/models.py`

The `Order` protocol (`sendparcel.protocols.Order`) requires four methods returning specific types:
- `get_total_weight() -> Decimal`
- `get_parcels() -> list[ParcelInfo]` — `ParcelInfo` is `TypedDict(weight_kg, length_cm, width_cm, height_cm)`, all optional
- `get_sender_address() -> AddressInfo` — `AddressInfo` is `TypedDict(name, company, line1, line2, city, state, postal_code, country_code, phone, email)`, all optional
- `get_receiver_address() -> AddressInfo`

The `ShipmentModel` already exists in `fastapi_sendparcel.contrib.sqlalchemy.models` and shares a `Base`. Our `OrderModel` must use the same `Base` so all tables are created together.

**Step 1: Write `example/models.py`**

```python
"""SQLAlchemy models for the example app."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from fastapi_sendparcel.contrib.sqlalchemy.models import Base
from sendparcel.types import AddressInfo, ParcelInfo


class OrderModel(Base):
    """Order stored in SQLite via SQLAlchemy.

    Implements the ``sendparcel.protocols.Order`` protocol.
    """

    __tablename__ = "example_orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    description: Mapped[str] = mapped_column(String(255), default="")
    total_weight: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), default=Decimal("1.0")
    )

    # Sender fields
    sender_name: Mapped[str] = mapped_column(String(128), default="")
    sender_email: Mapped[str] = mapped_column(String(128), default="")
    sender_phone: Mapped[str] = mapped_column(String(32), default="")
    sender_line1: Mapped[str] = mapped_column(String(255), default="")
    sender_city: Mapped[str] = mapped_column(String(128), default="")
    sender_postal_code: Mapped[str] = mapped_column(String(16), default="")
    sender_country_code: Mapped[str] = mapped_column(
        String(2), default="PL"
    )

    # Recipient fields
    recipient_name: Mapped[str] = mapped_column(String(128), default="")
    recipient_email: Mapped[str] = mapped_column(String(128), default="")
    recipient_phone: Mapped[str] = mapped_column(String(32), default="")
    recipient_line1: Mapped[str] = mapped_column(String(255), default="")
    recipient_city: Mapped[str] = mapped_column(String(128), default="")
    recipient_postal_code: Mapped[str] = mapped_column(
        String(16), default=""
    )
    recipient_country_code: Mapped[str] = mapped_column(
        String(2), default="PL"
    )

    def get_total_weight(self) -> Decimal:
        return self.total_weight

    def get_parcels(self) -> list[ParcelInfo]:
        return [ParcelInfo(weight_kg=self.total_weight)]

    def get_sender_address(self) -> AddressInfo:
        return AddressInfo(
            name=self.sender_name,
            email=self.sender_email,
            phone=self.sender_phone,
            line1=self.sender_line1,
            city=self.sender_city,
            postal_code=self.sender_postal_code,
            country_code=self.sender_country_code,
        )

    def get_receiver_address(self) -> AddressInfo:
        return AddressInfo(
            name=self.recipient_name,
            email=self.recipient_email,
            phone=self.recipient_phone,
            line1=self.recipient_line1,
            city=self.recipient_city,
            postal_code=self.recipient_postal_code,
            country_code=self.recipient_country_code,
        )
```

**Step 2: Verify it satisfies the Order protocol**

Run (from `example/` directory):

```bash
uv run python -c "
from sendparcel.protocols import Order
from models import OrderModel
assert issubclass(OrderModel, Order), 'OrderModel does not satisfy Order protocol'
print('OK: OrderModel satisfies Order protocol')
"
```

Expected: `OK: OrderModel satisfies Order protocol`

**Step 3: Commit**

```bash
git add example/models.py
git commit -m "feat(example): add OrderModel implementing Order protocol with AddressInfo/ParcelInfo"
```

---

## Task 3: Create delivery simulator provider

**Files:**
- Create: `example/delivery_sim.py`

This module contains two things:

1. `DeliverySimProvider(BaseProvider)` — a provider that calls the simulator's HTTP endpoints to create shipments, fetch labels, and get status.
2. A FastAPI `APIRouter` with the simulator's own endpoints that the provider calls, plus an "advance" endpoint that progresses the shipment status and sends an HTTP callback back to the main app's callback URL.

The provider stores shipment data in an in-memory dict (the simulator is ephemeral). The provider uses `httpx` to call the simulator endpoints. The simulator endpoints are mounted on the same FastAPI app, so we use `http://localhost:{port}` for self-calls.

Status progression order: `new → created → label_ready → in_transit → out_for_delivery → delivered`.

The callback URL pattern from the library's routes is: `POST /callbacks/{provider_slug}/{shipment_id}`.

**Step 1: Write `example/delivery_sim.py`**

```python
"""Fake delivery provider with HTTP simulator endpoints."""

from __future__ import annotations

from typing import Any, ClassVar
from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sendparcel.provider import BaseProvider
from sendparcel.types import LabelInfo, ShipmentCreateResult, ShipmentStatusResponse

# --- Simulator state (in-memory, ephemeral) ---

STATUS_PROGRESSION = [
    "created",
    "label_ready",
    "in_transit",
    "out_for_delivery",
    "delivered",
]

_sim_shipments: dict[str, dict[str, Any]] = {}

# --- Provider implementation ---


class DeliverySimProvider(BaseProvider):
    """Provider that delegates to the local delivery simulator endpoints."""

    slug: ClassVar[str] = "delivery-sim"
    display_name: ClassVar[str] = "Symulator dostawy"
    supported_countries: ClassVar[list[str]] = ["PL"]
    supported_services: ClassVar[list[str]] = ["standard"]

    def _base_url(self) -> str:
        return self.get_setting(
            "simulator_base_url", "http://localhost:8000"
        )

    async def create_shipment(self, **kwargs: Any) -> ShipmentCreateResult:
        ext_id = f"sim-{uuid4().hex[:8]}"
        tracking = f"SIM-{ext_id.upper()}"
        _sim_shipments[ext_id] = {
            "external_id": ext_id,
            "tracking_number": tracking,
            "status": "created",
            "shipment_id": str(self.shipment.id),
            "label_url": "",
        }
        return ShipmentCreateResult(
            external_id=ext_id,
            tracking_number=tracking,
        )

    async def create_label(self, **kwargs: Any) -> LabelInfo:
        ext_id = self.shipment.external_id
        entry = _sim_shipments.get(ext_id)
        if entry is None:
            return LabelInfo(format="PDF", url="")
        label_url = f"{self._base_url()}/delivery-sim/label/{ext_id}"
        entry["label_url"] = label_url
        return LabelInfo(format="PDF", url=label_url)

    async def verify_callback(
        self, data: dict, headers: dict, **kwargs: Any
    ) -> None:
        pass  # Simulator callbacks are always trusted

    async def handle_callback(
        self, data: dict, headers: dict, **kwargs: Any
    ) -> None:
        status_value = data.get("status")
        if not status_value:
            return
        from sendparcel.fsm import STATUS_TO_CALLBACK

        callback = STATUS_TO_CALLBACK.get(str(status_value), str(status_value))
        trigger = getattr(self.shipment, callback, None)
        may_trigger = getattr(self.shipment, "may_trigger", None)
        if trigger is None or may_trigger is None:
            return
        if may_trigger(callback):
            trigger()

    async def fetch_shipment_status(
        self, **kwargs: Any
    ) -> ShipmentStatusResponse:
        ext_id = self.shipment.external_id
        entry = _sim_shipments.get(ext_id)
        if entry is None:
            return ShipmentStatusResponse(status=self.shipment.status)
        return ShipmentStatusResponse(status=entry["status"])

    async def cancel_shipment(self, **kwargs: Any) -> bool:
        ext_id = self.shipment.external_id
        entry = _sim_shipments.get(ext_id)
        if entry is None:
            return False
        entry["status"] = "cancelled"
        return True


# --- Simulator API endpoints ---

sim_router = APIRouter(prefix="/delivery-sim", tags=["delivery-sim"])


class SimRegisterResponse(BaseModel):
    external_id: str
    tracking_number: str


class SimStatusResponse(BaseModel):
    external_id: str
    status: str


class SimAdvanceResponse(BaseModel):
    external_id: str
    previous_status: str
    new_status: str
    callback_sent: bool


@sim_router.get("/status/{ext_id}", response_model=SimStatusResponse)
async def sim_get_status(ext_id: str) -> SimStatusResponse:
    """Return current status of a simulated shipment."""
    entry = _sim_shipments.get(ext_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Nieznana przesyłka")
    return SimStatusResponse(
        external_id=ext_id,
        status=entry["status"],
    )


@sim_router.get("/label/{ext_id}")
async def sim_get_label(ext_id: str) -> dict[str, str]:
    """Return a fake label URL for a simulated shipment."""
    entry = _sim_shipments.get(ext_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Nieznana przesyłka")
    return {"label_url": entry.get("label_url", "")}


@sim_router.post("/advance/{ext_id}", response_model=SimAdvanceResponse)
async def sim_advance_status(ext_id: str) -> SimAdvanceResponse:
    """Advance shipment to next status and send callback to the main app."""
    entry = _sim_shipments.get(ext_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Nieznana przesyłka")

    current = entry["status"]
    if current not in STATUS_PROGRESSION:
        raise HTTPException(
            status_code=400,
            detail=f"Nie można przejść dalej ze statusu: {current}",
        )

    current_idx = STATUS_PROGRESSION.index(current)
    if current_idx >= len(STATUS_PROGRESSION) - 1:
        raise HTTPException(
            status_code=400,
            detail="Przesyłka jest już w stanie końcowym",
        )

    new_status = STATUS_PROGRESSION[current_idx + 1]
    previous = current
    entry["status"] = new_status

    # Send HTTP callback to the main app
    shipment_id = entry["shipment_id"]
    callback_url = (
        f"http://localhost:8000/api/shipping"
        f"/callbacks/delivery-sim/{shipment_id}"
    )
    callback_sent = False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                callback_url,
                json={"status": new_status},
                timeout=5.0,
            )
            callback_sent = resp.status_code == 200
    except httpx.HTTPError:
        callback_sent = False

    return SimAdvanceResponse(
        external_id=ext_id,
        previous_status=previous,
        new_status=new_status,
        callback_sent=callback_sent,
    )
```

**Step 2: Verify the module imports cleanly**

```bash
uv run python -c "
from sendparcel.provider import BaseProvider
from delivery_sim import DeliverySimProvider, sim_router
assert issubclass(DeliverySimProvider, BaseProvider)
print('OK: DeliverySimProvider is a valid BaseProvider subclass')
print(f'OK: sim_router has {len(sim_router.routes)} routes')
"
```

Expected:
```
OK: DeliverySimProvider is a valid BaseProvider subclass
OK: sim_router has 3 routes
```

**Step 3: Commit**

```bash
git add example/delivery_sim.py
git commit -m "feat(example): add DeliverySimProvider with HTTP simulator endpoints"
```

---

## Task 4: Create base template with Tabler

**Files:**
- Create: `example/templates/base.html`

All user-facing text must be in Polish.

**Step 1: Write `example/templates/base.html`**

```html
<!doctype html>
<html lang="pl">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{% block title %}Przesyłki{% endblock %} — fastapi-sendparcel</title>
    <link
      href="https://cdn.jsdelivr.net/npm/@tabler/core@1.0.0-beta20/dist/css/tabler.min.css"
      rel="stylesheet"
    />
    <script
      src="https://unpkg.com/htmx.org@2.0.4"
      integrity="sha384-HGfztofotfshcF7+8n44JQL2oJmowVChPTg48S+jvZoztPfvwD79OC/LTtG6dMp+"
      crossorigin="anonymous"
    ></script>
  </head>
  <body class="page">
    <header class="navbar navbar-expand-md d-print-none">
      <div class="container-xl">
        <h1 class="navbar-brand navbar-brand-autodark d-none-navbar-btn">
          <a href="/">fastapi-sendparcel demo</a>
        </h1>
        <div class="navbar-nav flex-row order-md-last">
          <span class="nav-link text-muted">Symulator przesyłek</span>
        </div>
      </div>
    </header>
    <div class="page-wrapper">
      <div class="page-body">
        <div class="container-xl">
          {% block content %}{% endblock %}
        </div>
      </div>
    </div>
  </body>
</html>
```

**Step 2: Verify file is valid HTML**

```bash
test -f example/templates/base.html && echo "OK: base.html exists"
```

Expected: `OK: base.html exists`

**Step 3: Commit**

```bash
git add example/templates/base.html
git commit -m "feat(example): add Tabler base template with Polish UI text"
```

---

## Task 5: Create page templates (home, order_detail, shipment_detail, delivery_gateway, result)

**Files:**
- Create: `example/templates/home.html`
- Create: `example/templates/order_detail.html`
- Create: `example/templates/shipment_detail.html`
- Create: `example/templates/delivery_gateway.html`
- Create: `example/templates/result.html`

All user-facing text in Polish. HTMX for dynamic interactions. No JavaScript.

**Step 1: Write `example/templates/home.html`**

This template lists all orders and has a form to create a new order.

```html
{% extends "base.html" %}

{% block title %}Zamówienia{% endblock %}

{% block content %}
<div class="page-header d-print-none">
  <div class="row align-items-center">
    <div class="col-auto">
      <h2 class="page-title">Zamówienia</h2>
    </div>
  </div>
</div>

<div class="card mt-3">
  <div class="card-header">
    <h3 class="card-title">Nowe zamówienie</h3>
  </div>
  <div class="card-body">
    <form method="post" action="/orders">
      <div class="row g-3">
        <div class="col-md-6">
          <label class="form-label">Opis</label>
          <input class="form-control" type="text" name="description"
                 placeholder="np. Paczka z książkami" required />
        </div>
        <div class="col-md-3">
          <label class="form-label">Waga (kg)</label>
          <input class="form-control" type="number" name="total_weight"
                 min="0.1" step="0.1" value="1.0" required />
        </div>
      </div>
      <div class="row g-3 mt-1">
        <div class="col-md-4">
          <label class="form-label">Nadawca — imię i nazwisko</label>
          <input class="form-control" type="text" name="sender_name" required />
        </div>
        <div class="col-md-4">
          <label class="form-label">Nadawca — e-mail</label>
          <input class="form-control" type="email" name="sender_email" required />
        </div>
        <div class="col-md-4">
          <label class="form-label">Nadawca — telefon</label>
          <input class="form-control" type="text" name="sender_phone" />
        </div>
      </div>
      <div class="row g-3 mt-1">
        <div class="col-md-6">
          <label class="form-label">Nadawca — adres</label>
          <input class="form-control" type="text" name="sender_line1"
                 placeholder="ul. Przykładowa 1" />
        </div>
        <div class="col-md-3">
          <label class="form-label">Miasto</label>
          <input class="form-control" type="text" name="sender_city" />
        </div>
        <div class="col-md-3">
          <label class="form-label">Kod pocztowy</label>
          <input class="form-control" type="text" name="sender_postal_code" />
        </div>
      </div>
      <div class="row g-3 mt-1">
        <div class="col-md-4">
          <label class="form-label">Odbiorca — imię i nazwisko</label>
          <input class="form-control" type="text" name="recipient_name" required />
        </div>
        <div class="col-md-4">
          <label class="form-label">Odbiorca — e-mail</label>
          <input class="form-control" type="email" name="recipient_email" required />
        </div>
        <div class="col-md-4">
          <label class="form-label">Odbiorca — telefon</label>
          <input class="form-control" type="text" name="recipient_phone" />
        </div>
      </div>
      <div class="row g-3 mt-1">
        <div class="col-md-6">
          <label class="form-label">Odbiorca — adres</label>
          <input class="form-control" type="text" name="recipient_line1"
                 placeholder="ul. Docelowa 5" />
        </div>
        <div class="col-md-3">
          <label class="form-label">Miasto</label>
          <input class="form-control" type="text" name="recipient_city" />
        </div>
        <div class="col-md-3">
          <label class="form-label">Kod pocztowy</label>
          <input class="form-control" type="text" name="recipient_postal_code" />
        </div>
      </div>
      <div class="mt-3">
        <button class="btn btn-primary" type="submit">Utwórz zamówienie</button>
      </div>
    </form>
  </div>
</div>

{% if orders %}
<div class="card mt-3">
  <div class="card-header">
    <h3 class="card-title">Lista zamówień</h3>
  </div>
  <div class="table-responsive">
    <table class="table table-vcenter card-table">
      <thead>
        <tr>
          <th>ID</th>
          <th>Opis</th>
          <th>Waga</th>
          <th>Odbiorca</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {% for order in orders %}
        <tr>
          <td>{{ order.id }}</td>
          <td>{{ order.description }}</td>
          <td>{{ order.total_weight }} kg</td>
          <td>{{ order.recipient_name }}</td>
          <td>
            <a class="btn btn-sm btn-outline-primary"
               href="/orders/{{ order.id }}">Szczegóły</a>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endif %}
{% endblock %}
```

**Step 2: Write `example/templates/order_detail.html`**

This template shows order details and provides a form to create a shipment.

```html
{% extends "base.html" %}

{% block title %}Zamówienie #{{ order.id }}{% endblock %}

{% block content %}
<div class="page-header d-print-none">
  <div class="row align-items-center">
    <div class="col-auto">
      <a href="/" class="btn btn-outline-secondary btn-sm mb-2">← Powrót</a>
      <h2 class="page-title">Zamówienie #{{ order.id }}</h2>
    </div>
  </div>
</div>

<div class="card mt-3">
  <div class="card-header">
    <h3 class="card-title">Dane zamówienia</h3>
  </div>
  <div class="card-body">
    <div class="datagrid">
      <div class="datagrid-item">
        <div class="datagrid-title">Opis</div>
        <div class="datagrid-content">{{ order.description }}</div>
      </div>
      <div class="datagrid-item">
        <div class="datagrid-title">Waga</div>
        <div class="datagrid-content">{{ order.total_weight }} kg</div>
      </div>
      <div class="datagrid-item">
        <div class="datagrid-title">Nadawca</div>
        <div class="datagrid-content">
          {{ order.sender_name }}<br />
          {{ order.sender_line1 }}, {{ order.sender_city }}
          {{ order.sender_postal_code }}
        </div>
      </div>
      <div class="datagrid-item">
        <div class="datagrid-title">Odbiorca</div>
        <div class="datagrid-content">
          {{ order.recipient_name }}<br />
          {{ order.recipient_line1 }}, {{ order.recipient_city }}
          {{ order.recipient_postal_code }}
        </div>
      </div>
    </div>
  </div>
</div>

<div class="card mt-3">
  <div class="card-header">
    <h3 class="card-title">Utwórz przesyłkę</h3>
  </div>
  <div class="card-body">
    <form method="post" action="/orders/{{ order.id }}/ship">
      <div class="row g-3">
        <div class="col-md-6">
          <label class="form-label">Dostawca</label>
          <select class="form-select" name="provider" required>
            {% for slug, name in providers %}
            <option value="{{ slug }}">{{ name }}</option>
            {% endfor %}
          </select>
        </div>
      </div>
      <div class="mt-3">
        <button class="btn btn-primary" type="submit">Nadaj przesyłkę</button>
      </div>
    </form>
  </div>
</div>
{% endblock %}
```

**Step 3: Write `example/templates/shipment_detail.html`**

Shows shipment status and provides controls to advance the delivery simulation.

```html
{% extends "base.html" %}

{% block title %}Przesyłka {{ shipment.id }}{% endblock %}

{% block content %}
<div class="page-header d-print-none">
  <div class="row align-items-center">
    <div class="col-auto">
      <a href="/" class="btn btn-outline-secondary btn-sm mb-2">← Powrót</a>
      <h2 class="page-title">Przesyłka {{ shipment.id }}</h2>
    </div>
  </div>
</div>

<div class="card mt-3" id="shipment-card">
  <div class="card-header">
    <h3 class="card-title">Stan przesyłki</h3>
  </div>
  <div class="card-body">
    <div class="datagrid">
      <div class="datagrid-item">
        <div class="datagrid-title">Status</div>
        <div class="datagrid-content">
          <span class="badge
            {% if shipment.status == 'delivered' %}bg-success
            {% elif shipment.status == 'in_transit' or shipment.status == 'out_for_delivery' %}bg-info
            {% elif shipment.status == 'cancelled' or shipment.status == 'failed' %}bg-danger
            {% else %}bg-secondary
            {% endif %}">
            {{ shipment.status }}
          </span>
        </div>
      </div>
      <div class="datagrid-item">
        <div class="datagrid-title">Dostawca</div>
        <div class="datagrid-content">{{ shipment.provider }}</div>
      </div>
      <div class="datagrid-item">
        <div class="datagrid-title">ID zewnętrzne</div>
        <div class="datagrid-content">{{ shipment.external_id }}</div>
      </div>
      <div class="datagrid-item">
        <div class="datagrid-title">Numer śledzenia</div>
        <div class="datagrid-content">{{ shipment.tracking_number }}</div>
      </div>
      <div class="datagrid-item">
        <div class="datagrid-title">Etykieta</div>
        <div class="datagrid-content">
          {% if shipment.label_url %}
          <a href="{{ shipment.label_url }}" target="_blank">Pobierz etykietę</a>
          {% else %}
          <span class="text-muted">Brak</span>
          {% endif %}
        </div>
      </div>
    </div>
  </div>
</div>

{% if shipment.status not in ('delivered', 'cancelled', 'failed', 'returned') %}
<div class="card mt-3">
  <div class="card-header">
    <h3 class="card-title">Symulator dostawy</h3>
  </div>
  <div class="card-body">
    <p class="text-muted">
      Kliknij przycisk, aby przejść do następnego etapu dostawy.
      Symulator wyśle callback HTTP do aplikacji.
    </p>
    <div id="sim-result"></div>
    <form hx-post="/sim/advance/{{ shipment.external_id }}"
          hx-target="#sim-result"
          hx-swap="innerHTML">
      <button class="btn btn-warning" type="submit">
        Następny etap dostawy
      </button>
    </form>
    <div class="mt-2">
      <a class="btn btn-outline-secondary btn-sm"
         hx-get="/shipments/{{ shipment.id }}"
         hx-target="body"
         hx-push-url="true">
        Odśwież status
      </a>
    </div>
  </div>
</div>
{% endif %}
{% endblock %}
```

**Step 4: Write `example/templates/delivery_gateway.html`**

Shown after a shipment is created — gateway/redirect to shipment detail.

```html
{% extends "base.html" %}

{% block title %}Przesyłka utworzona{% endblock %}

{% block content %}
<div class="page-header d-print-none">
  <div class="row align-items-center">
    <div class="col-auto">
      <h2 class="page-title">Przesyłka utworzona</h2>
    </div>
  </div>
</div>

<div class="card mt-3">
  <div class="card-body">
    <div class="alert alert-success">
      Przesyłka <strong>{{ shipment.id }}</strong> została zarejestrowana
      u dostawcy <strong>{{ shipment.provider }}</strong>.
    </div>
    <div class="datagrid">
      <div class="datagrid-item">
        <div class="datagrid-title">ID zewnętrzne</div>
        <div class="datagrid-content">{{ shipment.external_id }}</div>
      </div>
      <div class="datagrid-item">
        <div class="datagrid-title">Numer śledzenia</div>
        <div class="datagrid-content">{{ shipment.tracking_number }}</div>
      </div>
    </div>
    <div class="mt-3">
      <a class="btn btn-primary"
         href="/shipments/{{ shipment.id }}">
        Przejdź do śledzenia przesyłki
      </a>
      <a class="btn btn-outline-secondary" href="/">
        Powrót do zamówień
      </a>
    </div>
  </div>
</div>
{% endblock %}
```

**Step 5: Write `example/templates/result.html`**

Generic result/error template used for flash messages and errors.

```html
{% extends "base.html" %}

{% block title %}{{ title }}{% endblock %}

{% block content %}
<div class="page-header d-print-none">
  <div class="row align-items-center">
    <div class="col-auto">
      <h2 class="page-title">{{ title }}</h2>
    </div>
  </div>
</div>

<div class="card mt-3">
  <div class="card-body">
    <div class="alert alert-{{ alert_type | default('info') }}">
      {{ message }}
    </div>
    {% if back_url %}
    <a class="btn btn-outline-secondary" href="{{ back_url }}">← Powrót</a>
    {% endif %}
  </div>
</div>
{% endblock %}
```

**Step 6: Verify all templates exist**

```bash
ls -la example/templates/
```

Expected: `base.html`, `home.html`, `order_detail.html`, `shipment_detail.html`, `delivery_gateway.html`, `result.html`

**Step 7: Commit**

```bash
git add example/templates/
git commit -m "feat(example): add Jinja2 templates with Tabler CSS and HTMX"
```

---

## Task 6: Create main app

**Files:**
- Create: `example/app.py`

This is the central FastAPI application that:
1. Creates an async SQLAlchemy engine with aiosqlite.
2. Sets up the library's `create_shipping_router` with `SQLAlchemyShipmentRepository`.
3. Registers `DeliverySimProvider` in the plugin registry.
4. Mounts the delivery simulator's router.
5. Exposes Jinja2-rendered HTML views for orders and shipments.
6. Provides a proxy endpoint for the simulator "advance" action (used by HTMX from the shipment detail page).

The library's shipping router is mounted at `/api/shipping` prefix. The HTML views are on the root.

**Important implementation details from the library code:**

- `create_shipping_router` sets `app.state.sendparcel_*` attributes in its lifespan handler (`router.py:30-35`).
- The shipping router exposes `POST /shipments`, `POST /shipments/{id}/label`, `GET /shipments/{id}/status` (from `routes/shipments.py`).
- The shipping router exposes `POST /callbacks/{provider_slug}/{shipment_id}` (from `routes/callbacks.py`).
- `ShipmentFlow.create_shipment` expects an `Order` object and a provider slug string (`flow.py:28-54`).
- The `SQLAlchemyShipmentRepository` uses `async_sessionmaker` and creates sessions per operation (`repository.py`).
- All models share `Base` from `contrib.sqlalchemy.models` — our `OrderModel` also inherits from it, so `Base.metadata.create_all` creates both tables.

**Step 1: Write `example/app.py`**

```python
"""FastAPI example app demonstrating fastapi-sendparcel."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from delivery_sim import DeliverySimProvider, _sim_shipments, sim_router
from fastapi_sendparcel import (
    FastAPIPluginRegistry,
    SendparcelConfig,
    create_shipping_router,
)
from fastapi_sendparcel.contrib.sqlalchemy.models import Base, ShipmentModel
from fastapi_sendparcel.contrib.sqlalchemy.repository import (
    SQLAlchemyShipmentRepository,
)
from fastapi_sendparcel.contrib.sqlalchemy.retry_store import (
    SQLAlchemyRetryStore,
)
from models import OrderModel
from sendparcel.flow import ShipmentFlow

# --- Database setup ---

DATABASE_URL = "sqlite+aiosqlite:///./example.db"
engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession)

# --- Plugin registry ---

plugin_registry = FastAPIPluginRegistry()
plugin_registry.register(DeliverySimProvider)

# --- Library integration ---

config = SendparcelConfig(
    default_provider="delivery-sim",
    providers={
        "delivery-sim": {
            "simulator_base_url": "http://localhost:8000",
        },
    },
)
repository = SQLAlchemyShipmentRepository(async_session)
retry_store = SQLAlchemyRetryStore(async_session)


class ExampleOrderResolver:
    """Resolves order IDs to OrderModel instances from the database."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        self._session_factory = session_factory

    async def resolve(self, order_id: str) -> OrderModel:
        async with self._session_factory() as session:
            result = await session.execute(
                select(OrderModel).where(
                    OrderModel.id == int(order_id)
                )
            )
            order = result.scalar_one_or_none()
            if order is None:
                raise ValueError(
                    f"Zamówienie o ID {order_id} nie istnieje"
                )
            return order


order_resolver = ExampleOrderResolver(async_session)

shipping_router = create_shipping_router(
    config=config,
    repository=repository,
    registry=plugin_registry,
    order_resolver=order_resolver,
    retry_store=retry_store,
)

# --- FastAPI app ---

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title="fastapi-sendparcel demo",
    lifespan=lifespan,
)
app.include_router(shipping_router, prefix="/api/shipping")
app.include_router(sim_router)


# --- HTML views ---


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    """Lista zamówień."""
    async with async_session() as session:
        result = await session.execute(
            select(OrderModel).order_by(OrderModel.id.desc())
        )
        orders = result.scalars().all()
    return templates.TemplateResponse(
        request, "home.html", {"orders": orders}
    )


@app.post("/orders")
async def create_order(
    request: Request,
    description: str = Form(""),
    total_weight: str = Form("1.0"),
    sender_name: str = Form(""),
    sender_email: str = Form(""),
    sender_phone: str = Form(""),
    sender_line1: str = Form(""),
    sender_city: str = Form(""),
    sender_postal_code: str = Form(""),
    recipient_name: str = Form(""),
    recipient_email: str = Form(""),
    recipient_phone: str = Form(""),
    recipient_line1: str = Form(""),
    recipient_city: str = Form(""),
    recipient_postal_code: str = Form(""),
) -> RedirectResponse:
    """Utwórz nowe zamówienie i przekieruj do jego szczegółów."""
    try:
        weight = Decimal(total_weight)
    except (InvalidOperation, ValueError):
        weight = Decimal("1.0")

    order = OrderModel(
        description=description,
        total_weight=weight,
        sender_name=sender_name,
        sender_email=sender_email,
        sender_phone=sender_phone,
        sender_line1=sender_line1,
        sender_city=sender_city,
        sender_postal_code=sender_postal_code,
        recipient_name=recipient_name,
        recipient_email=recipient_email,
        recipient_phone=recipient_phone,
        recipient_line1=recipient_line1,
        recipient_city=recipient_city,
        recipient_postal_code=recipient_postal_code,
    )
    async with async_session() as session:
        session.add(order)
        await session.commit()
        await session.refresh(order)
    return RedirectResponse(
        url=f"/orders/{order.id}", status_code=303
    )


@app.get("/orders/{order_id}", response_class=HTMLResponse)
async def order_detail(request: Request, order_id: int) -> HTMLResponse:
    """Szczegóły zamówienia z formularzem nadania przesyłki."""
    async with async_session() as session:
        result = await session.execute(
            select(OrderModel).where(OrderModel.id == order_id)
        )
        order = result.scalar_one_or_none()
    if order is None:
        raise HTTPException(
            status_code=404, detail="Zamówienie nie znalezione"
        )

    providers = plugin_registry.get_choices()
    return templates.TemplateResponse(
        request,
        "order_detail.html",
        {"order": order, "providers": providers},
    )


@app.post("/orders/{order_id}/ship")
async def create_shipment_for_order(
    request: Request,
    order_id: int,
    provider: str = Form(...),
) -> HTMLResponse:
    """Utwórz przesyłkę dla zamówienia przez ShipmentFlow."""
    async with async_session() as session:
        result = await session.execute(
            select(OrderModel).where(OrderModel.id == order_id)
        )
        order = result.scalar_one_or_none()
    if order is None:
        raise HTTPException(
            status_code=404, detail="Zamówienie nie znalezione"
        )

    flow = ShipmentFlow(
        repository=repository, config=config.providers
    )
    shipment = await flow.create_shipment(order, provider)
    shipment = await flow.create_label(shipment)

    return templates.TemplateResponse(
        request,
        "delivery_gateway.html",
        {"shipment": shipment},
    )


@app.get("/shipments/{shipment_id}", response_class=HTMLResponse)
async def shipment_detail(
    request: Request, shipment_id: str
) -> HTMLResponse:
    """Szczegóły przesyłki ze śledzeniem."""
    shipment = await repository.get_by_id(shipment_id)
    return templates.TemplateResponse(
        request,
        "shipment_detail.html",
        {"shipment": shipment},
    )


@app.post("/sim/advance/{ext_id}", response_class=HTMLResponse)
async def advance_delivery(
    request: Request, ext_id: str
) -> HTMLResponse:
    """Proxy: advance delivery sim and return result fragment for HTMX."""
    entry = _sim_shipments.get(ext_id)
    if entry is None:
        return HTMLResponse(
            '<div class="alert alert-danger">Nieznana przesyłka w symulatorze</div>',
            status_code=404,
        )

    # Import here to call the sim advance logic directly (same process)
    from delivery_sim import STATUS_PROGRESSION

    current = entry["status"]
    if current not in STATUS_PROGRESSION:
        return HTMLResponse(
            f'<div class="alert alert-warning">'
            f"Nie można przejść dalej ze statusu: {current}</div>",
        )

    current_idx = STATUS_PROGRESSION.index(current)
    if current_idx >= len(STATUS_PROGRESSION) - 1:
        return HTMLResponse(
            '<div class="alert alert-info">'
            "Przesyłka jest już w stanie końcowym</div>",
        )

    new_status = STATUS_PROGRESSION[current_idx + 1]
    previous = current
    entry["status"] = new_status

    # Send callback to the shipping router (same app, via internal call)
    shipment_id = entry["shipment_id"]
    flow = ShipmentFlow(
        repository=repository, config=config.providers
    )
    shipment = await repository.get_by_id(shipment_id)

    try:
        shipment = await flow.handle_callback(
            shipment,
            {"status": new_status},
            {},
        )
    except Exception:
        pass  # Callback handling is best-effort in the sim

    return HTMLResponse(
        f'<div class="alert alert-success">'
        f"Status zmieniony: <strong>{previous}</strong> → "
        f"<strong>{new_status}</strong></div>",
    )
```

**Step 2: Verify the app starts without errors**

```bash
uv run python -c "from app import app; print(f'OK: FastAPI app loaded, routes: {len(app.routes)}')"
```

Expected: `OK: FastAPI app loaded, routes: ...` (some number > 5)

**Step 3: Verify database tables are created on startup**

```bash
rm -f example.db && uv run python -c "
import asyncio
from app import engine
from fastapi_sendparcel.contrib.sqlalchemy.models import Base

async def check():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print('OK: Tables created')
    await engine.dispose()

asyncio.run(check())
"
```

Expected: `OK: Tables created`

**Step 4: Commit**

```bash
git add example/app.py
git commit -m "feat(example): add main FastAPI app with Jinja2 views, SQLAlchemy, and delivery sim"
```

---

## Task 7: Delete old example and update test

**Files:**
- Delete: `examples/app.py`
- Delete: `examples/` (entire directory)
- Modify: `tests/test_example_app.py` — rewrite to test the new example
- Modify: `pyproject.toml:49` — remove ruff per-file-ignores for `examples/app.py`

**Step 1: Delete the old example**

```bash
rm -rf examples/
```

**Step 2: Remove the ruff per-file-ignores entry from `pyproject.toml`**

In `pyproject.toml`, remove these lines:

```toml
[tool.ruff.lint.per-file-ignores]
"examples/app.py" = ["E501"]
```

**Step 3: Rewrite `tests/test_example_app.py`**

The new test verifies the example app's key flows using `httpx.AsyncClient` (which FastAPI's test support uses) or `TestClient`. Since the example uses SQLAlchemy with aiosqlite, we need to use an in-memory database override for testing.

```python
"""Tests for the new example app."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


@pytest.fixture()
def example_app():
    """Load the example app module with an in-memory database."""
    example_dir = Path(__file__).resolve().parents[1] / "example"

    # Add example dir to sys.path so relative imports work
    sys_path_entry = str(example_dir)
    if sys_path_entry not in sys.path:
        sys.path.insert(0, sys_path_entry)

    # Create in-memory engine for testing
    test_engine = create_async_engine(
        "sqlite+aiosqlite://", echo=False
    )
    test_session = async_sessionmaker(
        test_engine, class_=AsyncSession
    )

    try:
        with patch.dict("os.environ", {}, clear=False):
            # Patch the database before importing the module
            models_spec = importlib.util.spec_from_file_location(
                "models", example_dir / "models.py"
            )
            models_mod = importlib.util.module_from_spec(models_spec)
            sys.modules["models"] = models_mod
            models_spec.loader.exec_module(models_mod)

            delivery_spec = importlib.util.spec_from_file_location(
                "delivery_sim", example_dir / "delivery_sim.py"
            )
            delivery_mod = importlib.util.module_from_spec(delivery_spec)
            sys.modules["delivery_sim"] = delivery_mod
            delivery_spec.loader.exec_module(delivery_mod)

            app_spec = importlib.util.spec_from_file_location(
                "example_app", example_dir / "app.py"
            )
            app_mod = importlib.util.module_from_spec(app_spec)
            sys.modules["example_app"] = app_mod
            app_spec.loader.exec_module(app_mod)

        # Override database components
        app_mod.engine = test_engine
        app_mod.async_session = test_session
        app_mod.repository.session_factory = test_session
        app_mod.retry_store.session_factory = test_session
        app_mod.order_resolver._session_factory = test_session

        yield app_mod
    finally:
        sys.modules.pop("models", None)
        sys.modules.pop("delivery_sim", None)
        sys.modules.pop("example_app", None)
        if sys_path_entry in sys.path:
            sys.path.remove(sys_path_entry)


def test_home_page_loads(example_app) -> None:
    """Home page renders with Tabler CSS and order form."""
    with TestClient(example_app.app) as client:
        resp = client.get("/")
        assert resp.status_code == 200
        assert "tabler" in resp.text.lower()
        assert "Zamówienia" in resp.text
        assert 'name="description"' in resp.text


def test_create_order_and_view_detail(example_app) -> None:
    """Create an order via form POST and view its detail page."""
    with TestClient(example_app.app) as client:
        resp = client.post(
            "/orders",
            data={
                "description": "Testowa paczka",
                "total_weight": "2.5",
                "sender_name": "Jan Kowalski",
                "sender_email": "jan@example.com",
                "sender_phone": "+48111222333",
                "sender_line1": "ul. Testowa 1",
                "sender_city": "Warszawa",
                "sender_postal_code": "00-001",
                "recipient_name": "Anna Nowak",
                "recipient_email": "anna@example.com",
                "recipient_phone": "+48444555666",
                "recipient_line1": "ul. Docelowa 5",
                "recipient_city": "Kraków",
                "recipient_postal_code": "30-001",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "Testowa paczka" in resp.text
        assert "Jan Kowalski" in resp.text
        assert "Anna Nowak" in resp.text
        assert "Nadaj przesyłkę" in resp.text


def test_full_shipment_flow(example_app) -> None:
    """Create order, ship it, verify shipment page loads."""
    with TestClient(example_app.app) as client:
        # Create order
        resp = client.post(
            "/orders",
            data={
                "description": "Paczka testowa",
                "total_weight": "1.0",
                "sender_name": "Nadawca",
                "sender_email": "sender@example.com",
                "recipient_name": "Odbiorca",
                "recipient_email": "recipient@example.com",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200

        # Ship the order
        ship_resp = client.post(
            "/orders/1/ship",
            data={"provider": "delivery-sim"},
        )
        assert ship_resp.status_code == 200
        assert "Przesyłka utworzona" in ship_resp.text
        assert "delivery-sim" in ship_resp.text

        # Extract shipment ID and view shipment detail
        import re

        match = re.search(
            r'href="/shipments/([^"]+)"', ship_resp.text
        )
        assert match is not None
        shipment_id = match.group(1)

        detail_resp = client.get(f"/shipments/{shipment_id}")
        assert detail_resp.status_code == 200
        assert "Przesyłka" in detail_resp.text
        assert "delivery-sim" in detail_resp.text
```

**Step 4: Run the tests**

```bash
uv run pytest tests/test_example_app.py -v
```

Expected: All 3 tests pass.

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor(example): replace old inline-HTML example with Jinja2+Tabler+HTMX app"
```

---

## Task 8: Set up Sphinx documentation

**Files:**
- Create: `docs/conf.py`
- Modify: `docs/index.md` — add proper index with toctree
- Create: `.readthedocs.yml`
- Modify: `pyproject.toml` — add `docs` optional dependency group

**Step 1: Add docs dependencies to `pyproject.toml`**

Add a `docs` extra to the `[project.optional-dependencies]` section:

```toml
docs = [
    "sphinx>=7.0",
    "furo>=2024.0",
    "myst-parser>=3.0",
    "sphinx-autodoc2>=0.5",
]
```

**Step 2: Write `docs/conf.py`**

```python
"""Sphinx configuration for fastapi-sendparcel."""

project = "fastapi-sendparcel"
author = "Dominik Kozaczko"
release = "0.1.0"

extensions = [
    "myst_parser",
    "autodoc2",
    "sphinx.ext.intersphinx",
]

autodoc2_packages = [
    {
        "path": "../src/fastapi_sendparcel",
        "module": "fastapi_sendparcel",
    },
]

myst_enable_extensions = [
    "colon_fence",
    "fieldlist",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "plans"]

html_theme = "furo"

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "fastapi": ("https://fastapi.tiangolo.com", None),
}

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}
```

**Step 3: Rewrite `docs/index.md`**

```markdown
# fastapi-sendparcel

FastAPI adapter for the python-sendparcel ecosystem.

```{toctree}
:maxdepth: 2
:caption: Contents

quickstart
configuration
api
```
```

**Step 4: Write `.readthedocs.yml`**

```yaml
version: 2

build:
  os: ubuntu-24.04
  tools:
    python: "3.12"

sphinx:
  configuration: docs/conf.py

python:
  install:
    - method: pip
      path: .
      extra_requirements:
        - docs
```

**Step 5: Verify Sphinx can parse the config**

```bash
uv run python -c "
import importlib.util, sys
spec = importlib.util.spec_from_file_location('conf', 'docs/conf.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print(f'OK: project={mod.project}, theme={mod.html_theme}')
"
```

Expected: `OK: project=fastapi-sendparcel, theme=furo`

**Step 6: Commit**

```bash
git add docs/conf.py docs/index.md .readthedocs.yml pyproject.toml
git commit -m "docs: set up Sphinx with furo theme, myst-parser, autodoc2"
```

---

## Task 9: Write quickstart documentation

**Files:**
- Create: `docs/quickstart.md`

**Step 1: Write `docs/quickstart.md`**

```markdown
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
```

**Step 2: Verify the file parses as valid markdown**

```bash
test -f docs/quickstart.md && wc -l docs/quickstart.md
```

Expected: file exists with ~80 lines.

**Step 3: Commit**

```bash
git add docs/quickstart.md
git commit -m "docs: add quickstart guide with installation and minimal example"
```

---

## Task 10: Write configuration documentation

**Files:**
- Create: `docs/configuration.md`

**Step 1: Write `docs/configuration.md`**

```markdown
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
    order_resolver=order_resolver,    # OrderResolver (optional)
    retry_store=retry_store,          # CallbackRetryStore (optional)
)
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `config` | `SendparcelConfig` | Yes | Runtime configuration |
| `repository` | `ShipmentRepository` | Yes | Persistence backend for shipments |
| `registry` | `FastAPIPluginRegistry` | No | Plugin registry; auto-created if not provided |
| `order_resolver` | `OrderResolver` | No | Resolves order IDs to `Order` objects; required for `POST /shipments` |
| `retry_store` | `CallbackRetryStore` | No | Stores failed callbacks for retry |

## Protocols

### Order

Your order model must implement these methods:

```python
from decimal import Decimal
from sendparcel.types import AddressInfo, ParcelInfo

class YourOrder:
    def get_total_weight(self) -> Decimal: ...
    def get_parcels(self) -> list[ParcelInfo]: ...
    def get_sender_address(self) -> AddressInfo: ...
    def get_receiver_address(self) -> AddressInfo: ...
```

### OrderResolver

Required if you use the `POST /shipments` endpoint:

```python
class YourResolver:
    async def resolve(self, order_id: str) -> Order: ...
```

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
```

**Step 2: Commit**

```bash
git add docs/configuration.md
git commit -m "docs: add configuration reference with settings, protocols, and SQLAlchemy guide"
```

---

## Task 11: Write API autodoc page

**Files:**
- Create: `docs/api.md`

**Step 1: Write `docs/api.md`**

```markdown
# API Reference

Auto-generated documentation for the `fastapi_sendparcel` package.

## Public API

```{autodoc2-summary}
fastapi_sendparcel
```

## Configuration

```{autodoc2-object} fastapi_sendparcel.config.SendparcelConfig
```

## Router factory

```{autodoc2-object} fastapi_sendparcel.router.create_shipping_router
```

## Plugin registry

```{autodoc2-object} fastapi_sendparcel.registry.FastAPIPluginRegistry
```

## Protocols

```{autodoc2-object} fastapi_sendparcel.protocols.OrderResolver
```

```{autodoc2-object} fastapi_sendparcel.protocols.CallbackRetryStore
```

## Schemas

```{autodoc2-object} fastapi_sendparcel.schemas.CreateShipmentRequest
```

```{autodoc2-object} fastapi_sendparcel.schemas.ShipmentResponse
```

```{autodoc2-object} fastapi_sendparcel.schemas.CallbackResponse
```

## Dependencies

```{autodoc2-object} fastapi_sendparcel.dependencies.get_config
```

```{autodoc2-object} fastapi_sendparcel.dependencies.get_repository
```

```{autodoc2-object} fastapi_sendparcel.dependencies.get_registry
```

```{autodoc2-object} fastapi_sendparcel.dependencies.get_flow
```

## SQLAlchemy contrib

### Models

```{autodoc2-object} fastapi_sendparcel.contrib.sqlalchemy.models.ShipmentModel
```

```{autodoc2-object} fastapi_sendparcel.contrib.sqlalchemy.models.CallbackRetryModel
```

### Repository

```{autodoc2-object} fastapi_sendparcel.contrib.sqlalchemy.repository.SQLAlchemyShipmentRepository
```

### Retry store

```{autodoc2-object} fastapi_sendparcel.contrib.sqlalchemy.retry_store.SQLAlchemyRetryStore
```
```

**Step 2: Commit**

```bash
git add docs/api.md
git commit -m "docs: add API reference page with autodoc2 directives"
```

---

## Task 12: Build and verify docs

**Files:** None (verification only)

**Step 1: Install docs dependencies**

```bash
uv sync --extra docs
```

**Step 2: Build the Sphinx documentation**

```bash
uv run sphinx-build -b html docs docs/_build/html -W
```

Expected: Build succeeds without warnings (`-W` makes warnings into errors).

If there are warnings about missing references or autodoc issues, fix them in `docs/conf.py` or the `.md` files and rebuild.

**Step 3: Verify the built HTML exists**

```bash
ls docs/_build/html/index.html docs/_build/html/quickstart.html docs/_build/html/configuration.html docs/_build/html/api.html
```

Expected: All four files exist.

**Step 4: Commit any fixes**

```bash
git add -A
git commit -m "docs: fix Sphinx build issues" --allow-empty
```

---

## Task 13: Final verification — run all tests

**Files:** None (verification only)

**Step 1: Run the full test suite**

```bash
uv run pytest tests/ -v
```

Expected: All tests pass, including the rewritten `test_example_app.py`.

**Step 2: Run ruff linting on the example**

```bash
uv run ruff check example/ --select E,W,F,I,N,UP,B,A,SIM,RUF
```

Expected: No errors.

**Step 3: Verify the example app starts**

```bash
cd example && timeout 5 uv run uvicorn app:app --host 0.0.0.0 --port 9999 || true
```

Expected: App starts and prints "Uvicorn running on http://0.0.0.0:9999", then times out (which is OK — just verifying startup).

**Step 4: Commit any final fixes**

```bash
git add -A
git commit -m "chore: final verification and cleanup" --allow-empty
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Example project scaffold | `example/pyproject.toml`, `example/README.md` |
| 2 | SQLAlchemy OrderModel | `example/models.py` |
| 3 | DeliverySimProvider + simulator routes | `example/delivery_sim.py` |
| 4 | Tabler base template | `example/templates/base.html` |
| 5 | Page templates (home, order, shipment, gateway, result) | `example/templates/*.html` |
| 6 | Main FastAPI app | `example/app.py` |
| 7 | Delete old example + rewrite test | `examples/` (deleted), `tests/test_example_app.py` |
| 8 | Sphinx setup | `docs/conf.py`, `docs/index.md`, `.readthedocs.yml`, `pyproject.toml` |
| 9 | Quickstart docs | `docs/quickstart.md` |
| 10 | Configuration docs | `docs/configuration.md` |
| 11 | API autodoc | `docs/api.md` |
| 12 | Build and verify docs | (verification) |
| 13 | Final verification | (verification) |
