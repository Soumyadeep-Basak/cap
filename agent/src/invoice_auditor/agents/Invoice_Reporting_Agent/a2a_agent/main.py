
"""A2A server for the Invoice Reporting Agent."""

from __future__ import annotations

import logging
import os

import uvicorn

from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    create_agent_card_routes,
    create_jsonrpc_routes,
)
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
)

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from invoice_auditor.agents.Invoice_Reporting_Agent.a2a_agent.reporting_executor import (
    ReportingAgentExecutor,
)

logger = logging.getLogger(__name__)

A2A_HOST = os.getenv(
    "REPORTING_A2A_HOST",
    "0.0.0.0",
)

A2A_PORT = int(
    os.getenv("REPORTING_A2A_PORT", "8015")
)

A2A_PUBLIC_URL = os.getenv(
    "REPORTING_A2A_PUBLIC_URL",
    "http://reporting-a2a:8015",
).rstrip("/")


async def health(request):
    """Container health endpoint."""
    return JSONResponse({"status": "healthy"})


skill = AgentSkill(
    id="invoice_audit_report_generation",
    name="Invoice Audit Report Generation",
    description=(
        "Generate JSON and HTML invoice audit reports "
        "using combined invoice data and business validation "
        "results. Summarize discrepancies, severity, "
        "translation confidence and final recommendations. "
        "Persist the report to PostgreSQL through the "
        "existing Reporting MCP and LangGraph."
    ),
    tags=[
        "invoice",
        "reporting",
        "audit",
        "html",
        "json",
        "discrepancies",
    ],
    examples=[
        '{"action": "generate_report", '
        '"invoice_id": "00000000-0000-0000-0000-000000000001", '
        '"file_path": "/app/data/incoming/INV_EN_001.pdf", '
        '"invoice": {"invoice_number": "INV-1001"}, '
        '"validation_result": {'
        '"validation_status": "failed", '
        '"recommendation": "review", '
        '"discrepancies": [], '
        '"missing_fields": [], '
        '"validation_errors": []}}',
    ],
    input_modes=["text/plain"],
    output_modes=["application/json"],
)


agent_card = AgentCard(
    name="Invoice Reporting Agent",
    description=(
        "A2A interface for generating and persisting "
        "invoice audit reports through Reporting MCP."
    ),
    version="1.0.0",
    default_input_modes=["text/plain"],
    default_output_modes=["application/json"],
    capabilities=AgentCapabilities(
        streaming=False,
        push_notifications=False,
    ),
    supported_interfaces=[
        AgentInterface(
            protocol_binding="JSONRPC",
            url=A2A_PUBLIC_URL,
            protocol_version="1.0",
        )
    ],
    skills=[skill],
)


request_handler = DefaultRequestHandler(
    agent_executor=ReportingAgentExecutor(),
    task_store=InMemoryTaskStore(),
    agent_card=agent_card,
)


routes = [
    Route("/health", health, methods=["GET"]),
]

routes.extend(
    create_agent_card_routes(agent_card)
)

routes.extend(
    create_jsonrpc_routes(request_handler, "/")
)

app = Starlette(routes=routes)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    logger.info(
        "Starting Reporting A2A server at %s",
        A2A_PUBLIC_URL,
    )

    uvicorn.run(
        app,
        host=A2A_HOST,
        port=A2A_PORT,
    )
