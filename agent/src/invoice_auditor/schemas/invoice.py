"""Pydantic schemas for extracted invoice data."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from invoice_auditor.schemas.invoice_line_items import (
    InvoiceLineItemSchema,
)


class InvoiceSchema(BaseModel):
    """Structured invoice data extracted from a document."""

    model_config = ConfigDict(extra="allow")

    invoice_number: str | None = None
    vendor_id: str | None = None
    vendor_name: str | None = None
    po_number: str | None = None
    invoice_date: date | None = None
    currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=3,
    )
    total_amount: Decimal | None = Field(default=None, ge=0)
    source_language: str | None = None
    translation_confidence: Decimal | None = Field(
        default=None,
        ge=0,
        le=1,
    )
    line_items: list[InvoiceLineItemSchema] = Field(default_factory=list)