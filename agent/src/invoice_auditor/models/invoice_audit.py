"""SQLAlchemy model for invoice audit records."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CHAR,
    Date,
    DateTime,
    Numeric,
    String,
    Text,
    CheckConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from invoice_auditor.db.base import Base


class InvoiceAudit(Base):
    """Persisted audit record for an invoice."""

    __tablename__ = "invoice_audit"
    __table_args__ = (
        CheckConstraint(
            "translation_confidence IS NULL OR "
            "translation_confidence BETWEEN 0 AND 1",
            name="chk_translation_confidence",
        ),
        CheckConstraint(
            "validation_status IN "
            "('pending', 'passed', 'failed', 'partial')",
            name="chk_validation_status",
        ),
        CheckConstraint(
            "recommendation IS NULL OR "
            "recommendation IN ('approve', 'review', 'reject')",
            name="chk_recommendation",
        ),
        {"schema": "audit"},
    )

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    file_path: Mapped[str] = mapped_column(
        String(512), nullable=False
    )
    file_checksum: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        unique=True,
    )
    extraction_method: Mapped[str | None] = mapped_column(String(32))
    raw_extracted_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    processing_error: Mapped[str | None] = mapped_column(Text)
    translated_text: Mapped[str | None] = mapped_column(Text)
    source_language: Mapped[str | None] = mapped_column(String(8))
    translation_confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(4, 3)
    )
    invoice_number: Mapped[str | None] = mapped_column(String(64))
    vendor_id: Mapped[str | None] = mapped_column(String(64))
    vendor_name: Mapped[str | None] = mapped_column(String(255))
    po_number: Mapped[str | None] = mapped_column(String(64))
    invoice_date: Mapped[date | None] = mapped_column(Date)
    currency: Mapped[str | None] = mapped_column(CHAR(3))
    total_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2)
    )
    validation_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )
    recommendation: Mapped[str | None] = mapped_column(String(32))
    extracted_raw: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    thread_id: Mapped[str | None] = mapped_column(String(128))
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )