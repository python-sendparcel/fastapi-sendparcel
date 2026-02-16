"""SQLAlchemy repository implementation."""

from __future__ import annotations

import uuid

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
        order = kwargs.pop("order", None)
        if order is not None and "order_id" not in kwargs:
            kwargs["order_id"] = str(getattr(order, "id", order))
        shipment = ShipmentModel(
            id=kwargs.get("id") or str(uuid.uuid4()),
            status=str(kwargs.get("status", "new")),
            provider=kwargs["provider"],
            order_id=kwargs.get("order_id", ""),
        )
        async with self.session_factory() as session:
            session.add(shipment)
            await session.commit()
            await session.refresh(shipment)
        return shipment

    async def save(self, shipment: ShipmentModel) -> ShipmentModel:
        async with self.session_factory() as session:
            merged = await session.merge(shipment)
            await session.commit()
            await session.refresh(merged)
            return merged

    async def update_status(
        self, shipment_id: str, status: str, **fields
    ) -> ShipmentModel:
        async with self.session_factory() as session:
            shipment = await session.get(ShipmentModel, shipment_id)
            if shipment is None:
                raise KeyError(shipment_id)
            shipment.status = status
            for key, value in fields.items():
                if hasattr(shipment, key):
                    setattr(shipment, key, value)
            await session.commit()
            await session.refresh(shipment)
            return shipment

    async def list_by_order(self, order_id: str) -> list[ShipmentModel]:
        """List all shipments for an order."""
        async with self.session_factory() as session:
            stmt = select(ShipmentModel).where(
                ShipmentModel.order_id == order_id
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
