
"""API endpoints for invoice auditing."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, File, UploadFile
from uuid import UUID
from invoice_auditor.db.session import SessionLocal
from invoice_auditor.services.ingestion_service import ingest_invoice, get_receipt, UploadError
from invoice_auditor.services.invoice_audit_service import save_index_result
from invoice_auditor.agents.Invoice_RAG_Agent.rag_agent_client import index_invoice
from pydantic import BaseModel, Field

from invoice_auditor.config import INCOMING_DIR
from invoice_auditor.workflows.invoice_workflow import (
    invoice_audit_graph,
)

router = APIRouter(
    prefix="/api/v1/invoices",
    tags=["Invoice Auditing"],
)


class InvoiceProcessingRequest(BaseModel):
    """Request options for processing incoming invoices."""

    incoming_dir: Path | None = Field(
        default=None,
        description="Optional path matching the configured incoming directory.",
    )


@router.post("/process")
def process_invoices(
    request: InvoiceProcessingRequest | None = None,
) -> dict[str, Any]:
    """Run the invoice auditing workflow."""

    incoming_dir = (
        request.incoming_dir
        if request and request.incoming_dir
        else INCOMING_DIR
    )

    if incoming_dir.resolve() != INCOMING_DIR.resolve():
        raise HTTPException(
            status_code=400,
            detail="Only the configured incoming directory may be scanned",
        )

    if not incoming_dir.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Incoming directory does not exist: {incoming_dir}",
        )

    if not incoming_dir.is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"Incoming path is not a directory: {incoming_dir}",
        )

    try:
        result = invoice_audit_graph.invoke(
            {"incoming_dir": str(incoming_dir)}
        )
        return result

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Invoice workflow failed: {exc}",
        ) from exc


@router.post("/upload")
def upload_invoice(file: UploadFile = File(...)) -> dict[str, Any]:
    """Save one supported file and run the full invoice audit/index pipeline."""
    try:
        return ingest_invoice(file.file, file.filename, file.content_type,
                              INCOMING_DIR, invoice_audit_graph.invoke)
    except UploadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

@router.get("/{invoice_id}/status")
def invoice_status(invoice_id: UUID) -> dict[str, Any]:
    """Read persisted processing/report/index status, including after a timeout."""
    try:
        return get_receipt(invoice_id)
    except UploadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

@router.post("/{invoice_id}/reindex")
def reindex_uploaded_invoice(invoice_id: UUID) -> dict[str, Any]:
    """Retry the derived RAG index using persisted text; never rerun OCR."""
    try:
        receipt = get_receipt(invoice_id)
        if receipt["extraction_status"] != "completed" or receipt["report_status"] != "completed":
            raise UploadError("Finish invoice extraction and reporting before indexing", 409)
        try:
            result = index_invoice({"invoice_id": str(invoice_id)})
        except Exception:
            result = {"index_status": "failed", "indexed_chunks": 0}
        with SessionLocal() as db:
            save_index_result(db, invoice_id, result)
        return get_receipt(invoice_id)
    except UploadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
