
"""A2A executor for invoice document extraction."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

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

from invoice_auditor.agents.Invoice_Extractor_Agent.extractor_agent_client import (
    extract_document_via_mcp,
)

from invoice_auditor.infrastructure.mcp_errors import describe_mcp_error

logger = logging.getLogger(__name__)


def parse_extraction_request(message: str) -> Path:
    """
    Accept a JSON request containing an invoice file path.

    The actual filesystem authorization is enforced by
    the Extractor MCP server.
    """
    try:
        payload = json.loads(message)
    except json.JSONDecodeError as exc:
        raise ValueError(
            'Expected JSON: {"action": "extract", '
            '"file_path": "/app/data/incoming/INV_EN_001.pdf"}'
        ) from exc

    if not isinstance(payload, dict):
        raise ValueError("A2A extraction request must be an object")

    if payload.get("action") != "extract":
        raise ValueError("Only the extract action is supported")

    if set(payload) != {"action", "file_path"}:
        raise ValueError(
            "Request must contain only action and file_path"
        )

    file_path = payload.get("file_path")

    if not isinstance(file_path, str) or not file_path.strip():
        raise ValueError("file_path must be a nonempty string")

    path = Path(file_path)

    if not path.is_absolute():
        raise ValueError("file_path must be an absolute path")

    if path.suffix.lower() not in {".pdf", ".docx", ".png"}:
        raise ValueError("Only PDF, DOCX and PNG files are supported")

    return path


class ExtractorAgentExecutor(AgentExecutor):
    """Execute invoice extraction requests received through A2A."""

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
                "Extracting invoice document through MCP."
            ),
        )

        try:
            request_text = get_message_text(context.message)
            file_path = parse_extraction_request(request_text)

            # Existing MCP client uses asyncio.run().
            # Run it in a separate thread to avoid a nested event loop.
            raw_text, extraction_method = await asyncio.to_thread(
                extract_document_via_mcp,
                file_path,
            )

            response = {
                "agent": "invoice-extractor-agent",
                "action": "extract",
                "status": "completed",
                "file_path": str(file_path),
                "raw_extracted_text": raw_text,
                "extraction_method": extraction_method,
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

            await updater.update_status(
                state=TaskState.TASK_STATE_COMPLETED,
                message=new_text_message(
                    "Invoice extraction completed successfully."
                ),
            )

            logger.info(
                "Extractor A2A completed: file=%s method=%s",
                file_path.name,
                extraction_method,
            )

        except Exception as exc:
            logger.exception("Extractor A2A task failed")

            await updater.update_status(
                state=TaskState.TASK_STATE_FAILED,
                message=new_text_message(
                    f"Invoice extraction failed: {describe_mcp_error(exc)}"
                ),
            )

    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        raise NotImplementedError(
            "Invoice extraction tasks do not support cancellation"
        )
