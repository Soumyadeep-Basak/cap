"""Chunking and high-level retrieve/index helpers for the RAG pipeline.

These wrap the low-level Qdrant/embedding primitives in
``vector_store`` with the text-splitting logic shared by the
Indexing and Retrieval agents.
"""

from __future__ import annotations

from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter

from invoice_auditor.config import RAG_TOP_K
from invoice_auditor.tools.rag_tools import vector_store

# Chunk size/overlap chosen for invoice and report text, which is
# short and line-oriented rather than long-form prose.
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", ". ", " ", ""],
)


def chunk_text(text: str) -> list[str]:
    """Split raw text into overlapping chunks suitable for embedding."""
    if not text or not text.strip():
        return []

    return _splitter.split_text(text)


def index_text(
    invoice_id: str,
    source_type: str,
    text: str,
    language: str | None = None,
    vendor: str | None = None,
) -> int:
    """Chunk, embed, and store one piece of invoice-related text.

    ``source_type`` distinguishes the origin of the text, e.g.
    "raw_text", "translated_text", or "report".
    """
    chunks = chunk_text(text)

    return vector_store.upsert_chunks(
        invoice_id=invoice_id,
        source_type=source_type,
        language=language,
        vendor=vendor,
        chunks=chunks,
    )


def reindex_invoice(invoice_id: str) -> None:
    """Drop any previously indexed chunks for an invoice.

    Called before re-indexing (e.g. after revalidation) so the
    collection never ends up with stale alongside fresh chunks.
    """
    vector_store.delete_invoice_points(invoice_id)


def retrieve(
    query: str,
    top_k: int = RAG_TOP_K,
    invoice_id: str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve the top-k most relevant chunks for a question."""
    return vector_store.search(
        query_text=query,
        top_k=top_k,
        invoice_id=invoice_id,
    )
