"""Pydantic schema tests."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi_sendparcel.schemas import (
    CallbackResponse,
    CreateShipmentRequest,
    ShipmentResponse,
)


class TestCreateShipmentRequest:
    def test_empty_request_is_valid(self) -> None:
        """All fields are optional — empty request is valid (route handles validation)."""
        req = CreateShipmentRequest()
        assert req.reference_id is None
        assert req.provider is None
        assert req.sender_address is None
        assert req.receiver_address is None
        assert req.parcels is None

    def test_reference_id_set(self) -> None:
        req = CreateShipmentRequest(reference_id="ref-1")
        assert req.reference_id == "ref-1"
        assert req.provider is None

    def test_provider_set(self) -> None:
        req = CreateShipmentRequest(reference_id="ref-1", provider="dhl")
        assert req.provider == "dhl"

    def test_direct_request(self) -> None:
        req = CreateShipmentRequest(
            sender_address={"country_code": "PL"},
            receiver_address={"country_code": "DE"},
            parcels=[{"weight_kg": "1.0"}],
        )
        assert req.reference_id is None
        assert req.sender_address == {"country_code": "PL"}
        assert req.receiver_address == {"country_code": "DE"}
        assert req.parcels == [{"weight_kg": "1.0"}]


class TestShipmentResponse:
    def test_from_shipment(self) -> None:
        shipment = SimpleNamespace(
            id="s-1",
            status="created",
            provider="dummy",
            external_id="ext-1",
            tracking_number="trk-1",
            label_url="https://labels/s-1.pdf",
        )
        resp = ShipmentResponse.from_shipment(shipment)
        assert resp.id == "s-1"
        assert resp.status == "created"
        assert resp.provider == "dummy"
        assert resp.external_id == "ext-1"
        assert resp.tracking_number == "trk-1"
        assert resp.label_url == "https://labels/s-1.pdf"

    def test_all_fields(self) -> None:
        resp = ShipmentResponse(
            id="s-2",
            status="label_ready",
            provider="inpost",
            external_id="ext-2",
            tracking_number="trk-2",
            label_url="",
        )
        assert resp.id == "s-2"
        assert resp.label_url == ""


class TestCallbackResponse:
    def test_all_fields(self) -> None:
        resp = CallbackResponse(
            provider="dummy",
            status="accepted",
            shipment_status="in_transit",
        )
        assert resp.provider == "dummy"
        assert resp.status == "accepted"
        assert resp.shipment_status == "in_transit"

    def test_serialization(self) -> None:
        resp = CallbackResponse(
            provider="dummy",
            status="accepted",
            shipment_status="delivered",
        )
        data = resp.model_dump()
        assert data == {
            "provider": "dummy",
            "status": "accepted",
            "shipment_status": "delivered",
        }
