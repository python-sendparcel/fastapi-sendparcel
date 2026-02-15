"""Retry queue helpers for failed callbacks."""

from __future__ import annotations

from datetime import UTC, datetime

import anyio

from fastapi_sendparcel.protocols import CallbackRetryStore


async def enqueue_callback_retry(
    store: CallbackRetryStore | None,
    *,
    provider_slug: str,
    shipment_id: str,
    payload: dict,
    headers: dict[str, str],
    reason: str,
) -> None:
    """Persist callback retry payload when a retry store is configured."""
    await anyio.sleep(0)
    if store is None:
        return

    await store.enqueue(
        {
            "provider": provider_slug,
            "shipment_id": shipment_id,
            "payload": payload,
            "headers": headers,
            "reason": reason,
            "queued_at": datetime.now(tz=UTC).isoformat(),
        }
    )
