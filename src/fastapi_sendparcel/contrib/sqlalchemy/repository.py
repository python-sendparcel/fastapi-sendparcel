"""SQLAlchemy repository implementation."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sendparcel.exceptions import ShipmentNotFoundError

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
            try:
                shipment = result.scalar_one()
                return shipment
            except NoResultFound as e:
                raise ShipmentNotFoundError(shipment_id) from e

    async def create(self, **kwargs) -> ShipmentModel:
        shipment = ShipmentModel(
            id=kwargs.get("id") or str(uuid.uuid4()),
            status=str(kwargs.get("status", "new")),
            provider=kwargs["provider"],
            reference_id=kwargs.get("reference_id", ""),
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
                raise ShipmentNotFoundError(shipment_id)
            shipment.status = status
            for key, value in fields.items():
                if hasattr(shipment, key):
                    setattr(shipment, key, value)
            await session.commit()
            await session.refresh(shipment)
            return shipment

    async def list_by_reference(self, reference_id: str) -> list[ShipmentModel]:
        """List all shipments for a reference."""
        async with self.session_factory() as session:
            stmt = select(ShipmentModel).where(
                ShipmentModel.reference_id == reference_id
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
