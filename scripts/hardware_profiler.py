"""
hardware_profiler.py — Data-driven hardware requirements profiling.

Seeds a throwaway SQLite database with 50,000 products and 100,000+ transactions,
then simulates heavy concurrent API load while recording CPU, RAM, and disk I/O
via psutil. Output is used to derive Minimum / Recommended hardware specs.

Usage (from project root):
    python scripts/hardware_profiler.py
"""

import os
import random
import sys
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

# ---------------------------------------------------------------------------
# 1. Environment setup — throwaway DB, temp media dir, fixed PIN
# ---------------------------------------------------------------------------
_TMP = Path(tempfile.mkdtemp(prefix="pos_hwprofile_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'hwprofile.db').as_posix()}"
os.environ["MEDIA_DIR"] = str(_TMP / "media")
os.environ["API_PORT"] = "8793"
PIN = "1234"

from app.core.security import hash_pin

os.environ["PIN_HASH"] = hash_pin(PIN)

from app.core.config import settings as backend_settings

backend_settings.database_url = os.environ["DATABASE_URL"]
backend_settings.pin_hash = os.environ["PIN_HASH"]
backend_settings.api_port = int(os.environ["API_PORT"])
backend_settings.media_dir = Path(os.environ["MEDIA_DIR"])
Path(os.environ["MEDIA_DIR"]).mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# 2. Imports
# ---------------------------------------------------------------------------
import httpx
import psutil
import uvicorn
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, engine


# Enable SQLite WAL mode + busy timeout for concurrent profiling
@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()
from app.db.base import Base
from app.main import app as fastapi_app
from app.models.customer import Customer
from app.models.product import Product
from app.models.sale import Payment, Sale, SaleItem
from app.models.store import Store

BASE = f"http://127.0.0.1:{backend_settings.api_port}/api/v1"
ROOT = f"http://127.0.0.1:{backend_settings.api_port}"
HEAD = {"X-Owner-Pin": PIN}

# ---------------------------------------------------------------------------
# 3. Metrics collector
# ---------------------------------------------------------------------------
class Metrics:
    def __init__(self):
        self.lock = threading.Lock()
        self.cpu_samples: list[float] = []
        self.ram_samples: list[float] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.sys_io_start = psutil.disk_io_counters()

    def _sample(self):
        proc = psutil.Process(os.getpid())
        while not self._stop.is_set():
            try:
                cpu = proc.cpu_percent(interval=0.0)
                rss = proc.memory_info().rss / (1024 * 1024)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                time.sleep(0.5)
                continue
            with self.lock:
                self.cpu_samples.append(cpu)
                self.ram_samples.append(rss)
            time.sleep(0.5)

    def start(self):
        self._thread = threading.Thread(target=self._sample, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        self.sys_io_end = psutil.disk_io_counters()

    @property
    def cpu_avg(self) -> float:
        return sum(self.cpu_samples) / len(self.cpu_samples) if self.cpu_samples else 0

    @property
    def cpu_max(self) -> float:
        return max(self.cpu_samples) if self.cpu_samples else 0

    @property
    def cpu_peak(self) -> float:
        if not self.cpu_samples:
            return 0
        s = sorted(self.cpu_samples)
        return s[int(len(s) * 0.95)]

    @property
    def ram_avg(self) -> float:
        return sum(self.ram_samples) / len(self.ram_samples) if self.ram_samples else 0

    @property
    def ram_max(self) -> float:
        return max(self.ram_samples) if self.ram_samples else 0

    @property
    def ram_peak(self) -> float:
        if not self.ram_samples:
            return 0
        s = sorted(self.ram_samples)
        return s[int(len(s) * 0.95)]

    @property
    def disk_read_mb(self) -> float:
        return (self.sys_io_end.read_bytes - self.sys_io_start.read_bytes) / 1048576

    @property
    def disk_write_mb(self) -> float:
        return (self.sys_io_end.write_bytes - self.sys_io_start.write_bytes) / 1048576


# ---------------------------------------------------------------------------
# 4. Database seeder  (50k products + 100k transactions)
# ---------------------------------------------------------------------------
def seed_database() -> tuple[str, list[str], list[str]]:
    """Create store, 50 000 products, 40 customers, 100 000 sales."""
    Base.metadata.create_all(bind=engine)
    db: Session = SessionLocal()

    print("Seeding store …")
    store = Store(name="Hardware Profile Store")
    db.add(store)
    db.commit()
    sid = str(store.id)

    print("Seeding 50 000 products …", end=" ", flush=True)
    product_ids: list[str] = []
    for batch_start in range(0, 50000, 5000):
        batch = []
        for i in range(batch_start, batch_start + 5000):
            detail = Decimal(str(round(random.uniform(15, 1000), 2)))
            gros = Decimal(str(round(float(detail) * random.uniform(0.7, 0.95), 2)))
            super_gros = Decimal(str(round(float(gros) * random.uniform(0.7, 0.95), 2)))
            cost = Decimal(str(round(float(super_gros) * random.uniform(0.3, 0.7), 2)))
            p = Product(
                id=uuid.uuid4(),
                store_id=store.id,
                name=f"Produit {i:05d}",
                barcode=f"61300{i:08d}",
                search_text=f"produit {i:05d}",
                cost_price=cost,
                price_detail=detail,
                price_gros=gros,
                price_super_gros=super_gros,
                stock_quantity=random.randint(20, 2000),
                low_stock_threshold=random.randint(3, 20),
                is_active=True,
            )
            product_ids.append(str(p.id))
            batch.append(p)
        db.bulk_save_objects(batch)
        db.commit()
    print(f"{len(product_ids)} done")

    print("Seeding 40 customers …", end=" ", flush=True)
    customer_ids: list[str] = []
    for i in range(40):
        c = Customer(
            id=uuid.uuid4(), store_id=store.id,
            name=f"Client {i:03d}", phone=f"05{i:08d}",
            search_text=f"client {i:03d}",
        )
        customer_ids.append(str(c.id))
        db.add(c)
    db.commit()
    print("done")

    print("Seeding 100 000 transactions …", end=" ", flush=True)
    pids = [uuid.UUID(pid) for pid in product_ids[:2000]]
    cids = [uuid.UUID(cid) for cid in customer_ids]

    for batch_start in range(0, 100000, 5000):
        s_batch, i_batch, p_batch = [], [], []
        for _ in range(5000):
            s_id = uuid.uuid4()
            total = Decimal(str(round(random.uniform(5, 500), 2)))
            paid = total if random.random() < 0.75 else (total * Decimal("0.3")).quantize(Decimal("0.01"))
            s_batch.append(Sale(
                id=s_id, store_id=store.id, total_amount=total, paid_amount=paid,
                customer_id=random.choice(cids) if paid < total else None,
            ))
            i_batch.append(SaleItem(
                id=uuid.uuid4(), store_id=store.id, sale_id=s_id,
                product_id=random.choice(pids), quantity=random.randint(1, 5),
                price_level=random.choice(["detail", "gros", "super_gros"]),
                unit_price_applied=total, line_total=total,
            ))
            p_batch.append(Payment(
                id=uuid.uuid4(), sale_id=s_id, store_id=store.id, amount=paid,
                payment_method=random.choice(["cash", "card", "transfer"]),
            ))
        db.bulk_save_objects(s_batch)
        db.bulk_save_objects(i_batch)
        db.bulk_save_objects(p_batch)
        db.commit()
    print("done")

    db.close()
    return sid, product_ids, customer_ids


# ---------------------------------------------------------------------------
# 5. API load simulation — throttled to avoid SQLite write contention
# ---------------------------------------------------------------------------
def simulate_api_load(store_id: str, product_ids: list[str],
                      customer_ids: list[str]) -> None:
    """Fire ~3 000 mixed API calls across parallel workers.

    SQLite serialises writes, so checkout throughput is limited; most workers
    spend time on read-heavy endpoints (overview, associations, alerts) that
    are the real CPU/Memory pressure points.
    """
    # We'll rate-limit checkouts to 1 at a time to keep SQLite happy
    checkout_lock = threading.Lock()

    call_counts: dict[str, int] = {}
    call_errors: dict[str, int] = {}
    results_lock = threading.Lock()

    def _record(name: str, ok: bool):
        with results_lock:
            call_counts[name] = call_counts.get(name, 0) + 1
            if not ok:
                call_errors[name] = call_errors.get(name, 0) + 1

    def worker_fn(worker_id: int):
        rng = random.Random(worker_id)
        local = httpx.Client(base_url=BASE, timeout=60.0)

        for _ in range(50):  # 10 × 50 = 500 iterations
            action = rng.random()

            # --- CHECKOUT (serialised write) ---
            if action < 0.15:
                pid = rng.choice(product_ids)
                qty = rng.randint(1, 3)
                level = rng.choice(["detail", "gros", "super_gros"])
                with checkout_lock:  # serialise writes for SQLite
                    try:
                        resp = local.post("/sales/checkout", json={
                            "store_id": store_id,
                            "items": [{"product_id": pid, "quantity": qty,
                                       "price_level": level}],
                            "payment": {"mode": "full", "payment_method": "cash"},
                        }, timeout=15.0)
                        _record("checkout", resp.status_code < 500)
                    except Exception:
                        _record("checkout", False)

            # --- SMART SEARCH (heaviest read — fuzzy scan on 50k products) ---
            elif action < 0.35:
                q = rng.choice(["Produit 1", "produit 5", "produit 10000",
                                "produit 25000", "produit 49999"])
                try:
                    resp = local.get("/products", params={
                        "store_id": store_id, "q": q, "limit": 50
                    })
                    _record("product_search", resp.status_code < 500)
                except Exception:
                    _record("product_search", False)

            # --- BARCODE LOOKUP ---
            elif action < 0.40:
                barcode = f"61300{rng.randint(0, 49999):08d}"
                try:
                    resp = local.get(f"/products/by-barcode/{barcode}",
                                     params={"store_id": store_id})
                    _record("barcode_lookup", resp.status_code < 500)
                except Exception:
                    _record("barcode_lookup", False)

            # --- STATISTICS OVERVIEW (aggregates 100k+ sales × 5 periods) ---
            elif action < 0.55:
                try:
                    resp = local.get("/statistics/overview",
                                     params={"store_id": store_id}, headers=HEAD)
                    _record("overview_stats", resp.status_code < 500)
                except Exception:
                    _record("overview_stats", False)

            # --- TOP PRODUCTS (rank aggregation) ---
            elif action < 0.65:
                try:
                    resp = local.get("/statistics/top-products",
                                     params={"store_id": store_id,
                                              "date_from": "2020-01-01",
                                              "date_to": "2030-01-01", "limit": 50},
                                     headers=HEAD)
                    _record("top_products", resp.status_code < 500)
                except Exception:
                    _record("top_products", False)

            # --- APRIORI (heaviest SQL — market-basket analysis on 100k baskets) ---
            elif action < 0.75:
                try:
                    resp = local.get("/statistics/associations",
                                     params={"store_id": store_id,
                                              "date_from": "2020-01-01",
                                              "date_to": "2030-01-01",
                                              "min_support": "0.05",
                                              "min_confidence": "0.3"},
                                     headers=HEAD)
                    _record("apriori", resp.status_code < 500)
                except Exception:
                    _record("apriori", False)

            # --- ALERTS (low-stock + credit summary) ---
            elif action < 0.85:
                try:
                    resp = local.get("/alerts", params={"store_id": store_id})
                    _record("alerts", resp.status_code < 500)
                except Exception:
                    _record("alerts", False)

            # --- SALES LIST ---
            elif action < 0.92:
                try:
                    resp = local.get("/sales", params={"store_id": store_id, "limit": 50})
                    _record("list_sales", resp.status_code < 500)
                except Exception:
                    _record("list_sales", False)

            # --- CUSTOMER SEARCH ---
            else:
                q = rng.choice(["Client 1", "client 20", "Client 35"])
                try:
                    resp = local.get("/customers",
                                     params={"store_id": store_id, "q": q, "limit": 20})
                    _record("customer_search", resp.status_code < 500)
                except Exception:
                    _record("customer_search", False)

        local.close()

    print("Simulating API load: 10 workers × 50 iterations "
          "(~500 iterations, ~1 000 API calls) …")
    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(worker_fn, range(10)))
    elapsed = time.monotonic() - t0

    total_ok = sum(call_counts.values())
    total_err = sum(call_errors.values())
    print(f"  Done in {elapsed:.1f}s | OK={total_ok} Errors={total_err}")
    for op in sorted(call_counts):
        errs = call_errors.get(op, 0)
        ok = call_counts[op]
        print(f"    {op}: {ok:>5} calls, {errs} errors"
              + (f" ({errs/ok*100:.0f}% fail)" if errs else ""))


# ---------------------------------------------------------------------------
# 6. DB info
# ---------------------------------------------------------------------------
def get_db_info() -> dict:
    size_mb = os.path.getsize(_TMP / "hwprofile.db") / (1024 * 1024)
    db = SessionLocal()
    counts = {}
    for table in ("products", "sales", "sale_items", "payments", "customers"):
        counts[table] = db.scalar(text(f"SELECT COUNT(*) FROM {table}"))
    db.close()
    return {"size_mb": size_mb, **counts}


# ---------------------------------------------------------------------------
# 7. Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("  GestionStockPOS — Hardware Profiler")
    print("=" * 60)

    # ---- Seed ----
    t0 = time.monotonic()
    store_id, product_ids, customer_ids = seed_database()
    seed_elapsed = time.monotonic() - t0
    db_info = get_db_info()
    print(f"\nDatabase seeded in {seed_elapsed:.1f}s")
    print(f"  DB file size : {db_info['size_mb']:.1f} MB")
    print(f"  Products     : {db_info['products']:>8,}")
    print(f"  Customers    : {db_info['customers']:>8,}")
    print(f"  Sales        : {db_info['sales']:>8,}")
    print(f"  Sale Items   : {db_info['sale_items']:>8,}")
    print(f"  Payments     : {db_info['payments']:>8,}")

    # ---- Start API ----
    print("\nStarting FastAPI server …")
    config = uvicorn.Config(fastapi_app, host="127.0.0.1",
                            port=backend_settings.api_port,
                            log_level="error", log_config=None)
    server = uvicorn.Server(config)
    api_thread = threading.Thread(target=server.run, daemon=True)
    api_thread.start()
    time.sleep(2)

    health = httpx.Client(base_url=ROOT, timeout=5.0)
    for attempt in range(40):
        try:
            r = health.get("/")
            if r.status_code == 200:
                print(f"  API ready at {ROOT}")
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    else:
        print("  ERROR: API not reachable after 20s")
        sys.exit(1)
    health.close()

    # ---- Profile ----
    metrics = Metrics()
    metrics.start()
    simulate_api_load(store_id, product_ids, customer_ids)
    metrics.stop()

    db_info_after = get_db_info()
    host_cpus = psutil.cpu_count(logical=True)
    host_ram_gb = psutil.virtual_memory().total / (1073741824)

    # ---- Report ----
    print("\n" + "=" * 60)
    print("  PROFILING RESULTS")
    print("=" * 60)
    print(f"  Test duration       : {len(metrics.cpu_samples) * 0.5:.1f} s")
    print(f"  Database size       : {db_info_after['size_mb']:.1f} MB")
    print(f"  CPU average         : {metrics.cpu_avg:.1f} %")
    print(f"  CPU 95th percentile : {metrics.cpu_peak:.1f} %")
    print(f"  CPU max             : {metrics.cpu_max:.1f} %")
    print(f"  RAM average         : {metrics.ram_avg:.1f} MB")
    print(f"  RAM 95th percentile : {metrics.ram_peak:.1f} MB")
    print(f"  RAM max             : {metrics.ram_max:.1f} MB")
    print(f"  System disk read    : {metrics.disk_read_mb:.1f} MB")
    print(f"  System disk write   : {metrics.disk_write_mb:.1f} MB")
    print(f"  Host                : {host_cpus} CPUs, {host_ram_gb:.1f} GB RAM")
    print("=" * 60)

    # Persist for report generation
    import json
    report = {
        "duration_s": len(metrics.cpu_samples) * 0.5,
        "db_size_mb": db_info_after["size_mb"],
        "records": {k: db_info_after[k] for k in
                    ("products", "sales", "sale_items", "payments")},
        "cpu_avg_pct": metrics.cpu_avg,
        "cpu_peak_pct": metrics.cpu_peak,
        "cpu_max_pct": metrics.cpu_max,
        "ram_avg_mb": metrics.ram_avg,
        "ram_peak_mb": metrics.ram_peak,
        "ram_max_mb": metrics.ram_max,
        "disk_read_mb": metrics.disk_read_mb,
        "disk_write_mb": metrics.disk_write_mb,
        "host_cpus": host_cpus,
        "host_ram_gb": host_ram_gb,
    }
    with open(_TMP / "profiling_results.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\nRaw results saved to {_TMP / 'profiling_results.json'}")


if __name__ == "__main__":
    main()
