
"""A2A server for the Invoice Monitoring Agent."""

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

from invoice_auditor.agents.Invoice_Monitoring_Agent.a2a_agent.monitor_executor import (
    MonitoringAgentExecutor,
)

logger = logging.getLogger(__name__)

A2A_HOST = os.getenv("MONITORING_A2A_HOST", "0.0.0.0")
A2A_PORT = int(os.getenv("MONITORING_A2A_PORT", "8010"))
A2A_PUBLIC_URL = os.getenv(
    "MONITORING_A2A_PUBLIC_URL",
    "http://monitoring-a2a:8010",
).rstrip("/")


async def health(request):
    """Container health endpoint."""
    return JSONResponse({"status": "healthy"})


skill = AgentSkill(
    id="invoice_monitoring_scan",
    name="Invoice Monitoring Scan",
    description=(
        "Discover and register new invoice documents, detect "
        "duplicates using SHA-256, and return invoices that "
        "are ready for downstream processing."
    ),
    tags=[
        "invoice",
        "monitoring",
        "document-discovery",
        "duplicate-detection",
    ],
    examples=[
        "scan",
        '{"action": "scan"}',
    ],
    input_modes=["text/plain"],
    output_modes=["application/json"],
)


agent_card = AgentCard(
    name="Invoice Monitoring Agent",
    description=(
        "A2A interface for discovering, registering, and "
        "routing invoice documents through the existing "
        "Invoice Monitoring MCP and LangGraph workflow."
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
    agent_executor=MonitoringAgentExecutor(),
    task_store=InMemoryTaskStore(),
    agent_card=agent_card,
)


routes = [
    Route("/health", health, methods=["GET"]),
]

routes.extend(create_agent_card_routes(agent_card))
routes.extend(create_jsonrpc_routes(request_handler, "/"))

app = Starlette(routes=routes)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    logger.info(
        "Starting Monitoring A2A server: %s",
        A2A_PUBLIC_URL,
    )

    uvicorn.run(
        app,
        host=A2A_HOST,
        port=A2A_PORT,
    )
