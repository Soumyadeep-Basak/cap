
"""FastAPI entry point for the AI Invoice Auditor."""

import logging
from contextlib import asynccontextmanager
from threading import Event, Thread

from fastapi import FastAPI
from langgraph.checkpoint.postgres import PostgresSaver

from invoice_auditor.agents.monitor_runner import run_invoice_monitor
from invoice_auditor.api.feedback_api import router as feedback_router
from invoice_auditor.api.invoice_api import router as invoice_router
from invoice_auditor.api.query_api import router as query_router
from invoice_auditor.config import (
    DATABASE_URL,
    INCOMING_DIR,
    MONITOR_POLL_INTERVAL_SECONDS,
)
from invoice_auditor.workflows import rag_workflow

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start/stop the background Invoice Monitor alongside the API server."""
    checkpoint_url = DATABASE_URL.replace(
        "postgresql+psycopg://", "postgresql://", 1
    )

    with PostgresSaver.from_conn_string(checkpoint_url) as checkpointer:
        checkpointer.conn.execute("SET search_path TO langgraph, public")
        checkpointer.setup()
        rag_workflow.rag_query_graph = rag_workflow.build_rag_query_graph(
            checkpointer
        )

        stop_event = Event()
        monitor_thread = Thread(
            target=run_invoice_monitor,
            kwargs={
                "incoming_dir": str(INCOMING_DIR),
                "stop_event": stop_event,
                "poll_interval": MONITOR_POLL_INTERVAL_SECONDS,
            },
            name="invoice-monitor",
            daemon=True,
        )
        monitor_thread.start()

        try:
            yield
        finally:
            stop_event.set()
            monitor_thread.join(timeout=10)

            if monitor_thread.is_alive():
                logger.warning("Monitor thread is still shutting down")


app = FastAPI(
    title="AI Invoice Auditor",
    lifespan=lifespan,
)

app.include_router(invoice_router)
app.include_router(feedback_router)
app.include_router(query_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
