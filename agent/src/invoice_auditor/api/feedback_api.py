"""API endpoints for human-in-the-loop feedback and revalidation."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from invoice_auditor.db.session import SessionLocal
from invoice_auditor.services.feedback_service import (
    feedback_to_dict,
    list_feedback,
    record_feedback,
)
from invoice_auditor.workflows.revalidation import revalidate_invoice

router = APIRouter(
    prefix="/api/v1/invoices",
    tags=["Human-in-the-Loop"],
)


class FeedbackRequest(BaseModel):
    """A single human correction to an extracted invoice field."""

    field_name: str = Field(
        description="Extracted invoice field being corrected, "
        "e.g. total_amount, vendor_name, invoice_date.",
    )
    corrected_value: str = Field(
        description="The auditor-supplied correct value.",
    )
    original_value: str | None = Field(
        default=None,
        description="The original extracted value, for the audit trail.",
    )
    corrected_by: str = Field(
        description="Identifier of the auditor submitting the correction.",
    )


@router.post("/{invoice_id}/feedback")
def submit_feedback(
    invoice_id: UUID,
    request: FeedbackRequest,
) -> dict[str, Any]:
    """Record a human correction without overwriting extracted values."""
    try:
        with SessionLocal() as db:
            feedback = record_feedback(
                db,
                invoice_id,
                field_name=request.field_name,
                original_value=request.original_value,
                corrected_value=request.corrected_value,
                corrected_by=request.corrected_by,
            )

            return feedback_to_dict(feedback)

    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to record feedback: {exc}",
        ) from exc


@router.get("/{invoice_id}/feedback")
def get_feedback(invoice_id: UUID) -> list[dict[str, Any]]:
    """List every recorded correction for an invoice."""
    with SessionLocal() as db:
        return [
            feedback_to_dict(feedback)
            for feedback in list_feedback(db, invoice_id)
        ]


@router.post("/{invoice_id}/revalidate")
def revalidate(invoice_id: UUID) -> dict[str, Any]:
    """Apply pending corrections and re-run validation and reporting."""
    try:
        return revalidate_invoice(str(invoice_id))

    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Revalidation failed: {exc}",
        ) from exc
