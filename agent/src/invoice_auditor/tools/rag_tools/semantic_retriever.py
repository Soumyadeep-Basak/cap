"""MCP adapter for retrieving semantically relevant invoice evidence."""

from typing import Annotated
from uuid import UUID

from anyio import to_thread
from pydantic import Field


async def semantic_retriever(
    question: str,
    invoice_id: UUID | None = None,
    top_k: Annotated[int, Field(ge=1, le=20)] | None = None,
) -> dict:
    """Retrieve invoice evidence similar to a question from the Qdrant index.

    Use first in a RAG query, then pass the returned retrieved_chunks to chunk_ranker.

    Args:
        question: Natural-language search query.
        invoice_id: Optional invoice UUID to restrict the search to one audit record.
        top_k: Optional result limit from 1 to 20. Omission uses the configured default.

    Returns:
        Retrieved chunks with similarity and source metadata, and any retrieval error.
    """
    from invoice_auditor.agents.Invoice_RAG_Agent.pipeline.retrieval_agent import retrieval_graph

    result = await to_thread.run_sync(retrieval_graph.invoke, {
        "question": question,
        "invoice_id": str(invoice_id) if invoice_id else None,
        "top_k": top_k,
    })
    return {
        "retrieved_chunks": result.get("retrieved_chunks", []),
        "retrieval_error": result.get("retrieval_error"),
    }
