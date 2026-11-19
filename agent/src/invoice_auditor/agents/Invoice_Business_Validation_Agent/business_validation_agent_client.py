
"""MCP client for the Invoice Business Validation Agent."""

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

from invoice_auditor.agents.Invoice_Business_Validation_Agent.business_validation_service import (
    make_json_safe,
)

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).with_name("mcp_config.json")


def load_mcp_config() -> dict[str, Any]:
    """Load the Business Validation MCP connection settings."""

    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        config = json.load(file)

    config["url"] = os.getenv(
        "BUSINESS_VALIDATION_MCP_URL",
        config["url"],
    )

    return config


async def _call_business_validation_tool(
    invoice: dict[str, Any],
) -> dict[str, Any]:
    """Call the ERP business validation MCP tool."""

    config = load_mcp_config()

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
                arguments={
                    "invoice": make_json_safe(invoice),
                },
            )

            if result.isError:
                messages = [
                    item.text
                    for item in result.content
                    if isinstance(item, TextContent)
                ]

                raise RuntimeError(
                    "Business Validation MCP tool failed: "
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
                        "Business Validation MCP returned no response"
                    )

                try:
                    response = json.loads(messages[0])
                except json.JSONDecodeError as exc:
                    raise RuntimeError(
                        "Business Validation MCP returned invalid JSON"
                    ) from exc

            if not isinstance(response, dict):
                raise RuntimeError(
                    "Business Validation MCP response must be a dictionary"
                )

            required_fields = {
                "business_validation_status",
                "business_recommendation",
                "discrepancies",
                "validation_errors",
                "erp_po",
                "erp_vendor",
                "erp_skus",
            }

            missing = required_fields - response.keys()

            if missing:
                raise RuntimeError(
                    "Business Validation MCP response missing fields: "
                    + ", ".join(sorted(missing))
                )

            if response["business_validation_status"] not in {
                "passed",
                "failed",
            }:
                raise RuntimeError(
                    "Invalid business validation status: "
                    + str(response["business_validation_status"])
                )

            if not isinstance(response["discrepancies"], list):
                raise RuntimeError(
                    "Business Validation discrepancies must be a list"
                )

            if not isinstance(response["validation_errors"], list):
                raise RuntimeError(
                    "Business Validation errors must be a list"
                )

            return response


def validate_business_invoice_via_mcp(
    invoice: dict[str, Any],
) -> dict[str, Any]:
    """
    Execute business validation through MCP.

    Returns the same business validation output fields
    expected by the parent LangGraph.
    """

    if not isinstance(invoice, dict) or not invoice:
        raise ValueError("invoice must be a nonempty dictionary")

    try:
        result = asyncio.run(
            _call_business_validation_tool(invoice)
        )

        logger.info(
            "Business Validation MCP response: status=%s",
            result["business_validation_status"],
        )

        return result

    except Exception:
        logger.exception(
            "Business Validation MCP invocation failed"
        )
        raise
