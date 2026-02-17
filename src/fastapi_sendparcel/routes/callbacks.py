"""Callback endpoints."""

from __future__ import annotations

import logging
from json import JSONDecodeError

from fastapi import APIRouter, Depends, Request
from sendparcel.exceptions import CommunicationError, InvalidCallbackError

from fastapi_sendparcel.dependencies import (
    get_flow,
    get_repository,
    get_retry_store,
)
from fastapi_sendparcel.schemas import CallbackResponse

logger = logging.getLogger(__name__)

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
        raise InvalidCallbackError("Provider slug mismatch")

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
    except InvalidCallbackError:
        # Bad callback data — do NOT enqueue retry, re-raise for 400 handler
        raise
    except CommunicationError as exc:
        # Transient failure — enqueue for retry, then re-raise for 502 handler
        if retry_store is not None:
            retry_payload = dict(payload)
            retry_payload["_raw_body"] = raw_body.decode("utf-8")
            await retry_store.store_failed_callback(
                shipment_id=shipment_id,
                provider_slug=provider_slug,
                payload=retry_payload,
                headers=headers,
            )
            logger.warning(
                "Callback for shipment %s failed, queued for retry: %s",
                shipment_id,
                exc,
            )
        raise

    return CallbackResponse(
        provider=provider_slug,
        status="accepted",
        shipment_status=str(updated.status),
    )
