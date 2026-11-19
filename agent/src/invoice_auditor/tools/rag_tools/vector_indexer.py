"""MCP adapter for indexing invoice evidence in Qdrant."""

from typing import Any
from uuid import UUID

from anyio import to_thread


async def vector_indexer(invoice_id: UUID, source: dict[str, Any] | None = None) -> dict:
    """Index invoice evidence as searchable vectors in Qdrant.

    Use after a report is generated or refreshed. The tool replaces prior
    vectors for this invoice and loads missing evidence from PostgreSQL.

    Args:
        invoice_id: UUID of the invoice audit record.
        source: Optional raw_extracted_text, translated_text, source_language,
            vendor_name, and report values to use during indexing.

    Returns:
        Index status, the number of indexed chunks, and any indexing error.
    """
    from invoice_auditor.agents.Invoice_RAG_Agent.pipeline.indexing_agent import indexing_graph

    fields = ("raw_extracted_text", "translated_text", "source_language", "vendor_name", "report")
    state = {key: source[key] for key in fields if source and key in source}
    result = await to_thread.run_sync(indexing_graph.invoke, {**state, "invoice_id": str(invoice_id)})
    return {
        "index_status": result.get("index_status"),
        "indexed_chunks": result.get("indexed_chunks", 0),
        "index_error": result.get("index_error"),
    }
