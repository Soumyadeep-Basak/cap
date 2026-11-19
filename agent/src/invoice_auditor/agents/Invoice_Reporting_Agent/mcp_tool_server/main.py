
"""Reporting MCP server exposing the existing LangGraph reporting agent."""

import logging
import os
from typing import Any
from uuid import UUID

from mcp.server.fastmcp import FastMCP

from invoice_auditor.agents.reporting_agent import (
    reporting_graph,
    json_safe,
)

logger = logging.getLogger(__name__)

MCP_HOST = os.getenv("REPORTING_MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("REPORTING_MCP_PORT", "8005"))

mcp = FastMCP(
    "invoice-reporting-mcp-server",
    host=MCP_HOST,
    port=MCP_PORT,
    stateless_http=True,
    json_response=True,
)


@mcp.tool()
def generate_invoice_report(
    invoice_id: str,
    file_path: str,
    invoice: dict[str, Any],
    validation_result: dict[str, Any],
    translation_confidence: float | None = None,
    source_language: str | None = None,
    translated_text: str | None = None,
    erp_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Generate and persist an invoice audit report.

    Invokes the existing Reporting Agent LangGraph to:

    1. Generate JSON and HTML reports.
    2. Include invoice information and validation results.
    3. Include discrepancies, translation confidence, and recommendations.
    4. Persist the report outcome in PostgreSQL.

    Args:
        invoice_id: Existing invoice audit UUID.
        file_path: Original invoice file path.
        invoice: Structured invoice data.
        validation_result: Combined data and business validation results.
        translation_confidence: Translation reliability score.
        source_language: Original invoice language.
        translated_text: English translated invoice text.
        erp_data: Related enterprise-system data.

    Returns:
        Report status, report paths, and generated report data.
    """

    if not isinstance(invoice_id, str) or not invoice_id.strip():
        raise ValueError("invoice_id is required")

    try:
        invoice_id = str(UUID(invoice_id))
    except (ValueError, AttributeError) as exc:
        raise ValueError("invoice_id must be a valid UUID") from exc

    if not isinstance(file_path, str):
        raise ValueError("file_path must be a string")

    if not isinstance(invoice, dict):
        raise ValueError("invoice must be a dictionary")

    if not isinstance(validation_result, dict):
        raise ValueError("validation_result must be a dictionary")

    if translation_confidence is not None:
        if isinstance(translation_confidence, bool):
            raise ValueError("translation_confidence must be numeric")

        translation_confidence = float(translation_confidence)

        if not 0.0 <= translation_confidence <= 1.0:
            raise ValueError(
                "translation_confidence must be between 0 and 1"
            )

    logger.info(
        "Starting reporting MCP for invoice_id=%s",
        invoice_id,
    )

    try:
        state = {
            "invoice_id": invoice_id,
            "file_path": file_path,
            "invoice": invoice,
            "validation_result": validation_result,
            "translation_confidence": translation_confidence,
            "source_language": source_language,
            "translated_text": translated_text,
            "erp_data": erp_data or {},
        }

        result = reporting_graph.invoke(state)

        if result.get("report_status") != "completed":
            raise RuntimeError(
                "Reporting graph did not complete successfully"
            )

        response = {
            "invoice_id": invoice_id,
            "report_status": result["report_status"],
            "json_report_path": result["json_report_path"],
            "html_report_path": result["html_report_path"],
            "report": result["report"],
        }

        logger.info(
            "Reporting MCP completed for invoice_id=%s",
            invoice_id,
        )

        return json_safe(response)

    except Exception:
        logger.exception(
            "Reporting MCP failed for invoice_id=%s",
            invoice_id,
        )
        raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    logger.info(
        "Starting Reporting MCP server on %s:%s",
        MCP_HOST,
        MCP_PORT,
    )

    mcp.run(transport="streamable-http")
