"""Top-level LangGraph workflow for RAG-based invoice querying.

Per the problem statement (3.6.6), a user's question is first
classified as structured or unstructured. Structured questions
(counts, filters, aggregates) are answered directly from PostgreSQL
using safely-validated, LLM-generated SQL. Unstructured questions are
answered through retrieval -> augmentation -> generation, graded by
the Reflection Agent's RAG Triad score, retrying up to three times
when the score does not clear the configured threshold.

This workflow never re-runs OCR, re-extracts documents, or rereads
original invoice files; it only reads already-persisted text from
PostgreSQL (via the RAG agents) and the vector index.
"""

from __future__ import annotations
from sqlalchemy import inspect, text

from invoice_auditor.tools.sql_tools import (
    ALLOWED_TABLES,
    UnsafeSqlError,
    run_safe_select,
)
import json
import logging
import re
from typing import Any

from langchain_litellm import ChatLiteLLM
from langgraph.graph import END, START, StateGraph

from invoice_auditor.agents.rag_agents.augmentation_agent import (
    augmentation_graph,
)
from invoice_auditor.agents.rag_agents.generation_agent import (
    generation_graph,
)
from invoice_auditor.agents.rag_agents.prompts import build_system_prompt
from invoice_auditor.agents.rag_agents.reflection_agent import (
    reflection_graph,
)
from invoice_auditor.agents.rag_agents.retrieval_agent import (
    retrieval_graph,
)
from invoice_auditor.config import (
    AWS_REGION,
    BEDROCK_RAG_MODEL_ID,
    RAG_MAX_RETRIES,
)
from invoice_auditor.db.session import SessionLocal
from invoice_auditor.tools.sql_tools import UnsafeSqlError, run_safe_select
from invoice_auditor.workflows.input_guardrail import input_guardrail_graph
from invoice_auditor.workflows.state import RagQueryState

logger = logging.getLogger(__name__)


def _invoke_bedrock_json(
    model_id: str,
    system_prompt: str,
    user_prompt: str,
) -> dict[str, Any]:
    """Invoke a Bedrock Converse model and parse its JSON response."""
    model = ChatLiteLLM(
        model=f"bedrock/{model_id}",
        temperature=0.0,
        max_tokens=1024,
        model_kwargs={"aws_region_name": AWS_REGION},
    )
    response = model.invoke(
        [("system", system_prompt), ("human", user_prompt)]
    )
    content = response.content
    if isinstance(content, list):
        response_text = "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict)
        ).strip()
    else:
        response_text = str(content).strip()

    response_text = re.sub(
        r"^```(?:json)?\s*|\s*```$",
        "",
        response_text,
        flags=re.IGNORECASE,
    ).strip()

    result = json.loads(response_text)

    if not isinstance(result, dict):
        raise ValueError("Bedrock response must be a JSON object")

    return result


# ------------------------------------------------------------------
# Node 1: Classify the question
# ------------------------------------------------------------------

def classify_query_node(state: RagQueryState) -> dict[str, Any]:
    """Classify the question as structured or unstructured."""
    question = state.get("question") or ""

    # Questions about a numbered invoice's stored audit record are structured
    # unless they explicitly ask for document evidence or cause.
    has_invoice_reference = re.search(
        r"\b(?:invoice\s+(?:number\s+|no\.?\s*|#\s*)?)?"
        r"(?:INV[- ]?\d+|\d{3,})\b",
        question,
        flags=re.IGNORECASE,
    )
    requests_document_reasoning = re.search(
        r"\b(?:why|explain|evidence|wording|say|contain|written|document|text|"
        r"original\s+(?:invoice|document)|supporting\s+(?:document|evidence))\b",
        question,
        flags=re.IGNORECASE,
    )
    if has_invoice_reference and not requests_document_reasoning:
        return {"query_type": "structured"}

    try:
        result = _invoke_bedrock_json(
            model_id=BEDROCK_RAG_MODEL_ID,
            system_prompt=build_system_prompt("query_classifier"),
            user_prompt=question,
        )

        query_type = result.get("query_type")

        if query_type not in {"structured", "unstructured"}:
            query_type = "unstructured"

        return {"query_type": query_type}

    except Exception:
        logger.exception("Query classification failed; defaulting")
        # An open-ended retrieval answer is a safer default than
        # guessing at a SQL statement for an unclassified question.
        return {"query_type": "unstructured"}


def route_by_query_type(state: RagQueryState) -> str:
    return (
        "structured_path"
        if state.get("query_type") == "structured"
        else "retrieve"
    )


def input_guardrail_node(state: RagQueryState) -> dict[str, Any]:
    result = input_guardrail_graph.invoke(
        {"question": state.get("question") or ""}
    )
    return {
        "guardrail_safe": result.get("is_safe", False),
        "guardrail_error": result.get("guardrail_error"),
    }


def route_after_guardrail(state: RagQueryState) -> str:
    return "classify_query" if state.get("guardrail_safe") else "blocked"


def finalize_guardrail_node(state: RagQueryState) -> dict[str, Any]:
    error = state.get("guardrail_error")
    if error:
        logger.error(
            "Input guardrail could not assess the question: %s", error
        )
        answer = (
            "The safety check could not be completed. "
            "Please try again later."
        )
        error_code = "input_guardrail_unavailable"
    else:
        answer = (
            "I can help with invoice auditing questions, but I can't assist "
            "with harmful requests or attempts to bypass safeguards."
        )
        error_code = "input_blocked_by_guardrail"

    return {
        "answer": answer,
        "answer_source": "guardrail",
        "query_type": "blocked",
        "query_status": "failed",
        "query_error": error_code,
    }


# ------------------------------------------------------------------
# Structured path: text-to-SQL
# ------------------------------------------------------------------

def _get_live_schema(db: Any) -> str:
    """Return the real columns and types of allowlisted audit tables."""
    inspector = inspect(db.get_bind())
    schema_lines: list[str] = []

    for table_name in sorted(ALLOWED_TABLES):
        columns = inspector.get_columns(table_name, schema="audit")
        if not columns:
            continue

        schema_lines.append(f"Table audit.{table_name}:")
        for column in columns:
            schema_lines.append(
                f"  {column['name']} ({column['type']})"
            )

        primary_key = inspector.get_pk_constraint(
            table_name, schema="audit"
        ).get("constrained_columns") or []

        if primary_key:
            schema_lines.append(
                f"  Primary key: {', '.join(primary_key)}"
            )

        schema_lines.append("")

    if not schema_lines:
        raise RuntimeError("Could not discover the audit database schema.")

    return "\n".join(schema_lines)


def _resolve_invoice_reference(
    db: Any,
    question: str,
) -> dict[str, Any] | None:
    """Resolve a business invoice number without confusing it with a UUID."""
    match = re.search(
        r"\b(?:invoice\s+(?:number\s+|no\.?\s*|#\s*)?)?"
        r"(INV[- ]?\d+|\d{3,})\b",
        question,
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    reference = match.group(1) or match.group(0)
    reference = re.sub(
        r"^invoice\s+", "", reference, flags=re.IGNORECASE
    ).strip().upper().replace(" ", "-")

    candidates = [reference]
    if reference.isdigit():
        candidates.append(f"INV-{reference}")
    elif reference.startswith("INV-") and reference[4:].isdigit():
        candidates.append(reference[4:])

    candidates = list(dict.fromkeys(candidates))

    rows = db.execute(
        text(
            """
            SELECT invoice_id, invoice_number
            FROM audit.invoice_audit
            WHERE UPPER(invoice_number) IN (:ref1, :ref2)
            LIMIT 3
            """
        ),
        {
            "ref1": candidates[0],
            "ref2": candidates[-1],
        },
    ).mappings().all()

    if not rows:
        return {
            "found": False,
            "reference": reference,
        }

    distinct = {
        str(row["invoice_id"]): {
            "invoice_id": str(row["invoice_id"]),
            "invoice_number": row["invoice_number"],
        }
        for row in rows
    }

    if len(distinct) > 1:
        return {
            "found": False,
            "ambiguous": True,
            "reference": reference,
            "matches": list(distinct.values()),
        }

    return {"found": True, **next(iter(distinct.values()))}


def _generate_structured_sql(
    question: str,
    schema: str,
    invoice_reference: dict[str, Any] | None,
    previous_sql: str = "",
    previous_error: str = "",
) -> str:
    """Generate SQL with the live schema and optional repair feedback."""
    system_prompt = build_system_prompt("text_to_sql")

    user_prompt = json.dumps(
        {
            "question": question,
            "live_database_schema": schema,
            "resolved_invoice_reference": invoice_reference,
            "previous_sql_to_repair": previous_sql or None,
            "previous_execution_error": previous_error or None,
        },
        default=str,
    )

    result = _invoke_bedrock_json(
        model_id=BEDROCK_RAG_MODEL_ID,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )

    sql = result.get("sql")
    if not isinstance(sql, str) or not sql.strip():
        raise ValueError("The SQL model returned no valid SQL string.")

    return sql.strip()


def _format_sql_answer(
    question: str,
    rows: list[dict[str, Any]],
) -> str:
    """Format returned database facts without fabricating information."""
    if not rows:
        return "No matching invoice records were found."

    def label_for(key: str) -> str:
        return re.sub(r"\s+", " ", key.replace("_", " ")).strip().capitalize()

    def format_value(value: Any) -> str:
        if value is None:
            return "Not provided (null)"
        return str(value)

    def collection_item_label(key: str) -> str:
        return {
            "line items": "Line item",
            "discrepancies": "Discrepancy",
            "human feedback": "Feedback entry",
        }.get(key.lower(), "Item")

    def append_field(lines: list[str], key: str, value: Any, indent: int) -> None:
        prefix = " " * indent
        label = label_for(key)
        if isinstance(value, dict):
            lines.append(f"{prefix}- **{label}:**")
            for child_key, child_value in value.items():
                append_field(lines, str(child_key), child_value, indent + 2)
        elif isinstance(value, (list, tuple)):
            lines.append(f"{prefix}- **{label}:**")
            item_label = collection_item_label(label)
            for item_index, item in enumerate(value, start=1):
                if isinstance(item, dict):
                    lines.append(f"{prefix}  - **{item_label} {item_index}**")
                    for child_key, child_value in item.items():
                        append_field(lines, str(child_key), child_value, indent + 4)
                elif isinstance(item, (list, tuple)):
                    append_field(
                        lines, f"{item_label} {item_index}", item, indent + 2
                    )
                else:
                    lines.append(f"{prefix}  - {format_value(item)}")
        else:
            lines.append(f"{prefix}- **{label}:** {format_value(value)}")

    lines = [f"Question: {question}", f"Found {len(rows)} matching record(s)."]
    for row_index, row in enumerate(rows, start=1):
        lines.extend(["", f"### Result {row_index}"])
        for key, value in row.items():
            append_field(lines, str(key), value, 0)

    return "\n".join(lines)


def generate_and_run_sql_node(
    state: RagQueryState,
) -> dict[str, Any]:
    """Resolve the invoice, generate SQL, validate it, and execute it."""
    question = (state.get("question") or "").strip()

    if not question:
        return {
            "answer": "A question is required.",
            "answer_source": "sql",
            "query_status": "failed",
            "query_error": "empty_question",
            "generated_sql": "",
            "sql_rows": [],
        }

    last_sql = ""
    last_error = ""

    try:
        with SessionLocal() as db:
            schema = _get_live_schema(db)
            invoice_reference = _resolve_invoice_reference(db, question)

            if invoice_reference and invoice_reference.get("ambiguous"):
                matches = ", ".join(
                    str(item.get("invoice_number"))
                    for item in invoice_reference["matches"]
                )
                return {
                    "answer": (
                        "The invoice reference is ambiguous. "
                        f"Please specify one of these invoice numbers: {matches}."
                    ),
                    "answer_source": "sql",
                    "query_status": "failed",
                    "query_error": "ambiguous_invoice_reference",
                    "generated_sql": "",
                    "sql_rows": [],
                }

            if invoice_reference and not invoice_reference.get("found"):
                return {
                    "answer": (
                        "No invoice was found for reference "
                        f"{invoice_reference['reference']}."
                    ),
                    "answer_source": "sql",
                    "query_status": "completed",
                    "query_error": None,
                    "generated_sql": "",
                    "sql_rows": [],
                }

            # Initial attempt + one repair attempt. Unsafe SQL is never
            # retried by weakening or bypassing the validator.
            for attempt in range(2):
                sql = _generate_structured_sql(
                    question=question,
                    schema=schema,
                    invoice_reference=invoice_reference,
                    previous_sql=last_sql,
                    previous_error=last_error,
                )
                last_sql = sql

                try:
                    rows = run_safe_select(db, sql)

                    return {
                        "generated_sql": sql,
                        "sql_rows": rows,
                        "answer": _format_sql_answer(question, rows),
                        "answer_source": "sql",
                        "query_status": "completed",
                        "query_error": None,
                    }

                except UnsafeSqlError:
                    # Invalid or disallowed SQL is rejected, not repaired
                    # by retrying around the security policy.
                    raise

                except Exception as exc:
                    last_error = str(exc)
                    logger.warning(
                        "SQL attempt %s failed: %s",
                        attempt + 1,
                        last_error,
                    )

                    if attempt == 1:
                        raise

    except UnsafeSqlError as exc:
        logger.warning("SQL rejected by guardrails: %s", exc)
        return {
            "answer": (
                "The generated query did not pass the SQL safety checks. "
                "Please rephrase the question."
            ),
            "answer_source": "sql",
            "query_status": "failed",
            "query_error": "unsafe_sql_rejected",
            "generated_sql": "",
            "sql_rows": [],
        }

    except Exception as exc:
        logger.exception("Structured query failed")
        return {
            "answer": (
                "I could not retrieve the requested invoice data after "
                "a SQL repair attempt."
            ),
            "answer_source": "sql",
            "query_status": "failed",
            "query_error": str(exc),
            "generated_sql": last_sql,
            "sql_rows": [],
        }

# ------------------------------------------------------------------
# Unstructured path: retrieval -> augmentation -> generation -> reflection
# ------------------------------------------------------------------

def retrieve_node(state: RagQueryState) -> dict[str, Any]:
    result = retrieval_graph.invoke(
        {
            "question": state.get("question"),
            "invoice_id": state.get("invoice_id"),
        }
    )

    return {"retrieved_chunks": result.get("retrieved_chunks", [])}


def augment_node(state: RagQueryState) -> dict[str, Any]:
    result = augmentation_graph.invoke(
        {
            "question": state.get("question"),
            "retrieved_chunks": state.get("retrieved_chunks", []),
        }
    )

    return {
        "reranked_chunks": result.get("reranked_chunks", []),
        "assembled_context": result.get("assembled_context", ""),
    }


def generate_node(state: RagQueryState) -> dict[str, Any]:
    result = generation_graph.invoke(
        {
            "question": state.get("question"),
            "assembled_context": state.get("assembled_context", ""),
        }
    )

    return {
        "answer": result.get("answer", ""),
        "query_error": result.get("generation_error"),
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
        result = reflection_graph.invoke(
            {
                "question": state.get("question"),
                "assembled_context": state.get("assembled_context", ""),
                "answer": state.get("answer", ""),
            }
        )

        answer_relevance = float(result.get("answer_relevance", 0.0))
        groundedness = float(result.get("groundedness", 0.0))
        context_relevance = float(result.get("context_relevance", 0.0))

        scores = [answer_relevance, groundedness, context_relevance]
        if any(not 0.0 <= score <= 1.0 for score in scores):
            raise ValueError("Reflection returned a score outside 0..1.")

        average_score = sum(scores) / len(scores)
        passed = average_score > 0.7

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
        and state.get("average_score", 0.0) > 0.7
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
        and state.get("average_score", 0.0) > 0.7
    )

    if accepted:
        status = "completed"
        error = None
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
    }

# ------------------------------------------------------------------
# Build graph
# ------------------------------------------------------------------

def build_rag_query_graph():
    """Build the top-level RAG query workflow."""
    workflow = StateGraph(RagQueryState)

    workflow.add_node("classify_query", classify_query_node)
    workflow.add_node("input_guardrail", input_guardrail_node)
    workflow.add_node("finalize_guardrail", finalize_guardrail_node)
    workflow.add_node("structured_path", generate_and_run_sql_node)
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("augment", augment_node)
    workflow.add_node("generate", generate_node)
    workflow.add_node("reflect", reflect_node)
    workflow.add_node("finalize_unstructured", finalize_unstructured_node)
    workflow.add_node("prepare_retry", prepare_retry_node)
    workflow.add_edge(START, "input_guardrail")
    workflow.add_conditional_edges(
        "input_guardrail",
        route_after_guardrail,
        {
            "classify_query": "classify_query",
            "blocked": "finalize_guardrail",
        },
    )
    workflow.add_edge("finalize_guardrail", END)

    workflow.add_conditional_edges(
        "classify_query",
        route_by_query_type,
        {
            "structured_path": "structured_path",
            "retrieve": "retrieve",
        },
    )

    workflow.add_edge("structured_path", END)

    workflow.add_edge("retrieve", "augment")
    workflow.add_edge("augment", "generate")
    workflow.add_edge("generate", "reflect")

    
    workflow.add_conditional_edges(
        "reflect",
        route_after_reflection,
        {
            "accept": "finalize_unstructured",
            "retry": "prepare_retry",
            "reject": "finalize_unstructured",
        },
    )
    workflow.add_edge("prepare_retry", "retrieve")
    workflow.add_edge("finalize_unstructured", END)

    return workflow.compile()


rag_query_graph = build_rag_query_graph()
