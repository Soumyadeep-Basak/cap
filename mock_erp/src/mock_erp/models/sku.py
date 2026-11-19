"""SKU master ORM model."""

from sqlalchemy import Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from mock_erp.db.base import Base


class SKU(Base):
    """Represents an item in the ERP SKU master."""

    __tablename__ = "sku_master"
    __table_args__ = {"schema": "erp"}

    item_code: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
    )
    category: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    uom: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    gst_rate: Mapped[float] = mapped_column(
        Numeric(5, 2),
        nullable=False,
    )
    id="sku-model"