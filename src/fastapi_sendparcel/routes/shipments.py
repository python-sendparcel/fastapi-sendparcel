"""Shipment endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from fastapi_sendparcel.config import SendparcelConfig
from fastapi_sendparcel.dependencies import (
    get_config,
    get_flow,
    get_order_resolver,
    get_repository,
)
from fastapi_sendparcel.protocols import OrderResolver
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
    order_resolver: OrderResolver | None = Depends(get_order_resolver),
) -> ShipmentResponse:
    """Create a shipment via ShipmentFlow."""
    if order_resolver is None:
        raise HTTPException(
            status_code=500,
            detail="Order resolver not configured",
        )

    provider_slug = body.provider or config.default_provider
    order = await order_resolver.resolve(body.order_id)
    shipment = await flow.create_shipment(order, provider_slug)
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
