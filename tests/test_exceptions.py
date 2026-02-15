"""Exception handler tests."""

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sendparcel.exceptions import (
    CommunicationError,
    InvalidCallbackError,
    InvalidTransitionError,
    SendParcelException,
)

from fastapi_sendparcel.exceptions import (
    ShipmentNotFoundError,
    register_exception_handlers,
)


def _create_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    return app


def test_shipment_not_found_error_has_shipment_id() -> None:
    exc = ShipmentNotFoundError("ship-42")
    assert exc.shipment_id == "ship-42"
    assert "ship-42" in str(exc)


def test_communication_error_returns_502() -> None:
    app = _create_app()

    @app.get("/boom")
    async def boom():
        raise CommunicationError("provider timeout")

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/boom")
    assert resp.status_code == 502
    body = resp.json()
    assert body["detail"] == "provider timeout"
    assert body["code"] == "communication_error"


def test_invalid_callback_returns_400() -> None:
    app = _create_app()

    @app.get("/boom")
    async def boom():
        raise InvalidCallbackError("bad signature")

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/boom")
    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"] == "bad signature"
    assert body["code"] == "invalid_callback"


def test_invalid_transition_returns_409() -> None:
    app = _create_app()

    @app.get("/boom")
    async def boom():
        raise InvalidTransitionError("cannot cancel")

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/boom")
    assert resp.status_code == 409
    body = resp.json()
    assert body["detail"] == "cannot cancel"
    assert body["code"] == "invalid_transition"


def test_shipment_not_found_returns_404() -> None:
    app = _create_app()

    @app.get("/boom")
    async def boom():
        raise ShipmentNotFoundError("ship-99")

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/boom")
    assert resp.status_code == 404
    body = resp.json()
    assert body["detail"] == "Shipment ship-99 not found"
    assert body["code"] == "not_found"


def test_generic_sendparcel_exception_returns_400() -> None:
    app = _create_app()

    @app.get("/boom")
    async def boom():
        raise SendParcelException("something broke")

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/boom")
    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"] == "something broke"
    assert body["code"] == "shipment_error"
