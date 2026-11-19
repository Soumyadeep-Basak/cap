
"""MCP client for the Invoice Monitoring Agent."""

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
    """Load the Monitoring MCP configuration."""
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        config = json.load(file)

    config["url"] = os.getenv(
        "MONITORING_MCP_URL",
        config["url"],
    )

    return config


async def _call_monitoring_tool(
    incoming_dir: str | None = None,
) -> dict[str, Any]:
    """Invoke the monitoring MCP tool over Streamable HTTP."""

    config = load_mcp_config()

    arguments = {}

    if incoming_dir is not None:
        arguments["incoming_dir"] = incoming_dir

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
                messages = [
                    item.text
                    for item in result.content
                    if isinstance(item, TextContent)
                ]

                raise RuntimeError(
                    "Monitoring MCP tool failed: "
                    + ("; ".join(messages) or "Unknown error")
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
                        "Monitoring MCP returned no response"
                    )

                try:
                    response = json.loads(messages[0])
                except json.JSONDecodeError as exc:
                    raise RuntimeError(
                        "Monitoring MCP returned invalid JSON"
                    ) from exc

            if not isinstance(response, dict):
                raise RuntimeError(
                    "Monitoring MCP response must be a dictionary"
                )

            required_fields = {
                "status",
                "discovered_files",
                "pending_invoices",
                "routed_invoices",
                "duplicate_files",
                "errors",
            }

            missing = required_fields - response.keys()

            if missing:
                raise RuntimeError(
                    "Monitoring MCP response missing fields: "
                    + ", ".join(sorted(missing))
                )

            if not isinstance(response["routed_invoices"], list):
                raise RuntimeError(
                    "Monitoring MCP routed_invoices must be a list"
                )

            if response["status"] != "completed":
                raise RuntimeError(
                    "Monitoring MCP did not complete: "
                    + str(response["status"])
                )

            return response


def scan_invoices_via_mcp(
    incoming_dir: str | None = None,
) -> dict[str, Any]:
    """
    Execute one Invoice Monitor scan through MCP.

    Returns the discovered, pending, routed, duplicate,
    and error fields from the existing monitoring LangGraph.

    The parent LangGraph is responsible for processing
    routed invoices after the scan.
    """
    if incoming_dir is not None:
        if not isinstance(incoming_dir, str) or not incoming_dir.strip():
            raise ValueError("incoming_dir must be a nonempty string")

    try:
        result = asyncio.run(
            _call_monitoring_tool(incoming_dir)
        )

        logger.info(
            "Monitoring MCP scan completed: routed=%d",
            len(result["routed_invoices"]),
        )

        return result

    except Exception:
        logger.exception("Monitoring MCP invocation failed")
        raise
