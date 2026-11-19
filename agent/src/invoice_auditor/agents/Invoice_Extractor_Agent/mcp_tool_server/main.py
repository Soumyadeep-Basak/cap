
"""MCP tool server for invoice document extraction."""

import logging
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from invoice_auditor.agents.Invoice_Extractor_Agent.extraction_service import (
    extract_document,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[6]

INCOMING_DIR = Path(
    os.getenv(
        "INCOMING_DIR",
        str(PROJECT_ROOT / "data" / "incoming"),
    )
).resolve()

mcp = FastMCP(
    "Extractor MCP Server",
    host="0.0.0.0",
    port=8002,
    stateless_http=True,
    json_response=True,
)


def resolve_invoice_path(file_path: str) -> Path:
    """Resolve and validate an invoice path against the allowed directory."""
    if not file_path or not file_path.strip():
        raise ValueError("file_path cannot be empty")

    resolved_path = Path(file_path).resolve()

    try:
        resolved_path.relative_to(INCOMING_DIR)
    except ValueError as exc:
        raise ValueError(
            "The requested file is outside the configured incoming directory"
        ) from exc

    if not resolved_path.exists():
        raise FileNotFoundError(
            f"Invoice file does not exist: {resolved_path.name}"
        )

    if not resolved_path.is_file():
        raise ValueError("The requested path is not a file")

    return resolved_path


@mcp.tool()
def extract_invoice_document(file_path: str) -> dict[str, str]:
    """
    Extract raw text from a PDF, DOCX, or PNG invoice.

    Args:
        file_path: Absolute path to the invoice file inside INCOMING_DIR.

    Returns:
        A dictionary containing raw extracted text and extraction method.
    """
    resolved_path = resolve_invoice_path(file_path)

    logger.info(
        "Starting invoice extraction for %s",
        resolved_path.name,
    )

    raw_text, extraction_method = extract_document(resolved_path)

    logger.info(
        "Completed invoice extraction for %s using %s",
        resolved_path.name,
        extraction_method,
    )

    return {
        "raw_text": raw_text,
        "extraction_method": extraction_method,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    mcp.run(transport="streamable-http")
