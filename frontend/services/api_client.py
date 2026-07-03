"""HTTP client for the local API.

BLOCKING by design — every method here performs network I/O and therefore
must ONLY ever be called from a worker thread (see services.workers.run_api).
Nothing in this module may be invoked directly from a Qt slot on the UI
thread. Business rules live server-side; this client never decides anything.
"""

from decimal import Decimal
from typing import Any

import httpx

from ui import strings


class ApiError(Exception):
    """Structured error from the API envelope, safe to show to the user."""

    def __init__(self, code: str, message: str, status_code: int = 0) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class ApiClient:
    def __init__(self, host: str, port: int) -> None:
        self._client = httpx.Client(
            base_url=f"http://{host}:{port}/api/v1", timeout=10.0
        )
        self.pin: str | None = None  # set after the PIN gate; owner actions

    # ------------------------------------------------------------ plumbing

    def _headers(self, owner: bool = False) -> dict[str, str]:
        if owner and self.pin:
            return {"X-Owner-Pin": self.pin}
        return {}

    def _request(self, method: str, path: str, *, owner: bool = False, **kwargs) -> Any:
        try:
            response = self._client.request(
                method, path, headers=self._headers(owner), **kwargs
            )
        except httpx.HTTPError as exc:
            raise ApiError("network_error", strings.NETWORK_ERROR) from exc

        if response.status_code >= 400:
            try:
                error = response.json()["error"]
                raise ApiError(
                    error.get("code", "unknown"),
                    error.get("message", strings.UNEXPECTED_ERROR),
                    response.status_code,
                )
            except (KeyError, ValueError):
                raise ApiError(
                    "unknown", strings.UNEXPECTED_ERROR, response.status_code
                ) from None
        content_type = response.headers.get("content-type", "")
        if content_type.startswith(("application/pdf", "image/")):
            return response.content
        if response.status_code == 204:
            return None
        return response.json()

    # ---------------------------------------------------------------- auth

    def verify_pin(self, pin: str) -> dict:
        return self._request("POST", "/auth/verify", json={"pin": pin})

    # --------------------------------------------------------------- stores

    def list_stores(self) -> list[dict]:
        return self._request("GET", "/stores")

    def create_store(self, name: str) -> dict:
        return self._request("POST", "/stores", json={"name": name})

    # ----------------------------------------------------------- categories

    def list_categories(self, store_id: str) -> list[dict]:
        return self._request("GET", "/categories", params={"store_id": store_id})

    def create_category(self, store_id: str, name: str) -> dict:
        return self._request(
            "POST",
            "/categories",
            owner=True,
            json={"store_id": store_id, "name": name},
        )

    # ------------------------------------------------------------- products

    def list_products(self, store_id: str) -> list[dict]:
        return self._request("GET", "/products", params={"store_id": store_id})

    def get_product_by_barcode(self, store_id: str, barcode: str) -> dict:
        return self._request(
            "GET", f"/products/by-barcode/{barcode}", params={"store_id": store_id}
        )

    def get_product_details(self, product_id: str) -> dict:
        """Owner view — includes cost_price. PIN-gated server-side."""
        return self._request("GET", f"/products/{product_id}/details", owner=True)

    def create_product(self, payload: dict) -> dict:
        return self._request("POST", "/products", owner=True, json=payload)

    def update_product(self, product_id: str, payload: dict) -> dict:
        return self._request(
            "PATCH", f"/products/{product_id}", owner=True, json=payload
        )

    def archive_product(self, product_id: str) -> None:
        return self._request("DELETE", f"/products/{product_id}", owner=True)

    # -------------------------------------------------------- product images

    def upload_product_image(
        self, product_id: str, data: bytes, content_type: str, filename: str
    ) -> dict:
        return self._request(
            "POST",
            f"/products/{product_id}/image",
            owner=True,
            files={"file": (filename, data, content_type)},
        )

    def get_product_image(self, product_id: str) -> bytes:
        """Raw image bytes; raises ApiError(not_found) when there is none."""
        return self._request("GET", f"/products/{product_id}/image")

    def delete_product_image(self, product_id: str) -> None:
        return self._request("DELETE", f"/products/{product_id}/image", owner=True)

    # -------------------------------------------------------------- customers

    def list_customers(self, store_id: str, query: str | None = None) -> list[dict]:
        params: dict = {"store_id": store_id}
        if query:
            params["q"] = query
        return self._request("GET", "/customers", params=params)

    def get_customer(self, customer_id: str) -> dict:
        return self._request("GET", f"/customers/{customer_id}")

    def create_customer(self, payload: dict) -> dict:
        return self._request("POST", "/customers", json=payload)

    def update_customer(self, customer_id: str, payload: dict) -> dict:
        return self._request("PATCH", f"/customers/{customer_id}", json=payload)

    def archive_customer(self, customer_id: str) -> None:
        return self._request("DELETE", f"/customers/{customer_id}", owner=True)

    # ---------------------------------------------------------------- sales

    def checkout(
        self, store_id: str, items: list[dict], payment: dict | None = None
    ) -> dict:
        """items: [{product_id, quantity, price_level}] — never prices.
        payment: {mode: full|partial, amount_paid?, customer_id?}."""
        body: dict = {"store_id": store_id, "items": items}
        if payment is not None:
            body["payment"] = payment
        return self._request("POST", "/sales/checkout", json=body)

    def list_sales(self, store_id: str) -> list[dict]:
        return self._request("GET", "/sales", params={"store_id": store_id})

    def record_payment(self, sale_id: str, amount: str) -> dict:
        """Later payment on a credit sale; server rejects overpayment."""
        return self._request(
            "POST", f"/sales/{sale_id}/payments", json={"amount": amount}
        )

    def get_receipt_pdf(self, sale_id: str) -> bytes:
        return self._request("GET", f"/sales/{sale_id}/receipt")

    # ----------------------------------------------------------- statistics

    def stats_summary(self, store_id: str, date_from: str, date_to: str) -> dict:
        return self._request(
            "GET",
            "/statistics/summary",
            owner=True,
            params={"store_id": store_id, "date_from": date_from, "date_to": date_to},
        )

    def stats_top_products(
        self, store_id: str, date_from: str, date_to: str, limit: int = 10
    ) -> list[dict]:
        return self._request(
            "GET",
            "/statistics/top-products",
            owner=True,
            params={
                "store_id": store_id,
                "date_from": date_from,
                "date_to": date_to,
                "limit": limit,
            },
        )

    def stats_overview(self, store_id: str) -> dict:
        return self._request(
            "GET", "/statistics/overview", owner=True, params={"store_id": store_id}
        )

    def stats_product(self, store_id: str, product_id: str) -> dict:
        return self._request(
            "GET",
            f"/statistics/products/{product_id}",
            owner=True,
            params={"store_id": store_id},
        )

    def stats_top_customers(
        self, store_id: str, date_from: str, date_to: str, limit: int = 10
    ) -> list[dict]:
        return self._request(
            "GET",
            "/statistics/top-customers",
            owner=True,
            params={
                "store_id": store_id,
                "date_from": date_from,
                "date_to": date_to,
                "limit": limit,
            },
        )

    def stats_customer(self, customer_id: str) -> dict:
        return self._request("GET", f"/statistics/customers/{customer_id}", owner=True)

    def stats_associations(
        self,
        store_id: str,
        date_from: str,
        date_to: str,
        min_support: float = 0.05,
        min_confidence: float = 0.3,
    ) -> dict:
        return self._request(
            "GET",
            "/statistics/associations",
            owner=True,
            params={
                "store_id": store_id,
                "date_from": date_from,
                "date_to": date_to,
                "min_support": min_support,
                "min_confidence": min_confidence,
            },
        )

    # ---------------------------------------------------------------- alerts

    def get_alerts(self, store_id: str) -> dict:
        return self._request("GET", "/alerts", params={"store_id": store_id})

    # -------------------------------------------------------------- settings

    def get_settings(self, store_id: str) -> dict:
        return self._request("GET", "/settings", params={"store_id": store_id})

    def update_settings(self, store_id: str, payload: dict) -> dict:
        return self._request(
            "PUT", "/settings", owner=True, params={"store_id": store_id}, json=payload
        )


def as_decimal(value: str | None) -> Decimal:
    return Decimal(value) if value is not None else Decimal("0.00")
