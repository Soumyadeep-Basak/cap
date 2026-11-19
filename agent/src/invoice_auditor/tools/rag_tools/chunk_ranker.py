"""MCP adapter for ranking retrieved chunks and assembling context."""
from invoice_auditor.agents.Invoice_RAG_Agent.pipeline.guardrails.rag_security import validate_query, validate_chunks, validate_context


from typing import Any

from anyio import to_thread


async def chunk_ranker(question: str, retrieved_chunks: list[dict[str, Any]]) -> dict:
    """Re-rank retrieved invoice chunks and assemble the context for generation.

    Args:
        question: The same question used for semantic retrieval.
        retrieved_chunks: Chunk objects returned by semantic_retriever, including
            chunk_text and available similarity and source metadata.

    Returns:
        Ranked chunks and assembled_context for the synthesizer and evaluator.
    """
    from invoice_auditor.agents.Invoice_RAG_Agent.pipeline.augmentation_agent import augmentation_graph

    validate_query(question)
    retrieved_chunks = validate_chunks(retrieved_chunks)
    result = await to_thread.run_sync(augmentation_graph.invoke, {
        "question": question,
        "retrieved_chunks": retrieved_chunks,
    })
    ranked = validate_chunks(result.get("reranked_chunks", []))
    sources = {str(c["invoice_id"]) for c in retrieved_chunks}
    if any(str(c["invoice_id"]) not in sources for c in ranked):
        raise ValueError("Ranker introduced an unretrieved source")
    if result.get("assembled_context"):
        validate_context(result["assembled_context"], source_ids=sources)
    return {
        "reranked_chunks": ranked,
        "assembled_context": result.get("assembled_context", ""),
    }
