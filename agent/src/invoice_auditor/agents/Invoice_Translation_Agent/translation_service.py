
"""Input and output helpers for Translation MCP."""

from __future__ import annotations

from invoice_auditor.security.content import validate_document

from typing import Any
from uuid import UUID


def prepare_translation_state(
    invoice_id: str,
    raw_extracted_text: str,
) -> dict[str, Any]:
    """Validate and prepare the Google ADK input state."""

    if not isinstance(invoice_id, str) or not invoice_id.strip():
        raise ValueError("invoice_id is required")

    try:
        normalized_invoice_id = str(UUID(invoice_id))
    except (ValueError, AttributeError) as exc:
        raise ValueError("invoice_id must be a valid UUID") from exc

    if (
        not isinstance(raw_extracted_text, str)
        or not raw_extracted_text.strip()
    ):
        raise ValueError("raw_extracted_text must not be empty")

    validate_document(raw_extracted_text)
    return {
        "invoice_id": normalized_invoice_id,
        "raw_extracted_text": raw_extracted_text,
    }


def prepare_translation_response(
    state: dict[str, Any],
) -> dict[str, Any]:
    """Return the translation fields required by the parent workflow."""

    if state.get("translated_text"):
        validate_document(state["translated_text"])
    status = state.get("translation_status", "failed")

    if status not in {"completed", "failed"}:
        status = "failed"

    return {
        "invoice_id": state.get("invoice_id"),
        "translation_status": status,
        "source_language": state.get("source_language"),
        "translated_text": state.get("translated_text"),
        "translation_confidence": state.get(
            "translation_confidence"
        ),
        "translation_cache_hit": bool(
            state.get("translation_cache_hit", False)
        ),
        "processing_error": state.get("processing_error"),
    }
