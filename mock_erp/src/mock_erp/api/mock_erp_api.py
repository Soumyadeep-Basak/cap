"""FastAPI endpoints for the Mock ERP service."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from mock_erp.db.session import get_db
from mock_erp.schemas.purchase_order import (
    POLineItemResponse,
    PurchaseOrderListResponse,
    PurchaseOrderResponse,
)
from mock_erp.schemas.sku import SKUListResponse, SKUResponse
from mock_erp.schemas.vendor import VendorListResponse, VendorResponse
from mock_erp.services import erp_service

router = APIRouter(prefix="/api/v1/erp", tags=["Mock ERP"])


@router.get("/po/{po_number}", response_model=PurchaseOrderResponse)
def read_purchase_order(po_number: str, db: Session = Depends(get_db)) -> PurchaseOrderResponse:
    """Get a purchase order and its line items."""
    purchase_order = erp_service.get_purchase_order(db, po_number)

    if purchase_order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Purchase order '{po_number}' not found",
        )

    line_items = erp_service.get_purchase_order_line_items(
        db, po_number
    )

    return PurchaseOrderResponse(
        po_number=purchase_order.po_number,
        vendor_id=purchase_order.vendor_id,
        line_items=[
            POLineItemResponse.model_validate(item)
            for item in line_items
        ],
    )


@router.get("/vendor/{vendor_id}", response_model=VendorResponse)
def read_vendor(vendor_id: str, db: Session = Depends(get_db)) -> VendorResponse:
    """Get a vendor by ID."""
    vendor = erp_service.get_vendor(db, vendor_id)

    if vendor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vendor '{vendor_id}' not found",
        )

    return VendorResponse.model_validate(vendor)


@router.get("/sku/{item_code}", response_model=SKUResponse)
def read_sku(item_code: str, db: Session = Depends(get_db)) -> SKUResponse:
    """Get an SKU by item code."""
    sku = erp_service.get_sku(db, item_code)

    if sku is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SKU '{item_code}' not found",
        )

    return SKUResponse.model_validate(sku)


@router.get("/po", response_model=PurchaseOrderListResponse)
def read_purchase_orders(db: Session = Depends(get_db)) -> PurchaseOrderListResponse:
    """List purchase orders, optionally filtered by vendor."""
    purchase_orders = erp_service.list_purchase_orders(db)

    return PurchaseOrderListResponse(
        purchase_orders=[
            PurchaseOrderResponse(
                po_number=po.po_number,
                vendor_id=po.vendor_id,
                line_items=[
                    POLineItemResponse.model_validate(item)
                    for item in erp_service.get_purchase_order_line_items(
                        db, po.po_number
                    )
                ],
            )
            for po in purchase_orders
        ]
    )


@router.get("/vendors", response_model=VendorListResponse)
def read_vendors(db: Session = Depends(get_db)) -> VendorListResponse:
    """List all vendors."""
    vendors = erp_service.list_vendors(db)

    return VendorListResponse(
        vendors=[
            VendorResponse.model_validate(vendor)
            for vendor in vendors
        ]
    )


@router.get("/skus", response_model=SKUListResponse)
def read_skus(db: Session = Depends(get_db)) -> SKUListResponse:
    """List all SKUs."""
    skus = erp_service.list_skus(db)

    return SKUListResponse(
        skus=[
            SKUResponse.model_validate(sku)
            for sku in skus
        ]
    )