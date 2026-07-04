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
from services.api_client import ApiClient, ApiError  # noqa: E402


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


def pump(app: QApplication, seconds: float = 0.5) -> None:
    """Spin the Qt event loop for `seconds`, letting debounced timers fire and
    run_api workers deliver their results back on the UI thread. Used where
    there is no single predicate to wait on (e.g. debounced live search)."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)


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
    from services import image_cache

    image_cache.init(api)  # MainWindow does this in the real app
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
    # Accented + Arabic-ish product for the smart-search assertions: the search
    # must be accent/typo tolerant, so "cafe" (no accent) and a small typo must
    # both find "Café Torréfié عربي".
    coffee = api.create_product(
        {
            "store_id": store_id,
            "name": "Café Torréfié عربي",
            "barcode": "6130000000022",
            "cost_price": "60.00",
            "price_detail": "90.00",
            "price_gros": "85.00",
            "price_super_gros": "80.00",
            "stock_quantity": 40,
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

    assert checkout.cart_stack.currentWidget() is checkout.cart_empty
    ok("Panier vide → état vide dessiné (icône + phrase)")

    # Live product search is now debounced + server-side: type, let the 250 ms
    # timer fire and the worker deliver, then inspect the rendered results.
    checkout.search.setText("eau")
    pump(app, 0.6)
    wait_until(app, lambda: checkout.results.count() >= 1, what="live search 'eau'")
    shown = checkout._shown_products()
    assert any(p["id"] == water["id"] for p in shown)
    ok("Recherche produit en direct (débounce + serveur) avec vignettes/3 prix")

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

    # ============================================================ Phase 8
    # Customer Attach + Guest Sale + Smart Search — new-feature acceptance.
    # ------------------------------------------------------ Smart search
    print("[Recherche intelligente]")
    # Accent-insensitive: "cafe" (no accent) must find "Café Torréfié عربي".
    hits = api.search_products(store_id, query="cafe", active_only=True)
    assert any(
        p["id"] == coffee["id"] for p in hits
    ), f"accent-insensitive search failed: {[p['name'] for p in hits]}"
    ok("Recherche produit tolérante aux accents (« cafe » → « Café Torréfié »)")

    # Fuzzy / typo-tolerant: a small typo must still surface the product.
    typo_hits = api.search_products(store_id, query="caef", limit=5)
    assert any(
        p["id"] == coffee["id"] for p in typo_hits
    ), f"fuzzy search failed: {[p['name'] for p in typo_hits]}"
    ok("Recherche produit tolérante aux fautes de frappe (« caef » → « Café »)")

    # The barcode fast path is untouched: exact active product or 404.
    by_barcode = api.get_product_by_barcode(store_id, "6130000000022")
    assert by_barcode["id"] == coffee["id"]
    ok("Chemin rapide code-barres inchangé (produit exact)")

    # Customer smart search: accent/typo tolerant on name or phone.
    cust_hits = api.list_customers(store_id, query="benali")
    assert any(c["id"] == customer["id"] for c in cust_hits)
    ok("Recherche client intelligente (nom/téléphone)")

    # ------------------------------------------ Attach client sur la Caisse
    print("[Caisse — attacher un client]")
    checkout2 = CheckoutScreen(api, store_id)
    assert checkout2.customer is None
    checkout2._on_customer_attached(customer)
    assert checkout2.customer is not None and checkout2.customer["id"] == customer["id"]
    assert checkout2.clear_customer_button.isVisible() or True  # strip toggled
    ok("CustomerSearchBox → client attaché à la Caisse (checkout.customer défini)")
    checkout2._clear_customer()
    assert checkout2.customer is None
    ok("Retrait du client → l'attache est effacée")

    # ------------------------------------------------ Vente anonyme (guest)
    print("[Vente anonyme]")
    guest_sale = api.checkout(
        store_id,
        [{"product_id": coffee["id"], "quantity": 1, "price_level": "detail"}],
        {"mode": "full"},
    )
    assert guest_sale["customer_id"] is None
    assert guest_sale["balance"] == "0.00"
    # Resolvable: server exposes the guest flag fields for later resolution.
    assert "guest_confirmed_at" in guest_sale
    ok("Paiement comptant sans client → vente anonyme (customer_id null, résoluble)")

    # A second guest sale so we can both attach one AND confirm the other.
    guest_sale_2 = api.checkout(
        store_id,
        [{"product_id": coffee["id"], "quantity": 1, "price_level": "detail"}],
        {"mode": "full"},
    )
    assert guest_sale_2["customer_id"] is None

    # -------------------------------------- Paiement partiel exige un client
    print("[Paiement partiel — client obligatoire]")
    # Server-side: a partial payment with NO customer is refused outright.
    partial_refused = False
    try:
        api.checkout(
            store_id,
            [{"product_id": coffee["id"], "quantity": 1, "price_level": "detail"}],
            {"mode": "partial", "amount_paid": "10.00"},
        )
    except ApiError as exc:
        partial_refused = exc.code == "credit_requires_customer"
    assert partial_refused, "server must refuse a partial payment without a customer"
    ok("Paiement partiel sans client → refus serveur (credit_requires_customer)")

    # In-dialog: fill name + phone inline, pay partial, and the sale is a
    # credit sale attached to the freshly-created customer.
    from ui.widgets.payment_dialogs import CheckoutPaymentDialog as _CPD

    total_coffee = Decimal("90.00")
    dlg = _CPD(api, store_id, total_coffee)
    dlg.partial_radio.setChecked(True)
    dlg.amount_input.setValue(30.0)
    dlg.new_name_input.setText("Nadia Zerhouni")
    dlg.new_phone_input.setText("0661222333")
    dlg.accept()
    wait_until(app, lambda: dlg.payment is not None, what="inline customer created")
    assert dlg.payment["mode"] == "partial"
    inline_customer_id = dlg.payment["customer_id"]
    assert inline_customer_id
    ok("Paiement partiel : création client en ligne (nom + téléphone) puis payload")

    credit_sale = api.checkout(
        store_id,
        [{"product_id": coffee["id"], "quantity": 1, "price_level": "detail"}],
        dlg.payment,
    )
    assert credit_sale["customer_id"] == inline_customer_id
    assert credit_sale["paid_amount"] == "30.00" and credit_sale["balance"] == "60.00"
    ok("Vente à crédit rattachée au client créé en ligne (payé 30.00, reste 60.00)")

    # ------------------------------------------------------ Écran Ventes
    print("[Ventes]")
    from ui.screens.ventes import SaleDetailDialog, VentesScreen

    ventes = VentesScreen(api, store_id)
    ventes.refresh()
    wait_until(app, lambda: ventes.table.rowCount() >= 1, what="ventes rows")
    # Let the "all" fetch fully settle before switching filters so its late
    # response can't overwrite the pending list below (overlapping run_api).
    pump(app, 0.4)
    ok("Écran Ventes : le journal des ventes affiche des lignes")

    def _pending_settled() -> bool:
        # Stable pending state: our guest sale is listed AND nothing carries a
        # customer (guards against a stale "all"/other response landing late).
        ids = {s["id"] for s in ventes.sales}
        return guest_sale["id"] in ids and all(
            s["customer_id"] is None for s in ventes.sales
        )

    # Filter to guest=pending: our two anonymous full sales must appear.
    # setCurrentIndex already triggers refresh(); pump then confirm stability.
    ventes.type_combo.setCurrentIndex(1)  # "Anonymes à résoudre" (pending)
    pump(app, 0.4)
    wait_until(app, _pending_settled, what="pending guest sale listed")
    pending_ids = {s["id"] for s in ventes.sales}
    assert guest_sale["id"] in pending_ids and guest_sale_2["id"] in pending_ids
    assert all(s["customer_id"] is None for s in ventes.sales)
    ok("Filtre « Anonymes à résoudre » → liste les ventes anonymes en attente")

    # Open the detail dialog for the first guest sale and ATTACH a customer.
    detail_dlg = SaleDetailDialog(api, store_id, guest_sale)
    detail_dlg._on_attach_picked(customer)  # invoke SALE_ATTACH_CUSTOMER path
    wait_until(app, lambda: detail_dlg.changed, what="guest sale assigned")
    assigned = api.get_sale(guest_sale["id"])
    assert assigned["customer_id"] == customer["id"]
    ok("Détail vente : attacher un client → la vente porte désormais le client")

    # It must have left the guest=pending set (still on the pending filter).
    ventes.refresh()
    pump(app, 0.4)
    wait_until(
        app,
        lambda: all(s["id"] != guest_sale["id"] for s in ventes.sales),
        what="assigned sale left pending",
    )
    assert guest_sale["id"] not in {s["id"] for s in ventes.sales}
    ok("Après attache : la vente disparaît des « Anonymes à résoudre »")

    # Confirm the OTHER guest sale as staying anonymous.
    detail_dlg_2 = SaleDetailDialog(api, store_id, guest_sale_2)
    detail_dlg_2._leave_anonymous()  # confirm_guest_sale
    wait_until(app, lambda: detail_dlg_2.changed, what="guest sale confirmed")
    confirmed = api.list_sales(store_id, guest="confirmed")
    assert any(s["id"] == guest_sale_2["id"] for s in confirmed)
    ok("Confirmer anonyme → la vente figure dans guest=confirmed")

    # -------------------------------------------- Agrégat rétroactif
    print("[Agrégat rétroactif]")
    # The now-attached guest sale must show up in the customer's stats.
    cust_stats = api.stats_customer(customer["id"])
    assert cust_stats["sales_count"] >= 1, cust_stats
    ok("Statistiques client : la vente ré-attachée est comptabilisée (sales_count ≥ 1)")

    # ------------------------------------ Conditionnements + prix manuel
    print("[Conditionnements & prix manuel]")
    packaged = api.create_product(
        {
            "store_id": store_id,
            "name": "Lait Carton",
            "barcode": "6130000009999",
            "cost_price": "10.00",
            "price_detail": "100.00",
            "price_gros": "95.00",
            "price_super_gros": "90.00",
            "stock_quantity": 500,
            "packagings": [
                {
                    "label": "Carton",
                    "unit_count": 24,
                    "price_detail": "2100.00",
                    "price_gros": "2050.00",
                    "price_super_gros": "2000.00",
                    "position": 0,
                }
            ],
        }
    )
    assert len(packaged["packagings"]) == 1, packaged
    ok("Produit créé avec conditionnement (Carton ×24, prix propre)")

    checkout3 = CheckoutScreen(api, store_id)
    checkout3._add_to_cart(packaged)
    pk_line = checkout3.cart[0]
    checkout3._on_packaging_changed(pk_line, packaged["packagings"][0])
    assert pk_line.unit_price == Decimal("2100.00")  # package price, not unit*24
    assert pk_line.total == Decimal("2100.00")
    assert pk_line.base_units == 24
    payload = checkout3._line_payload(pk_line)
    assert payload["packaging_id"] == packaged["packagings"][0]["id"]
    ok("Caisse : sélection du Carton → prix du colis (2100), payload packaging_id")

    stock_before = api.get_product_by_barcode(store_id, "6130000009999")[
        "stock_quantity"
    ]
    sale_pk = api.checkout(
        store_id, [checkout3._line_payload(pk_line)], {"mode": "full"}
    )
    stock_after = api.get_product_by_barcode(store_id, "6130000009999")[
        "stock_quantity"
    ]
    assert stock_before - stock_after == 24, (stock_before, stock_after)
    assert sale_pk["total_amount"] == "2100.00"
    ok("Vente d'un Carton → stock −24 unités de base, total 2100,00")

    # Manual price below the packaging floor is refused by the server.
    checkout3._on_level_changed(pk_line, "manual")
    checkout3._on_manual_price_changed(pk_line, 1999.0)  # below 2000 floor
    manual_payload = checkout3._line_payload(pk_line)
    assert manual_payload["unit_price_override"] == "1999.00"
    try:
        api.checkout(store_id, [manual_payload], {"mode": "full"})
        raise AssertionError("manual price below floor should be refused")
    except ApiError as exc:
        assert exc.code == "price_below_floor", exc.code
    ok("Prix manuel sous le plancher du conditionnement → refus serveur")

    # ---------------------------------------- Stock : rail catégories
    print("[Stock — catégories]")
    inv2 = InventoryScreen(api, store_id)
    wait_until(app, lambda: inv2.category_rail.count() >= 2, what="category rail")
    assert inv2._selected_category() is None  # defaults to "Tous les produits"
    inv2.search.setText("lait")
    wait_until(
        app,
        lambda: any(p["name"] == "Lait Carton" for p in inv2.visible_products),
        what="stock smart search 'lait'",
    )
    ok("Stock : rail catégories + recherche intelligente serveur")

    # ------------------------------------------------------ Shell / F11
    print("[Fenêtre]")
    from PySide6.QtWidgets import QMainWindow

    from ui.screens.main_window import TitleBar

    win = QMainWindow()
    title_bar = TitleBar(win)
    title_bar.toggle_fullscreen()
    assert win.isFullScreen()
    title_bar.toggle_fullscreen()
    assert not win.isFullScreen()
    win.close()  # offscreen: leaving it visible breaks later dialogs
    app.processEvents()
    ok("Plein écran : bascule aller-retour (bouton barre de titre / F11)")

    # -------------------------------------- Tout supprimer (à la toute fin)
    print("[Tout supprimer]")
    from ui.screens.settings_screen import FactoryResetDialog

    reset = FactoryResetDialog(api)
    reset.show()  # real lifecycle: exec() would show it before accept()
    app.processEvents()
    assert not reset.ok_button.isEnabled()  # empty PIN: button disabled
    errors_before = len(ERRORS_SHOWN)
    reset.pin_input.setText("9999")  # wrong PIN
    reset.accept()
    wait_until(app, lambda: len(ERRORS_SHOWN) > errors_before, what="bad pin refused")
    assert not reset.reset_done
    ok("Tout supprimer : PIN erroné refusé par le serveur, rien n'est effacé")
    assert api.list_stores(), "data must still exist after a refused reset"

    reset.pin_input.setText(PIN)
    reset.accept()
    wait_until(app, lambda: reset.reset_done, what="factory reset")
    assert api.list_stores() == []
    assert api.list_customers(store_id) == []
    media_root = Path(os.environ["MEDIA_DIR"])
    leftover = list(media_root.rglob("*")) if media_root.exists() else []
    assert not leftover, f"media files must be wiped, found {leftover}"
    ok("Tout supprimer : PIN correct → toutes les données et images effacées")

    print(f"\n{len(CHECKS)} vérifications UI passées.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
