"""Purchase order ORM models."""

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Integer,
    Numeric,
    String,
    CHAR,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from mock_erp.db.base import Base


class PurchaseOrder(Base):
    """Represents a purchase order."""

    __tablename__ = "purchase_orders"
    __table_args__ = {"schema": "erp"}

    po_number: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
    )
    vendor_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("erp.vendors.vendor_id"),
        nullable=False,
    )


class POLineItem(Base):
    """Represents an item in a purchase order."""

    __tablename__ = "po_line_items"
    __table_args__ = (
        UniqueConstraint(
            "po_number",
            "line_number",
            name="uq_po_line_number",
        ),
        {"schema": "erp"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    po_number: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("erp.purchase_orders.po_number"),
        nullable=False,
    )
    line_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    item_code: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("erp.sku_master.item_code"),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    quantity: Mapped[float] = mapped_column(
        Numeric(12, 3),
        nullable=False,
    )
    unit_price: Mapped[float] = mapped_column(
        Numeric(14, 4),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        CHAR(3),
        nullable=False,
    )
