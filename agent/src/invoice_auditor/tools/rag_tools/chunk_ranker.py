"""MCP adapter for ranking retrieved chunks and assembling context."""

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

    result = await to_thread.run_sync(augmentation_graph.invoke, {
        "question": question,
        "retrieved_chunks": retrieved_chunks,
    })
    return {
        "reranked_chunks": result.get("reranked_chunks", []),
        "assembled_context": result.get("assembled_context", ""),
    }
