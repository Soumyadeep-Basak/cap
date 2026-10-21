"""Reflection Agent: score a generated answer using the RAG Triad.

Per the problem statement (3.6.5), this agent evaluates the generated
answer on three dimensions — answer relevance, groundedness, and
context relevance — and averages the scores. If the average exceeds
0.7 the answer may be shown to the user; otherwise the caller should
retrieve again and regenerate, up to three retries total.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import boto3
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from invoice_auditor.agents.rag_agents.prompts import build_system_prompt
from invoice_auditor.config import (
    AWS_REGION,
    BEDROCK_RAG_MODEL_ID,
    RAG_SCORE_THRESHOLD,
)

logger = logging.getLogger(__name__)

bedrock_client = boto3.client("bedrock-runtime", region_name=AWS_REGION)


class ReflectionState(TypedDict, total=False):
    """Inputs and outputs for the Reflection Agent."""

    question: str
    assembled_context: str
    answer: str

    answer_relevance: float
    groundedness: float
    context_relevance: float
    average_score: float
    passed_reflection: bool
    reflection_error: str | None


def _parse_score(value: Any) -> float:
    """Clamp a judged score into the valid 0.0-1.0 range."""
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0

    return max(0.0, min(1.0, score))


def score_answer_node(state: ReflectionState) -> dict[str, Any]:
    """Score the generated answer against the RAG Triad."""
    question = state.get("question") or ""
    context = state.get("assembled_context") or ""
    answer = state.get("answer") or ""

    if not answer.strip():
        return {
            "answer_relevance": 0.0,
            "groundedness": 0.0,
            "context_relevance": 0.0,
            "average_score": 0.0,
            "passed_reflection": False,
            "reflection_error": "No answer was generated to evaluate",
        }

    system_prompt = build_system_prompt("rag_reflection")

    user_prompt = (
        f"Question: {question}\n\n"
        f"Context:\n{context}\n\n"
        f"Answer:\n{answer}"
    )

    try:
        response = bedrock_client.converse(
            modelId=BEDROCK_RAG_MODEL_ID,
            system=[{"text": system_prompt}],
            messages=[
                {"role": "user", "content": [{"text": user_prompt}]}
            ],
            inferenceConfig={"temperature": 0.0, "maxTokens": 512},
        )

        content = response["output"]["message"]["content"]
        response_text = "".join(
            block["text"] for block in content if "text" in block
        ).strip()

        response_text = re.sub(
            r"^```(?:json)?\s*|\s*```$",
            "",
            response_text,
            flags=re.IGNORECASE,
        ).strip()

        scores = json.loads(response_text)

        answer_relevance = _parse_score(scores.get("answer_relevance"))
        groundedness = _parse_score(scores.get("groundedness"))
        context_relevance = _parse_score(scores.get("context_relevance"))

        average_score = (
            answer_relevance + groundedness + context_relevance
        ) / 3

        return {
            "answer_relevance": answer_relevance,
            "groundedness": groundedness,
            "context_relevance": context_relevance,
            "average_score": average_score,
            "passed_reflection": average_score > RAG_SCORE_THRESHOLD,
            "reflection_error": None,
        }

    except Exception as exc:
        logger.exception("Reflection scoring failed")

        return {
            "answer_relevance": 0.0,
            "groundedness": 0.0,
            "context_relevance": 0.0,
            "average_score": 0.0,
            "passed_reflection": False,
            "reflection_error": str(exc),
        }


def build_reflection_graph():
    """Build the Reflection Agent subgraph."""
    workflow = StateGraph(ReflectionState)

    workflow.add_node("score_answer", score_answer_node)

    workflow.add_edge(START, "score_answer")
    workflow.add_edge("score_answer", END)

    return workflow.compile()


reflection_graph = build_reflection_graph()
