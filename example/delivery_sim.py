"""Fake delivery provider with HTTP simulator endpoints."""

from __future__ import annotations

from typing import Any, ClassVar
from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from sendparcel.fsm import STATUS_TO_CALLBACK
from sendparcel.provider import BaseProvider
from sendparcel.types import (
    LabelInfo,
    ShipmentCreateResult,
    ShipmentStatusResponse,
)

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
    user_selectable: ClassVar[bool] = False

    def _base_url(self) -> str:
        return self.get_setting("simulator_base_url", "http://localhost:8000")

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


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_label_pdf(text: str) -> bytes:
    """Generate a minimal valid PDF with the given text."""
    stream = (f"BT /F1 14 Tf 72 760 Td ({_pdf_escape(text)}) Tj ET").encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R "
            b"/MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 5 0 R >> >> "
            b"/Contents 4 0 R >>"
        ),
        (
            b"<< /Length "
            + str(len(stream)).encode("ascii")
            + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        ),
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
            f"trailer\n<< /Size {len(objects) + 1} "
            f"/Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(pdf)


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
async def sim_get_label(ext_id: str) -> Response:
    """Return a generated PDF label for a simulated shipment."""
    entry = _sim_shipments.get(ext_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Nieznana przesyłka")
    label_text = f"Etykieta przesylki {ext_id}"
    pdf_bytes = _build_label_pdf(label_text)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="label-{ext_id}.pdf"'
        },
    )


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
