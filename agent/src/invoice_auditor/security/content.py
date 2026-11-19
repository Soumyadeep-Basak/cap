"""Bound untrusted text and reject explicit instruction attacks."""
import re
import unicodedata

class GuardrailError(ValueError):
    """Untrusted content failed a security check."""

_ATTACK = re.compile(
    r"ignore\s+(?:all\s+)?(?:previous|prior|above|system)\s+instructions"
    r"|(?:reveal|show|print)\s+(?:the\s+)?(?:system\s+prompt|api\s+key|password)"
    r"|(?:bypass|disable|override)\s+(?:the\s+)?(?:guardrails?|safeguards?|security)"
    r"|<\|(?:system|im_start|im_end)\|>|\[INST\]|</?script\b", re.I)

def validate_text(value, *, max_chars=4000):
    if not isinstance(value, str) or not value.strip() or len(value) > max_chars:
        raise GuardrailError("Text is empty, malformed or too long")
    text = unicodedata.normalize("NFKC", value)
    text = "".join(c for c in text if unicodedata.category(c) != "Cf")
    if not text.strip() or len(text) > max_chars:
        raise GuardrailError("Normalized text is empty or too long")
    if any(ord(c) < 32 and c not in "\n\r\t" for c in text) or _ATTACK.search(text):
        raise GuardrailError("Unsafe instructions or control characters in input")
    return text.strip()

def validate_document(value):
    return validate_text(value, max_chars=200_000)
