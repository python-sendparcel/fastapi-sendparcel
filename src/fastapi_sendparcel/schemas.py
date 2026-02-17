"""Request/response schemas for HTTP endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class CreateShipmentRequest(BaseModel):
    """Payload for shipment creation.

    The ``sender_address``, ``receiver_address``, and ``parcels`` fields
    are required for creating a shipment.  An optional ``reference_id``
    can be provided for external reference tracking.
    """

    reference_id: str | None = None
    provider: str | None = None
    sender_address: dict | None = None
    receiver_address: dict | None = None
    parcels: list[dict] | None = None


class ShipmentResponse(BaseModel):
    """Serialized shipment response payload."""

    id: str
    status: str
    provider: str
    external_id: str
    tracking_number: str
    label_url: str

    @classmethod
    def from_shipment(cls, shipment) -> ShipmentResponse:
        return cls(
            id=str(shipment.id),
            status=str(shipment.status),
            provider=str(shipment.provider),
            external_id=str(shipment.external_id),
            tracking_number=str(shipment.tracking_number),
            label_url=str(shipment.label_url),
        )


class CallbackResponse(BaseModel):
    """Callback handling response payload."""

    provider: str
    status: str
    shipment_status: str
