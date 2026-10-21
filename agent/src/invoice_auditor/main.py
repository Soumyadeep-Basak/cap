
"""FastAPI entry point for the AI Invoice Auditor."""

import logging
from contextlib import asynccontextmanager
from threading import Event, Thread

from fastapi import FastAPI

from invoice_auditor.agents.monitor_runner import run_invoice_monitor
from invoice_auditor.api.feedback_api import router as feedback_router
from invoice_auditor.api.invoice_api import router as invoice_router
from invoice_auditor.api.query_api import router as query_router
from invoice_auditor.config import INCOMING_DIR, MONITOR_POLL_INTERVAL_SECONDS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start/stop the background Invoice Monitor alongside the API server."""
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