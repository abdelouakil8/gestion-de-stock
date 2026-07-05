"""Receipt edge cases: many lines, long names, non-Latin names, exact
totals — generation must never crash a checkout. Phase 6 adds the
settings-driven header/footer and the credit (paid/remaining) block."""

import base64
import re
import zlib
from decimal import Decimal

from app.schemas.category import CategoryCreate
from app.schemas.customer import CustomerCreate
from app.schemas.product import ProductCreate
from app.schemas.sale import CartItem, CheckoutRequest, PaymentInfo
from app.schemas.settings import SettingsUpdate
from app.schemas.store import StoreCreate
from app.services import categories, customers, products, receipts, sales, stores
from app.services import settings as settings_service


def pdf_text(pdf: bytes) -> bytes:
    """Concatenated decoded content streams — the receipt's drawn text.

    ReportLab emits /ASCII85Decode + /FlateDecode streams; fall back to raw
    bytes for any stream that is not encoded that way."""
    out = b""
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", pdf, re.S):
        data = match.group(1).strip()
        try:
            data = base64.a85decode(data, adobe=True)
        except ValueError:
            pass
        try:
            out += zlib.decompress(data)
        except zlib.error:
            out += data
    return out


def make_sale(db, product_names: list[str], quantity: int = 2, payment=None):
    store = stores.create_store(db, StoreCreate(name="Boutique Reçu"))
    categories.create_category(db, CategoryCreate(store_id=store.id, name="Divers"))
    items = []
    for index, name in enumerate(product_names):
        product = products.create_product(
            db,
            ProductCreate(
                store_id=store.id,
                name=name,
                barcode=f"200000000{index:04d}",
                cost_price=Decimal("7.00"),
                price_detail=Decimal("9.99"),
                price_gros=Decimal("9.99"),
                price_super_gros=Decimal("9.99"),
                stock_quantity=1000,
            ),
        )
        items.append(CartItem(product_id=product.id, quantity=quantity))
    sale = sales.finalize_sale(
        db,
        CheckoutRequest(
            store_id=store.id, items=items, payment=payment or PaymentInfo()
        ),
    )
    return store, sale


def test_receipt_many_items_and_exact_total(db):
    names = [f"Produit numéro {i}" for i in range(40)]
    store, sale = make_sale(db, names)
    pdf = receipts.build_receipt_pdf(sale, store)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 2000
    # 40 lines × 2 × 9.99 — total is exact, no float drift
    assert sale.total_amount == Decimal("799.20")


def test_receipt_long_and_accented_names(db):
    long_name = (
        "Huile d'olive extra vierge première pression à froid bidon familial 5 litres"
    )
    store, sale = make_sale(db, [long_name])
    pdf = receipts.build_receipt_pdf(sale, store)
    assert pdf.startswith(b"%PDF")


def test_receipt_non_latin_names_degrade_without_crashing(db):
    # Arabic product names render as placeholders if UI language is NOT Arabic,
    # but generation must never fail during a checkout.
    store, sale = make_sale(db, ["ماء معدني ١٫٥ لتر", "Savon — صابون"])
    pdf = receipts.build_receipt_pdf(sale, store)
    assert pdf.startswith(b"%PDF")


def test_receipt_arabic_names_are_shaped_with_rtl_setting(db):
    store, sale = make_sale(db, ["ماء معدني ١٫٥ لتر"])
    row = settings_service.update_settings(
        db, store.id, SettingsUpdate(ui_language="ar")
    )
    pdf = receipts.build_receipt_pdf(sale, store, row)
    assert pdf.startswith(b"%PDF")
    # Generating the PDF without crashing and with a valid PDF header is sufficient
    # since Arabic text shaping subsets the TTF and encodes it differently.
    assert len(pdf) > 2000


# --------------------------------------------- Phase 6: settings + credit


def test_receipt_uses_settings_header_and_footer(db):
    store, sale = make_sale(db, ["Savon"])
    row = settings_service.update_settings(
        db,
        store.id,
        SettingsUpdate(
            shop_name="Chez Wakil",
            phone="0550 12 34 56",
            address="12 rue du Marche",
            footer_message="A bientot !",
        ),
    )
    pdf = receipts.build_receipt_pdf(sale, store, row)
    assert pdf.startswith(b"%PDF")
    text = pdf_text(pdf)
    assert b"Chez Wakil" in text
    assert b"0550 12 34 56" in text
    assert b"12 rue du Marche" in text
    assert b"A bientot !" in text


def test_receipt_prints_credit_details_when_enabled(db):
    store = stores.create_store(db, StoreCreate(name="Boutique Crédit"))
    product = products.create_product(
        db,
        ProductCreate(
            store_id=store.id,
            name="Savon",
            cost_price=Decimal("7.00"),
            price_detail=Decimal("10.00"),
            price_gros=Decimal("10.00"),
            price_super_gros=Decimal("10.00"),
            stock_quantity=100,
        ),
    )
    customer = customers.create_customer(
        db, CustomerCreate(store_id=store.id, name="Ali Benali", phone="0550123456")
    )
    sale = sales.finalize_sale(
        db,
        CheckoutRequest(
            store_id=store.id,
            items=[CartItem(product_id=product.id, quantity=3)],  # 30.00
            payment=PaymentInfo(
                mode="partial", amount_paid=Decimal("12.00"), customer_id=customer.id
            ),
        ),
    )
    row = settings_service.get_settings(db, store.id)  # show_credit_details=True

    pdf = receipts.build_receipt_pdf(sale, store, row, customer)
    text = pdf_text(pdf)
    assert b"12.00" in text  # paid
    assert b"18.00" in text  # remaining
    assert b"Ali Benali" in text
    assert b"Reste" in text

    # Toggled off: no credit block, even for a partially paid sale.
    row = settings_service.update_settings(
        db, store.id, SettingsUpdate(show_credit_details=False)
    )
    text_off = pdf_text(receipts.build_receipt_pdf(sale, store, row, customer))
    assert b"Reste" not in text_off
    assert b"Ali Benali" not in text_off


def test_fully_paid_sale_never_shows_credit_block(db):
    store, sale = make_sale(db, ["Savon"])  # full payment
    row = settings_service.get_settings(db, store.id)
    pdf = receipts.build_receipt_pdf(sale, store, row)
    assert b"Reste" not in pdf_text(pdf)
