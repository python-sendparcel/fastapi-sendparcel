"""FastAPI single-page shipping demo with Tabler + HTMX."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from html import escape
from urllib.parse import parse_qs
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from sendparcel.flow import ShipmentFlow
from sendparcel.providers.dummy import DummyProvider
from sendparcel.registry import registry

DEFAULT_PROVIDER = DummyProvider.slug

BASE_PRICES = {
    "S": Decimal("12.00"),
    "M": Decimal("16.00"),
    "L": Decimal("22.00"),
}


@dataclass
class DemoOrder:
    """Order payload passed to ShipmentFlow."""

    order_id: str
    sender_email: str
    recipient_email: str
    recipient_phone: str
    recipient_address: str
    recipient_locker: str
    package_size: str

    def get_total_weight(self) -> Decimal:
        return {
            "S": Decimal("0.5"),
            "M": Decimal("1.0"),
            "L": Decimal("2.5"),
        }[self.package_size]

    def get_parcels(self) -> list[dict]:
        return [
            {
                "weight_kg": self.get_total_weight(),
                "size": self.package_size,
            }
        ]

    def get_sender_address(self) -> dict:
        return {
            "email": self.sender_email,
            "country_code": "PL",
        }

    def get_receiver_address(self) -> dict:
        return {
            "email": self.recipient_email,
            "phone": self.recipient_phone,
            "address": self.recipient_address,
            "locker_code": self.recipient_locker,
            "country_code": "PL",
        }


@dataclass
class DemoShipment:
    id: str
    order: DemoOrder
    status: str
    provider: str
    external_id: str = ""
    tracking_number: str = ""
    label_url: str = ""


@dataclass
class Checkout:
    checkout_id: str
    provider: str
    recipient_email: str
    recipient_phone: str
    recipient_address: str
    recipient_locker: str
    sender_email: str
    package_size: str
    insurance_enabled: bool
    insurance_amount: Decimal
    total_price: Decimal
    paid: bool = False
    shipment_id: str = ""
    tracking_number: str = ""


class InMemoryRepo:
    def __init__(self) -> None:
        self.items: dict[str, DemoShipment] = {}
        self._counter = 0

    async def get_by_id(self, shipment_id: str) -> DemoShipment:
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


registry.register(DummyProvider)
repository = InMemoryRepo()
flow = ShipmentFlow(repository=repository)
checkouts: dict[str, Checkout] = {}
labels: dict[str, bytes] = {}

app = FastAPI(title="fastapi-sendparcel checkout example")


def _provider_choices() -> list[tuple[str, str]]:
    choices = registry.get_choices()
    if not choices:
        return [(DEFAULT_PROVIDER, "Dummy")]
    return choices


def _html_shell(inner: str) -> str:
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>FastAPI Sendparcel Demo</title>
    <link
      href="https://cdn.jsdelivr.net/npm/@tabler/core@1.0.0-beta20/dist/css/tabler.min.css"
      rel="stylesheet"
    />
    <script src="https://unpkg.com/htmx.org@1.9.12"></script>
  </head>
  <body class="bg-light">
    <main class="container py-4">{inner}</main>
  </body>
</html>"""


def _render_index() -> str:
    options = "".join(
        f'<option value="{escape(slug)}">{escape(name)}</option>'
        for slug, name in _provider_choices()
    )
    return _html_shell(
        f"""
<div class="row justify-content-center">
  <div class="col-lg-9">
    <h1 class="mb-3">Create shipment label</h1>
    <p class="text-secondary">Select provider, fill parcel details, pay, and download PDF label.</p>
    <div class="card">
      <div class="card-body">
        <form hx-post="/checkout" hx-target="#flow-panel" hx-swap="innerHTML" method="post" action="/checkout">
          <div class="row g-3">
            <div class="col-md-6">
              <label class="form-label">Provider</label>
              <select class="form-select" name="provider" required>{options}</select>
            </div>
            <div class="col-md-6">
              <label class="form-label">Package size</label>
              <select class="form-select" name="package_size" required>
                <option value="S">S - small</option>
                <option value="M" selected>M - medium</option>
                <option value="L">L - large</option>
              </select>
            </div>
            <div class="col-md-6">
              <label class="form-label">Recipient email</label>
              <input class="form-control" type="email" name="recipient_email" required />
            </div>
            <div class="col-md-6">
              <label class="form-label">Recipient phone</label>
              <input class="form-control" type="text" name="recipient_phone" required />
            </div>
            <div class="col-md-8">
              <label class="form-label">Recipient address</label>
              <input class="form-control" type="text" name="recipient_address" placeholder="Street, city" />
            </div>
            <div class="col-md-4">
              <label class="form-label">Locker code</label>
              <input class="form-control" type="text" name="recipient_locker" placeholder="Optional" />
            </div>
            <div class="col-md-6">
              <label class="form-label">Sender email</label>
              <input class="form-control" type="email" name="sender_email" required />
            </div>
            <div class="col-md-3 d-flex align-items-end">
              <label class="form-check form-switch">
                <input class="form-check-input" type="checkbox" name="insurance" value="1" />
                <span class="form-check-label">Insurance</span>
              </label>
            </div>
            <div class="col-md-3">
              <label class="form-label">Insurance amount (PLN)</label>
              <input class="form-control" type="number" name="insurance_amount" min="0" step="1" value="0" />
            </div>
          </div>
          <div class="mt-4">
            <button class="btn btn-primary" type="submit">Continue to payment</button>
          </div>
        </form>
      </div>
    </div>
    <div id="flow-panel" class="mt-3">
      <div class="alert alert-secondary mb-0">Complete the form to continue.</div>
    </div>
  </div>
</div>
"""
    )


def _parse_form(raw_body: bytes) -> dict[str, str]:
    parsed = parse_qs(raw_body.decode("utf-8"), keep_blank_values=True)
    return {key: values[0] for key, values in parsed.items()}


def _parse_decimal(value: str) -> Decimal:
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _validate_payload(payload: dict[str, str]) -> str | None:
    provider = payload.get("provider", "")
    available = {slug for slug, _ in _provider_choices()}
    if provider not in available:
        return "Choose a valid provider."
    if not payload.get("recipient_email"):
        return "Recipient email is required."
    if not payload.get("recipient_phone"):
        return "Recipient phone is required."
    if not payload.get("sender_email"):
        return "Sender email is required."
    if not payload.get("recipient_address") and not payload.get("recipient_locker"):
        return "Provide recipient address or locker code."
    if payload.get("package_size", "") not in BASE_PRICES:
        return "Choose a valid package size."
    return None


def _calculate_price(payload: dict[str, str]) -> Decimal:
    package_size = payload.get("package_size", "M")
    total = BASE_PRICES[package_size]
    insurance_enabled = payload.get("insurance") == "1"
    insurance_amount = _parse_decimal(payload.get("insurance_amount", "0"))
    if insurance_enabled:
        total += max(Decimal("2.00"), insurance_amount * Decimal("0.01"))
    return total.quantize(Decimal("0.01"))


def _render_error(message: str) -> str:
    return f'<div class="alert alert-danger mb-0">{escape(message)}</div>'


def _render_payment(checkout: Checkout) -> str:
    insurance = "yes" if checkout.insurance_enabled else "no"
    return f"""
<div class="card">
  <div class="card-body">
    <h3 class="card-title">Payment step</h3>
    <p class="text-secondary">DummyPay simulator for provider <strong>{escape(checkout.provider)}</strong>.</p>
    <ul class="list-unstyled">
      <li><strong>Recipient:</strong> {escape(checkout.recipient_email)}</li>
      <li><strong>Package:</strong> {escape(checkout.package_size)}</li>
      <li><strong>Insurance:</strong> {insurance}</li>
      <li><strong>Total:</strong> PLN {checkout.total_price}</li>
    </ul>
    <form hx-post="/pay/{checkout.checkout_id}" hx-target="#flow-panel" hx-swap="innerHTML" method="post" action="/pay/{checkout.checkout_id}">
      <button type="submit" class="btn btn-success">Pay with DummyPay simulator</button>
    </form>
  </div>
</div>
"""


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_pdf(text: str) -> bytes:
    stream = f"BT /F1 14 Tf 72 760 Td ({_pdf_escape(text)}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for off in offsets:
        pdf.extend(f"{off:010} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(pdf)


def _render_label(checkout: Checkout) -> str:
    return f"""
<div class="card border-success">
  <div class="card-body">
    <h3 class="card-title text-success">Payment confirmed</h3>
    <p class="text-secondary mb-2">Shipment <strong>{escape(checkout.shipment_id)}</strong> is ready.</p>
    <p class="text-secondary">Tracking number: <strong>{escape(checkout.tracking_number)}</strong></p>
    <a class="btn btn-primary" href="/label/{checkout.checkout_id}.pdf">Download label PDF</a>
  </div>
</div>
"""


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    """Render checkout page."""
    return HTMLResponse(_render_index())


@app.post("/checkout", response_class=HTMLResponse)
async def checkout(request: Request) -> HTMLResponse:
    """Validate checkout payload and return payment panel."""
    payload = _parse_form(await request.body())
    error = _validate_payload(payload)
    if error:
        return HTMLResponse(_render_error(error), status_code=400)

    checkout_id = uuid4().hex
    checkout_data = Checkout(
        checkout_id=checkout_id,
        provider=payload["provider"],
        recipient_email=payload["recipient_email"],
        recipient_phone=payload["recipient_phone"],
        recipient_address=payload.get("recipient_address", ""),
        recipient_locker=payload.get("recipient_locker", ""),
        sender_email=payload["sender_email"],
        package_size=payload["package_size"],
        insurance_enabled=payload.get("insurance") == "1",
        insurance_amount=_parse_decimal(payload.get("insurance_amount", "0")),
        total_price=_calculate_price(payload),
    )
    checkouts[checkout_id] = checkout_data
    return HTMLResponse(_render_payment(checkout_data))


@app.post("/pay/{checkout_id}", response_class=HTMLResponse)
async def pay(checkout_id: str) -> HTMLResponse:
    """Simulate payment and create a PDF shipment label."""
    checkout_data = checkouts.get(checkout_id)
    if checkout_data is None:
        return HTMLResponse(_render_error("Unknown checkout."), status_code=404)

    if not checkout_data.paid:
        order = DemoOrder(
            order_id=f"order-{checkout_id[:8]}",
            sender_email=checkout_data.sender_email,
            recipient_email=checkout_data.recipient_email,
            recipient_phone=checkout_data.recipient_phone,
            recipient_address=checkout_data.recipient_address,
            recipient_locker=checkout_data.recipient_locker,
            package_size=checkout_data.package_size,
        )
        shipment = await flow.create_shipment(order, checkout_data.provider)
        shipment = await flow.create_label(shipment)
        checkout_data.paid = True
        checkout_data.shipment_id = str(shipment.id)
        checkout_data.tracking_number = str(shipment.tracking_number)
        labels[checkout_id] = _build_pdf(
            f"Label for {shipment.id} / {shipment.tracking_number}"
        )

    return HTMLResponse(_render_label(checkout_data))


@app.get("/label/{checkout_id}.pdf")
async def label_pdf(checkout_id: str) -> Response:
    """Return generated PDF label."""
    payload = labels.get(checkout_id)
    if payload is None:
        return Response(status_code=404)
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="label-{checkout_id}.pdf"',
        },
    )
