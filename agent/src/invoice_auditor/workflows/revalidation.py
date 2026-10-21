"""Human-in-the-loop revalidation workflow.

Triggered after an auditor submits corrections through the feedback
API. Applies the recorded corrections on top of the original
extracted invoice (without mutating it), re-runs data and business
validation plus reporting, persists the refreshed outcome, marks the
triggering feedback as revalidated, and refreshes the RAG index.

This never re-runs OCR, re-extracts the document, or rereads the
original invoice file; it only reuses already-persisted extraction
and translation text, consistent with 3.6.6 of the problem statement.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from invoice_auditor.agents.business_validation_agent import (
    business_validation_graph,
)
from invoice_auditor.agents.rag_agents.indexing_agent import indexing_graph
from invoice_auditor.agents.reporting_agent import reporting_graph
from invoice_auditor.agents.validation_agent import invoice_validation_graph
from invoice_auditor.db.session import SessionLocal
from invoice_auditor.services.feedback_service import (
    feedback_to_dict,
    list_feedback,
    mark_feedback_revalidated,
)
from invoice_auditor.services.invoice_audit_service import (
    get_invoice_audit,
    save_discrepancies,
    save_validation_result,
)
from invoice_auditor.workflows.invoice_workflow import (
    combine_validation_results,
    make_json_safe,
)

logger = logging.getLogger(__name__)

# Fields that hold monetary or numeric values on the extracted invoice.
_DECIMAL_FIELDS = {
    "total_amount",
    "subtotal_amount",
    "tax_amount",
    "tax_rate",
}


def _coerce_corrected_value(field_name: str, raw_value: str) -> Any:
    """Coerce a corrected value's type to match the invoice schema."""
    if field_name in _DECIMAL_FIELDS:
        try:
            return Decimal(raw_value)
        except (InvalidOperation, ValueError):
            return raw_value

    if field_name == "invoice_date":
        try:
            return date.fromisoformat(raw_value)
        except ValueError:
            return raw_value

    return raw_value


def apply_corrections(
    invoice: dict[str, Any],
    feedback_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply recorded corrections on top of a copy of the invoice.

    The original extracted invoice (and the DB record it came from)
    is never mutated; only this in-memory copy is used to re-run
    validation.
    """
    corrected = dict(invoice)

    for feedback in feedback_rows:
        field_name = feedback["field_name"]

        if field_name not in corrected:
            logger.warning(
                "Ignoring feedback for unknown invoice field: %s",
                field_name,
            )
            continue

        corrected[field_name] = _coerce_corrected_value(
            field_name,
            feedback["corrected_value"],
        )

    return corrected


def revalidate_invoice(invoice_id: str) -> dict[str, Any]:
    """Re-run validation, reporting, and indexing for one invoice.

    Returns a summary of the refreshed validation outcome.
    """
    parsed_invoice_id = UUID(invoice_id)

    with SessionLocal() as db:
        record = get_invoice_audit(db, parsed_invoice_id)

        if record is None:
            raise ValueError(f"Invoice audit record not found: {invoice_id}")

        extracted_raw = record.extracted_raw or {}
        original_invoice = extracted_raw.get("parsed_invoice")

        if not original_invoice:
            raise ValueError(
                "No extracted invoice data is available to revalidate "
                f"for {invoice_id}"
            )

        pending_feedback = [
            feedback_to_dict(feedback)
            for feedback in list_feedback(
                db, parsed_invoice_id, only_pending=True
            )
        ]

        translation_confidence = extracted_raw.get(
            "translation_confidence"
        )
        source_language = extracted_raw.get("source_language")
        translated_text = extracted_raw.get("translated_text")
        raw_extracted_text = record.raw_extracted_text
        file_path = record.file_path

    corrected_invoice = apply_corrections(
        original_invoice,
        pending_feedback,
    )

    # 1. Re-run data and business validation on the corrected invoice.
    data_validation_result = invoice_validation_graph.invoke(
        {
            "invoice": corrected_invoice,
            "translation_confidence": translation_confidence,
        }
    )

    business_validation_result = business_validation_graph.invoke(
        {"invoice": corrected_invoice}
    )

    validation_result, resolved_vendor_id = combine_validation_results(
        data_validation_result,
        business_validation_result,
    )

    safe_validation_result = make_json_safe(validation_result)

    # 2. Persist the refreshed validation result and discrepancies.
    with SessionLocal() as db:
        save_validation_result(
            db,
            parsed_invoice_id,
            safe_validation_result,
        )

        save_discrepancies(
            db=db,
            invoice_id=parsed_invoice_id,
            discrepancies=make_json_safe(
                validation_result["discrepancies"]
            ),
        )

    # 3. Regenerate the report against the corrected invoice.
    report_invoice = dict(corrected_invoice)
    if resolved_vendor_id is not None:
        report_invoice["vendor_id"] = resolved_vendor_id

    reporting_result = reporting_graph.invoke(
        {
            "invoice_id": invoice_id,
            "file_path": file_path,
            "invoice": report_invoice,
            "validation_result": safe_validation_result,
            "translation_confidence": translation_confidence,
            "source_language": source_language,
            "translated_text": translated_text,
            "erp_data": validation_result.get("erp_data", {}),
        }
    )

    report = reporting_result["report"]

    # 4. Mark the triggering feedback as revalidated.
    with SessionLocal() as db:
        revalidated_count = mark_feedback_revalidated(
            db, parsed_invoice_id
        )

    # 5. Refresh the RAG index so queries reflect the corrected report.
    index_result = indexing_graph.invoke(
        {
            "invoice_id": invoice_id,
            "raw_extracted_text": raw_extracted_text,
            "translated_text": translated_text,
            "source_language": source_language,
            "vendor_name": corrected_invoice.get("vendor_name"),
            "report": report,
        }
    )

    logger.info(
        "Revalidated invoice %s: status=%s recommendation=%s "
        "feedback_applied=%d",
        invoice_id,
        safe_validation_result["validation_status"],
        safe_validation_result["recommendation"],
        revalidated_count,
    )

    return {
        "invoice_id": invoice_id,
        "validation_status": safe_validation_result["validation_status"],
        "recommendation": safe_validation_result["recommendation"],
        "discrepancies": safe_validation_result["discrepancies"],
        "report": report,
        "feedback_applied": revalidated_count,
        "index_status": index_result.get("index_status"),
    }
