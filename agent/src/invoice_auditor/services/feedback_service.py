"""Database operations for human-in-the-loop feedback and corrections."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_auditor.models.human_feedback import HumanFeedback
from invoice_auditor.models.invoice_audit import InvoiceAudit


def record_feedback(
    db: Session,
    invoice_id: uuid.UUID,
    field_name: str,
    original_value: str | None,
    corrected_value: str,
    corrected_by: str,
) -> HumanFeedback:
    """Record a human correction without overwriting extracted values.

    The original extraction and the human intervention remain fully
    traceable: this only inserts a new ``human_feedback`` row and
    never mutates ``invoice_audit`` or ``invoice_line_items``.
    """
    if db.get(InvoiceAudit, invoice_id) is None:
        raise ValueError(f"Invoice audit record not found: {invoice_id}")

    feedback = HumanFeedback(
        invoice_id=invoice_id,
        field_name=field_name,
        original_value=original_value,
        corrected_value=corrected_value,
        corrected_by=corrected_by,
    )

    try:
        db.add(feedback)
        db.commit()
        db.refresh(feedback)
        return feedback
    except Exception:
        db.rollback()
        raise


def list_feedback(
    db: Session,
    invoice_id: uuid.UUID,
    *,
    only_pending: bool = False,
) -> list[HumanFeedback]:
    """List recorded feedback for an invoice, oldest first."""
    statement = (
        select(HumanFeedback)
        .where(HumanFeedback.invoice_id == invoice_id)
        .order_by(HumanFeedback.corrected_at)
    )

    if only_pending:
        statement = statement.where(HumanFeedback.revalidated.is_(False))

    return list(db.scalars(statement))


def mark_feedback_revalidated(
    db: Session,
    invoice_id: uuid.UUID,
) -> int:
    """Mark every pending feedback row for an invoice as revalidated.

    Returns the number of rows updated.
    """
    pending = list_feedback(db, invoice_id, only_pending=True)

    for feedback in pending:
        feedback.revalidated = True

    try:
        db.commit()
        return len(pending)
    except Exception:
        db.rollback()
        raise


def feedback_to_dict(feedback: HumanFeedback) -> dict[str, Any]:
    """Serialize a feedback row for API responses."""
    return {
        "id": feedback.id,
        "invoice_id": str(feedback.invoice_id),
        "field_name": feedback.field_name,
        "original_value": feedback.original_value,
        "corrected_value": feedback.corrected_value,
        "corrected_by": feedback.corrected_by,
        "corrected_at": feedback.corrected_at.isoformat(),
        "revalidated": feedback.revalidated,
    }
