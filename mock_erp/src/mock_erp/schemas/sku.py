"""Pydantic schemas for SKU API responses."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class SKUResponse(BaseModel):
    """SKU master record."""

    model_config = ConfigDict(from_attributes=True)

    item_code: str
    category: str
    uom: str
    gst_rate: Decimal


class SKUListResponse(BaseModel):
    """List of SKUs."""

    skus: list[SKUResponse]