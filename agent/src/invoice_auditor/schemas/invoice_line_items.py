"""Pydantic schemas for invoice line items."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class InvoiceLineItemSchema(BaseModel):
    """Structured data extracted for one invoice line."""

    model_config = ConfigDict(extra="forbid")

    line_number: int | None = Field(default=None, ge=1)
    item_code: str | None = None
    description: str | None = None
    quantity: Decimal | None = Field(default=None, gt=0)
    unit_price: Decimal | None = Field(default=None, ge=0)
    line_total: Decimal | None = Field(default=None, ge=0)