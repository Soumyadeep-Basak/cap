
"""A2A client for the Invoice Business Validation Agent."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from a2a.helpers import get_artifact_text

from invoice_auditor.infrastructure.a2a_client import request_completed_task

from invoice_auditor.agents.Invoice_Business_Validation_Agent.business_validation_service import (
    make_json_safe,
)


def parse_business_validation_artifacts(
    task,
) -> dict[str, Any]:
    """Parse a completed business validation A2A task."""

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
                "Business Validation A2A result missing fields: "
                + ", ".join(sorted(missing))
            )

        if result["business_validation_status"] not in {
            "passed",
            "failed",
        }:
            raise RuntimeError(
                "Unexpected business validation status: "
                + str(result["business_validation_status"])
            )

        if result["business_recommendation"] not in {
            "approve",
            "review",
        }:
            raise RuntimeError(
                "Unexpected business recommendation: "
                + str(result["business_recommendation"])
            )

        if not isinstance(result["discrepancies"], list):
            raise RuntimeError(
                "Business Validation discrepancies must be a list"
            )

        if not isinstance(result["validation_errors"], list):
            raise RuntimeError(
                "Business Validation errors must be a list"
            )

        if result["erp_po"] is not None and not isinstance(
            result["erp_po"], dict
        ):
            raise RuntimeError(
                "Business Validation erp_po must be an object or null"
            )

        if result["erp_vendor"] is not None and not isinstance(
            result["erp_vendor"], dict
        ):
            raise RuntimeError(
                "Business Validation erp_vendor must be an object or null"
            )

        if not isinstance(result["erp_skus"], dict):
            raise RuntimeError(
                "Business Validation erp_skus must be an object"
            )

        return result

    raise RuntimeError(
        "Business Validation A2A returned no valid JSON artifact"
    )


async def validate_business_invoice_via_a2a_async(
    invoice: dict[str, Any],
) -> dict[str, Any]:
    """Discover the Business Validation Agent and invoke its skill."""

    if not isinstance(invoice, dict) or not invoice:
        raise ValueError(
            "invoice must be a nonempty dictionary"
        )

    base_url = os.getenv(
        "BUSINESS_VALIDATION_A2A_URL",
        "http://business-validation-a2a:8014",
    ).rstrip("/")

    request_payload = {
        "action": "validate_business",
        "invoice": make_json_safe(invoice),
    }

    task = await request_completed_task(
        base_url,
        request_payload,
        agent_name="Business validation",
        timeout=120.0,
    )
    return parse_business_validation_artifacts(task)


def validate_business_invoice_via_a2a(
    invoice: dict[str, Any],
) -> dict[str, Any]:
    """Synchronous entry point for scripts and LangGraph."""

    return asyncio.run(
        validate_business_invoice_via_a2a_async(invoice)
    )
