"""Router tests."""

from fastapi import APIRouter, FastAPI
from sendparcel.exceptions import CommunicationError

from fastapi_sendparcel.config import SendparcelConfig
from fastapi_sendparcel.router import create_shipping_router


class _Repo:
    async def get_by_id(self, shipment_id: str):
        raise NotImplementedError

    async def create(self, **kwargs):
        raise NotImplementedError

    async def save(self, shipment):
        raise NotImplementedError

    async def update_status(self, shipment_id: str, status: str, **fields):
        raise NotImplementedError


def test_create_shipping_router_returns_apirouter() -> None:
    router = create_shipping_router(
        config=SendparcelConfig(default_provider="dummy"),
        repository=_Repo(),
    )

    assert isinstance(router, APIRouter)


async def test_exception_handlers_registered_after_lifespan() -> None:
    """Exception handlers should be registered when the router lifespan runs."""
    app = FastAPI()
    router = create_shipping_router(
        config=SendparcelConfig(default_provider="dummy"),
        repository=_Repo(),
    )
    app.include_router(router)

    # Before startup, no exception handlers for CommunicationError
    async with app.router.lifespan_context(app) as _:
        handlers = app.exception_handlers
        assert CommunicationError in handlers
