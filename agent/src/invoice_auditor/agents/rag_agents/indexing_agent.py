"""Indexing Agent: chunk and embed processed invoice text into Qdrant.

Per the problem statement (3.6.1), this agent retrieves persisted
invoice and report text, divides it into chunks, generates vector
embeddings, and stores them in Qdrant alongside their payloads.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from invoice_auditor.db.session import SessionLocal
from invoice_auditor.services.invoice_audit_service import (
    get_invoice_audit,
)
from invoice_auditor.tools.rag_tools.rag_retriever import (
    index_text,
    reindex_invoice,
)

logger = logging.getLogger(__name__)


class IndexingState(TypedDict, total=False):
    """Inputs and outputs for the Indexing Agent."""

    invoice_id: str
    raw_extracted_text: str | None
    translated_text: str | None
    source_language: str | None
    vendor_name: str | None
    report: dict[str, Any] | None

    indexed_chunks: int
    index_status: str
    index_error: str | None


def _report_to_text(report: dict[str, Any]) -> str:
    """Render the generated report as plain text suitable for chunking."""
    invoice = report.get("invoice") or {}
    discrepancies = report.get("discrepancies") or []

    lines = [
        f"Invoice {invoice.get('invoice_number', 'unknown')} report.",
        f"Vendor: {invoice.get('vendor_name', 'unknown')}",
        f"PO number: {invoice.get('po_number', 'unknown')}",
        f"Total amount: {invoice.get('total_amount', 'unknown')} "
        f"{invoice.get('currency', '')}".strip(),
        f"Validation status: {report.get('validation_status')}",
        f"Recommendation: {report.get('recommendation')}",
    ]

    missing_fields = report.get("missing_fields") or []
    if missing_fields:
        lines.append(f"Missing fields: {', '.join(missing_fields)}")

    for discrepancy in discrepancies:
        lines.append(
            "Discrepancy on {field}: invoice value {inv} vs "
            "ERP value {erp} (severity {sev}).".format(
                field=discrepancy.get("field_name"),
                inv=discrepancy.get("invoice_value"),
                erp=discrepancy.get("erp_value"),
                sev=discrepancy.get("severity"),
            )
        )

    return "\n".join(lines)


def load_source_node(state: IndexingState) -> dict[str, Any]:
    """Load any missing source text for this invoice from PostgreSQL.

    The main workflow already has extraction/translation/report text
    in memory and passes it in directly, so no reload or re-OCR is
    required there. This node only backfills text when the Indexing
    Agent is invoked standalone (e.g. a backfill or reindex job).
    """
    needs_lookup = (
        state.get("raw_extracted_text") is None
        or state.get("translated_text") is None
        or state.get("report") is None
    )

    if not needs_lookup:
        return {}

    invoice_id = state.get("invoice_id")

    if not invoice_id:
        return {
            "index_error": "No invoice_id was provided to load source text",
        }

    with SessionLocal() as db:
        record = get_invoice_audit(db, UUID(invoice_id))

        if record is None:
            return {
                "index_error": f"Invoice audit record not found: {invoice_id}",
            }

        extracted_raw = record.extracted_raw or {}

        return {
            "raw_extracted_text": (
                state.get("raw_extracted_text")
                or record.raw_extracted_text
            ),
            "translated_text": (
                state.get("translated_text")
                or extracted_raw.get("translated_text")
            ),
            "source_language": (
                state.get("source_language") or record.source_language
            ),
            "vendor_name": state.get("vendor_name") or record.vendor_name,
            "report": state.get("report") or extracted_raw.get("report"),
        }


def index_content_node(state: IndexingState) -> dict[str, Any]:
    """Chunk, embed, and upsert every available piece of invoice text."""
    invoice_id = state.get("invoice_id")

    if not invoice_id:
        return {
            "index_status": "failed",
            "index_error": "No invoice_id was provided for indexing",
        }

    if state.get("index_error"):
        return {
            "index_status": "failed",
            "index_error": state["index_error"],
        }

    vendor_name = state.get("vendor_name")
    source_language = state.get("source_language")

    try:
        # Drop any chunks from a prior indexing pass so reprocessing
        # or revalidation never leaves stale chunks behind.
        reindex_invoice(invoice_id)

        total_chunks = 0

        raw_text = state.get("raw_extracted_text")
        if raw_text:
            total_chunks += index_text(
                invoice_id=invoice_id,
                source_type="raw_text",
                text=raw_text,
                language=source_language,
                vendor=vendor_name,
            )

        translated_text = state.get("translated_text")
        if translated_text:
            total_chunks += index_text(
                invoice_id=invoice_id,
                source_type="translated_text",
                text=translated_text,
                language="en",
                vendor=vendor_name,
            )

        report = state.get("report")
        if report:
            total_chunks += index_text(
                invoice_id=invoice_id,
                source_type="report",
                text=_report_to_text(report),
                language="en",
                vendor=vendor_name,
            )

        logger.info(
            "Indexed %d chunks for invoice %s",
            total_chunks,
            invoice_id,
        )

        return {
            "indexed_chunks": total_chunks,
            "index_status": "completed",
        }

    except Exception as exc:
        logger.exception(
            "Indexing failed for invoice %s",
            invoice_id,
        )

        return {
            "index_status": "failed",
            "index_error": str(exc),
        }


def build_indexing_graph():
    """Build the Indexing Agent subgraph."""
    workflow = StateGraph(IndexingState)

    workflow.add_node("load_source", load_source_node)
    workflow.add_node("index_content", index_content_node)

    workflow.add_edge(START, "load_source")
    workflow.add_edge("load_source", "index_content")
    workflow.add_edge("index_content", END)

    return workflow.compile()


indexing_graph = build_indexing_graph()
