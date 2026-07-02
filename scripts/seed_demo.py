"""Standalone demo-data seeder for manual testing — not part of the app.

Usage (from the project root, venv active, after `alembic upgrade head`):

    python scripts/seed_demo.py

Idempotent: refuses to run twice against the same database.
"""

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import inspect, select  # noqa: E402

from app.db.session import SessionLocal, engine  # noqa: E402
from app.models import Store  # noqa: E402
from app.schemas.category import CategoryCreate  # noqa: E402
from app.schemas.price_tier import PriceTierCreate  # noqa: E402
from app.schemas.product import ProductCreate  # noqa: E402
from app.schemas.store import StoreCreate  # noqa: E402
from app.services import categories, price_tiers, products, stores  # noqa: E402

DEMO_STORE_NAME = "Boutique Démo"

# (category, name, barcode, cost, min_sale, stock, tiers[(min_qty, unit_price)])
DEMO_PRODUCTS = [
    ("Boissons", "Eau minérale 1.5L", "6130001000012", "25.00", "30.00", 120,
     [(1, "40.00"), (6, "37.50"), (12, "35.00")]),
    ("Boissons", "Jus d'orange 1L", "6130001000029", "80.00", "95.00", 60,
     [(1, "120.00"), (6, "112.50"), (12, "105.00")]),
    ("Épicerie", "Riz 5kg", "6130002000011", "450.00", "500.00", 40,
     [(1, "575.00"), (5, "550.00"), (10, "525.00")]),
    ("Épicerie", "Huile de tournesol 2L", "6130002000028", "320.00", "360.00", 35,
     [(1, "420.00"), (5, "400.00")]),
    ("Hygiène", "Savon de Marseille", "6130003000010", "45.00", "55.00", 200,
     [(1, "70.00"), (10, "65.00"), (24, "60.00")]),
    ("Hygiène", "Shampooing familial 750ml", "6130003000027", "210.00", "240.00", 25,
     [(1, "290.00"), (6, "275.00")]),
]


def main() -> int:
    if "stores" not in inspect(engine).get_table_names():
        print("Database not initialized. Run first:  cd backend && alembic upgrade head")
        return 1

    with SessionLocal() as db:
        already = db.scalar(
            select(Store).where(
                Store.name == DEMO_STORE_NAME, Store.deleted_at.is_(None)
            )
        )
        if already is not None:
            print(f"Demo data already present (store '{DEMO_STORE_NAME}') — nothing to do.")
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

        for cat_name, name, barcode, cost, floor, stock, tiers in DEMO_PRODUCTS:
            product = products.create_product(
                db,
                ProductCreate(
                    store_id=store.id,
                    category_id=category_by_name[cat_name].id,
                    name=name,
                    barcode=barcode,
                    cost_price=Decimal(cost),
                    min_sale_price=Decimal(floor),
                    stock_quantity=stock,
                ),
            )
            for min_qty, unit_price in tiers:
                price_tiers.create_price_tier(
                    db,
                    PriceTierCreate(
                        store_id=store.id,
                        product_id=product.id,
                        min_quantity=min_qty,
                        unit_price=Decimal(unit_price),
                    ),
                )
            print(f"    Produit : {name} — {len(tiers)} palier(s), stock {stock}")

    print("Seed terminé.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
