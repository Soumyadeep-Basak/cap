"""Invoke the separately hosted RAG tools using MCP Streamable HTTP."""

import asyncio
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from invoice_auditor.mcp_call_logging import logged_mcp_call

import httpx
from mcp import ClientSession
from mcp.types import TextContent
from mcp.client.streamable_http import streamable_http_client
from pydantic_core import to_jsonable_python


class RagMcpError(RuntimeError):
    """The RAG tool could not be reached or returned an MCP error."""


@lru_cache(maxsize=1)
def load_mcp_config() -> dict[str, Any]:
    config = Path(__file__).parent / "config" / "mcp_config.json"
    return json.loads(config.read_text(encoding="utf-8"))


async def invoke_rag_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    config = load_mcp_config()
    url = os.getenv("RAG_MCP_URL") or config["local_url"]
    timeout = config["timeout_seconds"]
    try:
        async with asyncio.timeout(timeout):
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout, connect=10.0)
            ) as http_client:
                async with streamable_http_client(
                    url, http_client=http_client
                ) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await logged_mcp_call(
                            session, "rag", name, to_jsonable_python(arguments)
                        )

        if result.isError:
            raise RagMcpError(f"RAG tool {name} failed")
        payload = result.structuredContent
        if payload is None:
            content = next(
                (item.text for item in result.content if isinstance(item, TextContent)), ""
            )
            payload = json.loads(content)
        if not isinstance(payload, dict):
            raise RagMcpError(f"RAG tool {name} returned an unexpected result")
        return payload
    except RagMcpError:
        raise
    except Exception as exc:
        raise RagMcpError(f"Could not invoke RAG tool {name}") from exc


def call_rag_tool(name: str, **arguments: Any) -> dict[str, Any]:
    return asyncio.run(invoke_rag_tool(name, arguments))


def index_invoice(state: dict[str, Any]) -> dict[str, Any]:
    # The indexing worker can load persisted evidence when optional source data
    # is missing. Forward supplied values to preserve revalidation behavior.
    source = {key: value for key, value in state.items() if key != "invoice_id"}
    try:
        return call_rag_tool("vector_indexer", invoice_id=state["invoice_id"], source=source)
    except RagMcpError as exc:
        return {"index_status": "failed", "index_error": str(exc), "indexed_chunks": 0}
