"""Webhook retry mechanism with exponential backoff."""

import logging
from datetime import UTC, datetime, timedelta

from sendparcel.exceptions import ShipmentNotFoundError
from sendparcel.flow import ShipmentFlow
from sendparcel.protocols import ShipmentRepository

from fastapi_sendparcel.config import SendparcelConfig
from fastapi_sendparcel.protocols import CallbackRetryStore

logger = logging.getLogger(__name__)


def compute_next_retry_at(
    attempt: int,
    backoff_seconds: int,
) -> datetime:
    """Compute the next retry time with exponential backoff.

    delay = backoff_seconds * 2^(attempt - 1)
    """
    delay = backoff_seconds * (2 ** (attempt - 1))
    return datetime.now(tz=UTC) + timedelta(seconds=delay)


async def process_due_retries(
    *,
    retry_store: CallbackRetryStore,
    repository: ShipmentRepository,
    config: SendparcelConfig,
) -> int:
    """Process all due callback retries.

    Returns the number of retries processed.
    """
    retries = await retry_store.get_due_retries(limit=10)
    processed = 0

    for retry in retries:
        retry_id = retry["id"]
        shipment_id = retry["shipment_id"]
        payload = retry["payload"]
        headers = retry["headers"]
        attempts = retry["attempts"]

        if attempts >= config.retry_max_attempts:
            logger.warning(
                "Retry exhausted for shipment %s after %d attempts",
                shipment_id,
                attempts,
            )
            await retry_store.mark_exhausted(retry_id)
            processed += 1
            continue

        try:
            shipment = await repository.get_by_id(shipment_id)
        except ShipmentNotFoundError:
            logger.error(
                "Retry %s: shipment %s not found, marking exhausted",
                retry_id,
                shipment_id,
            )
            await retry_store.mark_exhausted(retry_id)
            processed += 1
            continue

        flow = ShipmentFlow(
            repository=repository,
            config=config.providers,
        )
        raw_body = payload.get("_raw_body")
        callback_kwargs = (
            {"raw_body": raw_body.encode("utf-8")}
            if raw_body is not None
            else {}
        )

        try:
            await flow.handle_callback(
                shipment=shipment,
                data=payload,
                headers=headers,
                **callback_kwargs,
            )
            await retry_store.mark_succeeded(retry_id)
            logger.info(
                "Retry %s: callback for shipment %s succeeded",
                retry_id,
                shipment_id,
            )
        except Exception as exc:
            new_attempts = attempts + 1
            if new_attempts >= config.retry_max_attempts:
                logger.warning(
                    "Retry exhausted for shipment %s after %d attempts: %s",
                    shipment_id,
                    new_attempts,
                    exc,
                )
                await retry_store.mark_failed(
                    retry_id,
                    error=str(exc),
                )
                await retry_store.mark_exhausted(retry_id)
            else:
                await retry_store.mark_failed(
                    retry_id,
                    error=str(exc),
                )
                logger.info(
                    "Retry %s: attempt %d failed: %s",
                    retry_id,
                    new_attempts,
                    exc,
                )

        processed += 1

    return processed
