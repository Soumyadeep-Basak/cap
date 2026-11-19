"""Run the invoice auditing workflow continuously in the background.

This polls the incoming directory on a fixed interval and runs the full
``invoice_audit_graph`` (monitor -> extract -> translate -> validate ->
report -> index) for every newly discovered file. Already-audited files are
skipped by the monitor's checksum-based duplicate detection, so repeated
polling is safe and idempotent.
"""

import logging
from threading import Event

from invoice_auditor.workflows.invoice_workflow import invoice_audit_graph

logger = logging.getLogger(__name__)


def run_invoice_monitor(
    incoming_dir: str,
    stop_event: Event,
    poll_interval: float = 30.0,
) -> None:
    """Poll the incoming directory until shutdown is requested."""
    logger.info(
        "Invoice monitor started for %s (poll_interval=%ss)",
        incoming_dir,
        poll_interval,
    )

    while not stop_event.is_set():
        try:
            result = invoice_audit_graph.invoke(
                {"incoming_dir": incoming_dir}
            )

            logger.info(
                "Monitor cycle complete: status=%s",
                result.get("workflow_status"),
            )

        except Exception:
            logger.exception("Monitor iteration failed")

        stop_event.wait(poll_interval)

    logger.info("Invoice monitor stopped")
