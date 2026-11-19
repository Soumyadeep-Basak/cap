
"""A2A server for the Invoice Data Validation Agent."""

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

from invoice_auditor.agents.Invoice_Validation_Agent.a2a_agent.validation_executor import (
    ValidationAgentExecutor,
)

logger = logging.getLogger(__name__)

A2A_HOST = os.getenv(
    "VALIDATION_A2A_HOST",
    "0.0.0.0",
)

A2A_PORT = int(
    os.getenv("VALIDATION_A2A_PORT", "8013")
)

A2A_PUBLIC_URL = os.getenv(
    "VALIDATION_A2A_PUBLIC_URL",
    "http://validation-a2a:8013",
).rstrip("/")


async def health(request):
    """Container health endpoint."""
    return JSONResponse({"status": "healthy"})


skill = AgentSkill(
    id="invoice_data_validation",
    name="Invoice Data Validation",
    description=(
        "Validate invoice completeness, header fields, "
        "line-item arithmetic, subtotal, tax calculations, "
        "currency, and translation confidence using the "
        "existing Invoice Validation MCP and LangGraph."
    ),
    tags=[
        "invoice",
        "validation",
        "completeness",
        "arithmetic",
        "tax",
        "currency",
    ],
    examples=[
        '{"action": "validate", '
        '"invoice": {"invoice_number": "INV-1001", '
        '"currency": "USD", "line_items": []}, '
        '"translation_confidence": 1.0}',
    ],
    input_modes=["text/plain"],
    output_modes=["application/json"],
)


agent_card = AgentCard(
    name="Invoice Data Validation Agent",
    description=(
        "A2A interface for rule-driven invoice data "
        "validation through the existing Validation MCP."
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
    agent_executor=ValidationAgentExecutor(),
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
        "Starting Validation A2A server at %s",
        A2A_PUBLIC_URL,
    )

    uvicorn.run(
        app,
        host=A2A_HOST,
        port=A2A_PORT,
    )
