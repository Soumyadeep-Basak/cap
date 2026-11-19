
"""MCP client for the Invoice Translation Agent."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import TextContent

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).with_name("mcp_config.json")


def load_mcp_config() -> dict[str, Any]:
    """Load the Translation MCP client configuration."""

    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        config = json.load(file)

    config["url"] = os.getenv(
        "TRANSLATION_MCP_URL",
        config["url"],
    )

    return config


async def _call_translation_tool(
    state: dict[str, Any],
) -> dict[str, Any]:
    """Invoke the translation tool over Streamable HTTP."""

    config = load_mcp_config()

    arguments = {
        "invoice_id": state["invoice_id"],
        "raw_extracted_text": state["raw_extracted_text"],
    }

    async with streamable_http_client(config["url"]) as (
        read_stream,
        write_stream,
        _,
    ):
        async with ClientSession(
            read_stream,
            write_stream,
        ) as session:
            await session.initialize()

            result = await session.call_tool(
                config["tool_name"],
                arguments=arguments,
            )

            if result.isError:
                error_messages = [
                    item.text
                    for item in result.content
                    if isinstance(item, TextContent)
                ]

                raise RuntimeError(
                    "Translation MCP tool error: "
                    + (
                        "; ".join(error_messages)
                        or "Unknown MCP error"
                    )
                )

            response = result.structuredContent

            if not isinstance(response, dict):
                text_messages = [
                    item.text
                    for item in result.content
                    if isinstance(item, TextContent)
                ]

                if not text_messages:
                    raise RuntimeError(
                        "Translation MCP returned an empty response"
                    )

                try:
                    response = json.loads(text_messages[0])
                except json.JSONDecodeError as exc:
                    raise RuntimeError(
                        "Translation MCP returned invalid JSON"
                    ) from exc

            if not isinstance(response, dict):
                raise RuntimeError(
                    "Translation MCP response is not a dictionary"
                )

            required_fields = {
                "invoice_id",
                "translation_status",
                "source_language",
                "translated_text",
                "translation_confidence",
                "translation_cache_hit",
                "processing_error",
            }

            missing_fields = required_fields - response.keys()

            if missing_fields:
                raise RuntimeError(
                    "Translation MCP response missing fields: "
                    + ", ".join(sorted(missing_fields))
                )

            if response["translation_status"] not in {
                "completed",
                "failed",
            }:
                raise RuntimeError(
                    "Unexpected translation status: "
                    + str(response["translation_status"])
                )

            if response["translation_status"] == "completed":
                if not response["translated_text"]:
                    raise RuntimeError(
                        "Translation completed without translated text"
                    )

                if response["source_language"] is None:
                    raise RuntimeError(
                        "Translation completed without source language"
                    )

                if response["translation_confidence"] is None:
                    raise RuntimeError(
                        "Translation completed without confidence"
                    )

            return response


def translate_invoice_via_mcp(
    state: dict[str, Any],
) -> dict[str, Any]:
    """
    Run invoice translation through the MCP server.

    Expected input:
        {
            "invoice_id": "...",
            "raw_extracted_text": "..."
        }

    Returns a dictionary compatible with the existing
    Translation Agent output state.
    """

    if not isinstance(state, dict):
        raise TypeError("Translation state must be a dictionary")

    if not state.get("invoice_id"):
        raise ValueError("invoice_id is required")

    if not state.get("raw_extracted_text"):
        raise ValueError("raw_extracted_text is required")

    try:
        response = asyncio.run(
            _call_translation_tool(state)
        )

        logger.info(
            "Translation MCP response: invoice_id=%s, status=%s",
            state["invoice_id"],
            response["translation_status"],
        )

        return response

    except Exception:
        logger.exception(
            "Translation MCP invocation failed for invoice_id=%s",
            state["invoice_id"],
        )
        raise
