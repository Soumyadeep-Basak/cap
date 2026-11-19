import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")


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
ERP_API_URL = os.getenv("ERP_API_URL", "http://localhost:8001")

INCOMING_DIR = Path(
    os.getenv("INCOMING_DIR", str(PROJECT_ROOT / "data" / "incoming"))
)

# How often (in seconds) the background Invoice Monitor polls INCOMING_DIR
# for newly arrived files. Duplicate detection (checksum-based) makes
# repeated polling idempotent and safe.
MONITOR_POLL_INTERVAL_SECONDS = float(
    os.getenv("MONITOR_POLL_INTERVAL_SECONDS", "30")
)

MOCK_ERP_URL = os.getenv(
    "MOCK_ERP_URL",
    "http://localhost:8000",
)

# ------------------------------------------------------------------
# Cache (Redis) and vector index (Qdrant) — used by the RAG pipeline.
# ------------------------------------------------------------------
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv(
    "QDRANT_COLLECTION", "invoice_knowledge"
)

# ------------------------------------------------------------------
# AWS Bedrock models used by the RAG pipeline.
# ------------------------------------------------------------------
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# Embeddings for the Indexing/Retrieval agents.
BEDROCK_EMBEDDING_MODEL_ID = os.getenv(
    "BEDROCK_EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v1"
)

# Reasoning/generation model for the Generation and Reflection agents.
# Cohere Command R+ is the model specified for RAG generation; it is
# configurable so a deployment with Bedrock access to that model can
# switch to it without a code change.
BEDROCK_RAG_MODEL_ID = os.getenv(
    "BEDROCK_RAG_MODEL_ID", "amazon.nova-lite-v1:0"
)

# ------------------------------------------------------------------
# RAG pipeline tuning.
# ------------------------------------------------------------------
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "5"))
RAG_MAX_RETRIES = int(os.getenv("RAG_MAX_RETRIES", "3"))
RAG_SCORE_THRESHOLD = float(os.getenv("RAG_SCORE_THRESHOLD", "0.7"))
LLM_CACHE_TTL_SECONDS = int(
    os.getenv("LLM_CACHE_TTL_SECONDS", str(24 * 60 * 60))
)