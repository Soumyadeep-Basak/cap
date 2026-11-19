
"""A2A client for the Invoice Translation Agent."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from a2a.helpers import get_artifact_text

from invoice_auditor.infrastructure.a2a_client import request_completed_task


def parse_translation_artifacts(task) -> dict[str, Any]:
    """Read translation results from an A2A task artifact."""

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
            "translation_status",
            "source_language",
            "translated_text",
            "translation_confidence",
            "translation_cache_hit",
            "processing_error",
        }

        missing = required_fields - result.keys()

        if missing:
            raise RuntimeError(
                "Translation A2A result missing fields: "
                + ", ".join(sorted(missing))
            )

        if result["translation_status"] != "completed":
            raise RuntimeError(
                "Translation failed: "
                + str(result.get("processing_error"))
            )

        if (
            not isinstance(result["translated_text"], str)
            or not result["translated_text"].strip()
        ):
            raise RuntimeError(
                "Translation A2A returned empty translated text"
            )

        return result

    raise RuntimeError(
        "Translation A2A returned no valid JSON artifact"
    )


async def translate_invoice_via_a2a_async(
    invoice_id: str,
    raw_extracted_text: str,
) -> dict[str, Any]:
    """Discover Translation A2A and send a translation request."""

    base_url = os.getenv(
        "TRANSLATION_A2A_URL",
        "http://translation-a2a:8012",
    ).rstrip("/")

    request_payload = {
        "action": "translate",
        "invoice_id": invoice_id,
        "raw_extracted_text": raw_extracted_text,
    }

    task = await request_completed_task(
        base_url,
        request_payload,
        agent_name="Translation",
        timeout=180.0,
    )
    return parse_translation_artifacts(task)


def translate_invoice_via_a2a(
    invoice_id: str,
    raw_extracted_text: str,
) -> dict[str, Any]:
    """Synchronous wrapper for LangGraph and scripts."""

    return asyncio.run(
        translate_invoice_via_a2a_async(
            invoice_id,
            raw_extracted_text,
        )
    )


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        raise SystemExit(
            "Usage: python -m "
            "invoice_auditor.agents.Invoice_Translation_Agent."
            "a2a_agent.translation_a2a_client "
            "<existing_invoice_uuid> <raw_text>"
        )

    result = translate_invoice_via_a2a(
        invoice_id=sys.argv[1],
        raw_extracted_text=sys.argv[2],
    )

    print(json.dumps({
        "a2a_status": "PASS",
        "invoice_id": result["invoice_id"],
        "translation_status": result["translation_status"],
        "source_language": result["source_language"],
        "translation_confidence": result[
            "translation_confidence"
        ],
        "translation_cache_hit": result[
            "translation_cache_hit"
        ],
        "processing_error": result["processing_error"],
        "translated_text_length": len(
            result["translated_text"]
        ),
    }, indent=2))
