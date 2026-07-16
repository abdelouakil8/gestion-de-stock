"""Focused performance probe — seeds a moderately large dataset directly via
the service layer (fast) and times the key read endpoints through the real
ApiClient, the way the UI hits them. Prints median latencies (ms).

Usage:  python scripts/perf_probe.py [n_products] [n_sales]
"""

import os
import statistics as stat
import sys
import tempfile
import threading
import time
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Persistent DB path so seeding (slow) can be done once and reused across runs.
_PERF_DIR = Path(os.environ.get("PERF_DIR") or tempfile.gettempdir()) / "pos_perf_db"
_PERF_DIR.mkdir(parents=True, exist_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{(_PERF_DIR / 'perf.db').as_posix()}"
os.environ["MEDIA_DIR"] = str(_PERF_DIR / "media")
os.environ["API_PORT"] = "8793"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "frontend"))

from app.core.security import hash_pin  # noqa: E402

os.environ["PIN_HASH"] = hash_pin("1234")

import httpx  # noqa: E402
import uvicorn  # noqa: E402

from app.core.config import settings as S  # noqa: E402

S.database_url = os.environ["DATABASE_URL"]
S.pin_hash = os.environ["PIN_HASH"]
S.api_port = 8793
S.media_dir = Path(os.environ["MEDIA_DIR"])

import random  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.schemas.category import CategoryCreate  # noqa: E402
from app.schemas.customer import CustomerCreate  # noqa: E402
from app.schemas.product import ProductCreate  # noqa: E402
from app.schemas.sale import CartItem, CheckoutRequest, PaymentInfo  # noqa: E402
from app.schemas.store import StoreCreate  # noqa: E402
from app.services import categories, customers, products, sales, stores  # noqa: E402
from services.api_client import ApiClient  # noqa: E402

N_PRODUCTS = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
N_SALES = int(sys.argv[2]) if len(sys.argv) > 2 else 1500
N_CUSTOMERS = 400


def seed() -> str:
    random.seed(7)
    from sqlalchemy import select

    from app.models import Store

    with SessionLocal() as db:
        existing = db.scalar(
            select(Store).where(Store.name == "Perf", Store.deleted_at.is_(None))
        )
        if existing is not None:
            return str(existing.id)  # already seeded — reuse
        store = stores.create_store(db, StoreCreate(name="Perf"))
        cats = [
            categories.create_category(
                db, CategoryCreate(store_id=store.id, name=f"Cat {i:02d}")
            )
            for i in range(20)
        ]
        prods = []
        for i in range(N_PRODUCTS):
            cost = Decimal(random.randint(500, 20000)) / 100
            prods.append(
                products.create_product(
                    db,
                    ProductCreate(
                        store_id=store.id,
                        category_id=random.choice(cats).id,
                        name=f"Produit {i:05d}",
                        barcode=f"61300{i:07d}",
                        cost_price=cost,
                        price_detail=(cost * Decimal("1.5")).quantize(Decimal("0.01")),
                        price_gros=(cost * Decimal("1.3")).quantize(Decimal("0.01")),
                        price_super_gros=(cost * Decimal("1.2")).quantize(
                            Decimal("0.01")
                        ),
                        stock_quantity=random.randint(0, 500),
                        low_stock_threshold=10,
                    ),
                )
            )
        custs = [
            customers.create_customer(
                db,
                CustomerCreate(
                    store_id=store.id, name=f"Client {i:04d}", phone=f"05{i:08d}"
                ),
            )
            for i in range(N_CUSTOMERS)
        ]
        for _ in range(N_SALES):
            picks = random.sample(prods, random.randint(1, 6))
            items = [
                CartItem(product_id=p.id, quantity=random.randint(1, 4))
                for p in picks
                if p.stock_quantity > 5
            ]
            if not items:
                continue
            req = CheckoutRequest(store_id=store.id, items=items)
            if random.random() > 0.5:
                req.payment = PaymentInfo(
                    mode="partial",
                    amount_paid=Decimal("10.00"),
                    customer_id=random.choice(custs).id,
                )
            try:
                sales.finalize_sale(db, req)
            except Exception:
                db.rollback()
        return str(store.id)


def start_api() -> None:
    cfg = uvicorn.Config(fastapi_app, host=S.api_host, port=8793, log_config=None)
    threading.Thread(target=uvicorn.Server(cfg).run, daemon=True).start()
    for _ in range(100):
        try:
            if httpx.get(f"http://{S.api_host}:8793/", timeout=1).status_code == 200:
                return
        except Exception:
            time.sleep(0.1)


def timeit(label: str, fn, rounds: int = 5) -> None:
    samples = []
    for _ in range(rounds):
        t = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t) * 1000)
    print(f"  {label:<52} median {stat.median(samples):7.1f} ms  (max {max(samples):7.1f})")


def main() -> int:
    t0 = time.perf_counter()
    print(f"Seeding {N_PRODUCTS} products, {N_CUSTOMERS} customers, {N_SALES} sales...")
    sid = seed()
    print(f"  seeded in {time.perf_counter() - t0:.1f}s")
    start_api()
    api = ApiClient(S.api_host, 8793)
    api.pin = "1234"

    print("\nEndpoint latencies (fresh cache each call):")
    today = time.strftime("%Y-%m-%d")
    year_ago = "2020-01-01"

    def _fresh(fn):
        api.cache.clear()
        return fn()

    timeit("GET /products (page 1, limit 50)", lambda: _fresh(lambda: api.list_products(sid, limit=50)))
    timeit("GET /products?q=Produit (search)", lambda: _fresh(lambda: api.search_products(sid, query="Produit 001", limit=20)))
    timeit("GET /sales (list, no limit — 'Tout')", lambda: _fresh(lambda: api.list_sales(sid)))
    timeit("GET /sales (limit=50)", lambda: _fresh(lambda: api.list_sales(sid, limit=50)))
    timeit("GET /statistics/summary (1y range)", lambda: _fresh(lambda: api.stats_summary(sid, year_ago, today)))
    timeit("GET /statistics/stock-turnover (1y)", lambda: _fresh(lambda: api._request("GET", "/statistics/stock-turnover", params={"store_id": sid, "date_from": year_ago, "date_to": today})))
    timeit("GET /statistics/sales-patterns (1y)", lambda: _fresh(lambda: api._request("GET", "/statistics/sales-patterns", params={"store_id": sid, "date_from": year_ago, "date_to": today})))
    return 0


if __name__ == "__main__":
    sys.exit(main())
