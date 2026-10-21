"""Business logic for Mock ERP operations."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from mock_erp.models.purchase_order import POLineItem, PurchaseOrder
from mock_erp.models.sku import SKU
from mock_erp.models.vendor import Vendor


def get_vendor(db: Session, vendor_id: str) -> Vendor | None:
    return db.scalar(
        select(Vendor).where(Vendor.vendor_id == vendor_id)
    )


def list_vendors(db: Session) -> list[Vendor]:
    return list(
        db.scalars(select(Vendor).order_by(Vendor.vendor_id)).all()
    )


def get_purchase_order(db: Session, po_number: str) -> PurchaseOrder | None:
    return db.scalar(
        select(PurchaseOrder).where(
            PurchaseOrder.po_number == po_number
        )
    )


def get_purchase_order_line_items(db: Session, po_number: str) -> list[POLineItem]:
    statement = (
        select(POLineItem)
        .where(POLineItem.po_number == po_number)
        .order_by(POLineItem.line_number)
    )
    return list(db.scalars(statement).all())


def list_purchase_orders(db: Session) -> list[PurchaseOrder]:
    statement = select(PurchaseOrder)

    return list(
        db.scalars(statement.order_by(PurchaseOrder.po_number)).all()
    )


def get_sku(db: Session, item_code: str) -> SKU | None:
    return db.scalar(
        select(SKU).where(SKU.item_code == item_code)
    )


def list_skus(db: Session) -> list[SKU]:
    return list(
        db.scalars(select(SKU).order_by(SKU.item_code)).all()
    )