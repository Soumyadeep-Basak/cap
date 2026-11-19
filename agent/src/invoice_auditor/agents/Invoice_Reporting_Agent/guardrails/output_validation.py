"""Reject approvals that contradict validation evidence."""
from invoice_auditor.security.content import GuardrailError

def validate_report(report, validation):
    if report.get("recommendation") not in {"approve", "manual_review", "reject"}:
        raise GuardrailError("Invalid report recommendation")
    if report["recommendation"] == "approve" and (
        validation.get("validation_status") != "passed"
        or validation.get("recommendation") != "approve"
        or any(validation.get(k) for k in ("discrepancies", "missing_fields", "validation_errors"))
    ):
        raise GuardrailError("Approval is unsupported by validation evidence")
    return report
