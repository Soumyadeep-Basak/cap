
"""Translation MCP server using the existing Google ADK agent."""

from __future__ import annotations

import logging
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from invoice_auditor.agents.translation_agent import (
    run_translation,
)
from invoice_auditor.agents.Invoice_Translation_Agent.translation_service import (
    prepare_translation_response,
    prepare_translation_state,
)

logger = logging.getLogger(__name__)

MCP_HOST = os.getenv("TRANSLATION_MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("TRANSLATION_MCP_PORT", "8004"))

mcp = FastMCP(
    "invoice-translation-mcp-server",
    host=MCP_HOST,
    port=MCP_PORT,
    stateless_http=True,
    json_response=True,
)


@mcp.tool()
async def translate_invoice_document(
    invoice_id: str,
    raw_extracted_text: str,
) -> dict[str, Any]:
    """
    Translate extracted invoice text into English.

    Uses the existing Translation Agent Google ADK.

    The agent handles:
    - Redis cache lookup
    - Amazon Bedrock language detection
    - English pass-through
    - Non-English translation
    - Translation confidence
    - Redis cache storage
    - PostgreSQL persistence
    - Translation failure recording

    Args:
        invoice_id: Existing invoice audit UUID.
        raw_extracted_text: Text extracted from an invoice.

    Returns:
        Translation status, detected language, translated text,
        confidence, cache-hit indicator, and processing error.
    """

    state = prepare_translation_state(
        invoice_id=invoice_id,
        raw_extracted_text=raw_extracted_text,
    )

    logger.info(
        "Starting Translation MCP for invoice_id=%s",
        state["invoice_id"],
    )

    try:
        result = await run_translation(state)

        response = prepare_translation_response(result)

        if response["translation_status"] == "completed":
            logger.info(
                "Translation MCP completed: invoice_id=%s, "
                "language=%s, cache_hit=%s",
                state["invoice_id"],
                response["source_language"],
                response["translation_cache_hit"],
            )
        else:
            logger.error(
                "Translation MCP failed for invoice_id=%s: %s",
                state["invoice_id"],
                response["processing_error"],
            )

        return response

    except Exception:
        logger.exception(
            "Translation MCP agent raised an exception: %s",
            state["invoice_id"],
        )
        raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    logger.info(
        "Starting Translation MCP server on %s:%s",
        MCP_HOST,
        MCP_PORT,
    )

    mcp.run(transport="streamable-http")
