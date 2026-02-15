"""FastAPI adapter public API."""

from fastapi_sendparcel.config import SendparcelConfig
from fastapi_sendparcel.registry import FastAPIPluginRegistry
from fastapi_sendparcel.router import create_shipping_router

__all__ = [
    "FastAPIPluginRegistry",
    "SendparcelConfig",
    "create_shipping_router",
]
