"""Qdrant vector store and Bedrock embeddings for the RAG pipeline.

Qdrant is a derived index: every point stored here is rebuilt from
text already persisted in PostgreSQL (see 6.5 "Qdrant: Derived Vector
Index" in the problem statement). Losing this collection never loses
information; it only requires rechunking and re-embedding stored text.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from langchain_aws import BedrockEmbeddings
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from invoice_auditor.config import (
    AWS_REGION,
    BEDROCK_EMBEDDING_MODEL_ID,
    QDRANT_COLLECTION,
    QDRANT_URL,
)

logger = logging.getLogger(__name__)

# Dimensionality of the configured embedding model. Titan text
# embeddings (v1) produce 1536-dimension vectors.
EMBEDDING_DIMENSIONS = 1536

_embeddings = BedrockEmbeddings(
    model_id=BEDROCK_EMBEDDING_MODEL_ID,
    region_name=AWS_REGION,
)

_qdrant_client = QdrantClient(url=QDRANT_URL)


def embed_text(text: str) -> list[float]:
    """Embed one chunk of text through the configured Bedrock model."""
    if not text or not text.strip():
        raise ValueError("Cannot embed empty text")

    embedding = _embeddings.embed_query(text)
    if not embedding:
        raise ValueError(
            "Bedrock embedding response did not contain a vector"
        )

    return embedding


def ensure_collection() -> None:
    """Create the Qdrant collection if it does not already exist."""
    if _qdrant_client.collection_exists(QDRANT_COLLECTION):
        return

    _qdrant_client.create_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config=qmodels.VectorParams(
            size=EMBEDDING_DIMENSIONS,
            distance=qmodels.Distance.COSINE,
        ),
    )

    logger.info("Created Qdrant collection %s", QDRANT_COLLECTION)


def delete_invoice_points(invoice_id: str) -> None:
    """Remove every previously indexed chunk for one invoice.

    Called before re-indexing so that revalidation or re-processing
    never leaves stale chunks alongside the updated ones.
    """
    ensure_collection()

    _qdrant_client.delete(
        collection_name=QDRANT_COLLECTION,
        points_selector=qmodels.FilterSelector(
            filter=qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="invoice_id",
                        match=qmodels.MatchValue(value=invoice_id),
                    )
                ]
            )
        ),
    )


def upsert_chunks(
    invoice_id: str,
    source_type: str,
    language: str | None,
    vendor: str | None,
    chunks: list[str],
) -> int:
    """Embed and store chunks of invoice or report text.

    Returns the number of chunks written.
    """
    if not chunks:
        return 0

    ensure_collection()

    points = []

    for chunk_text in chunks:
        if not chunk_text or not chunk_text.strip():
            continue

        vector = embed_text(chunk_text)

        points.append(
            qmodels.PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={
                    "invoice_id": invoice_id,
                    "chunk_text": chunk_text,
                    "source_type": source_type,
                    "vendor": vendor,
                    "language": language,
                },
            )
        )

    if not points:
        return 0

    _qdrant_client.upsert(
        collection_name=QDRANT_COLLECTION,
        points=points,
    )

    return len(points)


def search(
    query_text: str,
    top_k: int,
    invoice_id: str | None = None,
) -> list[dict[str, Any]]:
    """Search the vector index for chunks relevant to a question."""
    ensure_collection()

    query_vector = embed_text(query_text)

    query_filter = None
    if invoice_id:
        query_filter = qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="invoice_id",
                    match=qmodels.MatchValue(value=invoice_id),
                )
            ]
        )

    results = _qdrant_client.query_points(
        collection_name=QDRANT_COLLECTION,
        query=query_vector,
        query_filter=query_filter,
        limit=top_k,
    ).points

    return [
        {
            "score": point.score,
            "invoice_id": point.payload.get("invoice_id"),
            "chunk_text": point.payload.get("chunk_text"),
            "source_type": point.payload.get("source_type"),
            "vendor": point.payload.get("vendor"),
            "language": point.payload.get("language"),
        }
        for point in results
    ]
