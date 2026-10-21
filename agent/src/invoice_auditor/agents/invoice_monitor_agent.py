
"""LangGraph subgraph for monitoring incoming invoice files."""

import hashlib
import logging
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from invoice_auditor.models.invoice_audit import InvoiceAudit
from invoice_auditor.config import INCOMING_DIR
from invoice_auditor.db.session import SessionLocal
from invoice_auditor.services.invoice_audit_service import (
    create_audit_record,
    mark_processing_failed,
)

logger = logging.getLogger(__name__)

# Supported formats and their future extraction paths.
EXTRACTION_ROUTES = {
    ".pdf": "pdf_extractor",
    ".docx": "docx_extractor",
    ".png": "ocr_extractor",
}


class MonitorState(TypedDict, total=False):
    """State passed between monitoring nodes."""

    incoming_dir: str
    discovered_files: list[dict[str, Any]]
    pending_invoices: list[dict[str, Any]]
    routed_invoices: list[dict[str, Any]]
    duplicate_files: list[str]
    errors: list[dict[str, str]]
    status: str


def calculate_checksum(file_path: Path) -> str:
    """Calculate the SHA-256 checksum of a file."""
    checksum = hashlib.sha256()

    with file_path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            checksum.update(chunk)

    return checksum.hexdigest()


def discover_files_node(state: MonitorState) -> dict[str, Any]:
    """Scan the incoming directory and calculate file checksums."""
    directory = Path(state.get("incoming_dir", str(INCOMING_DIR)))

    discovered_files = []
    errors = []

    if not directory.is_dir():
        return {
            "discovered_files": [],
            "errors": [{
                "file_path": str(directory),
                "error": "Incoming directory does not exist",
            }],
            "status": "error",
        }

    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue

        # Ignore hidden placeholder files such as .gitkeep in the mounted
        # incoming directory.
        if path.name.startswith("."):
            continue

        # Ignore metadata sidecars; they are not invoice documents.
        if path.name.lower().endswith(".meta.json"):
            continue

        file_info = {
            "file_path": str(path.resolve()),
            "file_type": path.suffix.lower(),
            "checksum": None,
            "checksum_error": None,
        }

        try:
            file_info["checksum"] = calculate_checksum(path)
        except OSError as exc:
            file_info["checksum_error"] = str(exc)
            errors.append({
                "file_path": str(path),
                "error": f"Could not calculate checksum: {exc}",
            })

        discovered_files.append(file_info)

    logger.info("Discovered %d files", len(discovered_files))

    return {
        "discovered_files": discovered_files,
        "errors": errors,
        "status": "discovered",
    }



def register_files_node(state: MonitorState) -> dict[str, Any]:
    """Register new files and skip previously audited invoices."""

    pending_invoices = []
    duplicate_files = list(state.get("duplicate_files", []))
    errors = list(state.get("errors", []))

    for info in state.get("discovered_files", []):
        file_path = info["file_path"]
        checksum = info["checksum"]
        failure = info["checksum_error"]

        try:
            with SessionLocal() as db:
                # Create an audit record only if this checksum or file path
                # has not already been registered.
                invoice_id = create_audit_record(
                    db=db,
                    file_path=file_path,
                    checksum=checksum,
                )

                if invoice_id is None:
                    # The file already exists in the audit trail.
                    # Never retry it automatically, regardless of status.
                    if checksum is not None:
                        existing = db.scalar(
                            select(InvoiceAudit).where(
                                InvoiceAudit.file_checksum == checksum
                            )
                        )
                    else:
                        existing = db.scalar(
                            select(InvoiceAudit).where(
                                InvoiceAudit.file_path == file_path,
                                InvoiceAudit.file_checksum.is_(None),
                            )
                        )

                    duplicate_files.append(file_path)

                    logger.info(
                        "Skipping duplicate invoice: %s (previous status=%s)",
                        file_path,
                        (
                            existing.validation_status
                            if existing is not None
                            else "unknown"
                        ),
                    )
                    continue

                # Audit unsupported file types and checksum failures too.
                if (
                    failure is None
                    and info["file_type"] not in EXTRACTION_ROUTES
                ):
                    failure = (
                        "Unsupported file type: "
                        f"{info['file_type'] or '(no extension)'}"
                    )

                if failure:
                    mark_processing_failed(
                        db=db,
                        invoice_id=invoice_id,
                        error_message=failure,
                    )
                    errors.append({
                        "file_path": file_path,
                        "error": failure,
                    })
                    continue

                # Only newly registered, supported files enter the workflow.
                pending_invoices.append({
                    **info,
                    "invoice_id": str(invoice_id),
                    "status": "pending",
                })

                logger.info(
                    "Registered new invoice: %s (invoice_id=%s)",
                    file_path,
                    invoice_id,
                )

        except Exception as exc:
            logger.exception(
                "Could not register file: %s",
                file_path,
            )
            errors.append({
                "file_path": file_path,
                "error": f"Audit registration failed: {exc}",
            })

    return {
        "pending_invoices": pending_invoices,
        "duplicate_files": duplicate_files,
        "errors": errors,
        "status": "registered",
    }


def route_files_node(state: MonitorState) -> dict[str, Any]:
    """Assign each registered invoice to its extraction path."""
    routed_invoices = []

    for invoice in state.get("pending_invoices", []):
        route = EXTRACTION_ROUTES[invoice["file_type"]]

        routed_invoices.append({
            **invoice,
            "extraction_route": route,
        })

    logger.info("Routed %d invoices", len(routed_invoices))

    return {
        "routed_invoices": routed_invoices,
        "status": "completed",
    }


def build_invoice_monitor_graph():
    """Build and compile the invoice monitoring subgraph."""
    workflow = StateGraph(MonitorState)

    workflow.add_node("discover_files", discover_files_node)
    workflow.add_node("register_files", register_files_node)
    workflow.add_node("route_files", route_files_node)

    workflow.add_edge(START, "discover_files")
    workflow.add_edge("discover_files", "register_files")
    workflow.add_edge("register_files", "route_files")
    workflow.add_edge("route_files", END)

    return workflow.compile()


invoice_monitor_graph = build_invoice_monitor_graph()
