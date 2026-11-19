
"""A2A executor for invoice data validation."""

from __future__ import annotations

import asyncio
import json
import logging
import math
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

from invoice_auditor.agents.Invoice_Validation_Agent.validation_agent_client import (
    validate_invoice_via_mcp,
)

from invoice_auditor.infrastructure.mcp_errors import describe_mcp_error

logger = logging.getLogger(__name__)


def parse_validation_request(
    message: str,
) -> dict[str, Any]:
    """Validate an incoming A2A invoice validation request."""

    try:
        payload = json.loads(message)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Validation request must contain valid JSON"
        ) from exc

    if not isinstance(payload, dict):
        raise ValueError(
            "Validation request must be a JSON object"
        )

    if payload.get("action") != "validate":
        raise ValueError(
            "Only the validate action is supported"
        )

    allowed_fields = {
        "action",
        "invoice",
        "translation_confidence",
    }

    if set(payload) - allowed_fields:
        raise ValueError(
            "Unexpected fields in validation request"
        )

    invoice = payload.get("invoice")

    if not isinstance(invoice, dict) or not invoice:
        raise ValueError(
            "invoice must be a nonempty JSON object"
        )

    confidence = payload.get("translation_confidence")

    if confidence is not None:
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
        ):
            raise ValueError(
                "translation_confidence must be numeric"
            )

        confidence = float(confidence)

        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError(
                "translation_confidence must be between 0 and 1"
            )

    return {
        "invoice": invoice,
        "translation_confidence": confidence,
    }


class ValidationAgentExecutor(AgentExecutor):
    """Run the existing Invoice Data Validation MCP through A2A."""

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
            task = new_task_from_user_message(
                context.message
            )
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(
            event_queue=event_queue,
            task_id=task.id,
            context_id=task.context_id,
        )

        await updater.update_status(
            state=TaskState.TASK_STATE_WORKING,
            message=new_text_message(
                "Validating invoice data through MCP."
            ),
        )

        try:
            request_text = get_message_text(
                context.message
            )

            request = parse_validation_request(
                request_text
            )

            # The existing synchronous MCP client uses
            # asyncio.run(). Execute it in a worker thread.
            result = await asyncio.to_thread(
                validate_invoice_via_mcp,
                invoice=request["invoice"],
                translation_confidence=request[
                    "translation_confidence"
                ],
            )

            if not isinstance(result, dict):
                raise RuntimeError(
                    "Validation MCP returned an invalid response"
                )

            response = {
                "agent": "invoice-data-validation-agent",
                "action": "validate",
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

            # A failed or partial invoice validation is a
            # legitimate audit outcome, not an A2A failure.
            await updater.update_status(
                state=TaskState.TASK_STATE_COMPLETED,
                message=new_text_message(
                    "Invoice data validation completed."
                ),
            )

            logger.info(
                "Validation A2A completed: status=%s, "
                "recommendation=%s",
                result.get("validation_status"),
                result.get("recommendation"),
            )

        except Exception as exc:
            logger.exception(
                "Validation A2A execution failed"
            )

            await updater.update_status(
                state=TaskState.TASK_STATE_FAILED,
                message=new_text_message(
                    f"Invoice validation request failed: {describe_mcp_error(exc)}"
                ),
            )

    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        raise NotImplementedError(
            "Invoice validation tasks do not support cancellation"
        )
