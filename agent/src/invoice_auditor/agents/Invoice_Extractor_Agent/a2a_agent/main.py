
"""A2A server for the Invoice Extractor Agent."""

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

from invoice_auditor.agents.Invoice_Extractor_Agent.a2a_agent.extractor_executor import (
    ExtractorAgentExecutor,
)

logger = logging.getLogger(__name__)

A2A_HOST = os.getenv("EXTRACTOR_A2A_HOST", "0.0.0.0")
A2A_PORT = int(os.getenv("EXTRACTOR_A2A_PORT", "8011"))
A2A_PUBLIC_URL = os.getenv(
    "EXTRACTOR_A2A_PUBLIC_URL",
    "http://extractor-a2a:8011",
).rstrip("/")


async def health(request):
    """Container health endpoint."""
    return JSONResponse({"status": "healthy"})


skill = AgentSkill(
    id="invoice_document_extraction",
    name="Invoice Document Extraction",
    description=(
        "Extract raw text from PDF, DOCX, and PNG invoices "
        "using the existing Extractor MCP tool. "
        "Supports embedded PDF text and OCR."
    ),
    tags=[
        "invoice",
        "extraction",
        "pdf",
        "docx",
        "ocr",
    ],
    examples=[
        '{"action": "extract", "file_path": '
        '"/app/data/incoming/INV_EN_001.pdf"}',
    ],
    input_modes=["application/json", "text/plain"],
    output_modes=["application/json"],
)


agent_card = AgentCard(
    name="Invoice Extractor Agent",
    description=(
        "A2A interface for extracting invoice text "
        "through the existing Extractor MCP server."
    ),
    version="1.0.0",
    default_input_modes=["application/json", "text/plain"],
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
    agent_executor=ExtractorAgentExecutor(),
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
        "Starting Extractor A2A server at %s",
        A2A_PUBLIC_URL,
    )

    uvicorn.run(
        app,
        host=A2A_HOST,
        port=A2A_PORT,
    )
