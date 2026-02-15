"""SQLAlchemy shipment/retry models."""

from __future__ import annotations

from sqlalchemy import JSON, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""


class ShipmentModel(Base):
    """Minimal shipment persistence model."""

    __tablename__ = "sendparcel_shipments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default="new")
    provider: Mapped[str] = mapped_column(String(64))
    external_id: Mapped[str] = mapped_column(String(128), default="")
    tracking_number: Mapped[str] = mapped_column(String(128), default="")
    label_url: Mapped[str] = mapped_column(String(512), default="")


class CallbackRetryModel(Base):
    """Queued callback retry payload."""

    __tablename__ = "sendparcel_callback_retries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    payload: Mapped[dict] = mapped_column(JSON)
