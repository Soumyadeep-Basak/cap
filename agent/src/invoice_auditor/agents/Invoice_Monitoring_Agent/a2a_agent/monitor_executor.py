
"""A2A executor for the existing Invoice Monitoring Agent."""

from __future__ import annotations

import asyncio
import json
import logging

from a2a.helpers import (
    get_message_text,
    new_task_from_user_message,
    new_text_message,
    new_text_part,
)
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import TaskState

from invoice_auditor.agents.Invoice_Monitoring_Agent.monitoring_agent_client import (
    scan_invoices_via_mcp,
)

from invoice_auditor.infrastructure.mcp_errors import describe_mcp_error

logger = logging.getLogger(__name__)


def validate_scan_request(message: str) -> str | None:
    """
    Accept only the monitoring scan action.

    The MCP server authorizes the optional configured incoming directory.
    """
    request = message.strip()

    if request.lower() == "scan":
        return None

    try:
        payload = json.loads(request)
    except json.JSONDecodeError as exc:
        raise ValueError(
            'Expected "scan" or {"action": "scan"}'
        ) from exc

    if not isinstance(payload, dict):
        raise ValueError("A2A request must be a JSON object")

    if payload.get("action") != "scan" or payload.keys() - {"action", "incoming_dir"}:
        raise ValueError("Expected the scan action and optional incoming_dir")

    incoming_dir = payload.get("incoming_dir")
    if "incoming_dir" in payload and (
        not isinstance(incoming_dir, str) or not incoming_dir.strip()
    ):
        raise ValueError("incoming_dir must be a nonempty string")
    return incoming_dir


class MonitoringAgentExecutor(AgentExecutor):
    """Expose one Monitoring MCP scan as an A2A task."""

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Handle a monitoring request from another A2A agent."""

        if context.message is None:
            raise ValueError("A2A request has no message")

        if context.current_task:
            task = context.current_task
        else:
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(
            event_queue=event_queue,
            task_id=task.id,
            context_id=task.context_id,
        )

        await updater.update_status(
            state=TaskState.TASK_STATE_WORKING,
            message=new_text_message(
                "Processing invoice monitoring request."
            ),
        )

        try:
            request_text = get_message_text(context.message)
            incoming_dir = validate_scan_request(request_text)

            # The MCP client is synchronous and calls asyncio.run().
            # Run it in a worker thread rather than inside this
            # A2A server's active asyncio event loop.
            result = await asyncio.to_thread(
                scan_invoices_via_mcp, incoming_dir
            )

            response = {
                "agent": "invoice-monitoring-agent",
                "action": "scan",
                **result,
            }

            await updater.add_artifact(
                parts=[
                    new_text_part(
                        text=json.dumps(response),
                        media_type="application/json",
                    )
                ],
            )

            await updater.update_status(
                state=TaskState.TASK_STATE_COMPLETED,
                message=new_text_message(
                    "Invoice monitoring scan completed."
                ),
            )

            logger.info(
                "Monitoring A2A completed: discovered=%s routed=%s",
                result["discovered_count"],
                result["routed_count"],
            )

        except Exception as exc:
            logger.exception("Monitoring A2A execution failed")

            await updater.update_status(
                state=TaskState.TASK_STATE_FAILED,
                message=new_text_message(
                    f"Monitoring request failed: {describe_mcp_error(exc)}"
                ),
            )

    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Cancellation is not supported for a short scan operation."""
        raise NotImplementedError(
            "Monitoring scan tasks do not support cancellation"
        )
