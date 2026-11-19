
"""LangGraph workflow for extracting text from invoice documents."""

import logging
import uuid
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from invoice_auditor.db.session import SessionLocal
from invoice_auditor.services.invoice_audit_service import (
    mark_processing_failed,
    save_extraction_result,
)
from invoice_auditor.agents.Invoice_Extractor_Agent.extraction_service import (
    extract_document,
    parse_invoice_text,
)

logger = logging.getLogger(__name__)


class ExtractorState(TypedDict, total=False):
    invoice: dict[str, Any]
    raw_extracted_text: str
    extraction_method: str
    status: str
    error: str


def extract_document_node(
    state: ExtractorState,
) -> dict[str, Any]:
    """Extract the document text."""
    invoice = state["invoice"]
    file_path = Path(invoice["file_path"])

    raw_text, extraction_method = extract_document(file_path)

    logger.info(
        "Extracted text from %s using %s",
        file_path.name,
        extraction_method,
    )

    return {
        "raw_extracted_text": raw_text,
        "extraction_method": extraction_method,
        "status": "extracted",
    }


def save_extraction_node(
    state: ExtractorState,
) -> dict[str, Any]:
    """Persist the extracted text and extraction method."""
    invoice = state["invoice"]
    invoice_id = uuid.UUID(invoice["invoice_id"])

    with SessionLocal() as db:
        save_extraction_result(
            db=db,
            invoice_id=invoice_id,
            raw_extracted_text=state["raw_extracted_text"],
            extraction_method=state["extraction_method"],
            invoice={},
            extracted_raw={},
        )

    return {"status": "completed"}


def handle_extraction_failure_node(
    state: ExtractorState,
) -> dict[str, Any]:
    """Persist an extraction failure in the audit record."""
    invoice = state["invoice"]
    invoice_id = uuid.UUID(invoice["invoice_id"])
    error_message = state.get(
        "error",
        "Unknown extraction error",
    )

    with SessionLocal() as db:
        mark_processing_failed(
            db=db,
            invoice_id=invoice_id,
            error_message=error_message,
        )

    logger.error(
        "Extraction failed for %s: %s",
        invoice.get("file_path"),
        error_message,
    )

    return {"status": "failed"}


def route_extraction_result(
    state: ExtractorState,
) -> str:
    """Route extraction to persistence or failure handling."""
    return (
        "save_extraction"
        if state.get("status") == "extracted"
        else "handle_failure"
    )


def build_invoice_extractor_graph():
    workflow = StateGraph(ExtractorState)

    workflow.add_node(
        "extract_document",
        extract_document_node,
    )
    workflow.add_node(
        "save_extraction",
        save_extraction_node,
    )
    workflow.add_node(
        "handle_failure",
        handle_extraction_failure_node,
    )

    workflow.add_edge(START, "extract_document")

    workflow.add_conditional_edges(
        "extract_document",
        route_extraction_result,
        {
            "save_extraction": "save_extraction",
            "handle_failure": "handle_failure",
        },
    )

    workflow.add_edge("save_extraction", END)
    workflow.add_edge("handle_failure", END)

    return workflow.compile()


invoice_extractor_graph = build_invoice_extractor_graph()
