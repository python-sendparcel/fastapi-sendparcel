"""SQLAlchemy models for the example app."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, String
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
)


class Base(DeclarativeBase):
    pass


class Shipment(Base):
    """Shipment model with inline address and parcel data."""

    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference_id: Mapped[str] = mapped_column(String(100), default="")

    # Sender address
    sender_name: Mapped[str] = mapped_column(String(255), default="")
    sender_street: Mapped[str] = mapped_column(String(500), default="")
    sender_city: Mapped[str] = mapped_column(String(255), default="")
    sender_postal_code: Mapped[str] = mapped_column(String(20), default="")
    sender_country_code: Mapped[str] = mapped_column(String(2), default="PL")

    # Receiver address
    receiver_name: Mapped[str] = mapped_column(String(255), default="")
    receiver_street: Mapped[str] = mapped_column(String(500), default="")
    receiver_city: Mapped[str] = mapped_column(String(255), default="")
    receiver_postal_code: Mapped[str] = mapped_column(String(20), default="")
    receiver_country_code: Mapped[str] = mapped_column(String(2), default="PL")

    # Parcel dimensions
    weight: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), default=Decimal("1.0")
    )
    width: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), default=Decimal("0.0")
    )
    height: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), default=Decimal("0.0")
    )
    length: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), default=Decimal("0.0")
    )

    # Shipment tracking
    provider: Mapped[str] = mapped_column(String(100), default="")
    tracking_number: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(50), default="new")
    external_id: Mapped[str] = mapped_column(String(255), default="")
    label_url: Mapped[str] = mapped_column(String(500), default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=UTC),
        onupdate=lambda: datetime.now(tz=UTC),
    )


class ShipmentRepository:
    """Async SQLAlchemy repository implementing ShipmentRepository protocol."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, shipment_id: str) -> Shipment:
        result = await self.session.get(Shipment, int(shipment_id))
        if result is None:
            raise KeyError(f"Shipment {shipment_id} not found")
        return result

    async def create(self, **kwargs) -> Shipment:
        shipment = Shipment(
            reference_id=str(kwargs.get("reference_id", "")),
            status=str(kwargs.get("status", "new")),
            provider=str(kwargs.get("provider", "")),
            external_id=str(kwargs.get("external_id", "")),
            tracking_number=str(kwargs.get("tracking_number", "")),
            label_url=str(kwargs.get("label_url", "")),
        )
        self.session.add(shipment)
        await self.session.flush()
        return shipment

    async def save(self, shipment: Shipment) -> Shipment:
        self.session.add(shipment)
        await self.session.flush()
        return shipment

    async def update_status(
        self, shipment_id: str, status: str, **fields
    ) -> Shipment:
        shipment = await self.get_by_id(shipment_id)
        shipment.status = status
        for key, value in fields.items():
            if hasattr(shipment, key):
                setattr(shipment, key, value)
        await self.session.flush()
        return shipment


engine = create_async_engine("sqlite+aiosqlite:///example.db")
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    """Create all tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
