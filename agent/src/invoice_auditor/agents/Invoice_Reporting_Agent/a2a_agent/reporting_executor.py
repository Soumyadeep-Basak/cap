
"""A2A executor for invoice audit reporting."""

from __future__ import annotations

import asyncio
import json
import logging
import math
from typing import Any
from uuid import UUID

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

from invoice_auditor.agents.Invoice_Reporting_Agent.reporting_agent_client import (
    generate_invoice_report_via_mcp,
)

from invoice_auditor.infrastructure.mcp_errors import describe_mcp_error

logger = logging.getLogger(__name__)


def parse_reporting_request(
    message: str,
) -> dict[str, Any]:
    """Validate an incoming Reporting A2A request."""

    try:
        payload = json.loads(message)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Reporting request must contain valid JSON"
        ) from exc

    if not isinstance(payload, dict):
        raise ValueError(
            "Reporting request must be a JSON object"
        )

    if payload.get("action") != "generate_report":
        raise ValueError(
            "Only the generate_report action is supported"
        )

    allowed_fields = {
        "action",
        "invoice_id",
        "file_path",
        "invoice",
        "validation_result",
        "translation_confidence",
        "source_language",
        "translated_text",
        "erp_data",
    }

    unexpected = set(payload) - allowed_fields

    if unexpected:
        raise ValueError(
            "Unexpected reporting request fields: "
            + ", ".join(sorted(unexpected))
        )

    invoice_id = payload.get("invoice_id")

    if not isinstance(invoice_id, str):
        raise ValueError("invoice_id must be a string")

    try:
        invoice_id = str(UUID(invoice_id))
    except (ValueError, AttributeError) as exc:
        raise ValueError(
            "invoice_id must be a valid UUID"
        ) from exc

    file_path = payload.get("file_path", "")

    if not isinstance(file_path, str):
        raise ValueError("file_path must be a string")

    invoice = payload.get("invoice")

    if not isinstance(invoice, dict) or not invoice:
        raise ValueError(
            "invoice must be a nonempty JSON object"
        )

    validation_result = payload.get("validation_result")

    if not isinstance(validation_result, dict):
        raise ValueError(
            "validation_result must be a JSON object"
        )

    if validation_result.get("validation_status") not in {
        "passed",
        "partial",
        "failed",
    }:
        raise ValueError(
            "validation_result must contain a valid validation_status"
        )

    if validation_result.get("recommendation") not in {
        "approve",
        "review",
        "reject",
    }:
        raise ValueError(
            "validation_result must contain a valid recommendation"
        )

    for field in (
        "discrepancies",
        "missing_fields",
        "validation_errors",
    ):
        value = validation_result.get(field, [])

        if not isinstance(value, list):
            raise ValueError(
                f"validation_result.{field} must be a list"
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

    source_language = payload.get("source_language")
    translated_text = payload.get("translated_text")

    if source_language is not None and not isinstance(
        source_language, str
    ):
        raise ValueError("source_language must be a string or null")

    if translated_text is not None and not isinstance(
        translated_text, str
    ):
        raise ValueError("translated_text must be a string or null")

    erp_data = payload.get("erp_data") or {}

    if not isinstance(erp_data, dict):
        raise ValueError("erp_data must be a JSON object")

    return {
        "invoice_id": invoice_id,
        "file_path": file_path,
        "invoice": invoice,
        "validation_result": validation_result,
        "translation_confidence": confidence,
        "source_language": source_language,
        "translated_text": translated_text,
        "erp_data": erp_data,
    }


class ReportingAgentExecutor(AgentExecutor):
    """Generate reports by delegating to the existing Reporting MCP."""

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
                "Generating invoice audit report through MCP."
            ),
        )

        try:
            request_text = get_message_text(context.message)
            reporting_state = parse_reporting_request(
                request_text
            )

            # The existing MCP client calls asyncio.run().
            # Execute in a worker thread to avoid nesting
            # event loops inside the A2A server.
            result = await asyncio.to_thread(
                generate_invoice_report_via_mcp,
                reporting_state,
            )

            if not isinstance(result, dict):
                raise RuntimeError(
                    "Reporting MCP returned an invalid response"
                )

            if result.get("report_status") != "completed":
                raise RuntimeError(
                    "Reporting MCP did not complete successfully"
                )

            response = {
                "agent": "invoice-reporting-agent",
                "action": "generate_report",
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

            await updater.update_status(
                state=TaskState.TASK_STATE_COMPLETED,
                message=new_text_message(
                    "Invoice audit report generated and persisted."
                ),
            )

            logger.info(
                "Reporting A2A completed: invoice_id=%s",
                reporting_state["invoice_id"],
            )

        except Exception as exc:
            logger.exception("Reporting A2A execution failed")

            await updater.update_status(
                state=TaskState.TASK_STATE_FAILED,
                message=new_text_message(
                    f"Invoice reporting failed: {describe_mcp_error(exc)}"
                ),
            )

    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        raise NotImplementedError(
            "Reporting tasks do not support cancellation"
        )
