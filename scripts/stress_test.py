"""Stress test — the whole API under concurrent, hostile load (Phase 7).

Boots uvicorn in-process on a throwaway database, then hammers it from
many threads at once: racing checkouts on scarce stock, racing payments on
one credit sale, and a mixed storm of sales/payments/reads/uploads/settings
writes. At the end, every financial invariant is re-checked row by row.

PASS criteria:
- zero unexpected errors (5xx / network) — business rejections are EXPECTED
  and counted (insufficient stock, overpayment, below floor…);
- stock never negative, never oversold;
- for EVERY sale: paid_amount == SUM(payments), 0 <= paid <= total,
  total == SUM(line totals);
- alerts summary matches a recomputation from raw data.

Usage:  python scripts/stress_test.py    (exit 0 = all invariants hold)
"""

import io
import os
import random
import sys
import tempfile
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
_TMP = Path(tempfile.mkdtemp(prefix="pos_stress_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'stress.db').as_posix()}"
os.environ["MEDIA_DIR"] = str(_TMP / "media")
os.environ["API_PORT"] = "8791"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.security import hash_pin  # noqa: E402

PIN = "1234"
os.environ["PIN_HASH"] = hash_pin(PIN)

import httpx  # noqa: E402
import uvicorn  # noqa: E402
from PIL import Image  # noqa: E402

from app.core.config import settings as backend_settings  # noqa: E402

backend_settings.database_url = os.environ["DATABASE_URL"]
backend_settings.pin_hash = os.environ["PIN_HASH"]
backend_settings.api_port = int(os.environ["API_PORT"])
backend_settings.media_dir = Path(os.environ["MEDIA_DIR"])

from app.main import app as fastapi_app  # noqa: E402

BASE = f"http://127.0.0.1:{backend_settings.api_port}/api/v1"
HEAD = {"X-Owner-Pin": PIN}
EXPECTED_CODES = {
    "insufficient_stock",
    "overpayment",
    "price_below_floor",
    "invalid_payment_amount",
    "credit_requires_customer",
    "invalid_image",
    "image_too_large",
    "customer_phone_exists",
    "product_unavailable",
}

unexpected: list[str] = []
expected_rejections: Counter = Counter()
op_counts: Counter = Counter()
_lock = threading.Lock()
_local = threading.local()


def client() -> httpx.Client:
    if not hasattr(_local, "client"):
        _local.client = httpx.Client(base_url=BASE, timeout=30.0)
    return _local.client


def record(response: httpx.Response, op: str) -> dict | list | None:
    with _lock:
        op_counts[op] += 1
    if response.status_code < 400:
        return response.json() if response.content else None
    try:
        code = response.json()["error"]["code"]
    except Exception:
        code = f"http_{response.status_code}"
    if code in EXPECTED_CODES or response.status_code in (401, 404, 422):
        with _lock:
            expected_rejections[code] += 1
        return None
    with _lock:
        unexpected.append(f"{op}: {response.status_code} {code}")
    return None


def start_api() -> None:
    config = uvicorn.Config(
        fastapi_app, host="127.0.0.1", port=backend_settings.api_port, log_config=None
    )
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            if (
                httpx.get(
                    f"http://127.0.0.1:{backend_settings.api_port}/", timeout=1.0
                ).status_code
                == 200
            ):
                return
        except httpx.HTTPError:
            time.sleep(0.15)
    raise RuntimeError("API did not start")


def png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (12, 12), (30, 60, 90)).save(buffer, format="PNG")
    return buffer.getvalue()


def main() -> int:  # noqa: PLR0915
    random.seed(42)
    start_api()
    t0 = time.monotonic()

    store = client().post("/stores", json={"name": "Boutique Stress"}).json()
    sid = store["id"]

    # ------------------------------------------------------------- seeding
    def make_product(i: int) -> dict:
        detail = Decimal(random.randint(500, 5000)) / 100
        return record(
            client().post(
                "/products",
                headers=HEAD,
                json={
                    "store_id": sid,
                    "name": f"Produit {i:03d}",
                    "barcode": f"61300{i:08d}",
                    "cost_price": f"{detail * Decimal('0.6'):.2f}",
                    "price_detail": f"{detail:.2f}",
                    "price_gros": f"{detail * Decimal('0.9'):.2f}",
                    "price_super_gros": f"{detail * Decimal('0.8'):.2f}",
                    "stock_quantity": random.randint(50, 500),
                    "low_stock_threshold": random.randint(3, 15),
                },
            ),
            "create_product",
        )

    def make_customer(i: int) -> dict:
        return record(
            client().post(
                "/customers",
                json={
                    "store_id": sid,
                    "name": f"Client {i:03d}",
                    "phone": f"05{i:08d}",
                },
            ),
            "create_customer",
        )

    with ThreadPoolExecutor(max_workers=12) as pool:
        products = [p for p in pool.map(make_product, range(150)) if p]
        customers = [c for c in pool.map(make_customer, range(40)) if c]
    print(f"seeded {len(products)} produits, {len(customers)} clients")
    assert len(products) == 150 and len(customers) == 40

    # ----------------------------------------- race 1: scarce stock
    scarce = record(
        client().post(
            "/products",
            headers=HEAD,
            json={
                "store_id": sid,
                "name": "Article rare",
                "cost_price": "10.00",
                "price_detail": "20.00",
                "price_gros": "18.00",
                "price_super_gros": "15.00",
                "stock_quantity": 25,
                "low_stock_threshold": 0,
            },
        ),
        "create_product",
    )

    sold = Counter()

    def race_checkout(_n: int) -> None:
        qty = random.randint(1, 3)
        result = record(
            client().post(
                "/sales/checkout",
                json={
                    "store_id": sid,
                    "items": [
                        {
                            "product_id": scarce["id"],
                            "quantity": qty,
                            "price_level": "detail",
                        }
                    ],
                },
            ),
            "race_checkout",
        )
        if result is not None:
            with _lock:
                sold["units"] += qty

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(race_checkout, range(60)))
    remaining = next(
        p["stock_quantity"]
        for p in client().get("/products", params={"store_id": sid}).json()
        if p["id"] == scarce["id"]
    )
    assert remaining >= 0, "stock must never go negative"
    assert remaining == 25 - sold["units"], "sold units must match stock delta"
    print(
        f"course au stock : 25 unités, {sold['units']} vendues, "
        f"{remaining} restantes, "
        f"{expected_rejections['insufficient_stock']} refus corrects"
    )

    # ----------------------------------------- race 2: payment race
    big_customer = customers[0]
    credit = record(
        client().post(
            "/sales/checkout",
            json={
                "store_id": sid,
                "items": [
                    {
                        "product_id": products[0]["id"],
                        "quantity": 10,
                        "price_level": "detail",
                    }
                ],
                "payment": {
                    "mode": "partial",
                    "amount_paid": "0.00",
                    "customer_id": big_customer["id"],
                },
            },
        ),
        "credit_checkout",
    )
    total = Decimal(credit["total_amount"])
    chunk = (total / 4).quantize(Decimal("0.01"))

    def race_pay(_n: int) -> None:
        record(
            client().post(
                f"/sales/{credit['id']}/payments", json={"amount": f"{chunk:.2f}"}
            ),
            "race_payment",
        )

    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(race_pay, range(10)))
    sale_after = client().get(f"/sales/{credit['id']}").json()
    paid = Decimal(sale_after["paid_amount"])
    assert paid <= total, "payments must never exceed the total"
    assert paid == sum(
        (Decimal(p["amount"]) for p in sale_after["payments"]), Decimal("0")
    ), "paid_amount must equal SUM(payments)"
    print(
        f"course aux paiements : total {total}, encaissé {paid} "
        f"({len(sale_after['payments'])} paiements, "
        f"{expected_rejections['overpayment']} surpaiements rejetés)"
    )

    # ------------------------------------------------ mixed storm
    open_credits: list[str] = [credit["id"]]

    def storm(worker: int) -> None:
        rng = random.Random(worker)
        for _ in range(30):
            action = rng.random()
            if action < 0.35:  # full checkout
                product = rng.choice(products)
                record(
                    client().post(
                        "/sales/checkout",
                        json={
                            "store_id": sid,
                            "items": [
                                {
                                    "product_id": product["id"],
                                    "quantity": rng.randint(1, 4),
                                    "price_level": rng.choice(
                                        ["detail", "gros", "super_gros"]
                                    ),
                                }
                            ],
                        },
                    ),
                    "storm_checkout",
                )
            elif action < 0.5:  # credit checkout
                product = rng.choice(products)
                result = record(
                    client().post(
                        "/sales/checkout",
                        json={
                            "store_id": sid,
                            "items": [{"product_id": product["id"], "quantity": 2}],
                            "payment": {
                                "mode": "partial",
                                "amount_paid": "1.00",
                                "customer_id": rng.choice(customers)["id"],
                            },
                        },
                    ),
                    "storm_credit",
                )
                if result is not None:
                    with _lock:
                        open_credits.append(result["id"])
            elif action < 0.6:  # payment on a random credit
                with _lock:
                    sale_id = rng.choice(open_credits)
                record(
                    client().post(
                        f"/sales/{sale_id}/payments", json={"amount": "1.00"}
                    ),
                    "storm_payment",
                )
            elif action < 0.7:  # hostile: below floor + bad payloads
                product = rng.choice(products)
                record(
                    client().post(
                        "/sales/checkout",
                        json={
                            "store_id": sid,
                            "items": [
                                {
                                    "product_id": product["id"],
                                    "quantity": 1,
                                    "unit_price_override": "0.01",
                                }
                            ],
                        },
                    ),
                    "storm_below_floor",
                )
                record(
                    client().post(
                        "/sales/checkout",
                        json={
                            "store_id": sid,
                            "items": [{"product_id": product["id"], "quantity": 1}],
                            "payment": {"mode": "partial", "amount_paid": "0.01"},
                        },
                    ),
                    "storm_credit_no_customer",
                )
            elif action < 0.8:  # image uploads: one valid, one hostile
                product = rng.choice(products)
                record(
                    client().post(
                        f"/products/{product['id']}/image",
                        headers=HEAD,
                        files={"file": ("p.png", png_bytes(), "image/png")},
                    ),
                    "storm_image",
                )
                record(
                    client().post(
                        f"/products/{product['id']}/image",
                        headers=HEAD,
                        files={"file": ("x.png", b"not an image", "image/png")},
                    ),
                    "storm_bad_image",
                )
            else:  # reads under load
                record(
                    client().get("/alerts", params={"store_id": sid}), "storm_alerts"
                )
                record(
                    client().get(
                        "/statistics/overview",
                        params={"store_id": sid},
                        headers=HEAD,
                    ),
                    "storm_overview",
                )
                record(
                    client().get(
                        "/statistics/associations",
                        params={
                            "store_id": sid,
                            "date_from": "2020-01-01",
                            "date_to": "2030-01-01",
                        },
                        headers=HEAD,
                    ),
                    "storm_assoc",
                )
                record(
                    client().put(
                        "/settings",
                        params={"store_id": sid},
                        headers=HEAD,
                        json={"footer_message": f"storm {worker}"},
                    ),
                    "storm_settings",
                )

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(storm, range(16)))

    # --------------------------------------------------- invariants
    sales = client().get("/sales", params={"store_id": sid}).json()
    for sale in sales:
        total = Decimal(sale["total_amount"])
        paid = Decimal(sale["paid_amount"])
        lines = sum((Decimal(i["line_total"]) for i in sale["items"]), Decimal("0"))
        payments_sum = sum(
            (Decimal(p["amount"]) for p in sale["payments"]), Decimal("0")
        )
        assert Decimal("0") <= paid <= total, sale["id"]
        assert paid == payments_sum, f"paid != SUM(payments) on {sale['id']}"
        assert total == lines, f"total != SUM(lines) on {sale['id']}"

    all_products = client().get("/products", params={"store_id": sid}).json()
    assert all(p["stock_quantity"] >= 0 for p in all_products)

    alerts = client().get("/alerts", params={"store_id": sid}).json()
    recomputed_credits = [
        s for s in sales if Decimal(s["paid_amount"]) < Decimal(s["total_amount"])
    ]
    assert alerts["summary"]["outstanding_credits_count"] == len(recomputed_credits)
    recomputed_low = [
        p
        for p in all_products
        if p["is_active"] and p["stock_quantity"] <= p["low_stock_threshold"]
    ]
    assert alerts["summary"]["low_stock_count"] == len(recomputed_low)

    elapsed = time.monotonic() - t0
    total_ops = sum(op_counts.values())
    print(
        f"\n{total_ops} opérations en {elapsed:.1f}s ({total_ops / elapsed:.0f} ops/s)"
    )
    print(f"ventes finales : {len(sales)} — toutes les invariantes vérifiées")
    print("rejets métier attendus :", dict(expected_rejections))
    if unexpected:
        print(f"\nERREURS INATTENDUES ({len(unexpected)}):")
        for line in unexpected[:20]:
            print("  ", line)
        return 1
    print("aucune erreur inattendue — STRESS TEST OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
