-- Vendors from vendors.json
CREATE TABLE erp.vendors (
    vendor_id VARCHAR(64) PRIMARY KEY,
    vendor_name VARCHAR(255) NOT NULL,
    country VARCHAR(100) NOT NULL,
    currency CHAR(3) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Purchase orders from PO Records.json
CREATE TABLE erp.purchase_orders (
    po_number VARCHAR(64) PRIMARY KEY,

    vendor_id VARCHAR(64) NOT NULL
        REFERENCES erp.vendors(vendor_id),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Individual items nested inside each purchase order
CREATE TABLE erp.po_line_items (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    po_number VARCHAR(64) NOT NULL
        REFERENCES erp.purchase_orders(po_number),

    line_number INTEGER NOT NULL,
    item_code VARCHAR(64) NOT NULL,
    description TEXT NOT NULL,
    quantity NUMERIC(12, 3) NOT NULL,
    unit_price NUMERIC(14, 4) NOT NULL,
    currency CHAR(3) NOT NULL,

    CONSTRAINT chk_po_line_number
        CHECK (line_number > 0),

    CONSTRAINT chk_po_quantity
        CHECK (quantity >= 0),

    CONSTRAINT chk_po_unit_price
        CHECK (unit_price >= 0),

    CONSTRAINT uq_po_line_number
        UNIQUE (po_number, line_number)
);

-- SKU master data from sku_master.json
CREATE TABLE erp.sku_master (
    item_code VARCHAR(64) PRIMARY KEY,
    category VARCHAR(100) NOT NULL,
    uom VARCHAR(32) NOT NULL,
    gst_rate NUMERIC(5, 2) NOT NULL,

    CONSTRAINT chk_sku_gst_rate
        CHECK (gst_rate BETWEEN 0 AND 100)
);

-- Indexes for common ERP lookups
CREATE INDEX idx_purchase_orders_vendor_id
    ON erp.purchase_orders(vendor_id);

CREATE INDEX idx_po_line_items_item_code
    ON erp.po_line_items(item_code);

CREATE INDEX idx_sku_master_category
    ON erp.sku_master(category);