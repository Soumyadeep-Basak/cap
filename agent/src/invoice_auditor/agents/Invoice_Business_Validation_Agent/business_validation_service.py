
"""Helpers for the Business Validation MCP integration."""

from __future__ import annotations

from typing import Any


def make_json_safe(value: Any) -> Any:
    """Convert nested results to JSON-compatible values."""

    if isinstance(value, dict):
        return {
            str(key): make_json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [make_json_safe(item) for item in value]

    if hasattr(value, "isoformat"):
        return value.isoformat()

    if hasattr(value, "as_tuple"):
        return str(value)

    return value


def prepare_business_validation_state(
    invoice: dict[str, Any],
) -> dict[str, Any]:
    """Validate the input required by the Google ADK."""

    if not isinstance(invoice, dict):
        raise TypeError("invoice must be a dictionary")

    if not invoice:
        raise ValueError("invoice must not be empty")

    line_items = invoice.get("line_items", [])

    if line_items is not None and not isinstance(line_items, list):
        raise ValueError("invoice.line_items must be a list")

    return {
        "invoice": make_json_safe(invoice),
    }


def prepare_business_validation_response(
    state: dict[str, Any],
) -> dict[str, Any]:
    """Extract the agent's business validation results."""

    if not isinstance(state, dict):
        raise TypeError("Business validation result must be a dictionary")

    required_fields = {
        "business_validation_status",
        "business_recommendation",
        "validation_errors",
        "discrepancies",
    }

    missing = required_fields - state.keys()

    if missing:
        raise ValueError(
            "Business validation agent missing fields: "
            + ", ".join(sorted(missing))
        )

    response = {
        "business_validation_status": state[
            "business_validation_status"
        ],
        "business_recommendation": state[
            "business_recommendation"
        ],
        "discrepancies": state["discrepancies"],
        "validation_errors": state["validation_errors"],
        "erp_po": state.get("erp_po"),
        "erp_vendor": state.get("erp_vendor"),
        "erp_skus": state.get("erp_skus") or {},
    }

    return make_json_safe(response)
