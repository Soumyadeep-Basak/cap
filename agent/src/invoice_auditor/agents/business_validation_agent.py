"""Business validation agent for comparing invoices against Mock ERP."""

from __future__ import annotations

import re
import os
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, TypedDict

import requests
import yaml
from dotenv import load_dotenv
from langgraph.graph import END, START, StateGraph

PROJECT_ROOT = Path(__file__).resolve().parents[4]
load_dotenv(PROJECT_ROOT / ".env")

RULES_PATH = PROJECT_ROOT / "config" / "rules.yaml"

ERP_BASE_URL = os.getenv(
    "MOCK_ERP_BASE_URL",
    os.getenv("ERP_API_URL", "http://localhost:8001/api/v1/erp"),
).rstrip("/")

class BusinessValidationState(TypedDict, total=False):
    invoice: dict[str, Any]
    rules: dict[str, Any]

    erp_po: dict[str, Any] | None
    erp_vendor: dict[str, Any] | None
    erp_skus: dict[str, dict[str, Any]]

    discrepancies: list[dict[str, Any]]
    validation_errors: list[str]

    business_validation_status: str
    business_recommendation: str


def load_rules_node(
    state: BusinessValidationState,
) -> dict[str, Any]:
    """Load business validation rules."""

    with RULES_PATH.open("r", encoding="utf-8") as file:
        rules = yaml.safe_load(file)

    return {"rules": rules}


def get_json(
    url: str,
) -> dict[str, Any]:
    """Call the Mock ERP API and return JSON."""

    response = requests.get(url, timeout=10)

    if response.status_code == 404:
        return {}

    response.raise_for_status()
    return response.json()



def fetch_erp_data_node(
    state: BusinessValidationState,
) -> dict[str, Any]:
    """Fetch ERP data through the Mock ERP HTTP API."""

    invoice = state["invoice"]
    po_number = invoice.get("po_number")
    invoice_vendor_id = invoice.get("vendor_id")

    erp_po = None
    erp_vendor = None
    erp_skus: dict[str, dict[str, Any]] = {}

    if po_number:
        erp_po = get_json(f"{ERP_BASE_URL}/po/{po_number}")

    # Prefer the invoice vendor ID; fall back to the PO's vendor ID.
    resolved_vendor_id = invoice_vendor_id or (
        erp_po.get("vendor_id") if erp_po else None
    )

    if resolved_vendor_id:
        erp_vendor = get_json(
            f"{ERP_BASE_URL}/vendor/{resolved_vendor_id}"
        )

    # Fetch SKU records for both extracted item codes and PO item codes.
    # This supports OCR invoices whose line items have no SKU code.
    item_codes = {
        item.get("item_code")
        for item in invoice.get("line_items", [])
        if item.get("item_code")
    }

    if erp_po:
        item_codes.update(
            item.get("item_code")
            for item in erp_po.get("line_items", [])
            if item.get("item_code")
        )

    for item_code in item_codes:
        sku = get_json(f"{ERP_BASE_URL}/sku/{item_code}")

        if sku:
            erp_skus[item_code] = sku

    return {
        "erp_po": erp_po,
        "erp_vendor": erp_vendor,
        "erp_skus": erp_skus,
    }



def to_decimal(value: Any) -> Decimal:
    """Convert numeric values safely to Decimal."""

    return Decimal(str(value))


def percentage_deviation(
    invoice_value: Decimal,
    erp_value: Decimal,
) -> Decimal:
    """Calculate percentage deviation relative to ERP value."""

    if erp_value == 0:
        if invoice_value == 0:
            return Decimal("0")

        return Decimal("100")

    return (
        abs(invoice_value - erp_value)
        / abs(erp_value)
        * Decimal("100")
    )

def normalize_description(value: Any) -> set[str]:
    """Normalize a description into comparable word tokens."""
    if not value:
        return set()

    return set(re.findall(r"[a-z0-9]+", str(value).lower()))


def match_invoice_item_to_po(
    invoice_item: dict[str, Any],
    po_items: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Return a unique PO line supported by description, quantity and price."""

    description_tokens = normalize_description(
        invoice_item.get("description")
    )

    if not description_tokens:
        return None

    try:
        invoice_qty = to_decimal(invoice_item.get("quantity"))
        invoice_price = to_decimal(invoice_item.get("unit_price"))
    except (InvalidOperation, TypeError, ValueError):
        return None

    candidates = []

    for po_item in po_items:
        po_tokens = normalize_description(po_item.get("description"))

        if not po_tokens:
            continue

        try:
            po_qty = to_decimal(po_item.get("quantity"))
            po_price = to_decimal(po_item.get("unit_price"))
        except (InvalidOperation, TypeError, ValueError):
            continue

        # Quantity and unit price must corroborate the description.
        if invoice_qty != po_qty or invoice_price != po_price:
            continue

        overlap = len(description_tokens & po_tokens) / len(
            description_tokens | po_tokens
        )

        if overlap >= 0.5:
            candidates.append((overlap, po_item))

    # Never guess when multiple PO lines are plausible.
    if len(candidates) != 1:
        return None

    return candidates[0][1]

def add_discrepancy(
    discrepancies: list[dict[str, Any]],
    *,
    field_name: str,
    invoice_value: Any,
    erp_value: Any,
    deviation_pct: Decimal | None,
    severity: str,
) -> None:
    """Add one discrepancy record."""

    discrepancies.append(
        {
            "field_name": field_name,
            "invoice_value": (
                None
                if invoice_value is None
                else str(invoice_value)
            ),
            "erp_value": (
                None
                if erp_value is None
                else str(erp_value)
            ),
            "deviation_pct": (
                None
                if deviation_pct is None
                else str(deviation_pct)
            ),
            "severity": severity,
        }
    )


def compare_business_rules_node(
    state: BusinessValidationState,
) -> dict[str, Any]:
    """Compare invoice data against ERP data."""

    invoice = state["invoice"]
    rules = state["rules"]

    erp_po = state.get("erp_po") or {}
    erp_vendor = state.get("erp_vendor") or {}
    erp_skus = state.get("erp_skus") or {}

    discrepancies: list[dict[str, Any]] = []
    validation_errors: list[str] = []

    tolerances = rules.get("tolerances", {})

    price_tolerance = Decimal(
        str(tolerances.get("price_difference_percent", 5))
    )

    quantity_tolerance = Decimal(
        str(tolerances.get("quantity_difference_percent", 0))
    )

    # --------------------------------------------------
    # Vendor validation
    # --------------------------------------------------
     
    invoice_vendor_id = invoice.get("vendor_id")
    erp_vendor_id = erp_vendor.get("vendor_id")

    if not erp_vendor:
        validation_errors.append(
            f"Vendor '{invoice_vendor_id or 'unresolved'}' "
            "could not be resolved in ERP."
        )
    elif invoice_vendor_id and invoice_vendor_id != erp_vendor_id:
        add_discrepancy(
            discrepancies,
            field_name="vendor_id",
            invoice_value=invoice_vendor_id,
            erp_value=erp_vendor_id,
            deviation_pct=None,
            severity="high",
        )


    # --------------------------------------------------
    # PO validation
    # --------------------------------------------------

    if not erp_po:
        validation_errors.append(
            f"Purchase order '{invoice.get('po_number')}' "
            "not found in ERP."
        )

    else:
        if (invoice_vendor_id and invoice_vendor_id != erp_po.get("vendor_id")):
            add_discrepancy(
                discrepancies,
                field_name="po.vendor_id",
                invoice_value=invoice_vendor_id,
                erp_value=erp_po.get("vendor_id"),
                deviation_pct=None,
                severity="high",
            )

        po_items = {
            item["item_code"]: item
            for item in erp_po.get("line_items", [])
        }
        po_line_items = erp_po.get("line_items", [])

        # --------------------------------------------------
        # Line-item validation
        # --------------------------------------------------

        for index, invoice_item in enumerate(
            invoice.get("line_items", [])
        ):
            item_code = invoice_item.get("item_code")

            # OCR may extract the description, quantity and price but no SKU.
            if not item_code:
                matched_po_item = match_invoice_item_to_po(
                    invoice_item,
                    po_line_items,
                )

                if matched_po_item is None:
                    validation_errors.append(
                        "Could not uniquely match invoice line "
                        f"{index + 1} to a purchase-order line."
                    )
                    continue

                item_code = matched_po_item.get("item_code")
                erp_item = matched_po_item
            else:
                erp_item = po_items.get(item_code)

            if not erp_item:
                validation_errors.append(
                    f"SKU '{item_code}' is not present in "
                    f"PO '{invoice.get('po_number')}'."
                )
                continue

            prefix = f"line_items[{index}]"

            if not erp_item:
                validation_errors.append(
                    f"SKU '{item_code}' is not present in "
                    f"PO '{invoice.get('po_number')}'."
                )
                continue

            prefix = f"line_items[{index}]"

            # Quantity
            try:
                invoice_qty = to_decimal(
                    invoice_item.get("quantity")
                )
                erp_qty = to_decimal(
                    erp_item.get("quantity")
                )

                quantity_deviation = percentage_deviation(
                    invoice_qty,
                    erp_qty,
                )

                if quantity_deviation > quantity_tolerance:
                    add_discrepancy(
                        discrepancies,
                        field_name=f"{prefix}.quantity",
                        invoice_value=invoice_qty,
                        erp_value=erp_qty,
                        deviation_pct=quantity_deviation,
                        severity="high",
                    )

            except (InvalidOperation, TypeError, ValueError):
                validation_errors.append(
                    f"Invalid quantity for SKU '{item_code}'."
                )

            # Unit price
            try:
                invoice_price = to_decimal(
                    invoice_item.get("unit_price")
                )
                erp_price = to_decimal(
                    erp_item.get("unit_price")
                )

                price_deviation = percentage_deviation(
                    invoice_price,
                    erp_price,
                )

                if price_deviation > price_tolerance:
                    add_discrepancy(
                        discrepancies,
                        field_name=f"{prefix}.unit_price",
                        invoice_value=invoice_price,
                        erp_value=erp_price,
                        deviation_pct=price_deviation,
                        severity="medium",
                    )

            except (InvalidOperation, TypeError, ValueError):
                validation_errors.append(
                    f"Invalid unit price for SKU '{item_code}'."
                )

            # Currency: resolve missing currency only from verified ERP data.
            invoice_currency = invoice.get("currency")
            erp_currency = erp_item.get("currency") or erp_vendor.get("currency")

            if (
                invoice_currency
                and erp_currency
                and invoice_currency != erp_currency
            ):
                add_discrepancy(
                    discrepancies,
                    field_name=f"{prefix}.currency",
                    invoice_value=invoice_currency,
                    erp_value=erp_currency,
                    deviation_pct=None,
                    severity="high",
                )

            # SKU master
            sku = erp_skus.get(item_code)

            if not sku:
                validation_errors.append(
                    f"SKU '{item_code}' not found in ERP master."
                )

    # --------------------------------------------------
    # Vendor currency validation
    # --------------------------------------------------

    if erp_vendor:
        invoice_currency = invoice.get("currency")
        vendor_currency = erp_vendor.get("currency")

        # Only flag a mismatch when the invoice explicitly states a currency.
        if (
            invoice_currency
            and vendor_currency
            and invoice_currency != vendor_currency
        ):
            add_discrepancy(
                discrepancies,
                field_name="currency",
                invoice_value=invoice_currency,
                erp_value=vendor_currency,
                deviation_pct=None,
                severity="high",
            )

    if validation_errors:
        status = "failed"
        recommendation = "review"
    elif discrepancies:
        status = "failed"
        recommendation = "review"
    else:
        status = "passed"
        recommendation = "approve"

    return {
        "discrepancies": discrepancies,
        "validation_errors": validation_errors,
        "business_validation_status": status,
        "business_recommendation": recommendation,
    }


def build_business_validation_graph():
    """Build the Business Validation Agent graph."""

    graph = StateGraph(BusinessValidationState)

    graph.add_node("load_rules", load_rules_node)
    graph.add_node("fetch_erp_data", fetch_erp_data_node)
    graph.add_node(
        "compare_business_rules",
        compare_business_rules_node,
    )

    graph.add_edge(START, "load_rules")
    graph.add_edge("load_rules", "fetch_erp_data")
    graph.add_edge(
        "fetch_erp_data",
        "compare_business_rules",
    )
    graph.add_edge(
        "compare_business_rules",
        END,
    )

    return graph.compile()


business_validation_graph = build_business_validation_graph()