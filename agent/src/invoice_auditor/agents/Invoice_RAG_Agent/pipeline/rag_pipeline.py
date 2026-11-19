"""Client-side LangGraph nodes for the remote RAG tools."""

import logging
from statistics import mean
from typing import Any

from invoice_auditor.services.field_labels import format_line_references
from invoice_auditor.agents.Invoice_RAG_Agent.rag_agent_client import RagMcpError, call_rag_tool
from invoice_auditor.config import RAG_MAX_RETRIES, RAG_SCORE_THRESHOLD
from invoice_auditor.workflows.state import RagQueryState

logger = logging.getLogger(__name__)


def retrieve_node(state: RagQueryState) -> dict[str, Any]:
    try:
        result = call_rag_tool(
            "semantic_retriever",
            question=state.get("question", ""),
            invoice_id=state.get("invoice_id"),
        )
    except RagMcpError as exc:
        return {"retrieved_chunks": [], "query_error": str(exc)}
    return {
        "retrieved_chunks": result.get("retrieved_chunks", []),
        "query_error": "Invoice retrieval failed." if result.get("retrieval_error") else None,
    }


def augment_node(state: RagQueryState) -> dict[str, Any]:
    if state.get("query_error"):
        return {}
    try:
        return call_rag_tool(
            "chunk_ranker",
            question=state.get("question", ""),
            retrieved_chunks=state.get("retrieved_chunks", []),
        )
    except RagMcpError as exc:
        return {"query_error": str(exc)}


def generate_node(state: RagQueryState) -> dict[str, Any]:
    if state.get("query_error"):
        return {"answer": ""}
    if not state.get("assembled_context"):
        return {"answer": "", "query_error": "No invoice evidence was found."}
    try:
        result = call_rag_tool(
            "response_synthesizer",
            question=state.get("question", ""),
            assembled_context=state.get("assembled_context", ""),
            bypass_cache=bool(state.get("retry_count", 0)),
        )
    except RagMcpError as exc:
        return {"answer": "", "query_error": str(exc)}
    return {
        "answer": result.get("answer", ""),
        "query_error": "Answer generation failed." if result.get("generation_error") else None,
    }


def reflect_node(state: RagQueryState) -> dict[str, Any]:
    """Evaluate the answer; evaluation failures must never pass."""
    if not state.get("answer") or state.get("query_error"):
        return {
            "answer_relevance": 0.0,
            "groundedness": 0.0,
            "context_relevance": 0.0,
            "average_score": 0.0,
            "passed_reflection": False,
            "evaluation_status": "failed",
        }

    try:
        result = call_rag_tool(
            "rag_evaluator",
            question=state.get("question", ""),
            assembled_context=state.get("assembled_context", ""),
            answer=state["answer"],
        )
        if result.get("reflection_error"):
            raise RagMcpError("Answer evaluation failed.")

        answer_relevance = float(result.get("answer_relevance", 0.0))
        groundedness = float(result.get("groundedness", 0.0))
        context_relevance = float(result.get("context_relevance", 0.0))

        scores = [answer_relevance, groundedness, context_relevance]
        if any(not 0.0 <= score <= 1.0 for score in scores):
            raise ValueError("Reflection returned a score outside 0..1.")

        average_score = mean(scores)
        passed = average_score > RAG_SCORE_THRESHOLD

        return {
            "answer_relevance": answer_relevance,
            "groundedness": groundedness,
            "context_relevance": context_relevance,
            "average_score": average_score,
            "passed_reflection": passed,
            "evaluation_status": "completed",
        }

    except Exception:
        logger.exception("RAG reflection failed")
        return {
            "answer_relevance": 0.0,
            "groundedness": 0.0,
            "context_relevance": 0.0,
            "average_score": 0.0,
            "passed_reflection": False,
            "evaluation_status": "failed",
        }


def route_after_reflection(state: RagQueryState) -> str:
    """Accept only a passing evaluation; otherwise retry or reject."""
    if (
        state.get("evaluation_status") == "completed"
        and state.get("passed_reflection") is True
        and state.get("average_score", 0.0) > RAG_SCORE_THRESHOLD
    ):
        return "accept"

    if int(state.get("retry_count", 0)) < RAG_MAX_RETRIES:
        return "retry"

    return "reject"


def prepare_retry_node(state: RagQueryState) -> dict[str, Any]:
    """Increment the retry count once and clear the previous attempt."""
    return {
        "retry_count": int(state.get("retry_count", 0)) + 1,
        "retrieved_chunks": [],
        "reranked_chunks": [],
        "assembled_context": "",
        "answer": "",
        "query_error": None,
        "passed_reflection": False,
        "evaluation_status": "skipped",
        "answer_relevance": 0.0,
        "groundedness": 0.0,
        "context_relevance": 0.0,
        "average_score": 0.0,
    }


def finalize_unstructured_node(
    state: RagQueryState,
) -> dict[str, Any]:
    """Do not mark a failed or low-scoring answer as completed."""
    accepted = (
        state.get("evaluation_status") == "completed"
        and state.get("passed_reflection") is True
        and state.get("average_score", 0.0) > RAG_SCORE_THRESHOLD
    )

    if accepted:
        status = "completed"
        error = None
    elif state.get("query_error"):
        status = "failed"
        error = state["query_error"]
    elif state.get("evaluation_status") == "failed":
        status = "failed"
        error = "Evaluation failed; the answer was not accepted."
    else:
        status = "failed"
        error = (
            "The answer did not meet the acceptance threshold after "
            "the permitted retries."
        )

    return {
        "answer_source": "rag",
        "query_status": status,
        "query_error": error,
        "accepted": accepted,
        "retry_count": int(state.get("retry_count", 0)),
        "answer": (
            format_line_references(state.get("answer") or "") if accepted
            else "I could not verify an answer from the invoice evidence."
        ),
    }
