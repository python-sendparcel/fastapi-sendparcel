"""FastAPI adapter protocol extensions."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = [
    "CallbackRetryStore",
]


@runtime_checkable
class CallbackRetryStore(Protocol):
    """Storage abstraction for the webhook retry queue.

    Full lifecycle: store -> get_due ->
    mark_succeeded / mark_failed / mark_exhausted.
    """

    async def store_failed_callback(
        self,
        shipment_id: str,
        provider_slug: str,
        payload: dict[str, Any],
        headers: dict[str, Any],
    ) -> str:
        """Store a failed callback for later retry. Returns retry ID."""
        ...

    async def get_due_retries(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get retries that are due for processing."""
        ...

    async def mark_succeeded(self, retry_id: str) -> None:
        """Mark a retry as successfully processed."""
        ...

    async def mark_failed(self, retry_id: str, error: str) -> None:
        """Mark a retry as failed and schedule next attempt."""
        ...

    async def mark_exhausted(self, retry_id: str) -> None:
        """Mark a retry as exhausted (dead letter)."""
        ...
