
"""A2A client for the Invoice Reporting Agent."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from a2a.helpers import get_artifact_text

from invoice_auditor.infrastructure.a2a_client import request_completed_task

from invoice_auditor.agents.Invoice_Reporting_Agent.reporting_agent_client import (
    make_json_safe,
)


def parse_reporting_artifacts(
    task,
) -> dict[str, Any]:
    """Parse the generated report from a completed A2A task."""

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

        required_fields = {
            "invoice_id",
            "report_status",
            "json_report_path",
            "html_report_path",
            "report",
        }

        missing = required_fields - result.keys()

        if missing:
            raise RuntimeError(
                "Reporting A2A result missing fields: "
                + ", ".join(sorted(missing))
            )

        if result["report_status"] != "completed":
            raise RuntimeError(
                "Reporting A2A did not complete successfully"
            )

        if not isinstance(result["report"], dict):
            raise RuntimeError(
                "Reporting A2A report must be an object"
            )

        for field in (
            "json_report_path",
            "html_report_path",
        ):
            if (
                not isinstance(result[field], str)
                or not result[field].strip()
            ):
                raise RuntimeError(
                    f"Reporting A2A returned invalid {field}"
                )

        return result

    raise RuntimeError(
        "Reporting A2A returned no valid JSON artifact"
    )


async def generate_invoice_report_via_a2a_async(
    state: dict[str, Any],
) -> dict[str, Any]:
    """Discover Reporting A2A and request report generation."""

    if not isinstance(state, dict):
        raise TypeError("Reporting state must be a dictionary")

    if not state.get("invoice_id"):
        raise ValueError("invoice_id is required")

    base_url = os.getenv(
        "REPORTING_A2A_URL",
        "http://reporting-a2a:8015",
    ).rstrip("/")

    request_payload = make_json_safe({
        "action": "generate_report",
        "invoice_id": state["invoice_id"],
        "file_path": state.get("file_path", ""),
        "invoice": state.get("invoice") or {},
        "validation_result": (
            state.get("validation_result") or {}
        ),
        "translation_confidence": state.get(
            "translation_confidence"
        ),
        "source_language": state.get("source_language"),
        "translated_text": state.get("translated_text"),
        "erp_data": state.get("erp_data") or {},
    })

    task = await request_completed_task(
        base_url,
        request_payload,
        agent_name="Reporting",
        timeout=180.0,
    )
    return parse_reporting_artifacts(task)


def generate_invoice_report_via_a2a(
    state: dict[str, Any],
) -> dict[str, Any]:
    """Synchronous entry point for scripts and LangGraph."""

    return asyncio.run(
        generate_invoice_report_via_a2a_async(state)
    )
