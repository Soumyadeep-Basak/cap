
"""Helpers for the Invoice Monitoring MCP integration."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def get_authorized_incoming_dir(
    requested_dir: str | None = None,
) -> str:
    """
    Validate the directory exposed through the MCP tool.

    The monitoring server may scan only its configured incoming
    directory. Clients cannot use this tool to scan arbitrary
    paths inside the container.
    """
    configured = Path(
        os.getenv("INCOMING_DIR", "/app/data/incoming")
    ).resolve()

    if requested_dir is None:
        directory = configured
    else:
        if not isinstance(requested_dir, str) or not requested_dir.strip():
            raise ValueError("incoming_dir must be a nonempty string")

        directory = Path(requested_dir).resolve()

    if directory != configured:
        raise ValueError(
            "Only the configured incoming directory may be scanned"
        )

    if not directory.is_dir():
        raise FileNotFoundError(
            f"Incoming directory does not exist: {directory}"
        )

    return str(directory)


def prepare_monitoring_response(
    result: dict[str, Any],
) -> dict[str, Any]:
    """Normalize the existing monitor graph's result for MCP."""

    if not isinstance(result, dict):
        raise TypeError("Monitoring graph must return a dictionary")

    discovered = result.get("discovered_files") or []
    pending = result.get("pending_invoices") or []
    routed = result.get("routed_invoices") or []
    duplicates = result.get("duplicate_files") or []
    errors = result.get("errors") or []

    return {
        "status": result.get("status", "unknown"),
        "discovered_files": discovered,
        "pending_invoices": pending,
        "routed_invoices": routed,
        "duplicate_files": duplicates,
        "errors": errors,
        "discovered_count": len(discovered),
        "pending_count": len(pending),
        "routed_count": len(routed),
        "duplicate_count": len(duplicates),
        "error_count": len(errors),
    }
