"""Augmentation Agent: rerank and assemble retrieved context.

Per the problem statement (3.6.3), this agent reranks and assembles
the retrieved chunks before they are handed to the Generation Agent.

Bedrock's Cohere rerank model is not available in every deployment's
AWS account, so reranking is done in-process with a lightweight
heuristic: the vector similarity score blended with a lexical
token-overlap bonus between the question and each chunk. This avoids
an extra network call and keeps the pipeline usable even where a
dedicated rerank model is not provisioned.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

logger = logging.getLogger(__name__)

# Maximum combined context length (characters) handed to the
# Generation Agent, to keep prompts within model context limits.
MAX_CONTEXT_CHARS = 6000

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def _rerank_score(question_tokens: set[str], chunk: dict[str, Any]) -> float:
    """Blend vector similarity with lexical overlap."""
    vector_score = float(chunk.get("score") or 0.0)

    chunk_tokens = _tokenize(chunk.get("chunk_text") or "")
    if not question_tokens or not chunk_tokens:
        overlap_bonus = 0.0
    else:
        overlap = len(question_tokens & chunk_tokens)
        overlap_bonus = overlap / len(question_tokens)

    # Weighted blend: vector similarity dominates, lexical overlap
    # breaks ties and rewards exact keyword/number matches (invoice
    # numbers, amounts) that embeddings alone can under-weight.
    return (0.75 * vector_score) + (0.25 * overlap_bonus)


class AugmentationState(TypedDict, total=False):
    """Inputs and outputs for the Augmentation Agent."""

    question: str
    retrieved_chunks: list[dict[str, Any]]

    reranked_chunks: list[dict[str, Any]]
    assembled_context: str


def rerank_node(state: AugmentationState) -> dict[str, Any]:
    """Rerank retrieved chunks using the blended heuristic score."""
    chunks = state.get("retrieved_chunks") or []
    question = state.get("question") or ""

    if not chunks:
        return {"reranked_chunks": []}

    question_tokens = _tokenize(question)

    reranked = sorted(
        chunks,
        key=lambda chunk: _rerank_score(question_tokens, chunk),
        reverse=True,
    )

    return {"reranked_chunks": reranked}


def assemble_context_node(state: AugmentationState) -> dict[str, Any]:
    """Assemble reranked chunks into one context string within budget."""
    chunks = state.get("reranked_chunks") or []

    sections: list[str] = []
    total_chars = 0

    for chunk in chunks:
        invoice_id = chunk.get("invoice_id", "unknown")
        source_type = chunk.get("source_type", "unknown")
        text = (chunk.get("chunk_text") or "").strip()

        if not text:
            continue

        section = (
            f"[invoice_id={invoice_id} source={source_type}]\n{text}"
        )

        if total_chars + len(section) > MAX_CONTEXT_CHARS and sections:
            break

        sections.append(section)
        total_chars += len(section)

    return {"assembled_context": "\n\n".join(sections)}


def build_augmentation_graph():
    """Build the Augmentation Agent subgraph."""
    workflow = StateGraph(AugmentationState)

    workflow.add_node("rerank", rerank_node)
    workflow.add_node("assemble_context", assemble_context_node)

    workflow.add_edge(START, "rerank")
    workflow.add_edge("rerank", "assemble_context")
    workflow.add_edge("assemble_context", END)

    return workflow.compile()


augmentation_graph = build_augmentation_graph()
