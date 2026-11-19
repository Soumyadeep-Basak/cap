
"""A2A executor for invoice business validation against Mock ERP."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

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

from invoice_auditor.agents.Invoice_Business_Validation_Agent.business_validation_agent_client import (
    validate_business_invoice_via_mcp,
)

from invoice_auditor.infrastructure.mcp_errors import describe_mcp_error

logger = logging.getLogger(__name__)


def parse_business_validation_request(
    message: str,
) -> dict[str, Any]:
    """Validate the invoice payload received through A2A."""

    try:
        payload = json.loads(message)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Business validation request must be valid JSON"
        ) from exc

    if not isinstance(payload, dict):
        raise ValueError(
            "Business validation request must be a JSON object"
        )

    if payload.get("action") != "validate_business":
        raise ValueError(
            "Only the validate_business action is supported"
        )

    if set(payload) != {"action", "invoice"}:
        raise ValueError(
            "Request must contain exactly action and invoice"
        )

    invoice = payload.get("invoice")

    if not isinstance(invoice, dict) or not invoice:
        raise ValueError(
            "invoice must be a nonempty JSON object"
        )

    line_items = invoice.get("line_items", [])

    if line_items is not None and not isinstance(line_items, list):
        raise ValueError(
            "invoice.line_items must be a list"
        )

    return invoice


class BusinessValidationAgentExecutor(AgentExecutor):
    """Execute ERP business validation through the existing MCP."""

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:

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
                "Validating invoice against Mock ERP through MCP."
            ),
        )

        try:
            request_text = get_message_text(context.message)

            invoice = parse_business_validation_request(
                request_text
            )

            # The synchronous MCP client internally uses asyncio.run().
            # Execute it in a thread to avoid a nested event loop.
            result = await asyncio.to_thread(
                validate_business_invoice_via_mcp,
                invoice,
            )

            if not isinstance(result, dict):
                raise RuntimeError(
                    "Business Validation MCP returned an invalid result"
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

            missing = required_fields - result.keys()

            if missing:
                raise RuntimeError(
                    "Business Validation MCP response missing: "
                    + ", ".join(sorted(missing))
                )

            response = {
                "agent": "invoice-business-validation-agent",
                "action": "validate_business",
                **result,
            }

            await updater.add_artifact(
                parts=[
                    new_text_part(
                        text=json.dumps(
                            response,
                            ensure_ascii=False,
                            default=str,
                        ),
                        media_type="application/json",
                    )
                ],
            )

            # The invoice may fail business rules while the
            # A2A task itself completes successfully.
            await updater.update_status(
                state=TaskState.TASK_STATE_COMPLETED,
                message=new_text_message(
                    "Invoice business validation completed."
                ),
            )

            logger.info(
                "Business Validation A2A completed: "
                "invoice=%s status=%s discrepancies=%d",
                invoice.get("invoice_number"),
                result["business_validation_status"],
                len(result["discrepancies"]),
            )

        except Exception as exc:
            logger.exception(
                "Business Validation A2A execution failed"
            )

            await updater.update_status(
                state=TaskState.TASK_STATE_FAILED,
                message=new_text_message(
                    f"Business validation request failed: {describe_mcp_error(exc)}"
                ),
            )

    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        raise NotImplementedError(
            "Business validation tasks do not support cancellation"
        )
