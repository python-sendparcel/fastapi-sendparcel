"""Router factory for fastapi-sendparcel."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from sendparcel.protocols import ShipmentRepository

from fastapi_sendparcel.config import SendparcelConfig
from fastapi_sendparcel.exceptions import register_exception_handlers
from fastapi_sendparcel.protocols import CallbackRetryStore, OrderResolver
from fastapi_sendparcel.registry import FastAPIPluginRegistry
from fastapi_sendparcel.routes.callbacks import router as callbacks_router
from fastapi_sendparcel.routes.shipments import router as shipments_router


def create_shipping_router(
    *,
    config: SendparcelConfig,
    repository: ShipmentRepository,
    registry: FastAPIPluginRegistry | None = None,
    order_resolver: OrderResolver | None = None,
    retry_store: CallbackRetryStore | None = None,
) -> APIRouter:
    """Create a configured API router."""
    actual_registry = registry or FastAPIPluginRegistry()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        app.state.sendparcel_config = config
        app.state.sendparcel_repository = repository
        app.state.sendparcel_registry = actual_registry
        app.state.sendparcel_order_resolver = order_resolver
        app.state.sendparcel_retry_store = retry_store
        register_exception_handlers(app)
        actual_registry.discover()
        yield

    router = APIRouter(lifespan=lifespan)
    router.include_router(shipments_router)
    router.include_router(callbacks_router)
    return router
