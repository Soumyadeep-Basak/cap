
"""A2A client for requesting an invoice monitoring scan."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from a2a.helpers import get_artifact_text

from invoice_auditor.infrastructure.a2a_client import request_completed_task


def parse_monitoring_artifacts(task) -> dict[str, Any]:
    """Read the JSON result from a completed A2A task."""

    for artifact in task.artifacts:
        artifact_text = get_artifact_text(artifact)

        if not artifact_text:
            continue

        try:
            result = json.loads(artifact_text)
        except json.JSONDecodeError:
            continue

        if not isinstance(result, dict):
            continue

        if result.get("status") != "completed":
            raise RuntimeError(
                "Monitoring scan did not complete: "
                + str(result.get("status"))
            )

        return result

    raise RuntimeError(
        "Monitoring A2A returned no valid JSON result artifact"
    )


async def scan_invoices_via_a2a_async(
    incoming_dir: str | None = None,
) -> dict[str, Any]:
    """Discover the Monitoring A2A Agent and request one scan."""

    base_url = os.getenv(
        "MONITORING_A2A_URL",
        "http://monitoring-a2a:8010",
    ).rstrip("/")

    request_payload = {"action": "scan"}
    if incoming_dir is not None:
        request_payload["incoming_dir"] = incoming_dir

    task = await request_completed_task(
        base_url,
        request_payload,
        agent_name="Monitoring",
        timeout=120.0,
    )
    return parse_monitoring_artifacts(task)


def scan_invoices_via_a2a(
    incoming_dir: str | None = None,
) -> dict[str, Any]:
    """Synchronous wrapper for scripts and LangGraph callers."""

    return asyncio.run(
        scan_invoices_via_a2a_async(incoming_dir)
    )


if __name__ == "__main__":
    result = scan_invoices_via_a2a()

    print(json.dumps({
        "a2a_status": "PASS",
        "monitor_status": result["status"],
        "discovered": result["discovered_count"],
        "pending": result["pending_count"],
        "routed": result["routed_count"],
        "duplicates": result["duplicate_count"],
        "errors": result["error_count"],
    }, indent=2))
