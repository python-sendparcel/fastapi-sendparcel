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
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from models import OrderModel
from sendparcel.flow import ShipmentFlow
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
from fastapi_sendparcel.contrib.sqlalchemy.models import Base
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


class ExampleOrderResolver:
    """Resolves order IDs to OrderModel instances from the database."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        self._session_factory = session_factory

    async def resolve(self, order_id: str) -> OrderModel:
        async with self._session_factory() as session:
            result = await session.execute(
                select(OrderModel).where(OrderModel.id == int(order_id))
            )
            order = result.scalar_one_or_none()
            if order is None:
                raise ValueError(f"Zamówienie o ID {order_id} nie istnieje")
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
    return templates.TemplateResponse(request, "home.html", {"orders": orders})


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
    return RedirectResponse(url=f"/orders/{order.id}", status_code=303)


@app.get("/orders/{order_id}", response_class=HTMLResponse)
async def order_detail(request: Request, order_id: int) -> HTMLResponse:
    """Szczegóły zamówienia z formularzem nadania przesyłki."""
    async with async_session() as session:
        result = await session.execute(
            select(OrderModel).where(OrderModel.id == order_id)
        )
        order = result.scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail="Zamówienie nie znalezione")

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
        raise HTTPException(status_code=404, detail="Zamówienie nie znalezione")

    flow = ShipmentFlow(repository=repository, config=config.providers)
    shipment = await flow.create_shipment(order, provider)
    shipment = await flow.create_label(shipment)

    return templates.TemplateResponse(
        request,
        "delivery_gateway.html",
        {"shipment": shipment},
    )


@app.get("/shipments/{shipment_id}", response_class=HTMLResponse)
async def shipment_detail(request: Request, shipment_id: str) -> HTMLResponse:
    """Szczegóły przesyłki ze śledzeniem."""
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
            "Nieznana przesyłka w symulatorze</div>",
            status_code=404,
        )

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
        f"Status zmieniony: <strong>{previous}</strong> → "
        f"<strong>{new_status}</strong></div>",
    )
