CREATE TABLE IF NOT EXISTS audit.invoice_audit (
    invoice_id UUID PRIMARY KEY,

    file_path VARCHAR(512) NOT NULL,
    file_checksum VARCHAR(64) NOT NULL UNIQUE,

    extraction_method VARCHAR(32),
    raw_extracted_text TEXT NOT NULL,
    translated_text TEXT,

    source_language VARCHAR(8),
    translation_confidence NUMERIC(4, 3),

    invoice_number VARCHAR(64),
    vendor_id VARCHAR(64),
    vendor_name VARCHAR(255),
    po_number VARCHAR(64),
    invoice_date DATE,
    currency CHAR(3),
    total_amount NUMERIC(14, 2),

    validation_status VARCHAR(32) NOT NULL DEFAULT 'pending',
    recommendation VARCHAR(32),

    extracted_raw JSONB NOT NULL DEFAULT '{}'::jsonb,
    thread_id VARCHAR(128),

    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_translation_confidence
        CHECK (
            translation_confidence IS NULL
            OR translation_confidence BETWEEN 0 AND 1
        ),

    CONSTRAINT chk_validation_status
        CHECK (
            validation_status IN (
                'pending', 'passed', 'failed', 'partial'
            )
        ),

    CONSTRAINT chk_recommendation
        CHECK (
            recommendation IS NULL
            OR recommendation IN ('approve', 'review', 'reject')
        )
);

CREATE TABLE IF NOT EXISTS audit.invoice_line_items (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    invoice_id UUID NOT NULL
        REFERENCES audit.invoice_audit(invoice_id),

    line_number INTEGER NOT NULL,
    item_code VARCHAR(64),
    description TEXT,
    quantity NUMERIC(12, 3),
    unit_price NUMERIC(14, 4),
    line_total NUMERIC(14, 2),

    CONSTRAINT uq_invoice_line_number
        UNIQUE (invoice_id, line_number)
);

CREATE TABLE IF NOT EXISTS audit.discrepancies (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    invoice_id UUID NOT NULL
        REFERENCES audit.invoice_audit(invoice_id),

    field_name VARCHAR(64) NOT NULL,
    invoice_value TEXT,
    erp_value TEXT,
    deviation_pct NUMERIC(8, 4),
    severity VARCHAR(16) NOT NULL,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_discrepancy_severity
        CHECK (severity IN ('low', 'medium', 'high', 'critical'))
);

CREATE TABLE IF NOT EXISTS audit.human_feedback (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    invoice_id UUID NOT NULL
        REFERENCES audit.invoice_audit(invoice_id),

    field_name VARCHAR(64) NOT NULL,
    original_value TEXT,
    corrected_value TEXT NOT NULL,
    corrected_by VARCHAR(128) NOT NULL,
    corrected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revalidated BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_invoice_audit_vendor
    ON audit.invoice_audit(vendor_id);

CREATE INDEX IF NOT EXISTS idx_invoice_audit_date
    ON audit.invoice_audit(invoice_date);

CREATE INDEX IF NOT EXISTS idx_invoice_audit_status
    ON audit.invoice_audit(validation_status);

CREATE INDEX IF NOT EXISTS idx_discrepancies_invoice
    ON audit.discrepancies(invoice_id);

CREATE INDEX IF NOT EXISTS idx_human_feedback_invoice
    ON audit.human_feedback(invoice_id);