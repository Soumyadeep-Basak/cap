"""Read-only data access for the Streamlit dashboard.

The dashboard reads audit information directly from PostgreSQL (per the
architecture: "Streamlit UI reads reports from PostgreSQL, and calls the
Agent for revalidation"). It never writes to the database directly --
all mutations (feedback, revalidation) go through the Agent API so that
the Agent remains the only service that writes application audit data.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import pandas as pd
import sqlalchemy as sa

from invoice_auditor_ui.config import DATABASE_URL


@lru_cache(maxsize=1)
def get_engine() -> sa.engine.Engine:
    """Return a cached, read-only SQLAlchemy engine."""
    return sa.create_engine(DATABASE_URL, pool_pre_ping=True)


def list_invoices(
    status: str | None = None,
    recommendation: str | None = None,
    limit: int = 200,
) -> pd.DataFrame:
    """Return a summary of processed invoices, most recent first."""
    query = """
        SELECT invoice_id, invoice_number, vendor_name, po_number,
               invoice_date, currency, total_amount, source_language,
               translation_confidence, validation_status, recommendation,
               file_path, processing_error, processed_at
        FROM audit.invoice_audit
        WHERE (CAST(:status AS VARCHAR) IS NULL OR validation_status = :status)
          AND (
              CAST(:recommendation AS VARCHAR) IS NULL
              OR recommendation = :recommendation
          )
        ORDER BY processed_at DESC
        LIMIT :limit
    """
    with get_engine().connect() as conn:
        return pd.read_sql(
            sa.text(query),
            conn,
            params={
                "status": status,
                "recommendation": recommendation,
                "limit": limit,
            },
        )


def get_invoice(invoice_id: str) -> dict[str, Any] | None:
    """Return the full audit row for one invoice, including its report."""
    query = """
        SELECT invoice_id, file_path, file_checksum, extraction_method,
               raw_extracted_text, translated_text, source_language,
               translation_confidence, invoice_number, vendor_id,
               vendor_name, po_number, invoice_date, currency,
               total_amount, validation_status, recommendation,
               extracted_raw, processing_error, thread_id, processed_at
        FROM audit.invoice_audit
        WHERE invoice_id = :invoice_id
    """
    with get_engine().connect() as conn:
        row = conn.execute(
            sa.text(query), {"invoice_id": invoice_id}
        ).mappings().first()
        return dict(row) if row else None


def get_line_items(invoice_id: str) -> pd.DataFrame:
    """Return the line items belonging to one invoice."""
    query = """
        SELECT line_number, item_code, description, quantity,
               unit_price, line_total
        FROM audit.invoice_line_items
        WHERE invoice_id = :invoice_id
        ORDER BY line_number
    """
    with get_engine().connect() as conn:
        return pd.read_sql(
            sa.text(query), conn, params={"invoice_id": invoice_id}
        )


def get_discrepancies(invoice_id: str) -> pd.DataFrame:
    """Return discrepancies detected for one invoice."""
    query = """
        SELECT field_name, invoice_value, erp_value, deviation_pct,
               severity, detected_at
        FROM audit.discrepancies
        WHERE invoice_id = :invoice_id
        ORDER BY detected_at
    """
    with get_engine().connect() as conn:
        return pd.read_sql(
            sa.text(query), conn, params={"invoice_id": invoice_id}
        )


def get_feedback(invoice_id: str) -> pd.DataFrame:
    """Return human corrections recorded for one invoice."""
    query = """
        SELECT id, field_name, original_value, corrected_value,
               corrected_by, corrected_at, revalidated
        FROM audit.human_feedback
        WHERE invoice_id = :invoice_id
        ORDER BY corrected_at DESC
    """
    with get_engine().connect() as conn:
        return pd.read_sql(
            sa.text(query), conn, params={"invoice_id": invoice_id}
        )


def get_dashboard_summary() -> dict[str, int]:
    """Return headline counts shown at the top of the dashboard."""
    query = """
        SELECT
            COUNT(*) AS total_invoices,
            COUNT(*) FILTER (WHERE recommendation = 'approve') AS approved,
            COUNT(*) FILTER (WHERE recommendation = 'review') AS review,
            COUNT(*) FILTER (WHERE recommendation = 'reject') AS rejected,
            COUNT(*) FILTER (WHERE processing_error IS NOT NULL)
                AS processing_errors
        FROM audit.invoice_audit
    """
    with get_engine().connect() as conn:
        row = conn.execute(sa.text(query)).mappings().first()
        return dict(row) if row else {}
