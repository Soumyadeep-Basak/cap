"""Vendor ORM model."""

from sqlalchemy import Boolean, CHAR, String, TIMESTAMP, text
from sqlalchemy.orm import Mapped, mapped_column

from mock_erp.db.base import Base


class Vendor(Base):
    """Represents a vendor in the ERP system."""

    __tablename__ = "vendors"
    __table_args__ = {"schema": "erp"}

    vendor_id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
    )
    vendor_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    country: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        CHAR(3),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("TRUE"),
    )
    created_at: Mapped[object] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=text("NOW()"),
    )