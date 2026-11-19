
"""MCP server exposing invoice data validation through LangGraph."""

import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from invoice_auditor.agents.validation_agent import (
    invoice_validation_graph,
)


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


mcp = FastMCP(
    "invoice-validation-mcp-server",
    host="0.0.0.0",
    port=8003,
    stateless_http=True,
    json_response=True,
)


@mcp.tool()
def validate_invoice_document(
    invoice: dict[str, Any],
    translation_confidence: float | None = None,
) -> dict[str, Any]:
    """
    Validate extracted invoice data using the invoice validation graph.

    Checks:
    - Required header and line-item fields
    - Line-item arithmetic
    - Invoice subtotal and total
    - Tax calculations
    - Currency and validation policies

    Args:
        invoice: Extracted and translated invoice data.
        translation_confidence: Translation confidence score between 0 and 1.

    Returns:
        Structured invoice validation results.
    """

    if not isinstance(invoice, dict) or not invoice:
        raise ValueError("A non-empty invoice object is required.")

    if translation_confidence is not None:
        if not 0.0 <= translation_confidence <= 1.0:
            raise ValueError(
                "translation_confidence must be between 0 and 1."
            )

    logger.info(
        "Starting invoice validation MCP tool. Invoice number: %s",
        invoice.get("invoice_number", "unknown"),
    )

    try:
        result = invoice_validation_graph.invoke(
            {
                "invoice": invoice,
                "translation_confidence": translation_confidence,
            }
        )

        validation_result = {
            "validation_status": result["validation_status"],
            "recommendation": result["recommendation"],
            "severity_level": result["severity_level"],
            "missing_fields": result.get("missing_fields", []),
            "validation_errors": result.get("validation_errors", []),
            "discrepancies": result.get("discrepancies", []),
            "observations": result.get("observations", []),
            "arithmetic_passed": result.get("arithmetic_passed", False),
            "tax_verified": result.get("tax_verified", False),
        }

        logger.info(
            "Invoice validation completed. Status: %s, Recommendation: %s",
            validation_result["validation_status"],
            validation_result["recommendation"],
        )

        return validation_result

    except Exception:
        logger.exception("Invoice validation MCP tool failed.")
        raise


if __name__ == "__main__":
    logger.info("Starting Invoice Validation MCP server on port 8003.")
    mcp.run(transport="streamable-http")
