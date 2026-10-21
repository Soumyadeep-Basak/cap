"""Persistence service for invoice audit reports."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from invoice_auditor.models.invoice_audit import InvoiceAudit


def persist_report_result(
    db: Session,
    invoice_id: str | UUID,
    report: dict[str, Any],
) -> None:
    """Persist report, validation status and recommendation."""

    parsed_invoice_id = (
        invoice_id
        if isinstance(invoice_id, UUID)
        else UUID(str(invoice_id))
    )

    audit = db.get(InvoiceAudit, parsed_invoice_id)

    if audit is None:
        raise ValueError(
            f"Audit record not found for invoice {parsed_invoice_id}"
        )

    # Preserve extraction and validation evidence already stored.
    extracted_raw = dict(audit.extracted_raw or {})
    extracted_raw["report"] = report

    audit.extracted_raw = extracted_raw
    audit.validation_status = report.get(
        "validation_status",
        "partial",
    )
    audit.recommendation = report.get(
        "database_recommendation",
        "review",
    )

    db.add(audit)
    db.commit()
    db.refresh(audit)
