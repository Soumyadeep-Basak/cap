"""Transport shared by the invoice agents' non-streaming A2A clients."""

import json
from typing import Any

import httpx
from a2a.client import ClientConfig, create_client
from a2a.helpers import get_message_text, new_text_message
from a2a.types import Role, SendMessageRequest, Task, TaskState


async def request_completed_task(
    base_url: str,
    payload: dict[str, Any],
    *,
    agent_name: str,
    timeout: float,
) -> Task:
    """Discover an agent, send a JSON request, and return its completed task."""
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout, connect=10.0)
    ) as http_client:
        client = await create_client(
            agent=base_url,
            client_config=ClientConfig(
                streaming=False,
                httpx_client=http_client,
            ),
        )
        try:
            request = SendMessageRequest(
                message=new_text_message(
                    json.dumps(payload, default=str, ensure_ascii=False),
                    role=Role.ROLE_USER,
                )
            )
            async for response in client.send_message(request):
                if response.HasField("task"):
                    task = response.task
                    if task.status.state == TaskState.TASK_STATE_COMPLETED:
                        return task
                    if task.status.state == TaskState.TASK_STATE_FAILED:
                        detail = get_message_text(task.status.message)
                        raise RuntimeError(
                            f"{agent_name} A2A task failed: {detail or 'Unknown error'}"
                        )
                    state = TaskState.Name(task.status.state)
                    raise RuntimeError(f"{agent_name} A2A task did not finish: {state}")

                if response.HasField("message"):
                    raise RuntimeError(
                        f"{agent_name} A2A returned a message instead of a task"
                    )

            raise RuntimeError(f"{agent_name} A2A returned no completed task")
        finally:
            await client.close()
