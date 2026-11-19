"""Human-readable labels for invoice line references in display text."""

import re

_LINE_FIELD = re.compile(r"\bline_items\[(\d+)\](?:\.([a-z_][a-z_0-9]*))?", re.IGNORECASE)


def format_line_references(text: str) -> str:
    def label(match: re.Match[str]) -> str:
        index, field = match.groups()
        line = f"Line item {int(index) + 1}"
        return f"{line} · {field.replace('_', ' ').capitalize()}" if field else line

    return _LINE_FIELD.sub(label, text)
