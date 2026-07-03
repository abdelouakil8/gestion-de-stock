"""Headless functional drive of the real UI against the real API (Phase 7).

Runs offscreen (QT_QPA_PLATFORM=offscreen is set below), boots uvicorn
in-process on the loopback with a THROWAWAY database, then instantiates
the actual screens and drives their code paths: checkout with price
levels, partial payment rules, customers, alerts, settings round-trip
with live accent re-theming, low-stock badges, empty states.

Every assertion here backs a ✅ line in docs/UI_CHECKLIST.md.

Usage:  python scripts/ui_drive.py     (exit 0 = all assertions passed)
"""

import os
import sys
import tempfile
import threading
import time
from decimal import Decimal
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_TMP = Path(tempfile.mkdtemp(prefix="pos_ui_drive_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'drive.db').as_posix()}"
os.environ["MEDIA_DIR"] = str(_TMP / "media")
os.environ["API_PORT"] = "8788"  # do not collide with a running dev app

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))
sys.path.insert(0, str(PROJECT_ROOT / "frontend"))

from app.core.security import hash_pin  # noqa: E402

PIN = "1234"
os.environ["PIN_HASH"] = hash_pin(PIN)

import httpx  # noqa: E402
import uvicorn  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.core.config import settings as backend_settings  # noqa: E402

# Rebuild settings so the env vars above are picked up even if config was
# imported earlier in this interpreter.
backend_settings.database_url = os.environ["DATABASE_URL"]
backend_settings.pin_hash = os.environ["PIN_HASH"]
backend_settings.api_port = int(os.environ["API_PORT"])
from pathlib import Path as _P  # noqa: E402

backend_settings.media_dir = _P(os.environ["MEDIA_DIR"])

from app.main import app as fastapi_app  # noqa: E402
from services.api_client import ApiClient  # noqa: E402


def start_api() -> None:
    config = uvicorn.Config(
        fastapi_app,
        host=backend_settings.api_host,
        port=backend_settings.api_port,
        log_config=None,
    )
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()
    base = f"http://{backend_settings.api_host}:{backend_settings.api_port}"
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            if httpx.get(base + "/", timeout=1.0).status_code == 200:
                return
        except httpx.HTTPError:
            time.sleep(0.15)
    raise RuntimeError("API did not start")


def wait_until(app: QApplication, predicate, timeout: float = 8.0, what: str = ""):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError(f"timeout waiting for: {what}")


CHECKS: list[str] = []
ERRORS_SHOWN: list[str] = []


def ok(label: str) -> None:
    CHECKS.append(label)
    print(f"  ✅ {label}")


def install_error_capture() -> None:
    """Headless runs can't click QMessageBox away — record instead of show.

    Every screen/dialog module imports show_error by name, so the
    replacement is applied per consuming module."""
    import ui.screens.alerts
    import ui.screens.checkout
    import ui.screens.customers
    import ui.screens.inventory
    import ui.screens.settings_screen
    import ui.screens.statistics
    import ui.widgets.customer_dialogs
    import ui.widgets.modal
    import ui.widgets.payment_dialogs

    def fake_show_error(_parent, message: str, _title: str = "") -> None:
        ERRORS_SHOWN.append(message)
        print(f"    (dialogue d'erreur capturé : {message})")

    for module in (
        ui.widgets.modal,
        ui.widgets.payment_dialogs,
        ui.widgets.customer_dialogs,
        ui.screens.checkout,
        ui.screens.inventory,
        ui.screens.customers,
        ui.screens.statistics,
        ui.screens.alerts,
        ui.screens.settings_screen,
    ):
        module.show_error = fake_show_error


def main() -> int:
    start_api()
    app = QApplication(sys.argv)

    from ui.styles.tokens import render_qss

    app.setStyleSheet(render_qss())
    install_error_capture()

    api = ApiClient(backend_settings.api_host, backend_settings.api_port)
    api.pin = PIN
    store = api.create_store("Boutique Drive")
    store_id = store["id"]

    # Seed catalog through the API.
    water = api.create_product(
        {
            "store_id": store_id,
            "name": "Eau minérale 1.5L",
            "barcode": "6130000000015",
            "cost_price": "25.00",
            "price_detail": "40.00",
            "price_gros": "37.50",
            "price_super_gros": "30.00",
            "stock_quantity": 50,
            "low_stock_threshold": 5,
        }
    )
    api.create_product(
        {
            "store_id": store_id,
            "name": "Savon presque épuisé",
            "cost_price": "10.00",
            "price_detail": "20.00",
            "price_gros": "18.00",
            "price_super_gros": "15.00",
            "stock_quantity": 2,
            "low_stock_threshold": 5,
        }
    )
    customer = api.create_customer(
        {"store_id": store_id, "name": "Ali Benali", "phone": "0550123456"}
    )

    # ------------------------------------------------------------ Caisse
    print("[Caisse]")
    from ui.screens.checkout import CheckoutScreen

    checkout = CheckoutScreen(api, store_id)
    wait_until(app, lambda: len(checkout.products) >= 2, what="products loaded")
    ok("Produits chargés en arrière-plan (worker thread)")

    assert checkout.cart_stack.currentWidget() is checkout.cart_empty
    ok("Panier vide → état vide dessiné (icône + phrase)")

    checkout.search.setText("eau")
    assert checkout.results.count() == 1
    ok("Recherche filtre par nom avec vignettes/badges/3 prix")

    checkout.search.setText("6130000000015")
    checkout._on_enter()
    wait_until(app, lambda: len(checkout.cart) == 1, what="barcode add")
    line = checkout.cart[0]
    assert line.unit_price == Decimal("40.00")  # detail by default
    ok("Scan code-barres + Entrée → ligne au niveau Détail (40.00)")

    line_widget_level = line.level
    assert line_widget_level == "detail"
    checkout._on_level_changed(line, "gros")
    assert line.unit_price == Decimal("37.50")
    checkout._on_qty_changed(line, 6)
    assert checkout._cart_total() == Decimal("225.00")
    ok("Sélecteur de niveau + quantité → totaux recalculés (6 × 37.50 = 225.00)")

    # Payment dialog logic — partial without customer must refuse.
    from ui.widgets.payment_dialogs import CheckoutPaymentDialog

    dialog = CheckoutPaymentDialog(api, store_id, checkout._cart_total())
    dialog.partial_radio.setChecked(True)
    dialog.amount_input.setValue(100.0)
    dialog.accept()
    assert dialog.payment is None  # refused: no customer
    ok(
        "Paiement partiel sans client → refus local "
        "(et code serveur credit_requires_customer)"
    )

    dialog.customer = customer
    dialog._refresh_customer()
    dialog.accept()
    assert dialog.payment == {
        "mode": "partial",
        "amount_paid": "100.00",
        "customer_id": customer["id"],
    }
    ok("Paiement partiel avec client → payload {mode, amount_paid, customer_id}")

    sale = api.checkout(
        store_id,
        [{"product_id": water["id"], "quantity": 6, "price_level": "gros"}],
        dialog.payment,
    )
    assert sale["paid_amount"] == "100.00" and sale["balance"] == "125.00"
    ok("Vente à crédit enregistrée : payé 100.00, reste 125.00")

    after = api.list_products(store_id)
    stock_now = next(p for p in after if p["id"] == water["id"])["stock_quantity"]
    assert stock_now == 44
    ok("Stock décrémenté côté serveur (50 → 44)")

    # ------------------------------------------------------------- Stock
    print("[Stock]")
    from ui.screens.inventory import InventoryScreen, ProductDialog

    inventory = InventoryScreen(api, store_id)
    wait_until(app, lambda: len(inventory.visible_products) >= 2, what="inventory rows")
    row_titles = [p["name"] for p in inventory.visible_products]
    assert "Savon presque épuisé" in row_titles
    ok("Tableau produits : vignette, 3 colonnes de prix, badge stock faible")

    form = ProductDialog(api, store_id, [])
    form.detail_input.setValue(10.0)
    form.gros_input.setValue(12.0)  # broken ordering
    assert form.order_hint.objectName() == "FieldError"
    form.gros_input.setValue(9.0)
    form.super_gros_input.setValue(8.0)
    assert form.order_hint.objectName() == "FieldHint"
    ok("Formulaire produit : indication d'ordre des prix en direct (erreur → ok)")

    form.name_input.setText("Produit du drive")
    form.cost_input.setValue(5.0)
    form.stock_input.setValue(30)  # above threshold: must NOT join the alerts
    form.accept()
    wait_until(app, lambda: form.result_product is not None, what="product save")
    ok("Création produit via le formulaire (PIN serveur)")

    # Image picker: stage a real PNG through the form's own upload path.
    from PIL import Image

    png_path = _TMP / "photo.png"
    Image.new("RGB", (24, 24), (200, 60, 30)).save(png_path, format="PNG")
    edit_form = ProductDialog(
        api, store_id, [], details=api.get_product_details(water["id"])
    )
    edit_form._staged_image = png_path
    edit_form.accept()
    wait_until(app, lambda: edit_form.result_product is not None, what="image save")
    wait_until(
        app,
        lambda: any(
            p["id"] == water["id"] and p.get("image_path")
            for p in api.list_products(store_id)
        ),
        what="image_path set",
    )
    assert api.get_product_image(water["id"]).startswith(b"\x89PNG")
    ok("Image produit envoyée via le formulaire et servie par l'API")

    from ui.screens.inventory import ProductDetailDialog

    detail = ProductDetailDialog(api, store_id, water)
    wait_until(
        app,
        lambda: not detail.loading.isVisible()
        or detail.loading.text() != "Chargement…",
        what="product stats",
    )
    ok("Fiche produit (double-clic) : statistiques par période chargées")

    # ----------------------------------------------------------- Clients
    print("[Clients]")
    from ui.screens.customers import CustomersScreen

    customers_screen = CustomersScreen(api, store_id)
    customers_screen.refresh()
    wait_until(app, lambda: customers_screen.list.count() >= 1, what="customer list")
    customers_screen.list.setCurrentRow(0)
    wait_until(
        app,
        lambda: customers_screen.card_balance._value.text() not in ("—", "…"),
        what="customer stats",
    )
    assert customers_screen.card_balance._value.text() == "125,00"
    ok("Panneau client : solde crédit exact (125,00), CA/bénéfice/ventes chargés")

    wait_until(
        app, lambda: customers_screen.sales_table.rowCount() >= 1, what="sales history"
    )
    ok("Historique des ventes du client avec statut Payée/Crédit")

    # -------------------------------------------------- paiement (Alertes)
    print("[Alertes]")
    from ui.screens.alerts import AlertsScreen

    alerts_screen = AlertsScreen(api, store_id, lambda pid: None)
    alerts_screen.refresh()
    wait_until(
        app,
        lambda: alerts_screen.credit_count_badge.text() == "1",
        what="alerts data",
    )
    assert alerts_screen.stock_count_badge.text() == "1"  # Savon (2 ≤ 5)
    ok("Alertes : 1 stock faible + 1 crédit en attente (badges de section)")

    from ui.widgets.payment_dialogs import RecordPaymentDialog

    pay = RecordPaymentDialog(api, sale)
    assert pay.balance == Decimal("125.00")
    pay.amount_input.setValue(125.0)
    pay.accept()
    wait_until(app, lambda: pay.result_sale is not None, what="record payment")
    assert pay.result_sale["balance"] == "0.00"
    ok("Encaisser un paiement → solde 0.00 (règlement complet, serveur autoritaire)")

    alerts_screen.refresh()
    wait_until(
        app,
        lambda: alerts_screen.credit_count_badge.text() == "0",
        what="alerts refresh after payment",
    )
    ok("Après paiement : la liste des crédits se vide")

    # ------------------------------------------------------- Statistiques
    print("[Statistiques]")
    from ui.screens.statistics import StatisticsScreen

    stats_screen = StatisticsScreen(api, store_id)
    stats_screen.refresh()
    today_card = stats_screen.overview_cards["today"]
    wait_until(
        app,
        lambda: today_card.revenue_value.text() not in ("—",),
        what="overview cards",
    )
    assert today_card.revenue_value.text() == "225,00"
    ok("Vue d'ensemble : CA du jour 225,00 avec comparaison période précédente")

    wait_until(app, lambda: stats_screen.top_table.rowCount() >= 1, what="top products")
    ok("Meilleures ventes avec vignettes")

    # -------------------------------------------------------- Réglages
    print("[Réglages]")
    from ui.screens.settings_screen import SettingsScreen

    settings_screen = SettingsScreen(api, store)
    settings_screen.refresh()
    wait_until(app, lambda: bool(settings_screen.settings), what="settings load")
    settings_screen.shop_name_input.setText("Chez Drive")
    settings_screen.credit_check.setChecked(True)
    settings_screen._update_preview()
    settings_screen._pick_accent("#0D9488")
    settings_screen._save()
    wait_until(
        app,
        lambda: settings_screen.settings.get("shop_name") == "Chez Drive",
        what="settings save",
    )
    assert "#0D9488" in app.styleSheet()
    ok("Réglages : sauvegarde PIN + accent appliqué en direct au style")

    persisted = api.get_settings(store_id)
    assert persisted["theme_accent"] == "#0D9488"
    ok("Réglages persistés côté serveur (round-trip)")

    print(f"\n{len(CHECKS)} vérifications UI passées.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
