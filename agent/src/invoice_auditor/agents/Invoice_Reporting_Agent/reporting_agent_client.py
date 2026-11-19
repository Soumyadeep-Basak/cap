
"""MCP client for the Invoice Reporting Agent."""

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
    """Load Reporting MCP connection configuration."""
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        config = json.load(file)

    config["url"] = os.getenv(
        "REPORTING_MCP_URL",
        config["url"],
    )

    return config


def make_json_safe(value: Any) -> Any:
    """Serialize dates, decimals, and nested values for MCP."""
    if isinstance(value, dict):
        return {
            str(key): make_json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [make_json_safe(item) for item in value]

    if hasattr(value, "isoformat"):
        return value.isoformat()

    if hasattr(value, "as_tuple"):
        return str(value)

    return value


async def _call_reporting_tool(
    state: dict[str, Any],
) -> dict[str, Any]:
    """Call the report-generation MCP tool."""
    config = load_mcp_config()

    arguments = make_json_safe({
        "invoice_id": state["invoice_id"],
        "file_path": state.get("file_path", ""),
        "invoice": state.get("invoice") or {},
        "validation_result": state.get("validation_result") or {},
        "translation_confidence": state.get(
            "translation_confidence"
        ),
        "source_language": state.get("source_language"),
        "translated_text": state.get("translated_text"),
        "erp_data": state.get("erp_data") or {},
    })

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
                errors = [
                    item.text
                    for item in result.content
                    if isinstance(item, TextContent)
                ]

                raise RuntimeError(
                    "Reporting MCP tool failed: "
                    + ("; ".join(errors) or "Unknown error")
                )

            response = result.structuredContent

            if not isinstance(response, dict):
                messages = [
                    item.text
                    for item in result.content
                    if isinstance(item, TextContent)
                ]

                if not messages:
                    raise RuntimeError(
                        "Reporting MCP returned no response"
                    )

                try:
                    response = json.loads(messages[0])
                except json.JSONDecodeError as exc:
                    raise RuntimeError(
                        "Reporting MCP returned invalid JSON"
                    ) from exc

            if not isinstance(response, dict):
                raise RuntimeError(
                    "Reporting MCP response must be an object"
                )

            required_fields = {
                "invoice_id",
                "report_status",
                "json_report_path",
                "html_report_path",
                "report",
            }

            missing = required_fields - response.keys()

            if missing:
                raise RuntimeError(
                    "Reporting MCP missing fields: "
                    + ", ".join(sorted(missing))
                )

            if response["report_status"] != "completed":
                raise RuntimeError(
                    "Reporting MCP did not complete successfully"
                )

            return response


def generate_invoice_report_via_mcp(
    state: dict[str, Any],
) -> dict[str, Any]:
    """
    Synchronously call the Reporting MCP server.

    Accepts the same input state as the existing reporting_graph.
    Returns a dictionary containing report status, report data,
    and the JSON/HTML output paths.
    """
    if not isinstance(state, dict):
        raise TypeError("Reporting state must be a dictionary")

    if not state.get("invoice_id"):
        raise ValueError("invoice_id is required")

    try:
        result = asyncio.run(
            _call_reporting_tool(state)
        )

        logger.info(
            "Reporting MCP completed for invoice_id=%s",
            state["invoice_id"],
        )

        return result

    except Exception:
        logger.exception(
            "Reporting MCP request failed for invoice_id=%s",
            state["invoice_id"],
        )
        raise
