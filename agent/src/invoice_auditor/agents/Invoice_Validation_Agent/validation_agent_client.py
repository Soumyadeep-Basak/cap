
"""MCP client for the Invoice Validation Agent."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


logger = logging.getLogger(__name__)

VALIDATION_MCP_URL = os.getenv(
    "VALIDATION_MCP_URL",
    "http://validation-mcp:8003/mcp",
)

VALIDATION_TOOL_NAME = "validate_invoice_document"


async def _validate_invoice_via_mcp(
    invoice: dict[str, Any],
    translation_confidence: float | None = None,
) -> dict[str, Any]:
    """Discover and invoke the invoice validation MCP tool."""

    if not isinstance(invoice, dict) or not invoice:
        raise ValueError("A non-empty invoice dictionary is required.")

    if translation_confidence is not None:
        if isinstance(translation_confidence, bool):
            raise TypeError(
                "translation_confidence must be numeric."
            )

        translation_confidence = float(translation_confidence)

        if not 0.0 <= translation_confidence <= 1.0:
            raise ValueError(
                "translation_confidence must be between 0 and 1."
            )

    try:
        async with streamable_http_client(
            VALIDATION_MCP_URL
        ) as (read_stream, write_stream, _):
            async with ClientSession(
                read_stream,
                write_stream,
            ) as session:
                await session.initialize()

                # Discover available MCP tools.
                tools_response = await session.list_tools()

                available_tools = {
                    tool.name
                    for tool in tools_response.tools
                }

                if VALIDATION_TOOL_NAME not in available_tools:
                    raise RuntimeError(
                        f"MCP tool '{VALIDATION_TOOL_NAME}' "
                        f"not found at {VALIDATION_MCP_URL}. "
                        f"Available tools: {sorted(available_tools)}"
                    )

                # Invoke the validation tool.
                arguments: dict[str, Any] = {
                    "invoice": invoice,
                    "translation_confidence": translation_confidence,
                }

                logger.info(
                    "Invoking invoice validation MCP tool."
                )

                result = await session.call_tool(
                    VALIDATION_TOOL_NAME,
                    arguments=arguments,
                )

                if result.isError:
                    error_messages = [
                        item.text
                        for item in result.content
                        if hasattr(item, "text")
                    ]

                    raise RuntimeError(
                        "Invoice validation MCP tool failed: "
                        + "; ".join(error_messages)
                    )

                # Prefer structured MCP output.
                structured_content = getattr(
                    result,
                    "structuredContent",
                    None,
                )

                if isinstance(structured_content, dict):
                    validation_result = structured_content

                else:
                    # Fall back to parsing text content.
                    text_content = [
                        item.text
                        for item in result.content
                        if hasattr(item, "text")
                    ]

                    if not text_content:
                        raise RuntimeError(
                            "MCP server returned an empty validation response."
                        )

                    try:
                        validation_result = json.loads(
                            text_content[0]
                        )
                    except json.JSONDecodeError as exc:
                        raise RuntimeError(
                            "MCP server returned invalid JSON: "
                            f"{text_content[0]}"
                        ) from exc

                if not isinstance(validation_result, dict):
                    raise RuntimeError(
                        "MCP validation response must be a JSON object."
                    )

                logger.info(
                    "Invoice validation completed. Status: %s",
                    validation_result.get("validation_status"),
                )

                return validation_result

    except Exception:
        logger.exception(
            "Invoice validation MCP request failed."
        )
        raise


def validate_invoice_via_mcp(
    invoice: dict[str, Any],
    translation_confidence: float | None = None,
) -> dict[str, Any]:
    """
    Synchronous entry point for the invoice workflow.

    Calls the asynchronous MCP client and returns validation results.
    """

    try:
        return asyncio.run(
            _validate_invoice_via_mcp(
                invoice=invoice,
                translation_confidence=translation_confidence,
            )
        )
    except RuntimeError as exc:
        if "asyncio.run() cannot be called" in str(exc):
            raise RuntimeError(
                "validate_invoice_via_mcp() cannot run inside "
                "an active event loop. Use "
                "_validate_invoice_via_mcp() asynchronously instead."
            ) from exc
        raise
