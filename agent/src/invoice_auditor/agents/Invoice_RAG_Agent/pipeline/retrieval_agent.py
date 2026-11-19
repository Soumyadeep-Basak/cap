"""Retrieval Agent: fetch relevant chunks for a user's question.

Per the problem statement (3.6.2), this agent retrieves relevant
chunks for a question, supports filtering to a specific invoice, and
returns the retrieved content for downstream augmentation/generation.
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from invoice_auditor.config import RAG_TOP_K
from invoice_auditor.tools.rag_tools.rag_retriever import retrieve

logger = logging.getLogger(__name__)


class RetrievalState(TypedDict, total=False):
    """Inputs and outputs for the Retrieval Agent."""

    question: str
    invoice_id: str | None
    top_k: int

    retrieved_chunks: list[dict[str, Any]]
    retrieval_error: str | None


def retrieve_chunks_node(state: RetrievalState) -> dict[str, Any]:
    """Retrieve the most relevant chunks for the question."""
    question = state.get("question")

    if not question or not question.strip():
        return {
            "retrieved_chunks": [],
            "retrieval_error": "No question was provided",
        }

    top_k = state.get("top_k") or RAG_TOP_K

    try:
        chunks = retrieve(
            query=question,
            top_k=top_k,
            invoice_id=state.get("invoice_id"),
        )

        return {"retrieved_chunks": chunks}

    except Exception as exc:
        logger.exception("Retrieval failed for question: %s", question)

        return {
            "retrieved_chunks": [],
            "retrieval_error": str(exc),
        }


def build_retrieval_graph():
    """Build the Retrieval Agent subgraph."""
    workflow = StateGraph(RetrievalState)

    workflow.add_node("retrieve_chunks", retrieve_chunks_node)

    workflow.add_edge(START, "retrieve_chunks")
    workflow.add_edge("retrieve_chunks", END)

    return workflow.compile()


retrieval_graph = build_retrieval_graph()
