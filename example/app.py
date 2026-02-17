"""FastAPI example app demonstrating fastapi-sendparcel."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path

from delivery_sim import (
    STATUS_PROGRESSION,
    DeliverySimProvider,
    _sim_shipments,
    sim_router,
)
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sendparcel.flow import ShipmentFlow
from sendparcel.types import AddressInfo, ParcelInfo
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

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

shipping_router = create_shipping_router(
    config=config,
    repository=repository,
    registry=plugin_registry,
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
    """List shipments."""
    async with async_session() as session:
        result = await session.execute(
            select(ShipmentModel).order_by(ShipmentModel.created_at.desc())
        )
        shipments = result.scalars().all()
    providers = plugin_registry.get_choices()
    return templates.TemplateResponse(
        request, "home.html", {"shipments": shipments, "providers": providers}
    )


@app.post("/shipments")
async def create_shipment_view(
    request: Request,
    description: str = Form(""),
    total_weight: str = Form("1.0"),
    provider: str = Form("delivery-sim"),
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
) -> HTMLResponse:
    """Create a new shipment directly via ShipmentFlow."""
    try:
        weight = Decimal(total_weight)
    except (InvalidOperation, ValueError):
        weight = Decimal("1.0")

    sender_address = AddressInfo(
        name=sender_name,
        email=sender_email,
        phone=sender_phone,
        line1=sender_line1,
        city=sender_city,
        postal_code=sender_postal_code,
        country_code="PL",
    )
    receiver_address = AddressInfo(
        name=recipient_name,
        email=recipient_email,
        phone=recipient_phone,
        line1=recipient_line1,
        city=recipient_city,
        postal_code=recipient_postal_code,
        country_code="PL",
    )
    parcels = [ParcelInfo(weight_kg=weight)]

    flow = ShipmentFlow(repository=repository, config=config.providers)
    shipment = await flow.create_shipment(
        provider,
        sender_address=sender_address,
        receiver_address=receiver_address,
        parcels=parcels,
        reference_id=description or "",
    )
    shipment = await flow.create_label(shipment)

    return templates.TemplateResponse(
        request,
        "delivery_gateway.html",
        {"shipment": shipment},
    )


@app.get("/shipments/{shipment_id}", response_class=HTMLResponse)
async def shipment_detail(request: Request, shipment_id: str) -> HTMLResponse:
    """Shipment details with tracking."""
    shipment = await repository.get_by_id(shipment_id)
    return templates.TemplateResponse(
        request,
        "shipment_detail.html",
        {"shipment": shipment},
    )


@app.post("/sim/advance/{ext_id}", response_class=HTMLResponse)
async def advance_delivery(request: Request, ext_id: str) -> HTMLResponse:
    """Proxy: advance delivery sim and return result fragment for HTMX."""
    entry = _sim_shipments.get(ext_id)
    if entry is None:
        return HTMLResponse(
            '<div class="alert alert-danger">'
            "Unknown shipment in simulator</div>",
            status_code=404,
        )

    current = entry["status"]
    if current not in STATUS_PROGRESSION:
        return HTMLResponse(
            f'<div class="alert alert-warning">'
            f"Cannot advance from status: {current}</div>",
        )

    current_idx = STATUS_PROGRESSION.index(current)
    if current_idx >= len(STATUS_PROGRESSION) - 1:
        return HTMLResponse(
            '<div class="alert alert-info">'
            "Shipment is already in a terminal state</div>",
        )

    new_status = STATUS_PROGRESSION[current_idx + 1]
    previous = current
    entry["status"] = new_status

    # Send callback to the shipping router (same app, via internal call)
    shipment_id = entry["shipment_id"]
    flow = ShipmentFlow(repository=repository, config=config.providers)
    shipment = await repository.get_by_id(shipment_id)

    with contextlib.suppress(Exception):
        shipment = await flow.handle_callback(
            shipment,
            {"status": new_status},
            {},
        )

    return HTMLResponse(
        f'<div class="alert alert-success">'
        f"Status changed: <strong>{previous}</strong> → "
        f"<strong>{new_status}</strong></div>",
    )
