"""Parsed, allowlisted SELECTs executed in a bounded read-only transaction."""
from typing import Any
import sqlglot
from sqlglot import exp
from sqlalchemy import text

ALLOWED_TABLES = {"invoice_audit", "invoice_line_items", "discrepancies", "human_feedback"}
MAX_ROW_LIMIT = 200
_ALLOWED_FUNCTIONS = {
    "COUNT", "SUM", "AVG", "MIN", "MAX", "COALESCE", "NULLIF", "CAST",
    "ROUND", "ABS", "LOWER", "UPPER", "TRIM", "LTRIM", "RTRIM", "LENGTH",
    "SUBSTRING", "REPLACE", "DATE_TRUNC", "DATE_PART", "EXTRACT",
    "CURRENT_DATE", "CURRENT_TIMESTAMP", "TO_CHAR", "CONCAT", "CONCAT_WS",
    "GREATEST", "LEAST", "ROW_NUMBER", "RANK", "DENSE_RANK",
}
_FORBIDDEN = {"insert", "update", "delete", "drop", "alter", "create",
              "command", "copy", "merge", "transaction", "into", "lock",
              "lateral", "fetch", "tablesample", "offset"}

class UnsafeSqlError(ValueError):
    """Generated SQL is outside the supported read-only query language."""

def validate_select_sql(sql):
    if not isinstance(sql, str) or not sql.strip() or len(sql) > 20_000:
        raise UnsafeSqlError("SQL is empty or too large")
    try:
        statements = sqlglot.parse(sql, read="postgres")
    except sqlglot.errors.ParseError as exc:
        raise UnsafeSqlError("SQL syntax is unsupported") from exc
    if len(statements) != 1 or not isinstance(statements[0], (exp.Select, exp.Union)):
        raise UnsafeSqlError("Only a single SELECT query is permitted")
    tree = statements[0]
    if any(node.comments or node.key in _FORBIDDEN for node in tree.walk()):
        raise UnsafeSqlError("SQL contains unsupported operations or comments")
    if any(node.args.get("recursive") for node in tree.find_all(exp.With)):
        raise UnsafeSqlError("Recursive queries are not permitted")
    ctes = {node.alias_or_name.lower() for node in tree.find_all(exp.CTE)}
    tables = list(tree.find_all(exp.Table))
    if not tables:
        raise UnsafeSqlError("Queries must read invoice tables")
    physical_tables = 0
    for table in tables:
        if not isinstance(table.this, exp.Identifier) or table.catalog:
            raise UnsafeSqlError("Dynamic or cross-database tables are forbidden")
        name, schema = table.name.lower(), table.db.lower()
        if not schema and name in ctes:
            continue
        if name not in ALLOWED_TABLES or schema not in {"", "audit"}:
            raise UnsafeSqlError("Query references an unauthorized schema or table")
        table.set("db", exp.to_identifier("audit"))
        physical_tables += 1
    if not physical_tables:
        raise UnsafeSqlError("Query has no invoice source")
    for func in tree.find_all(exp.Func):
        name = func.name.upper() if isinstance(func, exp.Anonymous) else func.sql_name().upper()
        if name not in _ALLOWED_FUNCTIONS:
            raise UnsafeSqlError("Query invokes an unsupported function")
    for column in tree.find_all(exp.Column):
        if column.catalog or (column.db and column.db.lower() != "audit"):
            raise UnsafeSqlError("Cross-schema columns are forbidden")
    limit = tree.args.get("limit")
    if limit is None:
        tree = tree.limit(MAX_ROW_LIMIT)
    else:
        value = limit.expression
        if not isinstance(value, exp.Literal) or not value.is_int or int(value.this) < 0:
            raise UnsafeSqlError("LIMIT must be a nonnegative integer")
        limit.set("expression", exp.Literal.number(min(int(value.this), MAX_ROW_LIMIT)))
    return tree.sql(dialect="postgres")

def run_safe_select(db, sql) -> list[dict[str, Any]]:
    validated = validate_select_sql(sql)
    # Every execution uses a dedicated caller-owned read session. Do not use
    # this helper in a transaction that also writes business records.
    db.execute(text("SET TRANSACTION READ ONLY"))
    db.execute(text("SET LOCAL statement_timeout = '5s'"))
    db.execute(text("SET LOCAL lock_timeout = '1s'"))
    db.execute(text("SET LOCAL search_path = pg_catalog"))
    result = db.execute(text(validated))
    return [dict(row._mapping) for row in result.fetchmany(MAX_ROW_LIMIT)]
