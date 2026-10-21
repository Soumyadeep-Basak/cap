
"""Rule-driven invoice data validation graph."""

import logging
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Literal, TypedDict

import yaml
from langgraph.graph import END, START, StateGraph

logger = logging.getLogger(__name__)

# services/ -> invoice_auditor/ -> src/ -> agent/ -> repository root
PROJECT_ROOT = Path(__file__).resolve().parents[4]
RULES_PATH = PROJECT_ROOT / "config" / "rules.yaml"
CENT = Decimal("0.01")


class ValidationState(TypedDict, total=False):
    invoice: dict[str, Any]
    translation_confidence: float | None
    rules: dict[str, Any]
    missing_fields: list[str]
    validation_errors: list[str]
    discrepancies: list[dict[str, Any]]
    observations: list[str]
    arithmetic_passed: bool
    tax_verified: bool
    severity_level: Literal["high", "medium", "low"]
    validation_status: Literal["pending", "passed", "failed", "partial"]
    recommendation: Literal["approve", "review", "reject"]


# The Invoice Data Validation Agent only sees text extracted directly
# from the invoice document. Invoices carry a vendor *name*, never an
# internal ERP vendor_id -- that identifier is only resolved later, by
# the Business Validation Agent, through the PO/vendor master lookup.
# Mapping "vendor_id" to "vendor_id" here would mean every invoice is
# missing that field forever, since extraction never populates it.
HEADER_MAPPING = {
    "invoice_no": "invoice_number",
    "invoice_date": "invoice_date",
    "vendor_id": "vendor_name",
    "currency": "currency",
    "total_amount": "total_amount",
}

LINE_MAPPING = {
    "item_code": "item_code",
    "description": "description",
    "qty": "quantity",
    "unit_price": "unit_price",
    "total": "line_total",
}


def is_missing(value: Any) -> bool:
    return value is None or (
        isinstance(value, str) and not value.strip()
    )


def as_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def load_rules_node(state: ValidationState) -> dict[str, Any]:
    """Load validation rules from the project configuration."""
    with RULES_PATH.open("r", encoding="utf-8") as file:
        rules = yaml.safe_load(file) or {}

    if "required_fields" not in rules:
        raise ValueError("rules.yaml is missing required_fields")

    return {"rules": rules}


def completeness_node(state: ValidationState) -> dict[str, Any]:
    """Check required header and line-item fields deterministically."""
    invoice = state["invoice"]
    rules = state["rules"]
    missing: list[str] = []

    for rule_name in rules["required_fields"].get("header", []):
        field = HEADER_MAPPING.get(rule_name, rule_name)
        if is_missing(invoice.get(field)):
            missing.append(field)

    line_items = invoice.get("line_items") or []

    if not line_items:
        missing.append("line_items")

    for index, item in enumerate(line_items):
        for rule_name in rules["required_fields"].get(
            "line_item", []
        ):
            field = LINE_MAPPING.get(rule_name, rule_name)
            if is_missing(item.get(field)):
                missing.append(f"line_items[{index}].{field}")

    return {"missing_fields": sorted(set(missing))}


def arithmetic_node(state: ValidationState) -> dict[str, Any]:
    """Verify line calculations and invoice-level totals."""
    invoice = state["invoice"]
    line_items = invoice.get("line_items") or []
    errors: list[str] = []
    discrepancies: list[dict[str, Any]] = []
    observations: list[str] = []

    line_sum = Decimal("0")
    all_line_values_valid = bool(line_items)

    for index, item in enumerate(line_items):
        quantity = as_decimal(item.get("quantity"))
        unit_price = as_decimal(item.get("unit_price"))
        recorded_total = as_decimal(item.get("line_total"))

        if (
            quantity is None
            or unit_price is None
            or recorded_total is None
        ):
            all_line_values_valid = False
            errors.append(
                f"Line item {index + 1} has missing or invalid "
                "numeric values."
            )
            continue

        calculated = money(quantity * unit_price)
        recorded = money(recorded_total)
        line_sum += recorded

        if calculated != recorded:
            errors.append(
                f"Line item {index + 1}: calculated total "
                f"{calculated} differs from recorded total {recorded}."
            )
            discrepancies.append({
                "type": "line_total_mismatch",
                "line_number": index + 1,
                "calculated": str(calculated),
                "recorded": str(recorded),
            })

    subtotal = as_decimal(invoice.get("subtotal_amount"))
    tax_amount = as_decimal(invoice.get("tax_amount"))
    tax_rate = as_decimal(invoice.get("tax_rate"))
    invoice_total = as_decimal(invoice.get("total_amount"))

    if subtotal is not None and all_line_values_valid:
        if money(line_sum) != money(subtotal):
            errors.append(
                f"Line-item sum {money(line_sum)} differs from "
                f"subtotal {money(subtotal)}."
            )
            discrepancies.append({
                "type": "subtotal_mismatch",
                "line_item_sum": str(money(line_sum)),
                "subtotal": str(money(subtotal)),
            })

    elif subtotal is None:
        observations.append(
            "Subtotal was not extracted; subtotal reconciliation "
            "could not be performed."
        )

    if invoice_total is not None and subtotal is not None:
        if tax_amount is not None:
            expected_total = money(subtotal + tax_amount)
            if money(invoice_total) != expected_total:
                errors.append(
                    f"Subtotal plus tax {expected_total} differs "
                    f"from invoice total {money(invoice_total)}."
                )
                discrepancies.append({
                    "type": "invoice_total_mismatch",
                    "calculated": str(expected_total),
                    "recorded": str(money(invoice_total)),
                })
        elif tax_rate is None and money(subtotal) != money(invoice_total):
            observations.append(
                "Invoice total differs from subtotal, but no tax "
                "amount or rate was extracted to explain the difference."
            )

    tax_verified = False

    if subtotal is not None and tax_amount is not None and tax_rate is not None:
        expected_tax = money(subtotal * tax_rate / Decimal("100"))
        tolerance_percent = Decimal(str(
            state["rules"].get("tolerances", {}).get(
                "tax_difference_percent", 2
            )
        ))
        allowed_difference = (
            abs(expected_tax) * tolerance_percent / Decimal("100")
        )

        tax_verified = (
            abs(tax_amount - expected_tax) <= allowed_difference
        )

        if not tax_verified:
            errors.append(
                f"Tax amount {money(tax_amount)} differs from "
                f"calculated tax {expected_tax} beyond the configured "
                f"{tolerance_percent}% tolerance."
            )
            discrepancies.append({
                "type": "tax_mismatch",
                "calculated": str(expected_tax),
                "recorded": str(money(tax_amount)),
                "tolerance_percent": str(tolerance_percent),
            })

    elif tax_amount is not None and subtotal is not None:
        # The arithmetic relationship can still be checked, but a
        # rate-based tax check is impossible without the rate.
        observations.append(
            "Tax amount was extracted, but a tax rate was not found; "
            "rate-based tax verification is incomplete."
        )

    else:
        observations.append(
            "Tax verification could not be completed from the "
            "available extracted fields."
        )

    arithmetic_passed = not errors and all_line_values_valid

    return {
        "arithmetic_passed": arithmetic_passed,
        "tax_verified": tax_verified,
        "validation_errors": errors,
        "discrepancies": discrepancies,
        "observations": observations,
    }


def decision_node(state: ValidationState) -> dict[str, Any]:
    """Apply currency, completeness, confidence, and arithmetic rules."""
    rules = state["rules"]
    invoice = state["invoice"]
    errors = list(state.get("validation_errors", []))
    observations = list(state.get("observations", []))
    missing = state.get("missing_fields", [])

    policies = rules.get("validation_policies", {})
    accepted = set(rules.get("accepted_currencies", []))
    currency = invoice.get("currency")

    recommendation: Literal["approve", "review", "reject"] = "review"
    status: Literal["pending", "passed", "failed", "partial"] = "partial"
    severity: Literal["high", "medium", "low"] = "low"

    if currency and currency not in accepted:
        errors.append(f"Unsupported currency: {currency}")
        recommendation = (
            "reject"
            if policies.get("invalid_currency_action") == "reject"
            else "review"
        )
        status = "failed"
        severity = "high"

    elif errors:
        # Total/tax mismatches are configured for manual review,
        # not automatic rejection.
        status = "failed"
        recommendation = "review"
        severity = "high"

    elif missing or not state.get("arithmetic_passed", False):
        status = "partial"
        recommendation = "review"
        severity = "medium"

    else:
        confidence = state.get("translation_confidence")
        threshold = float(
            policies.get("auto_approve_confidence_threshold", 0.95)
        )

        if confidence is None or confidence < threshold:
            observations.append(
                "Translation confidence is missing or below the "
                "auto-approval threshold."
            )
            status = "partial"
            recommendation = "review"
            severity = "medium"
        elif not state.get("tax_verified", False):
            status = "partial"
            recommendation = "review"
            severity = "medium"
        else:
            status = "passed"
            recommendation = "approve"
            severity = "low"

    return {
        "validation_status": status,
        "recommendation": recommendation,
        "severity_level": severity,
        "validation_errors": errors,
        "observations": observations,
    }


def build_invoice_validation_graph():
    graph = StateGraph(ValidationState)

    graph.add_node("load_rules", load_rules_node)
    graph.add_node("completeness", completeness_node)
    graph.add_node("arithmetic", arithmetic_node)
    graph.add_node("decision", decision_node)

    graph.add_edge(START, "load_rules")
    graph.add_edge("load_rules", "completeness")
    graph.add_edge("completeness", "arithmetic")
    graph.add_edge("arithmetic", "decision")
    graph.add_edge("decision", END)

    return graph.compile()


invoice_validation_graph = build_invoice_validation_graph()
