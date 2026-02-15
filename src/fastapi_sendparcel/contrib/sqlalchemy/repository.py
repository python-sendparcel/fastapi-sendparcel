"""SQLAlchemy repository implementation."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fastapi_sendparcel.contrib.sqlalchemy.models import ShipmentModel


class SQLAlchemyShipmentRepository:
    """Shipment repository backed by SQLAlchemy async sessions."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        self.session_factory = session_factory

    async def get_by_id(self, shipment_id: str) -> ShipmentModel:
        async with self.session_factory() as session:
            result = await session.execute(
                select(ShipmentModel).where(ShipmentModel.id == shipment_id)
            )
            shipment = result.scalar_one()
            return shipment

    async def create(self, **kwargs) -> ShipmentModel:
        shipment = ShipmentModel(
            id=kwargs.get("id", ""),
            status=str(kwargs.get("status", "new")),
            provider=kwargs["provider"],
        )
        async with self.session_factory() as session:
            session.add(shipment)
            await session.commit()
            await session.refresh(shipment)
        return shipment

    async def save(self, shipment: ShipmentModel) -> ShipmentModel:
        async with self.session_factory() as session:
            session.add(shipment)
            await session.commit()
            await session.refresh(shipment)
        return shipment

    async def update_status(
        self, shipment_id: str, status: str, **fields
    ) -> ShipmentModel:
        shipment = await self.get_by_id(shipment_id)
        shipment.status = status
        for key, value in fields.items():
            setattr(shipment, key, value)
        return await self.save(shipment)
