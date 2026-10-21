"""Pydantic schemas for vendor API responses."""

from pydantic import BaseModel, ConfigDict


class VendorResponse(BaseModel):
    """Vendor details returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    vendor_id: str
    vendor_name: str
    country: str
    currency: str
    is_active: bool


class VendorListResponse(BaseModel):
    """List of vendors."""

    vendors: list[VendorResponse]