"""Use the existing invoice schema without adding duplicate business rules."""
from pydantic import ValidationError
from invoice_auditor.schemas.invoice import InvoiceSchema
from invoice_auditor.security.content import GuardrailError

def validate_invoice_data(invoice):
    if not isinstance(invoice, dict) or not invoice:
        raise GuardrailError("A non-empty invoice object is required")
    try:
        InvoiceSchema.model_validate(invoice)
    except ValidationError as exc:
        raise GuardrailError("Invoice field types or values are invalid") from exc
    return invoice
