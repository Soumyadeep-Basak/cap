"""MCP adapter for scoring a generated answer using the RAG Triad."""

from anyio import to_thread


async def rag_evaluator(question: str, assembled_context: str, answer: str) -> dict:
    """Score an invoice answer against its question and supporting context.

    Use after synthesis. Scores cover answer relevance, context relevance,
    and groundedness. The calling workflow decides whether to accept or retry.

    Args:
        question: Original invoice question.
        assembled_context: The same context supplied to response_synthesizer.
        answer: Draft answer to evaluate.

    Returns:
        The three evaluation scores and any reflection error.
    """
    from invoice_auditor.agents.Invoice_RAG_Agent.pipeline.reflection_agent import reflection_graph

    result = await to_thread.run_sync(reflection_graph.invoke, {
        "question": question,
        "assembled_context": assembled_context,
        "answer": answer,
    })
    return {
        "answer_relevance": result.get("answer_relevance"),
        "groundedness": result.get("groundedness"),
        "context_relevance": result.get("context_relevance"),
        "reflection_error": result.get("reflection_error"),
    }
