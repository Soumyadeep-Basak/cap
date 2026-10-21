"""Generation Agent: produce a grounded natural-language answer.

Per the problem statement (3.6.4 and 3.6.7), this agent uses LiteLLM
to generate an answer from the assembled context, and caches responses
in Redis so repeated questions reuse an existing result instead of
making an unnecessary model call.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import redis
from langchain_litellm import ChatLiteLLM
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from invoice_auditor.agents.rag_agents.prompts import build_system_prompt
from invoice_auditor.config import (
    AWS_REGION,
    BEDROCK_RAG_MODEL_ID,
    LLM_CACHE_TTL_SECONDS,
    REDIS_URL,
)

logger = logging.getLogger(__name__)

redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)


def _cache_key(question: str, context: str) -> str:
    """Build a cache key that changes with the model, question, or context."""
    content = f"rag-generation-v3|{BEDROCK_RAG_MODEL_ID}|{question}|{context}"
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return f"llm:{digest}"


class GenerationState(TypedDict, total=False):
    """Inputs and outputs for the Generation Agent."""

    question: str
    assembled_context: str

    answer: str
    generation_cache_hit: bool
    generation_error: str | None


def generate_answer_node(state: GenerationState) -> dict[str, Any]:
    """Generate an answer grounded in the assembled context."""
    question = state.get("question") or ""
    context = state.get("assembled_context") or ""

    if not question.strip():
        return {
            "answer": "",
            "generation_cache_hit": False,
            "generation_error": "No question was provided",
        }

    cache_key = _cache_key(question, context)

    try:
        cached = redis_client.get(cache_key)
        if cached:
            return {"answer": cached, "generation_cache_hit": True}
    except Exception:
        logger.warning(
            "Redis cache lookup failed; continuing without cache",
            exc_info=True,
        )

    system_prompt = build_system_prompt("rag_generation")

    if context.strip():
        user_prompt = (
            f"Context:\n{context}\n\nQuestion: {question}"
        )
    else:
        user_prompt = (
            "No relevant context was retrieved.\n\n"
            f"Question: {question}"
        )

    try:
        model = ChatLiteLLM(
            model=f"bedrock/{BEDROCK_RAG_MODEL_ID}",
            temperature=0.0,
            max_tokens=1024,
            model_kwargs={"aws_region_name": AWS_REGION},
        )

        response = model.invoke(
            [("system", system_prompt), ("human", user_prompt)]
        )
        content = response.content
        if isinstance(content, list):
            answer = "".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict)
            ).strip()
        else:
            answer = str(content).strip()

        try:
            redis_client.set(cache_key, answer, ex=LLM_CACHE_TTL_SECONDS)
        except Exception:
            logger.warning(
                "Failed to write generation result to cache",
                exc_info=True,
            )

        return {"answer": answer, "generation_cache_hit": False}

    except Exception as exc:
        logger.exception("Answer generation failed")

        return {
            "answer": "",
            "generation_cache_hit": False,
            "generation_error": str(exc),
        }


def build_generation_graph():
    """Build the Generation Agent subgraph."""
    workflow = StateGraph(GenerationState)

    workflow.add_node("generate_answer", generate_answer_node)

    workflow.add_edge(START, "generate_answer")
    workflow.add_edge("generate_answer", END)

    return workflow.compile()


generation_graph = build_generation_graph()
