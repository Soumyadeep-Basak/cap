
"""Pydantic schemas for purchase order and SKU API responses."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class POLineItemResponse(BaseModel):
    """A purchase order line item."""

    model_config = ConfigDict(from_attributes=True)

    line_number: int
    item_code: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    currency: str


class PurchaseOrderResponse(BaseModel):
    """Purchase order with its line items."""

    model_config = ConfigDict(from_attributes=True)

    po_number: str
    vendor_id: str
    line_items: list[POLineItemResponse]


class PurchaseOrderListResponse(BaseModel):
    """List of purchase orders."""

    purchase_orders: list[PurchaseOrderResponse]