ALTER TABLE audit.invoice_audit
    ALTER COLUMN raw_extracted_text DROP NOT NULL;

ALTER TABLE audit.invoice_audit
    ADD COLUMN processing_error TEXT;