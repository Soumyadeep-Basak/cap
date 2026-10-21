"""API endpoint for RAG-based and structured invoice querying."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from invoice_auditor.workflows import rag_workflow

router = APIRouter(
    prefix="/api/v1/query",
    tags=["RAG Querying"],
)


class QueryRequest(BaseModel):
    """A natural-language question about processed invoices."""

    question: str = Field(description="The auditor's question.")
    invoice_id: str | None = Field(
        default=None,
        description="Optional invoice ID to scope an open-ended question to.",
    )


@router.post("")
def query_invoices(request: QueryRequest) -> dict[str, Any]:
    """Answer a structured or open-ended question about invoices."""
    try:
        result = rag_workflow.rag_query_graph.invoke(
            {
                "question": request.question,
                "invoice_id": request.invoice_id,
            },
            config={"configurable": {"thread_id": str(uuid4())}},
        )

        return {
            "answer": result.get("answer"),
            "answer_source": result.get("answer_source"),
            "query_type": result.get("query_type"),
            "status": result.get("query_status"),
            "average_score": result.get("average_score"),
            "retry_count": result.get("retry_count"),
            "error": result.get("query_error"),
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Query failed: {exc}",
        ) from exc
