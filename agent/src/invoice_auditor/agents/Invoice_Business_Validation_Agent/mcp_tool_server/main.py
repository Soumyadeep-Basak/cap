
"""Business Validation MCP server for invoice-to-ERP checks."""

from __future__ import annotations

import logging
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from invoice_auditor.agents.business_validation_agent import (
    run_business_validation,
)
from invoice_auditor.agents.Invoice_Business_Validation_Agent.business_validation_service import (
    prepare_business_validation_response,
    prepare_business_validation_state,
)

logger = logging.getLogger(__name__)

MCP_HOST = os.getenv(
    "BUSINESS_VALIDATION_MCP_HOST",
    "0.0.0.0",
)
MCP_PORT = int(
    os.getenv("BUSINESS_VALIDATION_MCP_PORT", "8007")
)

mcp = FastMCP(
    "invoice-business-validation-mcp-server",
    host=MCP_HOST,
    port=MCP_PORT,
    stateless_http=True,
    json_response=True,
)


@mcp.tool()
async def validate_invoice_against_erp(
    invoice: dict[str, Any],
) -> dict[str, Any]:
    """
    Validate invoice information against the Mock ERP system.

    Executes the existing Business Validation Google ADK:

      load_rules
        -> fetch_erp_data
        -> compare_business_rules

    Checks:
    - Vendor identity
    - Purchase-order identity and vendor
    - Invoice versus PO line items
    - SKU master records
    - Quantity differences
    - Unit-price differences
    - Currency mismatches

    Uses config/rules.yaml for deviation tolerances.

    Returns:
        Business validation status, recommendation,
        discrepancies, validation errors, and ERP data.
    """
    initial_state = prepare_business_validation_state(invoice)

    logger.info(
        "Business Validation MCP started: invoice_number=%s",
        invoice.get("invoice_number"),
    )

    try:
        result = await run_business_validation(initial_state)

        response = prepare_business_validation_response(result)

        logger.info(
            "Business Validation MCP completed: "
            "status=%s, discrepancies=%d, errors=%d",
            response["business_validation_status"],
            len(response["discrepancies"]),
            len(response["validation_errors"]),
        )

        return response

    except Exception:
        logger.exception(
            "Business Validation MCP failed for invoice=%s",
            invoice.get("invoice_number"),
        )
        raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    logger.info(
        "Starting Business Validation MCP server on %s:%s",
        MCP_HOST,
        MCP_PORT,
    )

    mcp.run(transport="streamable-http")
