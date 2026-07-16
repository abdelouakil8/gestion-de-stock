"""Phase B visual capture harness — renders every main screen in all four
language x theme combinations to PNG, offscreen, against a seeded live API.

Combos: (fr, light) (fr, dark) (ar, light) (ar, dark). Arabic sets the app
layout direction to RightToLeft, so the captures show real RTL mirroring, not
just translated text.

Usage:  python scripts/ui_capture.py [out_dir]
Output: <out_dir>/<screen>_<lang>_<mode>.png  (+ a manifest.txt)
"""

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_TMP = Path(tempfile.mkdtemp(prefix="pos_ui_capture_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'cap.db').as_posix()}"
os.environ["MEDIA_DIR"] = str(_TMP / "media")
os.environ["API_PORT"] = "8790"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))
sys.path.insert(0, str(PROJECT_ROOT / "frontend"))

from app.core.security import hash_pin  # noqa: E402

PIN = "1234"
os.environ["PIN_HASH"] = hash_pin(PIN)

import httpx  # noqa: E402
import uvicorn  # noqa: E402
from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.core.config import settings as backend_settings  # noqa: E402

backend_settings.database_url = os.environ["DATABASE_URL"]
backend_settings.pin_hash = os.environ["PIN_HASH"]
backend_settings.api_port = int(os.environ["API_PORT"])
backend_settings.media_dir = Path(os.environ["MEDIA_DIR"])

from app.main import app as fastapi_app  # noqa: E402
from services.api_client import ApiClient  # noqa: E402

OUT = (
    Path(sys.argv[1]) if len(sys.argv) > 1 else (PROJECT_ROOT / "scripts" / "captures")
)
OUT.mkdir(parents=True, exist_ok=True)

COMBOS = [("fr", "light"), ("fr", "dark"), ("ar", "light"), ("ar", "dark")]
MANIFEST: list[str] = []


def start_api() -> None:
    config = uvicorn.Config(
        fastapi_app,
        host=backend_settings.api_host,
        port=backend_settings.api_port,
        log_config=None,
    )
    threading.Thread(target=uvicorn.Server(config).run, daemon=True).start()
    base = f"http://{backend_settings.api_host}:{backend_settings.api_port}"
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            if httpx.get(base + "/", timeout=1.0).status_code == 200:
                return
        except httpx.HTTPError:
            time.sleep(0.15)
    raise RuntimeError("API did not start")


def pump(app: QApplication, seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)


def seed(api: ApiClient) -> dict:
    store = api.create_store("Boutique Démo")
    sid = store["id"]
    cat_boissons = api.create_category(sid, "Boissons")
    api.create_category(sid, "Épicerie")
    products = []
    catalog = [
        ("Eau minérale 1.5L", "6130000000015", "25.00", "40.00", 50, 5),
        ("Café Torréfié عربي", "6130000000022", "60.00", "90.00", 40, 5),
        ("Savon presque épuisé", None, "10.00", "20.00", 2, 5),
        ("Lait demi-écrémé 1L", "6130000000039", "55.00", "80.00", 120, 10),
        ("Sucre blanc 1kg", "6130000000046", "70.00", "95.00", 0, 8),
        ("Huile de tournesol 5L", "6130000000053", "600.00", "780.00", 15, 4),
    ]
    for name, bc, cost, detail, stock, thr in catalog:
        p = api.create_product(
            {
                "store_id": sid,
                "name": name,
                "barcode": bc,
                "category_id": cat_boissons["id"] if "Eau" in name else None,
                "cost_price": cost,
                "price_detail": detail,
                "price_gros": f"{float(detail) * 0.92:.2f}",
                "price_super_gros": f"{float(detail) * 0.85:.2f}",
                "stock_quantity": stock,
                "low_stock_threshold": thr,
            }
        )
        products.append(p)
    cust = api.create_customer(
        {"store_id": sid, "name": "Ali Benali", "phone": "0550123456"}
    )
    api.create_customer({"store_id": sid, "name": "محمد أمين", "phone": "0661222333"})
    # A couple of sales so stats/ventes/creances/alerts have data.
    api.checkout(
        sid,
        [{"product_id": products[0]["id"], "quantity": 3, "price_level": "detail"}],
        {"mode": "full"},
    )
    api.checkout(
        sid,
        [{"product_id": products[1]["id"], "quantity": 2, "price_level": "detail"}],
        {"mode": "partial", "amount_paid": "50.00", "customer_id": cust["id"]},
    )
    return store


def apply_combo(app: QApplication, lang: str, mode: str) -> None:
    from ui.i18n import apply_language
    from ui.styles import tokens
    from ui.styles.tokens import render_qss

    apply_language(lang)  # sets strings + app layoutDirection (RTL for ar)
    app.setStyleSheet(render_qss("#2563EB", mode, {}))
    app.setPalette(tokens.build_palette())


def build_screens(api: ApiClient, store: dict) -> list[tuple[str, object]]:
    sid = store["id"]
    from ui.screens.alerts import AlertsScreen
    from ui.screens.checkout import CheckoutScreen
    from ui.screens.creances import CreancesScreen
    from ui.screens.customers import CustomersScreen
    from ui.screens.dashboard import DashboardScreen
    from ui.screens.inventory import InventoryScreen
    from ui.screens.settings_screen import SettingsScreen
    from ui.screens.statistics import StatisticsScreen
    from ui.screens.suppliers import SuppliersScreen
    from ui.screens.ventes import VentesScreen

    noop = lambda *a, **k: None  # noqa: E731
    return [
        ("dashboard", DashboardScreen(api, sid, on_open_alerts=noop)),
        ("checkout", CheckoutScreen(api, sid)),
        ("inventory", InventoryScreen(api, sid)),
        ("customers", CustomersScreen(api, sid)),
        ("ventes", VentesScreen(api, sid, on_view_product=noop)),
        ("creances", CreancesScreen(api, sid)),
        ("statistics", StatisticsScreen(api, sid)),
        ("suppliers", SuppliersScreen(api, sid)),
        ("alerts", AlertsScreen(api, sid, noop, noop)),
        ("settings", SettingsScreen(api, store)),
    ]


def capture(app: QApplication, api: ApiClient, store: dict) -> None:
    for lang, mode in COMBOS:
        apply_combo(app, lang, mode)
        pump(app, 0.1)
        for name, screen in build_screens(api, store):
            try:
                screen.setLayoutDirection(app.layoutDirection())
                screen.resize(1280, 820)
                screen.show()
                if hasattr(screen, "refresh"):
                    try:
                        screen.refresh()
                    except Exception as exc:  # noqa: BLE001
                        print(f"    refresh() warn {name}: {exc}")
                pump(app, 1.1)
                pixmap = screen.grab()
                path = OUT / f"{name}_{lang}_{mode}.png"
                pixmap.save(str(path))
                screen.close()
                MANIFEST.append(f"{path.name}\t{pixmap.width()}x{pixmap.height()}")
                print(f"  ✅ {name} [{lang}/{mode}] -> {path.name}")
            except Exception as exc:  # noqa: BLE001
                print(f"  ❌ {name} [{lang}/{mode}]: {type(exc).__name__}: {exc}")
                MANIFEST.append(f"{name}_{lang}_{mode}.png\tFAILED: {exc}")
            finally:
                app.processEvents()


def main() -> int:
    start_api()
    app = QApplication(sys.argv)
    # Register the bundled Arabic font as a fallback (the UI QSS asks for
    # "Segoe UI", which covers Arabic on Windows; Amiri is a safety net).
    amiri = PROJECT_ROOT / "backend" / "app" / "assets" / "fonts" / "Amiri-Regular.ttf"
    if amiri.exists():
        QFontDatabase.addApplicationFont(str(amiri))

    api = ApiClient(backend_settings.api_host, backend_settings.api_port)
    api.pin = PIN
    from services import image_cache

    image_cache.init(api)
    store = seed(api)
    capture(app, api, store)

    (OUT / "manifest.txt").write_text("\n".join(MANIFEST), encoding="utf-8")
    print(
        f"\n{len([m for m in MANIFEST if 'FAILED' not in m])} captures written to {OUT}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
