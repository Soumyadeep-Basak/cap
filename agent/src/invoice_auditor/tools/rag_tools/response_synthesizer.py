"""MCP adapter for generating an answer from ranked RAG evidence."""
from invoice_auditor.agents.Invoice_RAG_Agent.pipeline.guardrails.rag_security import validate_query, validate_context
from invoice_auditor.security.content import validate_document


from anyio import to_thread


async def response_synthesizer(question: str, assembled_context: str, bypass_cache: bool = False) -> dict:
    """Generate a draft answer grounded in the assembled invoice evidence.

    Pass the answer and the same context to rag_evaluator before returning an
    answer to the user.

    Args:
        question: Original invoice question.
        assembled_context: Context returned by chunk_ranker.
        bypass_cache: Set to true on a retry to skip reading a cached answer.

    Returns:
        Draft answer and any generation error.
    """
    from invoice_auditor.agents.Invoice_RAG_Agent.pipeline.generation_agent import generation_graph

    validate_query(question)
    validate_context(assembled_context)
    result = await to_thread.run_sync(generation_graph.invoke, {
        "question": question,
        "assembled_context": assembled_context,
        "bypass_cache": bypass_cache,
    })
    if result.get("answer"):
        validate_document(result["answer"])
    return {
        "answer": result.get("answer", ""),
        "generation_error": result.get("generation_error"),
    }
