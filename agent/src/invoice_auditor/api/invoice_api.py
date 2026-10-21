
"""API endpoints for invoice auditing."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
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
        description="Optional directory containing invoices to process.",
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
