"""HTTP client for the local API.

BLOCKING by design — every method here performs network I/O and therefore
must ONLY ever be called from a worker thread (see services.workers.run_api).
Nothing in this module may be invoked directly from a Qt slot on the UI
thread. Business rules live server-side; this client never decides anything.
"""

from decimal import Decimal
from typing import Any

import httpx

from services.cache import AppCache
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
        self.pin: str | None = None
        self.session_token: str | None = None
        self.current_user: dict | None = None
        self.cache = AppCache(default_ttl=30.0)

    # ------------------------------------------------------------ plumbing

    def _headers(self, owner: bool = False) -> dict[str, str]:
        headers: dict[str, str] = {}
        # The session token authenticates EVERY request once a user is logged
        # in (cashier routes included), so it is not gated on `owner`.
        if self.session_token:
            headers["X-Session-Token"] = self.session_token
        # Legacy owner-PIN bridge, still used by the destructive re-confirm
        # dialogs (factory reset, restore, adjustment, clôture).
        if owner and self.pin:
            headers["X-Owner-Pin"] = self.pin
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        owner: bool = False,
        extra_headers: dict[str, str] | None = None,
        **kwargs,
    ) -> Any:
        headers = self._headers(owner)
        if extra_headers:
            headers.update(extra_headers)
        try:
            response = self._client.request(method, path, headers=headers, **kwargs)
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

    def _cached(self, key: str, method: str, path: str, **kwargs) -> Any:
        """GET with cache. Returns cached value if fresh, else fetches + stores."""
        hit, value = self.cache.get(key)
        if hit:
            return value
        result = self._request(method, path, **kwargs)
        self.cache.set(key, result)
        return result

    # ------------------------------------------------------------- version

    def check_version(self) -> dict:
        """GET /version — returns api_version and min_frontend_version."""
        return self._request("GET", "/version")

    # ---------------------------------------------------------------- auth

    def get_auth_status(self) -> dict:
        return self._request("GET", "/auth/status")

    def verify_pin(self, pin: str) -> dict:
        return self._request("POST", "/auth/verify", json={"pin": pin})

    def set_initial_pin(self, pin: str) -> dict:
        return self._request("POST", "/auth/set-pin", json={"pin": pin})

    def list_login_users(self) -> list[dict]:
        """Public list of users for the login picker (id, name, role)."""
        return self._request("GET", "/auth/users")

    def login(self, user_id: str, pin: str) -> dict:
        """Authenticate a user; on success store the session token + user."""
        data = self._request(
            "POST", "/auth/login", json={"user_id": user_id, "pin": pin}
        )
        self.session_token = data.get("token")
        self.current_user = data.get("user")
        return data

    def logout(self) -> None:
        """Revoke the session (best-effort) and forget the local credentials."""
        if self.session_token:
            try:
                self._request("POST", "/auth/logout")
            except ApiError:
                pass
        self.session_token = None
        self.current_user = None

    @property
    def role(self) -> str | None:
        return self.current_user.get("role") if self.current_user else None

    # ---------------------------------------------------------------- users

    def list_users(self, store_id: str) -> list[dict]:
        return self._request("GET", "/users", owner=True, params={"store_id": store_id})

    def create_user(self, payload: dict) -> dict:
        return self._request("POST", "/users", owner=True, json=payload)

    def update_user(self, user_id: str, payload: dict) -> dict:
        return self._request("PATCH", f"/users/{user_id}", owner=True, json=payload)

    def deactivate_user(self, user_id: str) -> None:
        return self._request("DELETE", f"/users/{user_id}", owner=True)

    # ----------------------------------------------------------- promotions

    def list_promotions(self, store_id: str, active_only: bool = False) -> list[dict]:
        return self._request(
            "GET",
            "/promotions",
            owner=True,
            params={"store_id": store_id, "active_only": active_only},
        )

    def create_promotion(self, payload: dict) -> dict:
        return self._request("POST", "/promotions", owner=True, json=payload)

    def validate_promotion(self, store_id: str, code: str, subtotal: str) -> dict:
        """Preview a promo code's discount at the caisse (does not consume it)."""
        return self._request(
            "POST",
            "/promotions/validate",
            json={"store_id": store_id, "code": code, "subtotal": subtotal},
        )

    def deactivate_promotion(self, promo_id: str) -> None:
        return self._request("DELETE", f"/promotions/{promo_id}", owner=True)

    # --------------------------------------------------------------- stores

    def list_stores(self) -> list[dict]:
        return self._request("GET", "/stores")

    def create_store(self, name: str) -> dict:
        return self._request("POST", "/stores", json={"name": name})

    # ----------------------------------------------------------- categories

    def list_categories(self, store_id: str) -> list[dict]:
        return self._cached(
            f"categories:{store_id}",
            "GET",
            "/categories",
            params={"store_id": store_id},
        )

    def create_category(self, store_id: str, name: str) -> dict:
        result = self._request(
            "POST",
            "/categories",
            owner=True,
            json={"store_id": store_id, "name": name},
        )
        self.cache.invalidate("categories:")
        return result

    # ------------------------------------------------------------- products

    def list_products(
        self,
        store_id: str,
        limit: int | None = None,
        offset: int = 0,
        category_id: str | None = None,
    ) -> dict:
        params: dict = {"store_id": store_id, "offset": offset}
        if limit is not None:
            params["limit"] = limit
        if category_id:
            params["category_id"] = category_id
        return self._cached(
            f"products:{store_id}:limit={limit}:offset={offset}:cat={category_id}",
            "GET",
            "/products",
            params=params,
        )

    def search_products(
        self,
        store_id: str,
        query: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        active_only: bool = False,
    ) -> dict:
        """Smart product search. Without query/limit/active_only this returns
        the full ordered catalog (same as list_products); with `query` it
        returns ranked results (exact > prefix > substring > fuzzy)."""
        params: dict = {"store_id": store_id, "offset": offset}
        if query:
            params["q"] = query
        if limit is not None:
            params["limit"] = limit
        if active_only:
            params["active_only"] = True
        return self._request("GET", "/products", params=params)

    def get_product_by_barcode(self, store_id: str, barcode: str) -> dict:
        return self._request(
            "GET", f"/products/by-barcode/{barcode}", params={"store_id": store_id}
        )

    def get_product_details(self, product_id: str) -> dict:
        """Owner view — includes cost_price. PIN-gated server-side."""
        return self._request("GET", f"/products/{product_id}/details", owner=True)

    def create_product(self, payload: dict) -> dict:
        result = self._request("POST", "/products", owner=True, json=payload)
        self.cache.invalidate("products:")
        return result

    def update_product(self, product_id: str, payload: dict) -> dict:
        result = self._request(
            "PATCH", f"/products/{product_id}", owner=True, json=payload
        )
        self.cache.invalidate("products:")
        return result

    def archive_product(self, product_id: str) -> None:
        result = self._request("DELETE", f"/products/{product_id}", owner=True)
        self.cache.invalidate("products:")
        return result

    # -------------------------------------------------------- product images

    def upload_product_image(
        self, product_id: str, data: bytes, content_type: str, filename: str
    ) -> dict:
        result = self._request(
            "POST",
            f"/products/{product_id}/image",
            owner=True,
            files={"file": (filename, data, content_type)},
        )
        # The product's image_path changed server-side; drop the stale list
        # cache so the inventory list reflects the new image immediately.
        self.cache.invalidate("products:")
        return result

    def get_product_image(self, product_id: str) -> bytes:
        """Raw image bytes; raises ApiError(not_found) when there is none."""
        return self._request("GET", f"/products/{product_id}/image")

    def delete_product_image(self, product_id: str) -> None:
        result = self._request("DELETE", f"/products/{product_id}/image", owner=True)
        # image_path is now null server-side; invalidate the list cache too.
        self.cache.invalidate("products:")
        return result

    def get_product_movements(
        self,
        store_id: str,
        product_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """Paginated movement ledger for one product (newest first)."""
        return self._request(
            "GET",
            f"/products/{product_id}/movements",
            params={"store_id": store_id, "limit": limit, "offset": offset},
        )

    def adjust_stock(
        self,
        product_id: str,
        new_quantity: int,
        reason: str,
        note: str | None,
        pin: str,
    ) -> dict:
        """Owner action: set a product's counted real stock. The freshly typed
        PIN is sent so the confirmation dialog cannot be bypassed."""
        body: dict = {"new_quantity": new_quantity, "reason": reason}
        if note:
            body["note"] = note
        result = self._request(
            "POST",
            f"/products/{product_id}/adjust-stock",
            extra_headers={"X-Owner-Pin": pin},
            json=body,
        )
        self.cache.invalidate("products:")
        return result

    def list_stock_movements(
        self,
        store_id: str,
        *,
        product_id: str | None = None,
        category_id: str | None = None,
        type: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        """Store-wide movement ledger (owner), product name joined in."""
        params: dict = {"store_id": store_id, "limit": limit, "offset": offset}
        if product_id:
            params["product_id"] = product_id
        if category_id:
            params["category_id"] = category_id
        if type:
            params["type"] = type
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to
        return self._request("GET", "/products/movements", owner=True, params=params)

    # -------------------------------------------------------------- customers

    def list_customers(
        self, store_id: str, query: str | None = None, limit: int | None = None
    ) -> list[dict]:
        """Smart customer search (name OR phone, accent/typo tolerant). No
        `query` returns all customers ordered by name; `limit` caps results."""
        params: dict = {"store_id": store_id}
        if query:
            params["q"] = query
        if limit is not None:
            params["limit"] = limit
        if not query and limit is None:
            return self._cached(
                f"customers:{store_id}", "GET", "/customers", params=params
            )
        return self._request("GET", "/customers", params=params)

    def get_customer(self, customer_id: str) -> dict:
        return self._request("GET", f"/customers/{customer_id}")

    def create_customer(self, payload: dict) -> dict:
        result = self._request("POST", "/customers", json=payload)
        self.cache.invalidate("customers:")
        return result

    def update_customer(self, customer_id: str, payload: dict) -> dict:
        result = self._request("PATCH", f"/customers/{customer_id}", json=payload)
        self.cache.invalidate("customers:")
        return result

    def archive_customer(self, customer_id: str) -> None:
        result = self._request("DELETE", f"/customers/{customer_id}", owner=True)
        self.cache.invalidate("customers:")
        return result

    # ---------------------------------------------------------------- sales

    def checkout(
        self,
        store_id: str,
        items: list[dict],
        payment: dict | None = None,
        promo_code: str | None = None,
    ) -> dict:
        """items: [{product_id, quantity, price_level, discount_percent?}] —
        never prices. payment: {mode: full|partial, amount_paid?, customer_id?}.
        promo_code: optional coupon validated + consumed server-side."""
        body: dict = {"store_id": store_id, "items": items}
        if payment is not None:
            body["payment"] = payment
        if promo_code:
            body["promo_code"] = promo_code
        result = self._request("POST", "/sales/checkout", json=body)
        self.cache.invalidate("products:")
        return result

    def list_sales(
        self,
        store_id: str,
        *,
        customer_id: str | None = None,
        created_by_user_id: str | None = None,
        guest: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict]:
        """Store sales, newest first. Optional filters: customer_id,
        created_by_user_id (the cashier who rang it), guest
        ('pending'|'confirmed'|'any'), date_from/date_to (ISO datetimes,
        half-open [from, to)), limit (no cap when omitted), offset."""
        params: dict = {"store_id": store_id}
        if customer_id is not None:
            params["customer_id"] = customer_id
        if created_by_user_id is not None:
            params["created_by_user_id"] = created_by_user_id
        if guest is not None:
            params["guest"] = guest
        if date_from is not None:
            params["date_from"] = date_from
        if date_to is not None:
            params["date_to"] = date_to
        if limit is not None:
            params["limit"] = limit
        if offset:
            params["offset"] = offset
        return self._request("GET", "/sales", params=params)

    def get_sale(self, sale_id: str) -> dict:
        return self._request("GET", f"/sales/{sale_id}")

    def assign_sale_customer(self, sale_id: str, customer_id: str) -> dict:
        """Attach a customer to an existing (guest) sale."""
        return self._request(
            "POST", f"/sales/{sale_id}/customer", json={"customer_id": customer_id}
        )

    def confirm_guest_sale(self, sale_id: str) -> dict:
        """Confirm a sale stays anonymous. Idempotent server-side."""
        return self._request("POST", f"/sales/{sale_id}/confirm-guest")

    def record_payment(
        self, sale_id: str, amount: str, payment_method: str = "cash"
    ) -> dict:
        """Later payment on a credit sale; server rejects overpayment."""
        return self._request(
            "POST",
            f"/sales/{sale_id}/payments",
            json={"amount": amount, "payment_method": payment_method},
        )

    def get_receipt_pdf(self, sale_id: str) -> bytes:
        return self._request("GET", f"/sales/{sale_id}/receipt")

    # --------------------------------------------------- outstanding credits

    def list_outstanding_sales(self, store_id: str) -> list[dict]:
        """Every credit sale with money still owed, oldest debt first (owner)."""
        return self._request(
            "GET", "/sales/outstanding", owner=True, params={"store_id": store_id}
        )

    def get_outstanding_report_pdf(self, store_id: str) -> bytes:
        """A4 debt-summary PDF for the Créances screen (owner)."""
        return self._request(
            "GET", "/sales/outstanding.pdf", owner=True, params={"store_id": store_id}
        )

    # ----------------------------------------------------- cash-register close

    def get_day_summary(self, store_id: str, day: str) -> dict:
        """Section-A recap for one calendar day + already-closed flag (owner)."""
        return self._request(
            "GET",
            "/sales/day-summary",
            owner=True,
            params={"store_id": store_id, "day": day},
        )

    def close_day(
        self,
        store_id: str,
        day: str,
        physical_cash_count: str,
        notes: str | None,
        pin: str,
    ) -> dict:
        """Persist the daily closing. The freshly typed PIN is sent."""
        return self._request(
            "POST",
            "/sales/close-day",
            extra_headers={"X-Owner-Pin": pin},
            json={
                "store_id": store_id,
                "date": day,
                "physical_cash_count": physical_cash_count,
                "notes": notes,
            },
        )

    def get_closing_pdf(
        self, store_id: str, day: str, physical_cash_count: str, notes: str | None
    ) -> bytes:
        """Printable clôture PDF for the given day + physical count (owner)."""
        params: dict = {
            "store_id": store_id,
            "day": day,
            "physical_cash_count": physical_cash_count,
        }
        if notes:
            params["notes"] = notes
        return self._request("GET", "/sales/close-day.pdf", owner=True, params=params)

    # ----------------------------------------------------------- statistics

    def get_report_pdf(self, store_id: str, date_from: str, date_to: str) -> bytes:
        return self._request(
            "GET",
            "/statistics/report.pdf",
            owner=True,
            params={"store_id": store_id, "date_from": date_from, "date_to": date_to},
        )

    def get_report_xlsx(self, store_id: str, date_from: str, date_to: str) -> bytes:
        return self._request(
            "GET",
            "/statistics/report.xlsx",
            owner=True,
            params={"store_id": store_id, "date_from": date_from, "date_to": date_to},
        )

    def get_daily_report_pdf(self, store_id: str, date: str) -> bytes:
        """End-of-day A4 report PDF for a single calendar day (owner)."""
        return self._request(
            "GET",
            "/statistics/daily-report.pdf",
            owner=True,
            params={"store_id": store_id, "date": date},
        )

    def get_comparison_report_pdf(
        self, store_id: str, a_from: str, a_to: str, b_from: str, b_to: str
    ) -> bytes:
        """Two-period comparison report PDF (owner)."""
        return self._request(
            "GET",
            "/statistics/comparison-report.pdf",
            owner=True,
            params={
                "store_id": store_id,
                "a_from": a_from,
                "a_to": a_to,
                "b_from": b_from,
                "b_to": b_to,
            },
        )

    def stats_summary(self, store_id: str, date_from: str, date_to: str) -> dict:
        return self._request(
            "GET",
            "/statistics/summary",
            owner=True,
            params={"store_id": store_id, "date_from": date_from, "date_to": date_to},
        )

    def stats_top_products(
        self,
        store_id: str,
        date_from: str,
        date_to: str,
        limit: int = 10,
        sort: str = "quantity",
    ) -> list[dict]:
        """Best sellers by 'quantity' (default) or by 'profit'."""
        return self._request(
            "GET",
            "/statistics/top-products",
            owner=True,
            params={
                "store_id": store_id,
                "date_from": date_from,
                "date_to": date_to,
                "limit": limit,
                "sort": sort,
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

    def stats_payment_methods(
        self, store_id: str, date_from: str, date_to: str
    ) -> list[dict]:
        return self._request(
            "GET",
            "/statistics/payment-methods",
            owner=True,
            params={"store_id": store_id, "date_from": date_from, "date_to": date_to},
        )

    def stats_daily_evolution(
        self, store_id: str, date_from: str, date_to: str
    ) -> list[dict]:
        """Revenue + profit per day over the range (zero-filled)."""
        return self._request(
            "GET",
            "/statistics/daily-evolution",
            owner=True,
            params={"store_id": store_id, "date_from": date_from, "date_to": date_to},
        )

    def stats_inventory(self, store_id: str) -> dict:
        """Stock value (cost + retail) and stock-health counts."""
        return self._request(
            "GET", "/statistics/inventory", owner=True, params={"store_id": store_id}
        )

    def stats_dead_stock(
        self, store_id: str, days: int = 60, limit: int = 20
    ) -> list[dict]:
        """Products in stock that have not sold in `days` days."""
        return self._request(
            "GET",
            "/statistics/dead-stock",
            owner=True,
            params={"store_id": store_id, "days": days, "limit": limit},
        )

    def stats_category_breakdown(
        self, store_id: str, date_from: str, date_to: str
    ) -> list[dict]:
        """Revenue/profit/quantity by product category."""
        return self._request(
            "GET",
            "/statistics/category-breakdown",
            owner=True,
            params={"store_id": store_id, "date_from": date_from, "date_to": date_to},
        )

    def stats_sales_patterns(self, store_id: str, date_from: str, date_to: str) -> dict:
        """Busy hours and weekdays (store-local) over the range."""
        return self._request(
            "GET",
            "/statistics/sales-patterns",
            owner=True,
            params={"store_id": store_id, "date_from": date_from, "date_to": date_to},
        )

    def stats_customer_insights(
        self, store_id: str, date_from: str, date_to: str
    ) -> dict:
        """Active / new / returning customers and guest sales over the range."""
        return self._request(
            "GET",
            "/statistics/customer-insights",
            owner=True,
            params={"store_id": store_id, "date_from": date_from, "date_to": date_to},
        )

    def stats_financial_snapshot(self, store_id: str) -> dict:
        """Outstanding customer credit and supplier debt (all-time)."""
        return self._request(
            "GET",
            "/statistics/financial-snapshot",
            owner=True,
            params={"store_id": store_id},
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

    # ----------------------------------------------------------------- admin

    def factory_reset(self, pin: str) -> dict:
        """Full wipe. The freshly TYPED pin is sent — never the cached one,
        so the confirmation dialog cannot be bypassed."""
        result = self._request(
            "POST", "/admin/factory-reset", extra_headers={"X-Owner-Pin": pin}
        )
        self.cache.clear()
        return result

    # --------------------------------------------------------------- backup

    def create_backup(self) -> bytes:
        """Download a full backup ZIP. Returns raw bytes."""
        return self._request("POST", "/backup/create", owner=True)

    def restore_backup(self, zip_data: bytes, pin: str) -> dict:
        """Upload a backup ZIP to restore. Returns safety backup info."""
        result = self._request(
            "POST",
            "/backup/restore",
            extra_headers={"X-Owner-Pin": pin},
            files={"file": ("backup.zip", zip_data, "application/zip")},
        )
        self.cache.clear()
        return result

    def list_backups(self) -> list[dict]:
        return self._request("GET", "/backup/list", owner=True)

    # -------------------------------------------------------------- refunds

    def get_refundable_items(self, sale_id: str) -> list[dict]:
        return self._request("GET", f"/sales/{sale_id}/refundable")

    def create_refund(
        self, sale_id: str, items: list[dict], reason: str | None = None
    ) -> dict:
        body: dict = {"items": items}
        if reason:
            body["reason"] = reason
        return self._request("POST", f"/sales/{sale_id}/refund", owner=True, json=body)

    def list_refunds(self, sale_id: str) -> list[dict]:
        return self._request("GET", f"/sales/{sale_id}/refunds")

    def get_refund_receipt(self, sale_id: str, refund_id: str) -> bytes:
        return self._request("GET", f"/sales/{sale_id}/refunds/{refund_id}/receipt")

    # ------------------------------------------------------------ suppliers

    def list_suppliers(self, store_id: str, q: str | None = None) -> list[dict]:
        params: dict = {"store_id": store_id}
        if q:
            params["q"] = q
        if not q:
            return self._cached(
                f"suppliers:{store_id}", "GET", "/suppliers", params=params
            )
        return self._request("GET", "/suppliers", params=params)

    def create_supplier(self, payload: dict) -> dict:
        result = self._request("POST", "/suppliers", owner=True, json=payload)
        self.cache.invalidate("suppliers:")
        return result

    def update_supplier(self, supplier_id: str, payload: dict) -> dict:
        result = self._request(
            "PATCH", f"/suppliers/{supplier_id}", owner=True, json=payload
        )
        self.cache.invalidate("suppliers:")
        return result

    def delete_supplier(self, supplier_id: str) -> None:
        result = self._request("DELETE", f"/suppliers/{supplier_id}", owner=True)
        self.cache.invalidate("suppliers:")
        return result

    # -------------------------------------------------------- purchase orders

    def list_purchase_orders(
        self, store_id: str, supplier_id: str | None = None
    ) -> list[dict]:
        params: dict = {"store_id": store_id}
        if supplier_id:
            params["supplier_id"] = supplier_id
        return self._request("GET", "/purchase-orders", params=params)

    def create_purchase_order(self, payload: dict) -> dict:
        result = self._request("POST", "/purchase-orders", owner=True, json=payload)
        self.cache.invalidate("products:")
        return result

    def record_supplier_payment(
        self, order_id: str, amount: str, payment_method: str = "cash"
    ) -> dict:
        return self._request(
            "POST",
            f"/purchase-orders/{order_id}/payments",
            owner=True,
            json={"amount": amount, "payment_method": payment_method},
        )

    # ---------------------------------------------------------- product import

    def import_products_csv(self, store_id: str, file_data: bytes) -> dict:
        result = self._request(
            "POST",
            "/products/import",
            owner=True,
            params={"store_id": store_id},
            files={"file": ("import.csv", file_data, "text/csv")},
        )
        self.cache.invalidate("products:", "categories:")
        return result


def as_decimal(value: str | None) -> Decimal:
    return Decimal(value) if value is not None else Decimal("0.00")
