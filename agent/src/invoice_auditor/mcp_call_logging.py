"""Record MCP tool calls without logging request or response bodies."""

import logging
from time import monotonic
from uuid import uuid4

logger = logging.getLogger(__name__)


async def logged_mcp_call(session, agent: str, tool: str, arguments: dict):
    call_id = uuid4().hex
    started = monotonic()
    logger.info("mcp_call_start agent=%s tool=%s call_id=%s", agent, tool, call_id)
    try:
        result = await session.call_tool(tool, arguments=arguments)
    except Exception as exc:
        logger.warning(
            "mcp_call_finish agent=%s tool=%s call_id=%s outcome=transport_error error_type=%s elapsed_ms=%d",
            agent, tool, call_id, type(exc).__name__, (monotonic() - started) * 1000,
        )
        raise
    logger.info(
        "mcp_call_finish agent=%s tool=%s call_id=%s outcome=%s elapsed_ms=%d",
        agent, tool, call_id, "tool_error" if result.isError else "ok",
        (monotonic() - started) * 1000,
    )
    return result
