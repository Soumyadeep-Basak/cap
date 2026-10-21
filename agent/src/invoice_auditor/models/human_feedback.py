"""SQLAlchemy model for human auditor corrections."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from invoice_auditor.db.base import Base


class HumanFeedback(Base):
    """Records corrections without overwriting extracted values."""

    __tablename__ = "human_feedback"
    __table_args__ = {"schema": "audit"}

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
    original_value: Mapped[str | None] = mapped_column(Text)
    corrected_value: Mapped[str] = mapped_column(
        Text, nullable=False
    )
    corrected_by: Mapped[str] = mapped_column(
        String(128), nullable=False
    )
    corrected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    revalidated: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("FALSE"),
    )