
"""LangGraph subgraph for multilingual invoice translation."""

import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any
from uuid import UUID

import boto3
import redis
from dotenv import load_dotenv
from langgraph.graph import END, START, StateGraph

from invoice_auditor.db.session import SessionLocal
from invoice_auditor.services.invoice_audit_service import (
    save_translation,
    save_translation_failure,
)
from invoice_auditor.workflows.state import InvoiceAuditState

PROJECT_ROOT = Path(__file__).resolve().parents[4]
load_dotenv(PROJECT_ROOT / ".env")

logger = logging.getLogger(__name__)

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
LANGUAGE_MODEL_ID = os.getenv(
    "BEDROCK_LANGUAGE_MODEL_ID",
    "amazon.nova-lite-v1:0",
)
TRANSLATION_MODEL_ID = os.getenv(
    "BEDROCK_TRANSLATION_MODEL_ID",
    "amazon.nova-lite-v1:0",
)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CACHE_TTL_SECONDS = 30 * 24 * 60 * 60

bedrock_client = boto3.client(
    "bedrock-runtime",
    region_name=AWS_REGION,
)

redis_client = redis.Redis.from_url(
    REDIS_URL,
    decode_responses=True,
)


def invoke_bedrock_json(
    model_id: str,
    system_prompt: str,
    user_prompt: str,
) -> dict[str, Any]:
    """Invoke a Bedrock Converse model and parse its JSON response."""
    response = bedrock_client.converse(
        modelId=model_id,
        system=[{"text": system_prompt}],
        messages=[
            {
                "role": "user",
                "content": [{"text": user_prompt}],
            }
        ],
        inferenceConfig={
            "temperature": 0.0,
            "maxTokens": 4096,
        },
    )

    content = response["output"]["message"]["content"]
    response_text = "".join(
        block["text"]
        for block in content
        if "text" in block
    ).strip()

    # Tolerate JSON enclosed in Markdown code fences.
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


def normalize_language_code(language: str) -> str:
    """Normalize common language names and codes."""
    normalized = language.strip().lower()

    aliases = {
        "english": "en",
        "spanish": "es",
        "german": "de",
        "french": "fr",
        "italian": "it",
        "portuguese": "pt",
        "chinese": "zh",
        "japanese": "ja",
        "korean": "ko",
        "dutch": "nl",
        "hindi": "hi",
        "en-us": "en",
        "en-gb": "en",
    }

    return aliases.get(normalized, normalized)


def build_cache_key(raw_text: str) -> str:
    """Build a cache key that changes with the models or source text."""
    content = (
        f"translation-v1|{LANGUAGE_MODEL_ID}|"
        f"{TRANSLATION_MODEL_ID}|{raw_text}"
    )
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return f"invoice-translation:{digest}"


def cache_lookup_node(
    state: InvoiceAuditState,
) -> dict[str, Any]:
    """Look up an existing translation without blocking on Redis failure."""
    raw_text = state.get("raw_extracted_text")

    if not raw_text or not raw_text.strip():
        return {
            "processing_error": "No extracted text was provided for translation",
            "translation_cache_hit": False,
        }

    cache_key = build_cache_key(raw_text)

    try:
        cached_value = redis_client.get(cache_key)

        if cached_value:
            cached = json.loads(cached_value)

            logger.info("Translation cache hit")

            return {
                "translation_cache_key": cache_key,
                "translation_cache_hit": True,
                "source_language": cached["source_language"],
                "translated_text": cached["translated_text"],
                "translation_confidence": float(
                    cached["translation_confidence"]
                ),
                "processing_error": None,
            }

    except (redis.RedisError, ValueError, KeyError, TypeError):
        logger.warning(
            "Translation cache lookup failed; continuing without cache",
            exc_info=True,
        )

    return {
        "translation_cache_key": cache_key,
        "translation_cache_hit": False,
        "processing_error": None,
    }


def detect_language_node(
    state: InvoiceAuditState,
) -> dict[str, Any]:
    """Detect the dominant language of the extracted invoice text."""
    try:
        result = invoke_bedrock_json(
            model_id=LANGUAGE_MODEL_ID,
            system_prompt=(
                "Identify the dominant language of the supplied invoice "
                "text. Return only a JSON object with a source_language "
                "field containing a lowercase ISO 639-1 language code "
                "(for example, en, es, de, fr). Use und if uncertain. "
                "Do not translate or summarize the text."
            ),
            user_prompt=state["raw_extracted_text"],
        )

        language = result.get("source_language")

        if not isinstance(language, str) or not language.strip():
            raise ValueError(
                "Bedrock did not return a source language"
            )

        language = normalize_language_code(language)

        if not re.fullmatch(r"[a-z]{2,3}", language):
            raise ValueError(
                f"Invalid detected language code: {language}"
            )

        return {
            "source_language": language,
            "processing_error": None,
        }

    except Exception as exc:
        logger.exception("Language detection failed")
        return {"processing_error": f"Language detection failed: {exc}"}


def use_original_english_node(
    state: InvoiceAuditState,
) -> dict[str, Any]:
    """Pass English text through without translating it."""
    return {
        "translated_text": state["raw_extracted_text"],
        "translation_confidence": 1.0,
        "processing_error": None,
    }


def translate_to_english_node(
    state: InvoiceAuditState,
) -> dict[str, Any]:
    """Translate non-English invoice text into English."""
    try:
        result = invoke_bedrock_json(
            model_id=TRANSLATION_MODEL_ID,
            system_prompt=(
                "Translate the supplied invoice text into English. "
                "Preserve all invoice numbers, PO references, SKU codes, "
                "dates, quantities, monetary amounts, currency symbols, "
                "table rows, and line breaks as faithfully as possible. "
                "Do not summarize, omit, invent, or calculate values. "
                "Return only a JSON object containing translated_text "
                "and confidence. confidence must be a numeric estimate "
                "from 0.0 to 1.0 reflecting translation reliability."
            ),
            user_prompt=(
                f"Detected source language: "
                f"{state['source_language']}\n\n"
                "Translate the following invoice text:\n\n"
                f"{state['raw_extracted_text']}"
            ),
        )

        translated_text = result.get("translated_text")
        confidence = result.get("confidence")

        if not isinstance(translated_text, str) or not translated_text.strip():
            raise ValueError("Bedrock returned empty translated text")

        if isinstance(confidence, bool) or not isinstance(
            confidence, (int, float)
        ):
            raise ValueError(
                "Bedrock did not return a numeric confidence score"
            )

        confidence = float(confidence)

        if not 0.0 <= confidence <= 1.0:
            raise ValueError(
                "Translation confidence must be between 0 and 1"
            )

        return {
            "translated_text": translated_text,
            "translation_confidence": confidence,
            "processing_error": None,
        }

    except Exception as exc:
        logger.exception("Invoice translation failed")
        return {"processing_error": f"Translation failed: {exc}"}


def cache_store_node(
    state: InvoiceAuditState,
) -> dict[str, Any]:
    """Cache successful translations for reuse."""
    cache_key = state.get("translation_cache_key")

    if not cache_key:
        return {}

    cache_value = {
        "source_language": state["source_language"],
        "translated_text": state["translated_text"],
        "translation_confidence": state["translation_confidence"],
    }

    try:
        redis_client.setex(
            cache_key,
            CACHE_TTL_SECONDS,
            json.dumps(cache_value, ensure_ascii=False),
        )
    except redis.RedisError:
        # Cache failure must not prevent durable database persistence.
        logger.warning(
            "Could not cache translation; continuing to PostgreSQL",
            exc_info=True,
        )

    return {}


def save_translation_node(
    state: InvoiceAuditState,
) -> dict[str, Any]:
    """Persist translation results for this invoice in PostgreSQL."""
    try:
        with SessionLocal() as db:
            save_translation(
                db=db,
                invoice_id=UUID(state["invoice_id"]),
                source_language=state["source_language"],
                translated_text=state["translated_text"],
                confidence=state["translation_confidence"],
            )

        return {
            "translation_status": "completed",
            "processing_error": None,
        }

    except Exception as exc:
        logger.exception("Could not save translation to PostgreSQL")
        return {
            "translation_status": "failed",
            "processing_error": f"Could not save translation: {exc}",
        }


def save_translation_failure_node(
    state: InvoiceAuditState,
) -> dict[str, Any]:
    """Record a translation failure against the audit record."""
    error_message = state.get(
        "processing_error",
        "Unknown translation error",
    )

    try:
        with SessionLocal() as db:
            save_translation_failure(
                db=db,
                invoice_id=UUID(state["invoice_id"]),
                error_message=error_message,
            )
    except Exception:
        logger.exception(
            "Could not persist translation failure to PostgreSQL"
        )

    return {"translation_status": "failed"}


def route_cache_result(state: InvoiceAuditState) -> str:
    """Choose the next node after cache lookup."""
    if state.get("processing_error"):
        return "failure"

    if state.get("translation_cache_hit"):
        return "save"

    return "detect"


def route_detected_language(state: InvoiceAuditState) -> str:
    """Choose pass-through, translation, or failure handling."""
    if state.get("processing_error"):
        return "failure"

    if state.get("source_language") == "en":
        return "english"

    return "translate"


def route_translation_result(state: InvoiceAuditState) -> str:
    """Continue only when translation succeeded."""
    if state.get("processing_error"):
        return "failure"

    return "cache"


def route_save_result(state: InvoiceAuditState) -> str:
    """Handle database persistence failures."""
    if state.get("translation_status") == "failed":
        return "failure"

    return "end"


def build_translation_graph():
    """Build the invoice translation LangGraph subgraph."""
    workflow = StateGraph(InvoiceAuditState)

    workflow.add_node("cache_lookup", cache_lookup_node)
    workflow.add_node("detect_language", detect_language_node)
    workflow.add_node("use_original_english", use_original_english_node)
    workflow.add_node("translate_to_english", translate_to_english_node)
    workflow.add_node("cache_store", cache_store_node)
    workflow.add_node("save_translation", save_translation_node)
    workflow.add_node(
        "save_translation_failure",
        save_translation_failure_node,
    )

    workflow.add_edge(START, "cache_lookup")

    workflow.add_conditional_edges(
        "cache_lookup",
        route_cache_result,
        {
            "failure": "save_translation_failure",
            "save": "save_translation",
            "detect": "detect_language",
        },
    )

    workflow.add_conditional_edges(
        "detect_language",
        route_detected_language,
        {
            "failure": "save_translation_failure",
            "english": "use_original_english",
            "translate": "translate_to_english",
        },
    )

    workflow.add_edge("use_original_english", "cache_store")

    workflow.add_conditional_edges(
        "translate_to_english",
        route_translation_result,
        {
            "failure": "save_translation_failure",
            "cache": "cache_store",
        },
    )

    workflow.add_edge("cache_store", "save_translation")

    workflow.add_conditional_edges(
        "save_translation",
        route_save_result,
        {
            "failure": "save_translation_failure",
            "end": END,
        },
    )

    workflow.add_edge("save_translation_failure", END)

    return workflow.compile()


translation_graph = build_translation_graph()
