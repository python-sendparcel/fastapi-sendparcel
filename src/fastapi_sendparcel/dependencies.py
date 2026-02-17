"""Dependency providers for request handlers."""

from __future__ import annotations

from fastapi import Request
from sendparcel.flow import ShipmentFlow
from sendparcel.protocols import ShipmentRepository

from fastapi_sendparcel.config import SendparcelConfig
from fastapi_sendparcel.protocols import CallbackRetryStore
from fastapi_sendparcel.registry import FastAPIPluginRegistry


def get_config(request: Request) -> SendparcelConfig:
    """Read config from FastAPI app state."""
    return request.app.state.sendparcel_config


def get_repository(request: Request) -> ShipmentRepository:
    """Read repository from FastAPI app state."""
    return request.app.state.sendparcel_repository


def get_registry(request: Request) -> FastAPIPluginRegistry:
    """Read plugin registry from FastAPI app state."""
    return request.app.state.sendparcel_registry


def get_retry_store(request: Request) -> CallbackRetryStore | None:
    """Read retry store from FastAPI app state."""
    return getattr(request.app.state, "sendparcel_retry_store", None)


def get_flow(request: Request) -> ShipmentFlow:
    """Create ShipmentFlow for the current request."""
    config = get_config(request)
    repository = get_repository(request)
    return ShipmentFlow(repository=repository, config=config.providers)
