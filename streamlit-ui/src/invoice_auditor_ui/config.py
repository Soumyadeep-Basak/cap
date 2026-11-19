"""Runtime configuration for the Streamlit human-in-the-loop dashboard."""

import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")

# The UI reads audit data directly from PostgreSQL (read-only) and calls
# the Agent API only for actions that must go through the Agent service:
# submitting corrections, requesting revalidation, and RAG querying.
def _build_database_url() -> str:
    if database_url := os.getenv("DATABASE_URL"):
        return database_url

    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")
    db_host = os.getenv("DB_HOST")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME")

    missing = [
        name
        for name, value in (
            ("DB_USER", db_user),
            ("DB_PASSWORD", db_password),
            ("DB_HOST", db_host),
            ("DB_NAME", db_name),
        )
        if not value
    ]
    if missing:
        missing_vars = ", ".join(missing)
        raise RuntimeError(
            "Database configuration is incomplete. Set DATABASE_URL or "
            f"provide DB_USER, DB_PASSWORD, DB_HOST, and DB_NAME. Missing: {missing_vars}"
        )

    return (
        "postgresql+psycopg://"
        f"{quote_plus(db_user)}:{quote_plus(db_password)}@"
        f"{db_host}:{db_port}/{quote_plus(db_name)}"
    )


DATABASE_URL = _build_database_url()

# Inside Docker Compose this must be the Agent's service name
# (http://agent:8000); the default below is for local, non-containerized
# development only.
AGENT_API_URL = os.getenv("AGENT_API_URL", "http://localhost:8000")
