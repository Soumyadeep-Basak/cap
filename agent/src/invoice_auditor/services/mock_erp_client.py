"""HTTP client for communicating with the Mock ERP service."""

from typing import Any

import httpx


class ERPClientError(RuntimeError):
    """Raised when the Mock ERP service cannot be reached or queried."""


class ERPClient:
    """HTTP client for the Mock ERP service."""

    def __init__(
        self,
        base_url: str,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _get(self, path: str) -> dict[str, Any]:
        """Perform a GET request against Mock ERP."""
        url = f"{self.base_url}{path}"

        try:
            response = httpx.get(
                url,
                timeout=self.timeout,
            )
        except httpx.RequestError as exc:
            raise ERPClientError(
                f"Could not reach Mock ERP: {exc}"
            ) from exc

        if response.status_code == 404:
            return {}

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ERPClientError(
                f"Mock ERP returned HTTP {response.status_code}"
            ) from exc

        try:
            return response.json()
        except ValueError as exc:
            raise ERPClientError(
                "Mock ERP returned invalid JSON"
            ) from exc

    def get_purchase_order(
        self,
        po_number: str,
    ) -> dict[str, Any]:
        """Fetch a purchase order and its line items."""
        return self._get(
            f"/api/v1/erp/po/{po_number}"
        )

    def get_vendor(
        self,
        vendor_id: str,
    ) -> dict[str, Any]:
        """Fetch a vendor master record."""
        return self._get(
            f"/api/v1/erp/vendor/{vendor_id}"
        )

    def get_sku(
        self,
        item_code: str,
    ) -> dict[str, Any]:
        """Fetch an SKU master record."""
        return self._get(
            f"/api/v1/erp/sku/{item_code}"
        )
