
"""A2A client for Invoice Extractor Agent."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from a2a.helpers import get_artifact_text

from invoice_auditor.infrastructure.a2a_client import request_completed_task


def parse_extraction_artifacts(task) -> dict[str, Any]:
    """Read the extraction JSON from a completed A2A task."""

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
                "Extraction did not complete: "
                + str(result.get("status"))
            )

        raw_text = result.get("raw_extracted_text")
        method = result.get("extraction_method")

        if not isinstance(raw_text, str) or not raw_text.strip():
            raise RuntimeError(
                "Extractor A2A returned empty extracted text"
            )

        if not isinstance(method, str) or not method:
            raise RuntimeError(
                "Extractor A2A returned no extraction method"
            )

        return result

    raise RuntimeError(
        "Extractor A2A returned no valid JSON result artifact"
    )


async def extract_invoice_via_a2a_async(
    file_path: str | Path,
) -> dict[str, Any]:
    """Discover the Extractor Agent and request extraction."""

    base_url = os.getenv(
        "EXTRACTOR_A2A_URL",
        "http://extractor-a2a:8011",
    ).rstrip("/")

    request_payload = {
        "action": "extract",
        "file_path": str(file_path),
    }
    task = await request_completed_task(
        base_url,
        request_payload,
        agent_name="Extractor",
        timeout=300.0,
    )
    return parse_extraction_artifacts(task)


def extract_invoice_via_a2a(
    file_path: str | Path,
) -> dict[str, Any]:
    """Synchronous wrapper for scripts and LangGraph callers."""
    return asyncio.run(
        extract_invoice_via_a2a_async(file_path)
    )


if __name__ == "__main__":
    path = Path(
        os.getenv(
            "EXTRACTOR_A2A_TEST_FILE",
            "/app/data/incoming/INV_EN_001.pdf",
        )
    )

    result = extract_invoice_via_a2a(path)

    print(json.dumps({
        "a2a_status": "PASS",
        "file_path": result["file_path"],
        "extraction_method": result["extraction_method"],
        "text_length": len(result["raw_extracted_text"]),
        "text_preview": result["raw_extracted_text"][:150],
    }, indent=2))
