"""Thin HTTP client for calling the Agent API from the dashboard.

Per the architecture, the Streamlit UI must never write audit data or
mutate invoices directly -- it always goes through the Agent service
(reached via its Docker Compose service name, e.g. http://agent:8000).
"""

from __future__ import annotations

from typing import Any

import httpx

from invoice_auditor_ui.config import AGENT_API_URL

_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


class AgentApiError(RuntimeError):
    """Raised when the Agent API returns an error response."""


def _request(method: str, path: str, **kwargs: Any) -> Any:
    url = f"{AGENT_API_URL.rstrip('/')}{path}"
    try:
        response = httpx.request(method, url, timeout=_TIMEOUT, **kwargs)
    except httpx.RequestError as exc:
        raise AgentApiError(
            f"Could not reach the Agent service at {url}: {exc}"
        ) from exc

    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise AgentApiError(f"Agent API error ({response.status_code}): {detail}")

    return response.json()


def health_check() -> bool:
    """Return True if the Agent API is reachable and healthy."""
    try:
        result = _request("GET", "/health")
        return result.get("status") == "ok"
    except AgentApiError:
        return False


def submit_feedback(
    invoice_id: str,
    field_name: str,
    corrected_value: str,
    corrected_by: str,
    original_value: str | None = None,
) -> dict[str, Any]:
    """Record a human correction for an invoice field."""
    return _request(
        "POST",
        f"/api/v1/invoices/{invoice_id}/feedback",
        json={
            "field_name": field_name,
            "corrected_value": corrected_value,
            "original_value": original_value,
            "corrected_by": corrected_by,
        },
    )


def revalidate_invoice(invoice_id: str) -> dict[str, Any]:
    """Apply pending corrections and re-run validation/reporting."""
    return _request(
        "POST", f"/api/v1/invoices/{invoice_id}/revalidate"
    )


def process_incoming() -> dict[str, Any]:
    """Trigger an immediate on-demand processing run (in addition to the
    Agent's own background polling)."""
    return _request("POST", "/api/v1/invoices/process", json={})


def ask_question(
    question: str, invoice_id: str | None = None
) -> dict[str, Any]:
    """Ask a natural-language question through the RAG/SQL query pipeline."""
    return _request(
        "POST",
        "/api/v1/query",
        json={"question": question, "invoice_id": invoice_id},
    )
