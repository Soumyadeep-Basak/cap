
"""Invoice Monitoring MCP server.

Exposes the existing Invoice Monitor LangGraph as an MCP tool.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from invoice_auditor.agents.invoice_monitor_agent import (
    invoice_monitor_graph,
)
from invoice_auditor.agents.Invoice_Monitoring_Agent.monitoring_service import (
    get_authorized_incoming_dir,
    prepare_monitoring_response,
)

logger = logging.getLogger(__name__)

MCP_HOST = os.getenv("MONITORING_MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("MONITORING_MCP_PORT", "8006"))

mcp = FastMCP(
    "invoice-monitoring-mcp-server",
    host=MCP_HOST,
    port=MCP_PORT,
    stateless_http=True,
    json_response=True,
)


@mcp.tool()
def scan_incoming_invoices(
    incoming_dir: str | None = None,
) -> dict[str, Any]:
    """
    Discover and register invoices from the configured directory.

    Runs the existing Invoice Monitor LangGraph:
        discover_files -> register_files -> route_files

    Features:
    - Discovers PDF, DOCX, and PNG invoice files.
    - Computes SHA-256 checksums.
    - Skips previously registered invoices.
    - Creates PostgreSQL audit records for new invoices.
    - Marks unsupported documents or checksum failures.
    - Assigns extraction routes to new invoices.

    This tool does not start a polling loop and does not run
    extraction, translation, validation, or reporting.

    Args:
        incoming_dir: Optional directory path. If supplied,
            it must match the server's configured INCOMING_DIR.

    Returns:
        Monitoring status, routed invoices, duplicates,
        errors, and scan counts.
    """
    directory = get_authorized_incoming_dir(incoming_dir)

    logger.info(
        "Monitoring MCP scan started: directory=%s",
        directory,
    )

    try:
        result = invoice_monitor_graph.invoke({
            "incoming_dir": directory,
        })

        response = prepare_monitoring_response(result)

        logger.info(
            "Monitoring MCP scan completed: "
            "discovered=%d, pending=%d, routed=%d, "
            "duplicates=%d, errors=%d",
            response["discovered_count"],
            response["pending_count"],
            response["routed_count"],
            response["duplicate_count"],
            response["error_count"],
        )

        return response

    except Exception:
        logger.exception(
            "Monitoring MCP scan failed: directory=%s",
            directory,
        )
        raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    logger.info(
        "Starting Monitoring MCP server on %s:%s",
        MCP_HOST,
        MCP_PORT,
    )

    mcp.run(transport="streamable-http")
