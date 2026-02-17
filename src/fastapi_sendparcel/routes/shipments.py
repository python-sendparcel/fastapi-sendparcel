"""Shipment endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from fastapi_sendparcel.config import SendparcelConfig
from fastapi_sendparcel.dependencies import (
    get_config,
    get_flow,
    get_repository,
)
from fastapi_sendparcel.schemas import CreateShipmentRequest, ShipmentResponse

router = APIRouter()


@router.get("/shipments/health")
async def shipments_health() -> dict[str, str]:
    """Healthcheck endpoint for shipment routes."""
    return {"status": "ok"}


@router.post("/shipments", response_model=ShipmentResponse)
async def create_shipment(
    body: CreateShipmentRequest,
    flow=Depends(get_flow),
    config: SendparcelConfig = Depends(get_config),
) -> ShipmentResponse:
    """Create a shipment via ShipmentFlow.

    Requires ``sender_address``, ``receiver_address``, and ``parcels``.
    Optionally accepts ``reference_id`` for external reference tracking.
    """
    provider_slug = body.provider or config.default_provider

    if (
        body.sender_address is not None
        and body.receiver_address is not None
        and body.parcels is not None
    ):
        shipment = await flow.create_shipment(
            provider_slug,
            sender_address=body.sender_address,
            receiver_address=body.receiver_address,
            parcels=body.parcels,
        )
    else:
        raise HTTPException(
            status_code=400,
            detail=(
                "Provide 'sender_address', 'receiver_address', and 'parcels'"
            ),
        )

    return ShipmentResponse.from_shipment(shipment)


@router.post("/shipments/{shipment_id}/label", response_model=ShipmentResponse)
async def create_label(
    shipment_id: str,
    flow=Depends(get_flow),
    repository=Depends(get_repository),
) -> ShipmentResponse:
    """Create shipment label via provider."""
    shipment = await repository.get_by_id(shipment_id)
    shipment = await flow.create_label(shipment)
    return ShipmentResponse.from_shipment(shipment)


@router.get("/shipments/{shipment_id}/status", response_model=ShipmentResponse)
async def fetch_status(
    shipment_id: str,
    flow=Depends(get_flow),
    repository=Depends(get_repository),
) -> ShipmentResponse:
    """Fetch and persist latest provider shipment status."""
    shipment = await repository.get_by_id(shipment_id)
    shipment = await flow.fetch_and_update_status(shipment)
    return ShipmentResponse.from_shipment(shipment)
