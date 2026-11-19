
"""A2A executor for invoice translation."""

from __future__ import annotations

import asyncio
import json
import logging
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

from invoice_auditor.agents.Invoice_Translation_Agent.translation_agent_client import (
    translate_invoice_via_mcp,
)

from invoice_auditor.infrastructure.mcp_errors import describe_mcp_error

logger = logging.getLogger(__name__)


def parse_translation_request(
    message: str,
) -> dict[str, Any]:
    """Validate an A2A translation request."""

    try:
        payload = json.loads(message)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Translation request must be valid JSON"
        ) from exc

    if not isinstance(payload, dict):
        raise ValueError(
            "Translation request must be a JSON object"
        )

    if payload.get("action") != "translate":
        raise ValueError(
            "Only the translate action is supported"
        )

    required_fields = {
        "action",
        "invoice_id",
        "raw_extracted_text",
    }

    if set(payload) != required_fields:
        raise ValueError(
            "Request must contain exactly action, "
            "invoice_id and raw_extracted_text"
        )

    invoice_id = payload["invoice_id"]
    raw_text = payload["raw_extracted_text"]

    if not isinstance(invoice_id, str):
        raise ValueError("invoice_id must be a string")

    try:
        normalized_invoice_id = str(UUID(invoice_id))
    except (ValueError, AttributeError) as exc:
        raise ValueError(
            "invoice_id must be a valid UUID"
        ) from exc

    if not isinstance(raw_text, str) or not raw_text.strip():
        raise ValueError(
            "raw_extracted_text must be a nonempty string"
        )

    return {
        "invoice_id": normalized_invoice_id,
        "raw_extracted_text": raw_text,
    }


class TranslationAgentExecutor(AgentExecutor):
    """Execute translation requests through Translation MCP."""

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
                "Translating invoice through Translation MCP."
            ),
        )

        try:
            request_text = get_message_text(
                context.message
            )

            translation_state = parse_translation_request(
                request_text
            )

            # The existing MCP client calls asyncio.run().
            # Execute it in a worker thread to avoid nesting
            # event loops in the A2A server.
            result = await asyncio.to_thread(
                translate_invoice_via_mcp,
                translation_state,
            )

            response = {
                "agent": "invoice-translation-agent",
                "action": "translate",
                **result,
            }

            await updater.add_artifact(
                parts=[
                    new_text_part(
                        text=json.dumps(
                            response,
                            ensure_ascii=False,
                        ),
                        media_type="application/json",
                    )
                ],
            )

            if result["translation_status"] == "completed":
                await updater.update_status(
                    state=TaskState.TASK_STATE_COMPLETED,
                    message=new_text_message(
                        "Invoice translation completed successfully."
                    ),
                )
            else:
                await updater.update_status(
                    state=TaskState.TASK_STATE_FAILED,
                    message=new_text_message(
                        "Invoice translation failed: "
                        + str(
                            result.get("processing_error")
                            or "Unknown translation error"
                        )
                    ),
                )

            logger.info(
                "Translation A2A result: invoice_id=%s, status=%s",
                translation_state["invoice_id"],
                result["translation_status"],
            )

        except Exception as exc:
            logger.exception(
                "Translation A2A execution failed"
            )

            await updater.update_status(
                state=TaskState.TASK_STATE_FAILED,
                message=new_text_message(
                    f"Translation request failed: {describe_mcp_error(exc)}"
                ),
            )

    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        raise NotImplementedError(
            "Translation tasks do not support cancellation"
        )
