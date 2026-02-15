"""Callback endpoints."""

from __future__ import annotations

from json import JSONDecodeError

from fastapi import APIRouter, Depends, HTTPException, Request
from sendparcel.exceptions import InvalidCallbackError

from fastapi_sendparcel.dependencies import (
    get_flow,
    get_repository,
    get_retry_store,
)
from fastapi_sendparcel.retry import enqueue_callback_retry
from fastapi_sendparcel.schemas import CallbackResponse

router = APIRouter()


@router.post(
    "/callbacks/{provider_slug}/{shipment_id}",
    response_model=CallbackResponse,
)
async def provider_callback(
    provider_slug: str,
    shipment_id: str,
    request: Request,
    flow=Depends(get_flow),
    repository=Depends(get_repository),
    retry_store=Depends(get_retry_store),
) -> CallbackResponse:
    """Handle provider callback using core flow and retry hooks."""
    shipment = await repository.get_by_id(shipment_id)
    if str(shipment.provider) != provider_slug:
        raise HTTPException(status_code=400, detail="Provider slug mismatch")

    raw_body = await request.body()
    try:
        payload = await request.json()
    except JSONDecodeError:
        payload = {}
    headers = dict(request.headers)

    try:
        updated = await flow.handle_callback(
            shipment,
            payload,
            headers,
            raw_body=raw_body,
        )
    except InvalidCallbackError as exc:
        await enqueue_callback_retry(
            retry_store,
            provider_slug=provider_slug,
            shipment_id=shipment_id,
            payload=payload,
            headers=headers,
            reason=str(exc),
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        await enqueue_callback_retry(
            retry_store,
            provider_slug=provider_slug,
            shipment_id=shipment_id,
            payload=payload,
            headers=headers,
            reason=str(exc),
        )
        raise HTTPException(
            status_code=502,
            detail="Callback handling failed",
        ) from exc

    return CallbackResponse(
        provider=provider_slug,
        status="accepted",
        shipment_status=str(updated.status),
    )
