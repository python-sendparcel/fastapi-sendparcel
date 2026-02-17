"""Exception handlers mapping sendparcel-core exceptions to HTTP responses."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sendparcel.exceptions import (
    CommunicationError,
    InvalidCallbackError,
    InvalidTransitionError,
    SendParcelException,
    ShipmentNotFoundError,
)


def register_exception_handlers(app: FastAPI) -> None:
    """Register sendparcel exception handlers on a FastAPI app.

    More specific handlers must be registered first so FastAPI
    matches them before the generic SendParcelException handler.

    Handler order (most specific first):
    1. ShipmentNotFoundError → 404
    2. CommunicationError → 502
    3. InvalidCallbackError → 400
    4. InvalidTransitionError → 409
    5. SendParcelException → 400 (catch-all)
    """

    @app.exception_handler(ShipmentNotFoundError)
    async def _not_found(
        request: Request,
        exc: ShipmentNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={
                "detail": str(exc),
                "code": "shipment_not_found",
            },
        )

    @app.exception_handler(CommunicationError)
    async def _communication_error(
        request: Request,
        exc: CommunicationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content={
                "detail": str(exc),
                "code": "communication_error",
            },
        )

    @app.exception_handler(InvalidCallbackError)
    async def _invalid_callback(
        request: Request,
        exc: InvalidCallbackError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={
                "detail": str(exc),
                "code": "invalid_callback",
            },
        )

    @app.exception_handler(InvalidTransitionError)
    async def _invalid_transition(
        request: Request,
        exc: InvalidTransitionError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={
                "detail": str(exc),
                "code": "invalid_transition",
            },
        )

    @app.exception_handler(SendParcelException)
    async def _sendparcel_error(
        request: Request,
        exc: SendParcelException,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={
                "detail": str(exc),
                "code": "shipment_error",
            },
        )
