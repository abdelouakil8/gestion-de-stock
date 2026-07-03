"""Standalone demo-data seeder for manual testing — not part of the app.

Usage (from the project root, venv active, after `alembic upgrade head`):

    python scripts/seed_demo.py

Idempotent: refuses to run twice against the same database.

Phase 6: products carry realistic named prices (détail / gros / super
gros) and per-product low-stock thresholds; customers, full and credit
sales (with their Payment history) are seeded too. Product images are
optional — attach them from the app via POST /products/{id}/image.
"""

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import inspect, select  # noqa: E402

from app.db.session import SessionLocal, engine  # noqa: E402
from app.models import Store  # noqa: E402
from app.schemas.category import CategoryCreate  # noqa: E402
from app.schemas.customer import CustomerCreate  # noqa: E402
from app.schemas.product import ProductCreate  # noqa: E402
from app.schemas.sale import (  # noqa: E402
    CartItem,
    CheckoutRequest,
    PaymentInfo,
)
from app.schemas.store import StoreCreate  # noqa: E402
from app.services import (  # noqa: E402
    categories,
    customers,
    payments,
    products,
    sales,
    stores,
)

DEMO_STORE_NAME = "Boutique Démo"

# (category, name, barcode, cost, detail, gros, super_gros, stock, low_stock)
DEMO_PRODUCTS = [
    (
        "Boissons",
        "Eau minérale 1.5L",
        "6130001000012",
        "25.00",
        "40.00",
        "37.50",
        "35.00",
        120,
        24,
    ),
    (
        "Boissons",
        "Jus d'orange 1L",
        "6130001000029",
        "80.00",
        "120.00",
        "112.50",
        "105.00",
        60,
        12,
    ),
    (
        "Épicerie",
        "Riz 5kg",
        "6130002000011",
        "450.00",
        "575.00",
        "550.00",
        "525.00",
        40,
        8,
    ),
    (
        "Épicerie",
        "Huile de tournesol 2L",
        "6130002000028",
        "320.00",
        "420.00",
        "400.00",
        "380.00",
        35,
        10,
    ),
    (
        "Hygiène",
        "Savon de Marseille",
        "6130003000010",
        "45.00",
        "70.00",
        "65.00",
        "60.00",
        200,
        30,
    ),
    (
        "Hygiène",
        "Shampooing familial 750ml",
        "6130003000027",
        "210.00",
        "290.00",
        "275.00",
        "260.00",
        25,
        5,
    ),
    # Deliberately at its threshold so /alerts has something to show.
    (
        "Boissons",
        "Soda cola 2L",
        "6130001000036",
        "95.00",
        "140.00",
        "130.00",
        "120.00",
        4,
        5,
    ),
]

# (name, phone, note)
DEMO_CUSTOMERS = [
    ("Ali Benali", "0550 11 22 33", "Épicier du quartier — passe le mardi"),
    ("Lina Cherif", "0660 44 55 66", None),
    ("Mohamed Haddad", "0770 77 88 99", "Restaurant El Bahdja"),
]


def main() -> int:
    if "stores" not in inspect(engine).get_table_names():
        print(
            "Database not initialized. Run first:  cd backend && alembic upgrade head"
        )
        return 1

    with SessionLocal() as db:
        already = db.scalar(
            select(Store).where(
                Store.name == DEMO_STORE_NAME, Store.deleted_at.is_(None)
            )
        )
        if already is not None:
            print(f"Demo data already present ('{DEMO_STORE_NAME}') — nothing to do.")
            return 0

        store = stores.create_store(db, StoreCreate(name=DEMO_STORE_NAME))
        print(f"Store créé : {store.name} ({store.id})")

        category_by_name = {}
        for cat_name in dict.fromkeys(entry[0] for entry in DEMO_PRODUCTS):
            category = categories.create_category(
                db, CategoryCreate(store_id=store.id, name=cat_name)
            )
            category_by_name[cat_name] = category
            print(f"  Catégorie : {cat_name}")

        product_by_name = {}
        for (
            cat_name,
            name,
            barcode,
            cost,
            detail,
            gros,
            s_gros,
            stock,
            low,
        ) in DEMO_PRODUCTS:
            product = products.create_product(
                db,
                ProductCreate(
                    store_id=store.id,
                    category_id=category_by_name[cat_name].id,
                    name=name,
                    barcode=barcode,
                    cost_price=Decimal(cost),
                    price_detail=Decimal(detail),
                    price_gros=Decimal(gros),
                    price_super_gros=Decimal(s_gros),
                    stock_quantity=stock,
                    low_stock_threshold=low,
                ),
            )
            product_by_name[name] = product
            print(f"    Produit : {name} — {detail}/{gros}/{s_gros}, stock {stock}")

        customer_by_name = {}
        for name, phone, note in DEMO_CUSTOMERS:
            customer = customers.create_customer(
                db, CustomerCreate(store_id=store.id, name=name, phone=phone, note=note)
            )
            customer_by_name[name] = customer
            print(f"  Client : {name} ({phone})")

        # Walk-in sale, fully paid, mixed levels.
        sale = sales.finalize_sale(
            db,
            CheckoutRequest(
                store_id=store.id,
                items=[
                    CartItem(
                        product_id=product_by_name["Eau minérale 1.5L"].id,
                        quantity=6,
                        price_level="gros",
                    ),
                    CartItem(
                        product_id=product_by_name["Savon de Marseille"].id,
                        quantity=2,
                    ),
                ],
            ),
        )
        print(f"  Vente comptant : {sale.total_amount}")

        # Credit sale: partially paid, then one instalment recorded.
        credit = sales.finalize_sale(
            db,
            CheckoutRequest(
                store_id=store.id,
                items=[
                    CartItem(
                        product_id=product_by_name["Riz 5kg"].id,
                        quantity=10,
                        price_level="super_gros",
                    ),
                ],
                payment=PaymentInfo(
                    mode="partial",
                    amount_paid=Decimal("2000.00"),
                    customer_id=customer_by_name["Mohamed Haddad"].id,
                ),
            ),
        )
        payments.record_payment(db, credit.id, Decimal("1500.00"))
        db.refresh(credit)
        print(
            f"  Vente à crédit : {credit.total_amount} "
            f"(payé {credit.paid_amount}, reste {credit.balance})"
        )

        # A second, fully outstanding credit for the alerts screen.
        outstanding = sales.finalize_sale(
            db,
            CheckoutRequest(
                store_id=store.id,
                items=[
                    CartItem(
                        product_id=product_by_name["Jus d'orange 1L"].id,
                        quantity=12,
                        price_level="gros",
                    ),
                ],
                payment=PaymentInfo(
                    mode="partial",
                    amount_paid=Decimal("0.00"),
                    customer_id=customer_by_name["Ali Benali"].id,
                ),
            ),
        )
        print(f"  Crédit en cours : {outstanding.balance} (Ali Benali)")

    print("Seed terminé.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
