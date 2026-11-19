"""RAG evidence, provenance and acceptance checks; no new agent framework."""
import math
import re
from statistics import mean
from uuid import UUID
from invoice_auditor.security.content import GuardrailError, validate_text, validate_document

_TERMS = re.compile(r"\b(?:invoices?|audit(?:ing)?|vendors?|suppliers?|payments?|paid|unpaid|purchase|orders?|po|sku|tax(?:es)?|vat|totals?|subtotal|amounts?|currency|freight|shipping|discrepanc(?:y|ies)|line\s+items?|prices?|costs?|quantity|quantities|documents?|receipts?|bills?)\b", re.I)
_SOURCE = re.compile(r"invoice_id\s*=\s*([0-9a-fA-F-]{36})")
_UUID = re.compile(r"\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b")

def validate_query(question, invoice_id=None):
    question = validate_text(question)
    if invoice_id is not None:
        try:
            UUID(str(invoice_id))
        except (TypeError, ValueError) as exc:
            raise GuardrailError("Invalid invoice identifier") from exc
    if not _TERMS.search(question):
        raise GuardrailError("Question must concern invoice auditing")
    return question

def validate_chunks(chunks, invoice_id=None):
    if not isinstance(chunks, list) or len(chunks) > 100:
        raise GuardrailError("Invalid evidence list")
    checked = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            raise GuardrailError("Evidence must be an object")
        try:
            source = str(UUID(str(chunk["invoice_id"])))
        except (KeyError, TypeError, ValueError) as exc:
            raise GuardrailError("Evidence requires an invoice source") from exc
        if invoice_id is not None and source != str(UUID(str(invoice_id))):
            raise GuardrailError("Evidence belongs to a different invoice")
        text = chunk.get("chunk_text")
        if not text:
            continue
        validate_document(text)
        if chunk.get("score") is not None:
            try:
                score = float(chunk["score"])
            except (TypeError, ValueError) as exc:
                raise GuardrailError("Invalid retrieval score") from exc
            if not math.isfinite(score) or score < 0.15:
                continue
        checked.append(chunk)
    if sum(len(c["chunk_text"]) for c in checked) > 200_000:
        raise GuardrailError("Evidence exceeds the context budget")
    return checked

def context_sources(context):
    validate_document(context)
    try:
        sources = {str(UUID(value)) for value in _SOURCE.findall(context)}
    except ValueError as exc:
        raise GuardrailError("Malformed context identifier") from exc
    if len(context) > 8000 or not sources:
        raise GuardrailError("Context requires bounded identified invoice evidence")
    return sources

def validate_context(context, *, invoice_id=None, source_ids=None):
    sources = context_sources(context)
    if invoice_id is not None and sources != {str(UUID(str(invoice_id)))}:
        raise GuardrailError("Context belongs to a different invoice")
    if source_ids is not None and not sources <= set(source_ids):
        raise GuardrailError("Context includes an unretrieved invoice source")
    return context

def validate_citations(answer, context):
    validate_document(answer)
    sources = context_sources(context)
    cited = {str(UUID(value)) for value in _UUID.findall(answer)}
    if not cited or not cited <= sources:
        raise GuardrailError("Answer must cite identified invoice evidence")
    return answer

def triad_score(values):
    if len(values) != 3 or any(isinstance(v, bool) or v is None for v in values):
        raise ValueError("RAG requires three numeric scores")
    values = [float(v) for v in values]
    if any(not math.isfinite(v) or not 0 <= v <= 1 for v in values):
        raise ValueError("RAG scores must be finite and between zero and one")
    return mean(values)

def retry_limit(configured):
    return min(3, max(0, int(configured)))

def is_accepted(state, threshold=0.7):
    try:
        score = triad_score([state.get(k) for k in ("answer_relevance", "groundedness", "context_relevance")])
        return (state.get("evaluation_status") == "completed"
                and state.get("passed_reflection") is True
                and score > max(0.7, threshold)
                and math.isclose(score, float(state.get("average_score", 0)), abs_tol=1e-9))
    except (ValueError, TypeError, OverflowError):
        return False
