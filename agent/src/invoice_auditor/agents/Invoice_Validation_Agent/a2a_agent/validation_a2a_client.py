
"""A2A client for the Invoice Data Validation Agent."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from a2a.helpers import get_artifact_text

from invoice_auditor.infrastructure.a2a_client import request_completed_task


def parse_validation_artifacts(task) -> dict[str, Any]:
    """Parse and validate the completed A2A task artifact."""

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
            "validation_status",
            "recommendation",
            "severity_level",
            "missing_fields",
            "validation_errors",
            "discrepancies",
            "observations",
            "arithmetic_passed",
            "tax_verified",
        }

        missing = required_fields - result.keys()

        if missing:
            raise RuntimeError(
                "Validation A2A result missing fields: "
                + ", ".join(sorted(missing))
            )

        if result["validation_status"] not in {
            "passed",
            "failed",
            "partial",
        }:
            raise RuntimeError(
                "Unexpected validation status: "
                + str(result["validation_status"])
            )

        if result["recommendation"] not in {
            "approve",
            "review",
            "reject",
        }:
            raise RuntimeError(
                "Unexpected validation recommendation"
            )

        for field in (
            "missing_fields",
            "validation_errors",
            "discrepancies",
            "observations",
        ):
            if not isinstance(result[field], list):
                raise RuntimeError(
                    f"Validation A2A field {field} must be a list"
                )

        return result

    raise RuntimeError(
        "Validation A2A returned no valid JSON artifact"
    )


async def validate_invoice_via_a2a_async(
    invoice: dict[str, Any],
    translation_confidence: float | None = None,
) -> dict[str, Any]:
    """Discover and invoke the Invoice Data Validation A2A agent."""

    if not isinstance(invoice, dict) or not invoice:
        raise ValueError(
            "invoice must be a nonempty dictionary"
        )

    if translation_confidence is not None:
        if (
            isinstance(translation_confidence, bool)
            or not isinstance(translation_confidence, (int, float))
            or not 0 <= translation_confidence <= 1
        ):
            raise ValueError(
                "translation_confidence must be between 0 and 1"
            )

    base_url = os.getenv(
        "VALIDATION_A2A_URL",
        "http://validation-a2a:8013",
    ).rstrip("/")

    request_payload = {
        "action": "validate",
        "invoice": invoice,
        "translation_confidence": translation_confidence,
    }

    task = await request_completed_task(
        base_url,
        request_payload,
        agent_name="Validation",
        timeout=120.0,
    )
    return parse_validation_artifacts(task)


def validate_invoice_via_a2a(
    invoice: dict[str, Any],
    translation_confidence: float | None = None,
) -> dict[str, Any]:
    """Synchronous entry point for LangGraph and scripts."""

    return asyncio.run(
        validate_invoice_via_a2a_async(
            invoice=invoice,
            translation_confidence=translation_confidence,
        )
    )
