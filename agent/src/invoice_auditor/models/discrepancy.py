"""SQLAlchemy model for invoice discrepancies."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from invoice_auditor.db.base import Base


class Discrepancy(Base):
    """A mismatch detected during invoice validation."""

    __tablename__ = "discrepancies"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="chk_discrepancy_severity",
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
    field_name: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    invoice_value: Mapped[str | None] = mapped_column(Text)
    erp_value: Mapped[str | None] = mapped_column(Text)
    deviation_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    severity: Mapped[str] = mapped_column(
        String(16), nullable=False
    )
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )