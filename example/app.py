"""FastAPI example app demonstrating fastapi-sendparcel."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from decimal import Decimal
from pathlib import Path

from delivery_sim import (
    STATUS_LABELS,
    DeliverySimProvider,
    sim_router,
)
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sendparcel.enums import ShipmentStatus
from sendparcel.exceptions import InvalidTransitionError
from sendparcel.flow import ShipmentFlow
from sendparcel.registry import registry
from sendparcel.types import AddressInfo, ParcelInfo
from sqlalchemy import func, select

from models import (
    Shipment,
    ShipmentRepository,
    async_session,
    init_db,
)

# --- Register the simulator provider ---
registry.register(DeliverySimProvider)

# --- Weight presets ---
WEIGHT_BY_SIZE: dict[str, Decimal] = {
    "S": Decimal("0.5"),
    "M": Decimal("1.0"),
    "L": Decimal("2.5"),
}


# --- Template helpers ---
def status_label(status: str) -> str:
    """Human-readable label for a shipment status."""
    return STATUS_LABELS.get(status, status)


def status_color(status: str) -> str:
    """Tabler badge color for a shipment status."""
    colors: dict[str, str] = {
        ShipmentStatus.NEW: "secondary",
        ShipmentStatus.CREATED: "info",
        ShipmentStatus.LABEL_READY: "cyan",
        ShipmentStatus.IN_TRANSIT: "blue",
        ShipmentStatus.OUT_FOR_DELIVERY: "indigo",
        ShipmentStatus.DELIVERED: "success",
        ShipmentStatus.CANCELLED: "warning",
        ShipmentStatus.FAILED: "danger",
        ShipmentStatus.RETURNED: "orange",
    }
    return colors.get(status, "secondary")


# --- FastAPI app ---

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Add helpers to templates
templates.env.globals["status_label"] = status_label
templates.env.globals["status_color"] = status_color


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    await init_db()
    yield


app = FastAPI(
    title="fastapi-sendparcel demo",
    lifespan=lifespan,
)
app.include_router(sim_router)


# --- HTML views ---


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    """List shipments."""
    async with async_session() as session:
        result = await session.execute(
            select(Shipment).order_by(Shipment.id.desc())
        )
        shipments = result.scalars().all()

        return templates.TemplateResponse(
            request, "home.html", {"shipments": shipments}
        )


@app.get("/shipments/new", response_class=HTMLResponse)
async def shipment_new(request: Request) -> HTMLResponse:
    """Render new shipment form."""
    providers = registry.get_choices()
    print(f"DEBUG: Providers: {providers}")
    return templates.TemplateResponse(
        request, "delivery_gateway.html", {"providers": providers}
    )


@app.post("/shipments/create", response_class=RedirectResponse)
async def shipment_create(
    request: Request,
    provider: str = Form(...),
    package_size: str = Form("M"),
    sender_name: str = Form(""),
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
    """Create a new shipment."""
    weight = WEIGHT_BY_SIZE.get(package_size, Decimal("1.0"))

    sender_address = AddressInfo(
        name=sender_name,
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

    async with async_session() as session:
        count_result = await session.execute(select(func.count(Shipment.id)))
        count = count_result.scalar() or 0
        reference_id = f"SHP-{count + 1:04d}"

        repo = ShipmentRepository(session)
        flow = ShipmentFlow(repository=repo)
        shipment = await flow.create_shipment(
            provider,
            sender_address=sender_address,
            receiver_address=receiver_address,
            parcels=parcels,
            reference_id=reference_id,
        )

        # Store address and parcel data on the example model
        shipment.sender_name = sender_name
        shipment.sender_street = sender_line1
        shipment.sender_city = sender_city
        shipment.sender_postal_code = sender_postal_code
        shipment.receiver_name = recipient_name
        shipment.receiver_street = recipient_line1
        shipment.receiver_city = recipient_city
        shipment.receiver_postal_code = recipient_postal_code
        shipment.weight = weight

        with suppress(NotImplementedError):
            shipment = await flow.create_label(shipment)

        await session.commit()
        return RedirectResponse(
            url=f"/shipments/{shipment.id}", status_code=303
        )


@app.get("/shipments/{shipment_id}", response_class=HTMLResponse)
async def shipment_detail(request: Request, shipment_id: int) -> HTMLResponse:
    """Shipment details."""
    async with async_session() as session:
        shipment = await session.get(Shipment, shipment_id)
        if shipment is None:
            return HTMLResponse("Nie znaleziono przesyłki", status_code=404)

        return templates.TemplateResponse(
            request,
            "shipment_detail.html",
            {"shipment": shipment},
        )


@app.post(
    "/shipments/{shipment_id}/create-label", response_class=RedirectResponse
)
async def shipment_create_label(shipment_id: int) -> RedirectResponse:
    """Generate label for shipment."""
    async with async_session() as session:
        repo = ShipmentRepository(session)
        flow = ShipmentFlow(repository=repo)
        shipment = await repo.get_by_id(str(shipment_id))
        with suppress(NotImplementedError):
            shipment = await flow.create_label(shipment)
        await session.commit()
    return RedirectResponse(url=f"/shipments/{shipment_id}", status_code=303)


@app.get("/shipments/{shipment_id}/refresh-status", response_class=HTMLResponse)
async def shipment_refresh_status(
    request: Request, shipment_id: int
) -> HTMLResponse:
    """HTMX endpoint: fetch latest status and return badge HTML."""
    async with async_session() as session:
        repo = ShipmentRepository(session)
        flow = ShipmentFlow(repository=repo)
        shipment = await repo.get_by_id(str(shipment_id))
        with suppress(InvalidTransitionError):
            shipment = await flow.fetch_and_update_status(shipment)
        await session.commit()

        return templates.TemplateResponse(
            request,
            "partials/status_badge.html",
            {"shipment": shipment},
        )
