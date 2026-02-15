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
    """Storage abstraction for failed callback retries."""

    async def enqueue(self, payload: dict) -> None: ...
