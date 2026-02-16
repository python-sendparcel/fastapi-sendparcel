"""SQLAlchemy models for the example app."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from fastapi_sendparcel.contrib.sqlalchemy.models import Base
from sendparcel.types import AddressInfo, ParcelInfo


class OrderModel(Base):
    """Order stored in SQLite via SQLAlchemy.

    Implements the ``sendparcel.protocols.Order`` protocol.
    """

    __tablename__ = "example_orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    description: Mapped[str] = mapped_column(String(255), default="")
    total_weight: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), default=Decimal("1.0")
    )

    # Sender fields
    sender_name: Mapped[str] = mapped_column(String(128), default="")
    sender_email: Mapped[str] = mapped_column(String(128), default="")
    sender_phone: Mapped[str] = mapped_column(String(32), default="")
    sender_line1: Mapped[str] = mapped_column(String(255), default="")
    sender_city: Mapped[str] = mapped_column(String(128), default="")
    sender_postal_code: Mapped[str] = mapped_column(String(16), default="")
    sender_country_code: Mapped[str] = mapped_column(String(2), default="PL")

    # Recipient fields
    recipient_name: Mapped[str] = mapped_column(String(128), default="")
    recipient_email: Mapped[str] = mapped_column(String(128), default="")
    recipient_phone: Mapped[str] = mapped_column(String(32), default="")
    recipient_line1: Mapped[str] = mapped_column(String(255), default="")
    recipient_city: Mapped[str] = mapped_column(String(128), default="")
    recipient_postal_code: Mapped[str] = mapped_column(String(16), default="")
    recipient_country_code: Mapped[str] = mapped_column(String(2), default="PL")

    def get_total_weight(self) -> Decimal:
        return self.total_weight

    def get_parcels(self) -> list[ParcelInfo]:
        return [ParcelInfo(weight_kg=self.total_weight)]

    def get_sender_address(self) -> AddressInfo:
        return AddressInfo(
            name=self.sender_name,
            email=self.sender_email,
            phone=self.sender_phone,
            line1=self.sender_line1,
            city=self.sender_city,
            postal_code=self.sender_postal_code,
            country_code=self.sender_country_code,
        )

    def get_receiver_address(self) -> AddressInfo:
        return AddressInfo(
            name=self.recipient_name,
            email=self.recipient_email,
            phone=self.recipient_phone,
            line1=self.recipient_line1,
            city=self.recipient_city,
            postal_code=self.recipient_postal_code,
            country_code=self.recipient_country_code,
        )
