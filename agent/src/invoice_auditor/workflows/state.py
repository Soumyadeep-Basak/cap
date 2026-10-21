
"""Shared state for the invoice auditing LangGraph workflow."""

from typing import Any, Literal

from typing_extensions import TypedDict


class InvoiceAuditState(TypedDict, total=False):
    """Data passed between invoice auditing workflow nodes."""

    # Monitor input and file tracking
    incoming_dir: str
    file_path: str
    file_name: str
    file_type: str
    file_checksum: str | None
    supported: bool
    invoice_id: str
    duplicate_files: list[str]
    workflow_status: Literal["completed", "partial", "failed"]

    discovered_files: list[dict[str, Any]]
    pending_invoices: list[dict[str, Any]]
    monitor_errors: list[dict[str, str]]
    routed_invoices: list[dict[str, Any]]
    extraction_route: str

    # Extraction
    extraction_method: str | None
    raw_extracted_text: str | None
    invoice: dict[str, Any] | None
    processing_error: str | None
    extraction_results: list[dict[str, Any]]

    # Translation
    source_language: str | None
    translated_text: str | None
    translation_confidence: float | None
    translation_cache_key: str | None
    translation_cache_hit: bool
    translation_status: Literal["completed", "failed"]

    # Validation
    missing_fields: list[str]
    validation_errors: list[str]
    discrepancies: list[dict[str, Any]]
    validation_results: list[dict[str, Any]]
    business_validation_passed: bool
    
    business_validation_status: Literal[
        "passed",
        "failed",
        "partial",
    ]

    business_recommendation: Literal[
        "approve",
        "review",
        "reject",
    ]
    
    # ERP validation results
    erp_data: dict[str, Any]

    # Final outcome
    validation_status: Literal[
        "pending", "passed", "failed", "partial"
    ]
    recommendation: Literal["approve", "review", "reject"] | None
    report: dict[str, Any] | None

    # Workflow tracking
    thread_id: str | None
    error: str | None

    report_results: list[dict[str, Any]]


class RagQueryState(TypedDict, total=False):
    """Data passed between nodes of the RAG query workflow."""

    # Input
    question: str
    invoice_id: str | None

    # Query classification
    query_type: Literal["structured", "unstructured"]

    # Structured (text-to-SQL) path
    generated_sql: str | None
    sql_rows: list[dict[str, Any]]
    sql_error: str | None
    # Structured-query output and diagnostic
    query_error: str | None
    resolved_invoice: dict[str, Any] | None

    # RAG evaluation and final acceptance
    evaluation_status: Literal["completed", "failed", "skipped"]
    accepted: bool
    generation_failed: bool
    # Unstructured (retrieval-augmented) path
    retrieved_chunks: list[dict[str, Any]]
    reranked_chunks: list[dict[str, Any]]
    assembled_context: str
    retry_count: int

    # Reflection (RAG Triad)
    answer_relevance: float
    groundedness: float
    context_relevance: float
    average_score: float
    passed_reflection: bool

    # Output
    answer: str
    answer_source: Literal["sql", "rag", "cache"]
    query_status: Literal["completed", "failed"]
    query_error: str | None