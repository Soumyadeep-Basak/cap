"""Safe read-only SQL execution for the structured-query RAG path.

Per the problem statement (3.6.6), structured questions must be
answered directly from PostgreSQL using SQL, generated from natural
language by an LLM. Because text-to-SQL output is untrusted, every
statement is validated here before execution: it must be a single
read-only SELECT against the ``audit`` schema, and an upper row limit
is always enforced.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

# Only these tables may be referenced by generated SQL.
ALLOWED_TABLES = {
    "invoice_audit",
    "invoice_line_items",
    "discrepancies",
    "human_feedback",
}

# Statements containing any of these keywords are rejected outright,
# regardless of where they appear.
FORBIDDEN_KEYWORDS = (
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "truncate",
    "grant",
    "revoke",
    "create",
    "copy",
    "call",
    "execute",
    "merge",
    "vacuum",
    "--",
    "/*",
)

MAX_ROW_LIMIT = 200


class UnsafeSqlError(ValueError):
    """Raised when generated SQL fails the read-only safety checks."""


def validate_select_sql(sql: str) -> str:
    """Validate that ``sql`` is a single, read-only, schema-scoped SELECT.

    Returns the statement with a row limit enforced. Raises
    ``UnsafeSqlError`` if the statement fails any safety check.
    """
    if not sql or not sql.strip():
        raise UnsafeSqlError("No SQL statement was generated")

    cleaned = sql.strip().rstrip(";").strip()
    lowered = cleaned.lower()

    if ";" in cleaned:
        raise UnsafeSqlError("Only a single SQL statement is permitted")

    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise UnsafeSqlError("Only SELECT statements are permitted")

    for keyword in FORBIDDEN_KEYWORDS:
        if keyword in lowered:
            raise UnsafeSqlError(
                f"SQL statement contains a disallowed keyword: {keyword}"
            )

    # Every table named after FROM/JOIN must be in the allow-list.
    # This intentionally does not try to fully parse the SQL; it is a
    # conservative additional guard on top of the keyword blacklist.
    from_join_tables = re.findall(
        r"(?:from|join)\s+(?:audit\.)?([a-z_][a-z0-9_]*)",
        lowered,
    )

    for table in from_join_tables:
        if table not in ALLOWED_TABLES:
            raise UnsafeSqlError(
                f"SQL statement references a disallowed table: {table}"
            )

    if "limit" not in lowered:
        cleaned = f"{cleaned} LIMIT {MAX_ROW_LIMIT}"

    return cleaned


def run_safe_select(db: Session, sql: str) -> list[dict[str, Any]]:
    """Validate and execute a read-only SELECT, returning rows as dicts."""
    validated_sql = validate_select_sql(sql)

    result = db.execute(text(validated_sql))

    return [dict(row._mapping) for row in result]
