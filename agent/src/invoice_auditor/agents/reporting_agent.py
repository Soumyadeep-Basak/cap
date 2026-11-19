"""Reporting agent for invoice audit outcomes."""

from __future__ import annotations

import html
import json
import logging
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

import yaml
from langgraph.graph import END, START, StateGraph

from invoice_auditor.db.session import SessionLocal
from invoice_auditor.services.reporting_service import (
    persist_report_result,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[4]
RULES_PATH = PROJECT_ROOT / "config" / "rules.yaml"


class ReportingState(TypedDict, total=False):
    """Inputs and outputs for invoice reporting."""

    invoice_id: str
    file_path: str
    invoice: dict[str, Any]
    validation_result: dict[str, Any]
    translation_confidence: float | None
    source_language: str | None
    translated_text: str | None
    erp_data: dict[str, Any]

    report: dict[str, Any]
    json_report_path: str
    html_report_path: str
    report_status: str
    report_error: str


def json_safe(value: Any) -> Any:
    """Convert values into JSON-compatible types."""

    if isinstance(value, dict):
        return {
            str(key): json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]

    if hasattr(value, "isoformat"):
        return value.isoformat()

    if hasattr(value, "as_tuple"):  # Decimal
        return str(value)

    return value


def load_reporting_config() -> dict[str, Any]:
    """Load report configuration from rules.yaml."""

    with RULES_PATH.open("r", encoding="utf-8") as file:
        rules = yaml.safe_load(file) or {}

    return rules.get("reporting", {})


def safe_filename(value: str) -> str:
    """Create a filesystem-safe report filename."""

    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def determine_recommendation(
    validation: dict[str, Any],
) -> tuple[str, str]:
    """Return external and database recommendation values."""

    recommendation = validation.get("recommendation")

    if recommendation in {"reject"}:
        return "reject", "reject"

    if (
        recommendation == "approve"
        and validation.get("validation_status") == "passed"
        and not validation.get("validation_errors")
        and not validation.get("discrepancies")
        and not validation.get("missing_fields")
    ):
        return "approve", "approve"

    # The report uses the requested wording. The audit table
    # retains the existing canonical value "review".
    return "manual_review", "review"


def build_report_node(
    state: ReportingState,
) -> dict[str, Any]:
    """Build discrepancy summary and generate JSON and HTML files."""

    invoice = state.get("invoice") or {}
    validation = state.get("validation_result") or {}

    discrepancies = validation.get("discrepancies") or []
    missing_fields = validation.get("missing_fields") or []
    validation_errors = validation.get("validation_errors") or []

    recommendation, database_recommendation = (
        determine_recommendation(validation)
    )

    severity_counts = Counter(
        str(item.get("severity", "unspecified")).lower()
        for item in discrepancies
    )

    field_counts = Counter(
        str(item.get("field_name", "unspecified"))
        for item in discrepancies
    )

    confidence = state.get("translation_confidence")

    report = {
        "report_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "invoice_id": state.get("invoice_id"),
        "invoice": {
            "invoice_number": invoice.get("invoice_number"),
            "invoice_date": invoice.get("invoice_date"),
            "vendor_id": invoice.get("vendor_id"),
            "vendor_name": invoice.get("vendor_name"),
            "po_number": invoice.get("po_number"),
            "currency": invoice.get("currency"),
            "total_amount": invoice.get("total_amount"),
            "file_path": state.get("file_path"),
        },
        "source_language": state.get("source_language"),
        "translation_confidence": confidence,
        "validation_status": validation.get(
            "validation_status",
            "partial",
        ),
        "recommendation": recommendation,
        "missing_fields": missing_fields,
        "validation_errors": validation_errors,
        "discrepancy_summary": {
            "total": len(discrepancies),
            "by_severity": dict(severity_counts),
            "by_field": dict(field_counts),
        },
        "discrepancies": discrepancies,
        "database_recommendation": database_recommendation,
    }

    report = json_safe(report)

    reporting_config = load_reporting_config()
    configured_dir = os.getenv(
        "REPORT_OUTPUT_DIR",
        reporting_config.get(
            "output_dir",
            "./outputs/reports",
        ),
    )

    output_dir = Path(configured_dir)
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir

    output_dir.mkdir(parents=True, exist_ok=True)

    report_key = safe_filename(
        state.get("invoice_id")
        or invoice.get("invoice_number")
        or "unknown_invoice"
    )

    json_path = output_dir / f"{report_key}.json"
    html_path = output_dir / f"{report_key}.html"

    # JSON report for machine consumption.
    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Escape all inserted values to prevent invoice content
    # from being interpreted as HTML.
    invoice_html = "".join(
        f"<tr><th>{html.escape(str(key))}</th>"
        f"<td>{html.escape(str(value if value is not None else '—'))}</td></tr>"
        for key, value in report["invoice"].items()
    )

    missing_html = (
        "".join(
            f"<li>{html.escape(str(field))}</li>"
            for field in missing_fields
        )
        or "<li>None</li>"
    )

    errors_html = (
        "".join(
            f"<li>{html.escape(str(error))}</li>"
            for error in validation_errors
        )
        or "<li>None</li>"
    )

    discrepancy_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item.get('field_name', '—')))}</td>"
        f"<td>{html.escape(str(item.get('invoice_value', '—')))}</td>"
        f"<td>{html.escape(str(item.get('erp_value', '—')))}</td>"
        f"<td>{html.escape(str(item.get('deviation_pct', '—')))}</td>"
        f"<td>{html.escape(str(item.get('severity', '—')))}</td>"
        "</tr>"
        for item in discrepancies
    )

    if not discrepancy_rows:
        discrepancy_rows = (
            '<tr><td colspan="5">No discrepancies detected.</td></tr>'
        )

    html_document = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Invoice Audit Report</title>
<style>
body {{ font-family: Arial, sans-serif; max-width: 1100px;
       margin: 32px auto; padding: 0 20px; color: #222; }}
h1, h2 {{ color: #183153; }}
table {{ border-collapse: collapse; width: 100%; margin-bottom: 24px; }}
th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
th {{ background: #f2f5f8; }}
.status {{ padding: 12px; border: 1px solid #ccc; margin: 16px 0; }}
pre {{ white-space: pre-wrap; }}
</style>
</head>
<body>
<h1>Invoice Audit Report</h1>
<div class="status">
<strong>Recommendation:</strong>
{html.escape(recommendation)}<br>
<strong>Validation status:</strong>
{html.escape(str(report["validation_status"]))}<br>
<strong>Translation confidence:</strong>
{html.escape(str(confidence if confidence is not None else "Unavailable"))}
</div>

<h2>Invoice Details</h2>
<table>{invoice_html}</table>

<h2>Discrepancy Summary</h2>
<p>Total discrepancies: {len(discrepancies)}</p>
<pre>{html.escape(json.dumps(report["discrepancy_summary"], indent=2))}</pre>

<h2>Discrepancies</h2>
<table>
<thead><tr><th>Field</th><th>Invoice value</th>
<th>ERP value</th><th>Deviation (%)</th><th>Severity</th></tr></thead>
<tbody>{discrepancy_rows}</tbody>
</table>

<h2>Missing Fields</h2>
<ul>{missing_html}</ul>

<h2>Validation Errors</h2>
<ul>{errors_html}</ul>

<p><small>Generated at:
{html.escape(report["generated_at"])}</small></p>
</body>
</html>
"""

    html_path.write_text(html_document, encoding="utf-8")

    report["json_report_path"] = str(json_path)
    report["html_report_path"] = str(html_path)

    return {
        "report": report,
        "json_report_path": str(json_path),
        "html_report_path": str(html_path),
    }


def persist_report_node(
    state: ReportingState,
) -> dict[str, Any]:
    """Persist report outcome to PostgreSQL."""

    invoice_id = state.get("invoice_id")
    report = state.get("report")

    if not invoice_id or not report:
        raise ValueError(
            "invoice_id and report are required for persistence."
        )

    with SessionLocal() as db:
        persist_report_result(
            db=db,
            invoice_id=invoice_id,
            report=report,
        )

    logger.info(
        "Report persisted for invoice %s",
        invoice_id,
    )

    return {"report_status": "completed"}


def build_reporting_graph():
    """Build the Reporting Agent LangGraph."""

    graph = StateGraph(ReportingState)

    graph.add_node("build_report", build_report_node)
    graph.add_node("persist_report", persist_report_node)

    graph.add_edge(START, "build_report")
    graph.add_edge("build_report", "persist_report")
    graph.add_edge("persist_report", END)

    return graph.compile()


reporting_graph = build_reporting_graph()
