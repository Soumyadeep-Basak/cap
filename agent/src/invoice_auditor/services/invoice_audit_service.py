
"""Database operations for invoice monitoring and audit records."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from invoice_auditor.models.discrepancy import Discrepancy
from invoice_auditor.models.invoice_audit import InvoiceAudit
from invoice_auditor.models.invoice_line_item import InvoiceLineItem


def _json_safe(value: Any) -> Any:
    """Convert Python values into JSON-compatible values.

    Decimal values are stored as strings to preserve monetary precision.
    Dates and UUIDs are stored as ISO strings and UUID strings respectively.
    """
    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, uuid.UUID):
        return str(value)

    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]

    return value


def find_by_checksum(
    db: Session,
    checksum: str,
) -> InvoiceAudit | None:
    """Find an audit record with the same file contents."""
    statement = select(InvoiceAudit).where(
        InvoiceAudit.file_checksum == checksum
    )
    return db.scalar(statement)


def create_audit_record(
    db: Session,
    file_path: str,
    checksum: str | None,
) -> uuid.UUID | None:
    """Register a file and return its ID, or None if already registered."""
    if checksum is not None:
        if find_by_checksum(db, checksum) is not None:
            return None
    else:
        statement = select(InvoiceAudit).where(
            InvoiceAudit.file_path == file_path,
            InvoiceAudit.file_checksum.is_(None),
        )
        if db.scalar(statement) is not None:
            return None

    record = InvoiceAudit(
        file_path=file_path,
        file_checksum=checksum,
        validation_status="pending",
    )
    db.add(record)

    try:
        db.commit()
        db.refresh(record)
        return record.invoice_id
    except IntegrityError:
        db.rollback()

        if checksum is not None and find_by_checksum(db, checksum):
            return None

        raise


def get_invoice_audit(
    db: Session,
    invoice_id: uuid.UUID,
) -> InvoiceAudit | None:
    """Load a persisted invoice audit record, if one exists."""
    return db.get(InvoiceAudit, invoice_id)


def get_invoice_line_items(
    db: Session,
    invoice_id: uuid.UUID,
) -> list[InvoiceLineItem]:
    """Load the persisted line items for an invoice, in order."""
    statement = (
        select(InvoiceLineItem)
        .where(InvoiceLineItem.invoice_id == invoice_id)
        .order_by(InvoiceLineItem.line_number)
    )
    return list(db.scalars(statement))


def mark_processing_failed(
    db: Session,
    invoice_id: uuid.UUID,
    error_message: str,
) -> None:
    """Persist a monitoring, extraction, or processing failure."""
    record = db.get(InvoiceAudit, invoice_id)

    if record is None:
        raise ValueError(f"Invoice record not found: {invoice_id}")

    try:
        record.validation_status = "failed"
        record.processing_error = error_message
        db.commit()
    except Exception:
        db.rollback()
        raise


def save_translation(
    db: Session,
    invoice_id: uuid.UUID,
    source_language: str,
    translated_text: str,
    confidence: float,
) -> None:
    """Persist translation results for an existing invoice."""
    if not 0 <= confidence <= 1:
        raise ValueError("Translation confidence must be between 0 and 1")

    record = db.get(InvoiceAudit, invoice_id)

    if record is None:
        raise ValueError(f"Invoice record not found: {invoice_id}")

    try:
        record.source_language = source_language
        record.translated_text = translated_text
        record.translation_confidence = confidence
        db.commit()
    except Exception:
        db.rollback()
        raise


def save_translation_failure(
    db: Session,
    invoice_id: uuid.UUID,
    error_message: str,
) -> None:
    """Persist a translation failure against the invoice record."""
    mark_processing_failed(db, invoice_id, error_message)


def save_extraction_result(
    db: Session,
    invoice_id: uuid.UUID,
    *,
    raw_extracted_text: str,
    extraction_method: str,
    invoice: dict[str, Any],
    extracted_raw: dict[str, Any],
) -> None:
    """Persist raw text, extracted fields, JSON metadata, and line items.

    The complete source text is stored separately from structured data.
    Normalized invoice fields and line items are persisted atomically.
    """
    record = db.get(InvoiceAudit, invoice_id)

    if record is None:
        raise ValueError(
            f"Invoice audit record not found: {invoice_id}"
        )

    try:
        # Preserve the full extracted text exactly as received from the
        # document extraction stage. Do not replace it with parsed fields.
        record.raw_extracted_text = raw_extracted_text
        record.extraction_method = extraction_method

        # Persist normalized invoice header fields.
        record.invoice_number = invoice.get("invoice_number")
        record.invoice_date = invoice.get("invoice_date")
        record.vendor_name = invoice.get("vendor_name")
        record.po_number = invoice.get("po_number")
        record.currency = invoice.get("currency")
        record.total_amount = invoice.get("total_amount")

        # JSON/JSONB cannot serialize Python Decimal or date objects
        # using the default JSON encoder.
        record.extracted_raw = _json_safe(extracted_raw)
        record.processing_error = None

        # Replace existing line items to prevent duplicates if this
        # persistence function is explicitly called again.
        db.execute(
            delete(InvoiceLineItem).where(
                InvoiceLineItem.invoice_id == invoice_id
            )
        )

        for line_number, item in enumerate(
            invoice.get("line_items", []),
            start=1,
        ):
            db.add(
                InvoiceLineItem(
                    invoice_id=invoice_id,
                    line_number=line_number,
                    item_code=item.get("item_code"),
                    description=item.get("description"),
                    quantity=item.get("quantity"),
                    unit_price=item.get("unit_price"),
                    line_total=item.get("line_total"),
                )
            )

        db.commit()

    except Exception:
        db.rollback()
        raise


def save_validation_result(
    db: Session,
    invoice_id: uuid.UUID,
    validation_result: dict[str, Any],
) -> None:
    """Persist validation findings without overwriting extraction data."""
    record = db.get(InvoiceAudit, invoice_id)

    if record is None:
        raise ValueError(
            f"Invoice audit record not found: {invoice_id}"
        )

    status = validation_result["validation_status"]
    recommendation = validation_result["recommendation"]

    if status not in {"pending", "passed", "failed", "partial"}:
        raise ValueError(f"Invalid validation status: {status}")

    if recommendation not in {"approve", "review", "reject"}:
        raise ValueError(
            f"Invalid recommendation: {recommendation}"
        )

    try:
        extracted_raw = dict(record.extracted_raw or {})
        extracted_raw["validation"] = _json_safe(validation_result)

        record.validation_status = status
        record.recommendation = recommendation
        record.extracted_raw = extracted_raw

        db.commit()
    except Exception:
        db.rollback()
        raise


def save_discrepancies(
    db: Session,
    invoice_id: uuid.UUID,
    discrepancies: list[dict[str, Any]],
) -> None:
    """Replace and persist discrepancies for an invoice."""
    if db.get(InvoiceAudit, invoice_id) is None:
        raise ValueError(
            f"Invoice audit record not found: {invoice_id}"
        )

    try:
        db.execute(
            delete(Discrepancy).where(
                Discrepancy.invoice_id == invoice_id
            )
        )

        for discrepancy in discrepancies:
            db.add(
                Discrepancy(
                    invoice_id=invoice_id,
                    field_name=discrepancy["field_name"],
                    invoice_value=discrepancy.get("invoice_value"),
                    erp_value=discrepancy.get("erp_value"),
                    deviation_pct=discrepancy.get("deviation_pct"),
                    severity=discrepancy["severity"],
                )
            )

        db.commit()
    except Exception:
        db.rollback()
        raise
