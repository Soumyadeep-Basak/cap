
"""A2A server for the Invoice Translation Agent."""

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

from invoice_auditor.agents.Invoice_Translation_Agent.a2a_agent.translation_executor import (
    TranslationAgentExecutor,
)

logger = logging.getLogger(__name__)

A2A_HOST = os.getenv(
    "TRANSLATION_A2A_HOST",
    "0.0.0.0",
)
A2A_PORT = int(
    os.getenv("TRANSLATION_A2A_PORT", "8012")
)
A2A_PUBLIC_URL = os.getenv(
    "TRANSLATION_A2A_PUBLIC_URL",
    "http://translation-a2a:8012",
).rstrip("/")


async def health(request):
    """Container health endpoint."""
    return JSONResponse({"status": "healthy"})


skill = AgentSkill(
    id="invoice_text_translation",
    name="Invoice Text Translation",
    description=(
        "Detect the language of an invoice and translate it "
        "into English through the existing Translation MCP. "
        "Supports Redis caching, Amazon Bedrock, confidence "
        "scoring and PostgreSQL persistence."
    ),
    tags=[
        "invoice",
        "translation",
        "language-detection",
        "amazon-bedrock",
        "multilingual",
    ],
    examples=[
        '{"action": "translate", '
        '"invoice_id": "00000000-0000-0000-0000-000000000001", '
        '"raw_extracted_text": "Invoice No: INV-1001"}',
    ],
    input_modes=["text/plain"],
    output_modes=["application/json"],
)


agent_card = AgentCard(
    name="Invoice Translation Agent",
    description=(
        "A2A interface for multilingual invoice translation "
        "using the existing Translation MCP and Google ADK."
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
    agent_executor=TranslationAgentExecutor(),
    task_store=InMemoryTaskStore(),
    agent_card=agent_card,
)


routes = [
    Route(
        "/health",
        health,
        methods=["GET"],
    ),
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
        "Starting Translation A2A server at %s",
        A2A_PUBLIC_URL,
    )

    uvicorn.run(
        app,
        host=A2A_HOST,
        port=A2A_PORT,
    )
