"""FastAPI adapter public API."""

from typing import TYPE_CHECKING

__version__ = "0.1.0"

__all__ = [
    "CallbackRetryStore",
    "FastAPIPluginRegistry",
    "SendparcelConfig",
    "ShipmentNotFoundError",
    "__version__",
    "create_shipping_router",
    "register_exception_handlers",
]

if TYPE_CHECKING:
    from fastapi_sendparcel.config import SendparcelConfig
    from fastapi_sendparcel.exceptions import (
        ShipmentNotFoundError,
        register_exception_handlers,
    )
    from fastapi_sendparcel.protocols import CallbackRetryStore
    from fastapi_sendparcel.registry import FastAPIPluginRegistry
    from fastapi_sendparcel.router import create_shipping_router


def __getattr__(name: str):
    # Lazy imports to avoid loading all submodules on package import.
    if name == "SendparcelConfig":
        from fastapi_sendparcel.config import SendparcelConfig

        return SendparcelConfig
    if name == "create_shipping_router":
        from fastapi_sendparcel.router import create_shipping_router

        return create_shipping_router
    if name == "FastAPIPluginRegistry":
        from fastapi_sendparcel.registry import FastAPIPluginRegistry

        return FastAPIPluginRegistry
    if name in ("ShipmentNotFoundError", "register_exception_handlers"):
        from fastapi_sendparcel import exceptions

        return getattr(exceptions, name)
    if name == "CallbackRetryStore":
        from fastapi_sendparcel import protocols

        return getattr(protocols, name)
    raise AttributeError(
        f"module 'fastapi_sendparcel' has no attribute {name!r}"
    )
