-- Seed mock ERP data for the AI Invoice Auditor.

BEGIN;

-- =========================================================
-- 1. VENDORS
-- =========================================================

INSERT INTO erp.vendors (
    vendor_id,
    vendor_name,
    country,
    currency
)
VALUES
    ('VEND-001', 'Global Logistics Ltd', 'UK', 'USD'),
    ('VEND-002', 'BlueOcean Transport Co.', 'USA', 'USD'),
    ('VEND-003', 'Transporte Ibérico S.A.', 'Spain', 'EUR'),
    ('VEND-004', 'HafenLogistik GmbH', 'Germany', 'EUR'),
    ('VEND-005', 'SwiftMove Couriers', 'USA', 'USD'),
    ('VEND-006', 'OceanFreight Pvt Ltd', 'India', 'INR')
ON CONFLICT (vendor_id) DO NOTHING;


-- =========================================================
-- 2. PURCHASE ORDERS
-- =========================================================

INSERT INTO erp.purchase_orders (
    po_number,
    vendor_id
)
VALUES
    ('PO-1001', 'VEND-001'),
    ('PO-1002', 'VEND-002'),
    ('PO-1003', 'VEND-003'),
    ('PO-1004', 'VEND-004'),
    ('PO-1005', 'VEND-005'),
    ('PO-1006', 'VEND-006')
ON CONFLICT (po_number) DO NOTHING;


-- =========================================================
-- 3. PURCHASE ORDER LINE ITEMS
-- =========================================================

-- PO-1001
INSERT INTO erp.po_line_items (
    po_number,
    line_number,
    item_code,
    description,
    quantity,
    unit_price,
    currency
)
VALUES
    (
        'PO-1001', 1, 'SKU-001',
        'Pallet Wrapping Film', 50, 12.00, 'USD'
    ),
    (
        'PO-1001', 2, 'SKU-002',
        'Industrial Gloves', 120, 3.00, 'USD'
    ),
    (
        'PO-1001', 3, 'SKU-003',
        'Safety Helmets', 30, 15.00, 'USD'
    )
ON CONFLICT (po_number, line_number) DO NOTHING;


-- PO-1002
INSERT INTO erp.po_line_items (
    po_number,
    line_number,
    item_code,
    description,
    quantity,
    unit_price,
    currency
)
VALUES
    (
        'PO-1002', 1, 'SKU-101',
        'Container Seals', 200, 1.25, 'USD'
    )
ON CONFLICT (po_number, line_number) DO NOTHING;


-- PO-1003
INSERT INTO erp.po_line_items (
    po_number,
    line_number,
    item_code,
    description,
    quantity,
    unit_price,
    currency
)
VALUES
    (
        'PO-1003', 1, 'SKU-201',
        'Cajas de carton', 100, 2.50, 'EUR'
    ),
    (
        'PO-1003', 2, 'SKU-202',
        'Etiquetas adhesivas', 300, 0.30, 'EUR'
    )
ON CONFLICT (po_number, line_number) DO NOTHING;


-- PO-1004
INSERT INTO erp.po_line_items (
    po_number,
    line_number,
    item_code,
    description,
    quantity,
    unit_price,
    currency
)
VALUES
    (
        'PO-1004', 1, 'SKU-301',
        'Transportkisten', 40, 25.00, 'EUR'
    ),
    (
        'PO-1004', 2, 'SKU-302',
        'Sicherheitswesten', 60, 10.00, 'EUR'
    )
ON CONFLICT (po_number, line_number) DO NOTHING;


-- PO-1005
INSERT INTO erp.po_line_items (
    po_number,
    line_number,
    item_code,
    description,
    quantity,
    unit_price,
    currency
)
VALUES
    (
        'PO-1005', 1, 'SKU-401',
        'Fuel Surcharge', 1, 120.00, 'USD'
    ),
    (
        'PO-1005', 2, 'SKU-402',
        'Express Delivery Boxes', 25, 4.50, 'USD'
    )
ON CONFLICT (po_number, line_number) DO NOTHING;


-- PO-1006
INSERT INTO erp.po_line_items (
    po_number,
    line_number,
    item_code,
    description,
    quantity,
    unit_price,
    currency
)
VALUES
    (
        'PO-1006', 1, 'SKU-501',
        'Container Transport', 5, 8000.00, 'INR'
    )
ON CONFLICT (po_number, line_number) DO NOTHING;


-- =========================================================
-- 4. SKU MASTER
-- =========================================================

INSERT INTO erp.sku_master (
    item_code,
    category,
    uom,
    gst_rate
)
VALUES
    ('SKU-001', 'Packaging', 'roll', 10),
    ('SKU-002', 'Safety', 'pair', 10),
    ('SKU-003', 'Safety', 'piece', 10),
    ('SKU-101', 'Logistics', 'piece', 10),
    ('SKU-201', 'Packaging', 'box', 10),
    ('SKU-202', 'Packaging', 'label', 10),
    ('SKU-301', 'Transport', 'crate', 10),
    ('SKU-302', 'Safety', 'vest', 10),
    ('SKU-401', 'Charges', 'service', 10),
    ('SKU-402', 'Packaging', 'box', 10),
    ('SKU-501', 'Transport', 'service', 10)
ON CONFLICT (item_code) DO NOTHING;


COMMIT;