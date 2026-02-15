"""FastAPI adapter protocol extensions."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from sendparcel.protocols import Order


@runtime_checkable
class OrderResolver(Protocol):
    """Resolves order IDs to core Order objects."""

    async def resolve(self, order_id: str) -> Order: ...


@runtime_checkable
class CallbackRetryStore(Protocol):
    """Storage abstraction for the webhook retry queue."""

    async def store_failed_callback(
        self,
        shipment_id: str,
        payload: dict,
        headers: dict,
    ) -> str: ...

    async def get_due_retries(self, limit: int = 10) -> list[dict]: ...

    async def mark_succeeded(self, retry_id: str) -> None: ...

    async def mark_failed(
        self,
        retry_id: str,
        error: str,
    ) -> None: ...

    async def mark_exhausted(self, retry_id: str) -> None: ...
