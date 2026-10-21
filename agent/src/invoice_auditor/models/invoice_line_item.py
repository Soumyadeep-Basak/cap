"""SQLAlchemy model for invoice line items."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from invoice_auditor.db.base import Base


class InvoiceLineItem(Base):
    """An extracted line item belonging to an invoice."""

    __tablename__ = "invoice_line_items"
    __table_args__ = (
        UniqueConstraint(
            "invoice_id",
            "line_number",
            name="uq_invoice_line_number",
        ),
        {"schema": "audit"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    invoice_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("audit.invoice_audit.invoice_id"),
        nullable=False,
    )
    line_number: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    item_code: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    line_total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))