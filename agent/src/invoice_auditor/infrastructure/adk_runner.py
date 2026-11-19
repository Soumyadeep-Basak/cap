"""Run an ADK invoice agent in an isolated, in-memory session."""

from contextlib import aclosing
from typing import Any

from google.adk.agents import BaseAgent
from google.adk.runners import InMemoryRunner
from google.genai import types


async def run_agent(agent: BaseAgent, state: dict[str, Any]) -> dict[str, Any]:
    # ADK derives the application name from the root agent package.
    runner = InMemoryRunner(agent=agent, app_name="agents")
    try:
        service = runner.session_service
        session = await service.create_session(
            app_name=runner.app_name, user_id="invoice_auditor", state=state
        )
        events = runner.run_async(
            user_id=session.user_id,
            session_id=session.id,
            new_message=types.Content(
                role="user", parts=[types.Part(text="Process invoice")]
            ),
        )
        async with aclosing(events) as stream:
            async for event in stream:
                if event.error_code:
                    raise RuntimeError(event.error_message or event.error_code)

        result = await service.get_session(
            app_name=session.app_name, user_id=session.user_id, session_id=session.id
        )
        if result is None:
            raise RuntimeError(f"ADK session disappeared for {agent.name}")
        return result.state
    finally:
        await runner.close()
