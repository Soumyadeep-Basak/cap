"""Explicit sample-data preview. Never reads or writes production audit data."""
import pandas as pd

_ROWS = [
    ("INV-2481", "Northstar Studio", "2026-11-18", 2480.00, "partial", "review"),
    ("INV-2480", "Meridian Logistics", "2026-11-18", 1850.00, "passed", "approve"),
    ("INV-2479", "Evergreen Office Co.", "2026-11-17", 624.50, "passed", "approve"),
    ("INV-2478", "Atlas Supply Group", "2026-11-17", 4260.00, "failed", "reject"),
    ("INV-2477", "Fieldwork Services", "2026-11-16", 3120.00, "partial", "review"),
    ("INV-2476", "Forma Technologies", "2026-11-16", 960.00, "passed", "approve"),
]

def list_invoices(status=None, recommendation=None, limit=200):
    records = []
    for index, (number, vendor, date, total, validation, outcome) in enumerate(_ROWS, 1):
        records.append(dict(invoice_id=f"00000000-0000-4000-8000-{index:012d}", invoice_number=number,
                            vendor_name=vendor, po_number=f"PO-{8040 + index}", invoice_date=date,
                            currency="USD", total_amount=total, source_language="en",
                            translation_confidence=0.98, validation_status=validation,
                            recommendation=outcome, file_path=f"/sample/{number}.pdf",
                            processing_error=None, processed_at=pd.Timestamp(date, tz="UTC")))
    result = pd.DataFrame(records)
    if status: result = result[result.validation_status == status]
    if recommendation: result = result[result.recommendation == recommendation]
    return result.head(limit)

def get_dashboard_summary():
    frame = list_invoices()
    return dict(total_invoices=len(frame), approved=int((frame.recommendation == "approve").sum()),
                review=int((frame.recommendation == "review").sum()), rejected=int((frame.recommendation == "reject").sum()),
                processing_errors=0)

def get_invoice(invoice_id):
    matches = list_invoices()
    matches = matches[matches.invoice_id == invoice_id]
    if matches.empty: return None
    record = matches.iloc[0].to_dict()
    findings = get_discrepancies(invoice_id).to_dict("records")
    report = dict(report_version="1.0", invoice_id=invoice_id, recommendation=record["recommendation"],
                  validation_status=record["validation_status"], discrepancies=findings,
                  discrepancy_summary={"total": len(findings)}, validation_errors=[], missing_fields=[])
    record.update(raw_extracted_text=f"Invoice Number: {record['invoice_number']}\nVendor: {record['vendor_name']}\nCurrency: USD\nTotal: {record['total_amount']:.2f}",
                  translated_text="Original document is already in English.",
                  extracted_raw={"report": report, "parsed_invoice": {"subtotal_amount": record["total_amount"], "tax_amount": 0, "tax_rate": 0}})
    return record

def get_line_items(invoice_id):
    record = list_invoices().set_index("invoice_id").loc[invoice_id]
    return pd.DataFrame([dict(line_number=1, item_code="SVC-001", description="Professional services",
                              quantity=20, unit_price=float(record.total_amount)/20, line_total=float(record.total_amount))])

def get_discrepancies(invoice_id):
    columns = ["field_name", "invoice_value", "erp_value", "deviation_pct", "severity", "detected_at"]
    outcome = list_invoices().set_index("invoice_id").loc[invoice_id].recommendation
    if outcome == "approve": return pd.DataFrame(columns=columns)
    return pd.DataFrame([dict(field_name="line_items[0].unit_price", invoice_value="124.00",
                              erp_value="120.00", deviation_pct=3.33, severity="medium",
                              detected_at="2026-11-18")], columns=columns)

def get_feedback(invoice_id):
    return pd.DataFrame(columns=["id", "field_name", "original_value", "corrected_value", "corrected_by", "corrected_at", "revalidated"])
