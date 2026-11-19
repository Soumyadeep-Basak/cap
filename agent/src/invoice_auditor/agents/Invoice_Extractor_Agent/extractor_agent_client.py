
"""MCP client for the Extractor Agent."""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any
from datetime import timedelta
import httpx

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import TextContent

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).with_name("mcp_config.json")


def load_mcp_config() -> dict[str, Any]:
    """Load Extractor MCP connection configuration."""
    with CONFIG_PATH.open("r", encoding="utf-8") as config_file:
        config = json.load(config_file)

    config["url"] = os.getenv(
        "EXTRACTOR_MCP_URL",
        config["url"],
    )

    return config


async def _call_extraction_tool(
    file_path: Path,
) -> tuple[str, str]:
    """Connect to Extractor MCP and invoke its extraction tool."""
    config = load_mcp_config()
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(240.0, connect=10.0),
    ) as http_client:
        async with streamable_http_client(
            config["url"],
            http_client=http_client,
        ) as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(
                read_stream,
                write_stream,
                read_timeout_seconds=timedelta(seconds=240),
            ) as session:
                await session.initialize()

                result = await session.call_tool(
                    config["tool_name"],
                    arguments={
                        "file_path": str(file_path.resolve()),
                    },
                )

                if result.isError:
                    error_messages = [
                        content.text
                        for content in result.content
                        if isinstance(content, TextContent)
                    ]

                    error_message = (
                        "\n".join(error_messages)
                        or "Extractor MCP tool execution failed"
                    )

                    raise RuntimeError(error_message)

                response = result.structuredContent

                if not response:
                    text_messages = [
                        content.text
                        for content in result.content
                        if isinstance(content, TextContent)
                    ]

                    if not text_messages:
                        raise RuntimeError(
                            "Extractor MCP returned an empty response"
                        )

                    try:
                        response = json.loads(text_messages[0])
                    except json.JSONDecodeError as exc:
                        raise RuntimeError(
                            "Extractor MCP returned an invalid response"
                        ) from exc

                raw_text = response.get("raw_text")
                extraction_method = response.get("extraction_method")

                if not isinstance(raw_text, str) or not raw_text.strip():
                    raise RuntimeError(
                        "Extractor MCP returned empty extracted text"
                    )

                if not isinstance(extraction_method, str):
                    raise RuntimeError(
                        "Extractor MCP did not return an extraction method"
                    )

                return raw_text, extraction_method


def extract_document_via_mcp(
    file_path: Path,
) -> tuple[str, str]:
    """
    Synchronously invoke the Extractor MCP server.

    The parent invoice workflow currently uses synchronous graph
    invocation, so this provides a synchronous interface.
    """
    try:
        return asyncio.run(
            _call_extraction_tool(file_path)
        )
    except Exception:
        logger.exception(
            "Extractor MCP call failed for %s",
            file_path,
        )
        raise
