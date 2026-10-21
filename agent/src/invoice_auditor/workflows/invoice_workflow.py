"""Parent LangGraph workflow for invoice auditing."""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from langgraph.graph import END, START, StateGraph

from invoice_auditor.agents.business_validation_agent import (
    business_validation_graph,
)
from invoice_auditor.agents.extractor_agent import (
    extract_document,
    parse_invoice_text,
)
from invoice_auditor.agents.invoice_monitor_agent import (
    invoice_monitor_graph,
)
from invoice_auditor.agents.rag_agents.indexing_agent import (
    indexing_graph,
)
from invoice_auditor.agents.reporting_agent import reporting_graph
from invoice_auditor.agents.translation_agent import translation_graph
from invoice_auditor.agents.validation_agent import (
    invoice_validation_graph,
)
from invoice_auditor.db.session import SessionLocal
from invoice_auditor.services.invoice_audit_service import (
    mark_processing_failed,
    save_discrepancies,
    save_extraction_result,
    save_validation_result,
)
from invoice_auditor.workflows.state import InvoiceAuditState


logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Utility
# ------------------------------------------------------------------

def make_json_safe(value: Any) -> Any:
    """Convert Python values into JSON-compatible values."""

    if isinstance(value, dict):
        return {
            str(key): make_json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [make_json_safe(item) for item in value]

    if isinstance(value, (date, datetime)):
        return value.isoformat()

    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, UUID):
        return str(value)

    return value


# ------------------------------------------------------------------
# Node 1: Invoice Monitor Agent
# ------------------------------------------------------------------

def monitor_invoices_node(
    state: InvoiceAuditState,
) -> dict[str, Any]:
    """Run the Invoice Monitor Agent subgraph.

    The monitor discovers files, calculates checksums, registers audit
    records, identifies duplicates, and routes supported invoice files.
    """

    monitor_input: dict[str, Any] = {}

    if state.get("incoming_dir"):
        monitor_input["incoming_dir"] = state["incoming_dir"]

    result = invoice_monitor_graph.invoke(monitor_input)

    return {
        "discovered_files": result.get("discovered_files", []),
        "pending_invoices": result.get("pending_invoices", []),
        "routed_invoices": result.get("routed_invoices", []),
        "duplicate_files": result.get("duplicate_files", []),
        "monitor_errors": result.get(
            "errors",
            result.get("monitor_errors", []),
        ),
    }


# ------------------------------------------------------------------
# Node 2: Extract, translate, parse, and persist extraction results
# ------------------------------------------------------------------

def process_invoices_node(
    state: InvoiceAuditState,
) -> dict[str, Any]:
    """Extract, translate, parse, and persist each routed invoice.

    Validation is intentionally separate from this node.

    Required order:
        1. Extraction
        2. Invoice data validation
        3. Business validation
        4. Combine validation results
        5. Persist validation results
        6. Generate reports
    """

    extraction_results: list[dict[str, Any]] = []
    monitor_errors = list(state.get("monitor_errors", []))

    for invoice_file in state.get("routed_invoices", []):
        file_path = invoice_file["file_path"]
        invoice_id = UUID(invoice_file["invoice_id"])

        try:
            # 1. Extract text from the original document.
            raw_text, extraction_method = extract_document(
                Path(file_path)
            )

            # 2. Translate through the translation subgraph.
            translation_result = translation_graph.invoke(
                {
                    "invoice_id": str(invoice_id),
                    "raw_extracted_text": raw_text,
                }
            )

            if translation_result.get("translation_status") != "completed":
                raise RuntimeError(
                    translation_result.get(
                        "processing_error",
                        "Translation did not complete",
                    )
                )

            source_language = translation_result["source_language"]
            translated_text = translation_result["translated_text"]
            confidence = translation_result["translation_confidence"]

            # 3. Parse the translated English text.
            invoice = parse_invoice_text(translated_text)

            # 4. Preserve extraction and translation metadata.
            extracted_raw = {
                "parsed_invoice": make_json_safe(invoice),
                "source_language": source_language,
                "translated_text": translated_text,
                "translation_confidence": confidence,
            }

            # 5. Persist the original raw text and extracted fields.
            with SessionLocal() as db:
                save_extraction_result(
                    db=db,
                    invoice_id=invoice_id,
                    raw_extracted_text=raw_text,
                    extraction_method=extraction_method,
                    invoice=invoice,
                    extracted_raw=extracted_raw,
                )

            extraction_results.append(
                {
                    "invoice_id": str(invoice_id),
                    "file_path": file_path,
                    "extraction_method": extraction_method,
                    "source_language": source_language,
                    "raw_extracted_text": raw_text,
                    "translated_text": translated_text,
                    "translation_confidence": confidence,
                    "translation_cache_hit": translation_result.get(
                        "translation_cache_hit",
                        False,
                    ),
                    "invoice": make_json_safe(invoice),
                    "status": "extracted",
                }
            )

            logger.info(
                "Extracted and translated %s (language=%s)",
                file_path,
                source_language,
            )

        except Exception as exc:
            logger.exception(
                "Invoice processing failed: %s",
                file_path,
            )

            error_message = str(exc)

            # Persist processing failures where possible.
            try:
                with SessionLocal() as db:
                    mark_processing_failed(
                        db=db,
                        invoice_id=invoice_id,
                        error_message=error_message,
                    )

            except Exception as db_exc:
                logger.exception(
                    "Could not persist failure for %s",
                    file_path,
                )

                error_message = (
                    f"{error_message}; "
                    "failure recording also failed: "
                    f"{db_exc}"
                )

            monitor_errors.append(
                {
                    "file_path": file_path,
                    "error": error_message,
                }
            )

            extraction_results.append(
                {
                    "invoice_id": str(invoice_id),
                    "file_path": file_path,
                    "status": "failed",
                    "error": error_message,
                }
            )

    return {
        "extraction_results": extraction_results,
        "monitor_errors": monitor_errors,
    }


# ------------------------------------------------------------------
# Validation utility
# ------------------------------------------------------------------

def normalize_data_discrepancy(
    discrepancy: dict[str, Any],
) -> dict[str, Any]:
    """Normalize arithmetic discrepancies for reporting and persistence."""

    discrepancy_type = discrepancy.get(
        "type",
        "validation_mismatch",
    )

    field_mapping = {
        "line_total_mismatch": (
            f"line_items[{discrepancy.get('line_number', 1) - 1}]"
            ".line_total"
        ),
        "subtotal_mismatch": "subtotal_amount",
        "invoice_total_mismatch": "total_amount",
        "tax_mismatch": "tax_amount",
    }

    if discrepancy_type == "subtotal_mismatch":
        invoice_value = discrepancy.get("subtotal")
        erp_value = discrepancy.get("line_item_sum")
    else:
        invoice_value = discrepancy.get("recorded")
        erp_value = discrepancy.get("calculated")

    return {
        **discrepancy,
        "field_name": discrepancy.get(
            "field_name",
            field_mapping.get(discrepancy_type, discrepancy_type),
        ),
        "invoice_value": discrepancy.get(
            "invoice_value",
            invoice_value,
        ),
        "erp_value": discrepancy.get("erp_value", erp_value),
        "deviation_pct": discrepancy.get("deviation_pct"),
        "severity": discrepancy.get("severity", "medium"),
    }


# ------------------------------------------------------------------
# Validation utility: combine data + business validation results
# ------------------------------------------------------------------

def combine_validation_results(
    data_validation_result: dict[str, Any],
    business_validation_result: dict[str, Any],
) -> tuple[dict[str, Any], str | None]:
    """Combine data and business validation into one validation result.

    Shared by the normal processing workflow (``validate_invoices_node``)
    and the human-in-the-loop revalidation workflow so both apply the
    exact same recommendation/status/severity rules.

    Returns the combined validation result along with an ERP-resolved
    vendor ID (for report display only, see note below).
    """

    # ------------------------------------------------------
    # 1. Normalize ERP results
    # ------------------------------------------------------
    erp_data = {
        "purchase_order": business_validation_result.get("erp_po"),
        "vendor": business_validation_result.get("erp_vendor"),
        "skus": business_validation_result.get("erp_skus", {}),
    }

    erp_po = erp_data["purchase_order"] or {}
    erp_vendor = erp_data["vendor"] or {}

    # A vendor ID may be resolved for reporting only when the
    # purchase order and vendor master contain the same vendor ID.
    # This does not change the extracted invoice or its validation.
    resolved_vendor_id = None
    po_vendor_id = erp_po.get("vendor_id")
    master_vendor_id = erp_vendor.get("vendor_id")

    if (
        po_vendor_id
        and master_vendor_id
        and str(po_vendor_id).strip()
        == str(master_vendor_id).strip()
    ):
        resolved_vendor_id = master_vendor_id

    # ------------------------------------------------------
    # 2. Collect validation statuses and recommendations
    # ------------------------------------------------------
    data_status = data_validation_result.get(
        "validation_status",
        "failed",
    )

    business_status = business_validation_result.get(
        "business_validation_status",
        "partial",
    )

    data_recommendation = data_validation_result.get(
        "recommendation"
    )

    business_recommendation = business_validation_result.get(
        "business_recommendation"
    )

    data_discrepancies = data_validation_result.get(
        "discrepancies",
        [],
    )

    business_discrepancies = business_validation_result.get(
        "discrepancies",
        [],
    )

    normalized_data_discrepancies = [
        normalize_data_discrepancy(discrepancy)
        for discrepancy in data_discrepancies
    ]

    all_discrepancies = (
        normalized_data_discrepancies
        + business_discrepancies
    )

    all_errors = (
        data_validation_result.get("validation_errors", [])
        + business_validation_result.get("validation_errors", [])
    )

    missing_fields = data_validation_result.get(
        "missing_fields",
        [],
    )

    # ------------------------------------------------------
    # 3. Combine results and determine final recommendation
    # ------------------------------------------------------
    if (
        data_recommendation == "reject"
        or business_recommendation == "reject"
    ):
        final_recommendation = "reject"

    elif (
        data_recommendation in {"review", "manual_review"}
        or business_recommendation in {"review", "manual_review"}
    ):
        final_recommendation = "review"

    elif missing_fields or all_discrepancies or all_errors:
        final_recommendation = "review"

    else:
        final_recommendation = "approve"

    # Determine the final validation status.
    if final_recommendation == "reject":
        final_status = "failed"

    elif final_recommendation == "review":
        final_status = "partial"

    elif (
        data_status == "passed"
        and business_status == "passed"
    ):
        final_status = "passed"

    else:
        final_status = "partial"
        final_recommendation = "review"

    # ------------------------------------------------------
    # 4. Determine highest discrepancy severity
    # ------------------------------------------------------
    severity_levels = {
        "low": 1,
        "medium": 2,
        "high": 3,
        "critical": 4,
    }

    highest_severity = "low"

    for discrepancy in all_discrepancies:
        severity = discrepancy.get("severity", "medium")

        if severity_levels.get(
            severity,
            2,
        ) > severity_levels[highest_severity]:
            highest_severity = severity

    if (
        missing_fields
        and severity_levels[highest_severity] < 2
    ):
        highest_severity = "medium"

    if (
        all_errors
        and severity_levels[highest_severity] < 3
    ):
        highest_severity = "high"

    # ------------------------------------------------------
    # 5. Build the combined validation result
    # ------------------------------------------------------
    validation_result = {
        "missing_fields": missing_fields,
        "validation_errors": all_errors,
        "observations": data_validation_result.get(
            "observations",
            [],
        ),
        "arithmetic_passed": data_validation_result.get(
            "arithmetic_passed",
            False,
        ),
        "tax_verified": data_validation_result.get(
            "tax_verified",
            False,
        ),
        "data_validation_discrepancies": data_discrepancies,
        "business_validation_status": business_status,
        "business_recommendation": business_recommendation,
        "business_discrepancies": business_discrepancies,
        "erp_data": erp_data,
        "discrepancies": all_discrepancies,
        "severity_level": highest_severity,
        "validation_status": final_status,
        "recommendation": final_recommendation,
    }

    return validation_result, resolved_vendor_id


# ------------------------------------------------------------------
# Node 3: Invoice data validation, then business validation
# ------------------------------------------------------------------

def validate_invoices_node(
    state: InvoiceAuditState,
) -> dict[str, Any]:
    """Validate extracted invoice data before checking it against Mock ERP."""

    extraction_results = [
        dict(item)
        for item in state.get("extraction_results", [])
    ]

    validation_results: list[dict[str, Any]] = []
    monitor_errors = list(state.get("monitor_errors", []))

    for item in extraction_results:
        if item.get("status") != "extracted":
            continue

        invoice_id = UUID(item["invoice_id"])
        file_path = item["file_path"]
        invoice = item.get("invoice") or {}

        try:
            # ------------------------------------------------------
            # 1. Invoice data validation
            # ------------------------------------------------------
            # Validate the extracted invoice against config/rules.yaml.
            # Do not inject ERP-derived values into the extracted invoice.
            data_validation_result = invoice_validation_graph.invoke(
                {
                    "invoice": invoice,
                    "translation_confidence": item.get(
                        "translation_confidence"
                    ),
                }
            )

            # ------------------------------------------------------
            # 2. Business validation against Mock ERP
            # ------------------------------------------------------
            business_validation_result = business_validation_graph.invoke(
                {"invoice": invoice}
            )

            # ------------------------------------------------------
            # 3. Combine both results using the shared helper.
            # ------------------------------------------------------
            validation_result, resolved_vendor_id = (
                combine_validation_results(
                    data_validation_result,
                    business_validation_result,
                )
            )

            final_status = validation_result["validation_status"]
            final_recommendation = validation_result["recommendation"]
            all_discrepancies = validation_result["discrepancies"]

            safe_validation_result = make_json_safe(validation_result)

            # ------------------------------------------------------
            # 8. Persist validation results and discrepancies
            # ------------------------------------------------------
            with SessionLocal() as db:
                save_validation_result(
                    db,
                    invoice_id,
                    safe_validation_result,
                )

                save_discrepancies(
                    db=db,
                    invoice_id=invoice_id,
                    discrepancies=make_json_safe(all_discrepancies),
                )

            # ------------------------------------------------------
            # 9. Store results in parent workflow state
            # ------------------------------------------------------
            item["validation"] = safe_validation_result
            item["validation_status"] = final_status
            item["recommendation"] = final_recommendation

            # Keep the resolved ID separately from the extracted invoice.
            if resolved_vendor_id is not None:
                item["resolved_vendor_id"] = resolved_vendor_id

            validation_results.append(
                {
                    "invoice_id": str(invoice_id),
                    "file_path": file_path,
                    **safe_validation_result,
                }
            )

            logger.info(
                "Validation completed for %s: "
                "status=%s recommendation=%s discrepancies=%d",
                file_path,
                final_status,
                final_recommendation,
                len(all_discrepancies),
            )

        except Exception as exc:
            logger.exception(
                "Validation failed to execute for %s",
                file_path,
            )

            error_message = str(exc)

            try:
                with SessionLocal() as db:
                    mark_processing_failed(
                        db=db,
                        invoice_id=invoice_id,
                        error_message=(
                            "Validation execution error: "
                            f"{error_message}"
                        ),
                    )

            except Exception:
                logger.exception(
                    "Could not persist validation execution failure "
                    "for %s",
                    file_path,
                )

            item["validation_execution_error"] = error_message

            monitor_errors.append(
                {
                    "file_path": file_path,
                    "error": (
                        "Validation execution error: "
                        f"{error_message}"
                    ),
                }
            )

    return {
        "extraction_results": extraction_results,
        "validation_results": validation_results,
        "monitor_errors": monitor_errors,
    }


# ------------------------------------------------------------------
# Node 4: Generate reports
# ------------------------------------------------------------------

def report_invoices_node(
    state: InvoiceAuditState,
) -> dict[str, Any]:
    """Generate JSON and HTML reports for processed invoices."""

    extraction_results = [
        dict(item)
        for item in state.get("extraction_results", [])
    ]

    report_results: list[dict[str, Any]] = []
    monitor_errors = list(state.get("monitor_errors", []))

    for item in extraction_results:
        if item.get("status") != "extracted":
            continue

        invoice_id = item["invoice_id"]
        file_path = item["file_path"]

        validation_result = item.get("validation") or {}

        # If validation failed to execute, still generate a report
        # that clearly identifies the invoice as requiring review.
        if item.get("validation_execution_error"):
            validation_result = {
                "validation_status": "partial",
                "recommendation": "review",
                "missing_fields": [],
                "discrepancies": [],
                "validation_errors": [
                    (
                        "Validation execution failed: "
                        f"{item['validation_execution_error']}"
                    )
                ],
                "erp_data": {},
            }

        # Use a separate report copy. Never mutate the extracted invoice.
        report_invoice = dict(item.get("invoice") or {})

        erp_data = validation_result.get("erp_data") or {}
        erp_po = erp_data.get("purchase_order") or {}
        erp_vendor = erp_data.get("vendor") or {}

        po_vendor_id = erp_po.get("vendor_id")
        master_vendor_id = erp_vendor.get("vendor_id")

        # Display an ERP-resolved vendor ID only when both ERP records
        # agree. The invoice's own completeness requirement is checked
        # against the extracted vendor_name, not this ERP-resolved ID;
        # this only enriches the report for human readability.
        if (
            po_vendor_id
            and master_vendor_id
            and str(po_vendor_id).strip()
            == str(master_vendor_id).strip()
        ):
            report_invoice["vendor_id"] = master_vendor_id

        try:
            reporting_result = reporting_graph.invoke(
                {
                    "invoice_id": invoice_id,
                    "file_path": file_path,
                    "invoice": report_invoice,
                    "validation_result": validation_result,
                    "translation_confidence": item.get(
                        "translation_confidence"
                    ),
                    "source_language": item.get("source_language"),
                    "translated_text": item.get("translated_text"),
                    "erp_data": erp_data,
                }
            )

            report = reporting_result["report"]
            report_status = reporting_result.get(
                "report_status",
                "completed",
            )

            item["report"] = report
            item["report_status"] = report_status
            item["json_report_path"] = reporting_result.get(
                "json_report_path"
            )
            item["html_report_path"] = reporting_result.get(
                "html_report_path"
            )

            report_results.append(
                {
                    "invoice_id": invoice_id,
                    "file_path": file_path,
                    "report": report,
                    "json_report_path": reporting_result.get(
                        "json_report_path"
                    ),
                    "html_report_path": reporting_result.get(
                        "html_report_path"
                    ),
                    "status": report_status,
                }
            )

            logger.info(
                "Reports generated for invoice %s: status=%s",
                invoice_id,
                report_status,
            )

        except Exception as exc:
            logger.exception(
                "Report generation failed for invoice %s",
                invoice_id,
            )

            item["report_status"] = "failed"
            item["report_error"] = str(exc)

            report_results.append(
                {
                    "invoice_id": invoice_id,
                    "file_path": file_path,
                    "status": "failed",
                    "error": str(exc),
                }
            )

            monitor_errors.append(
                {
                    "file_path": file_path,
                    "error": f"Report generation failed: {exc}",
                }
            )

    return {
        "extraction_results": extraction_results,
        "report_results": report_results,
        "monitor_errors": monitor_errors,
    }


# ------------------------------------------------------------------
# Node 4b: Index processed invoice and report text into Qdrant
# ------------------------------------------------------------------

def index_invoices_node(
    state: InvoiceAuditState,
) -> dict[str, Any]:
    """Run the Indexing Agent for every reported invoice.

    Indexing failures never fail the overall workflow and are not
    added to ``monitor_errors`` (which drives workflow_status); the
    audit trail in PostgreSQL remains complete and authoritative even
    if the derived vector index could not be updated this run. Each
    failure is still recorded on its extraction result item and
    logged so it is visible for troubleshooting.
    """

    extraction_results = [
        dict(item)
        for item in state.get("extraction_results", [])
    ]

    for item in extraction_results:
        if item.get("status") != "extracted":
            continue

        invoice_id = item["invoice_id"]
        invoice = item.get("invoice") or {}

        try:
            index_result = indexing_graph.invoke(
                {
                    "invoice_id": invoice_id,
                    "raw_extracted_text": item.get("raw_extracted_text"),
                    "translated_text": item.get("translated_text"),
                    "source_language": item.get("source_language"),
                    "vendor_name": invoice.get("vendor_name"),
                    "report": item.get("report"),
                }
            )

            item["index_status"] = index_result.get("index_status")
            item["indexed_chunks"] = index_result.get("indexed_chunks", 0)

            if index_result.get("index_status") == "failed":
                item["index_error"] = index_result.get("index_error")
                logger.warning(
                    "RAG indexing failed for invoice %s: %s",
                    invoice_id,
                    index_result.get("index_error"),
                )

        except Exception as exc:
            logger.exception(
                "RAG indexing failed for invoice %s",
                invoice_id,
            )

            item["index_status"] = "failed"
            item["index_error"] = str(exc)

    return {
        "extraction_results": extraction_results,
    }


# ------------------------------------------------------------------
# Node 5: Summarize workflow
# ------------------------------------------------------------------

def determine_workflow_status(
    state: InvoiceAuditState,
) -> dict[str, Any]:
    """Summarize the complete parent workflow."""

    results = state.get("extraction_results", [])
    errors = state.get("monitor_errors", [])

    failed_count = sum(
        result.get("status") == "failed"
        for result in results
    )

    validation_failed_count = sum(
        result.get("validation_status") == "failed"
        for result in results
    )

    validation_partial_count = sum(
        result.get("validation_status") == "partial"
        for result in results
    )

    # No invoices were successfully processed.
    if not results and errors:
        status = "failed"

    # Processing, validation, or reporting execution errors exist.
    elif errors or failed_count:
        status = "partial" if results else "failed"

    # Invoices were processed but validation found problems.
    elif validation_failed_count:
        status = "partial"

    elif validation_partial_count:
        status = "partial"

    else:
        status = "completed"

    return {
        "workflow_status": status,
    }


# ------------------------------------------------------------------
# Build parent graph
# ------------------------------------------------------------------

def build_invoice_audit_graph():
    """Build the parent invoice auditing graph."""

    workflow = StateGraph(InvoiceAuditState)

    workflow.add_node(
        "monitor_invoices",
        monitor_invoices_node,
    )

    workflow.add_node(
        "process_invoices",
        process_invoices_node,
    )

    workflow.add_node(
        "validate_invoices",
        validate_invoices_node,
    )

    workflow.add_node(
        "report_invoices",
        report_invoices_node,
    )

    workflow.add_node(
        "index_invoices",
        index_invoices_node,
    )

    workflow.add_node(
        "summarize",
        determine_workflow_status,
    )

    # The Invoice Monitor Agent is always the first node.
    workflow.add_edge(START, "monitor_invoices")

    # Monitor -> extraction/translation/parsing -> validation.
    workflow.add_edge(
        "monitor_invoices",
        "process_invoices",
    )

    workflow.add_edge(
        "process_invoices",
        "validate_invoices",
    )

    # Validation results are persisted before report generation.
    workflow.add_edge(
        "validate_invoices",
        "report_invoices",
    )

    # Reports are generated and persisted before indexing them into
    # the RAG vector store, so Qdrant payloads always reflect the
    # latest validation outcome.
    workflow.add_edge(
        "report_invoices",
        "index_invoices",
    )

    workflow.add_edge(
        "index_invoices",
        "summarize",
    )

    workflow.add_edge(
        "summarize",
        END,
    )

    return workflow.compile()


invoice_audit_graph = build_invoice_audit_graph()
