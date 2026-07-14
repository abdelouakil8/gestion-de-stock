"""Stress Data Seeder for GestionStockPOS Audit.

Usage (from the project root, venv active, after `alembic upgrade head`):
    python scripts/seed_stress.py

Generates:
- 1 Store
- 20 Categories
- 500 Products
- 100 Customers
- 20 Suppliers
- 50 Purchases (Purchase Orders)
- 200 Sales
"""
import sys
import random
from decimal import Decimal
from pathlib import Path
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.db.session import SessionLocal, engine
from app.models import Store
from sqlalchemy import select, inspect

from app.schemas.category import CategoryCreate
from app.schemas.customer import CustomerCreate
from app.schemas.product import ProductCreate
from app.schemas.supplier import SupplierCreate, PurchaseOrderCreate, PurchaseOrderItemCreate
from app.schemas.sale import CartItem, CheckoutRequest, PaymentInfo
from app.schemas.store import StoreCreate

from app.services import (
    categories,
    customers,
    products,
    purchasing,
    sales,
    stores,
    suppliers
)

STORE_NAME = "Boutique Stress Audit"

def main() -> int:
    if "stores" not in inspect(engine).get_table_names():
        print("Database not initialized. Run first:  cd backend && alembic upgrade head")
        return 1

    random.seed(12345)

    with SessionLocal() as db:
        store = db.scalar(select(Store).where(Store.name == STORE_NAME, Store.deleted_at.is_(None)))
        if store is None:
            store = stores.create_store(db, StoreCreate(name=STORE_NAME))
            print(f"Store created : {store.name} ({store.id})")
        else:
            print(f"Store already exists: {store.name}. We will continue seeding inside it.")

        # 1. Categories
        print("Seeding Categories...")
        cats = []
        for i in range(1, 21):
            cat_name = f"Catégorie {i:02d}"
            cat = categories.create_category(db, CategoryCreate(store_id=store.id, name=cat_name))
            cats.append(cat)

        # 2. Products
        print("Seeding Products (500)...")
        prods = []
        for i in range(1, 501):
            cat = random.choice(cats)
            cost = Decimal(random.randint(500, 10000)) / 100
            prod = products.create_product(
                db,
                ProductCreate(
                    store_id=store.id,
                    category_id=cat.id,
                    name=f"Produit Audit {i:03d}",
                    barcode=f"613009{i:05d}",
                    cost_price=cost,
                    price_detail=(cost * Decimal("1.5")).quantize(Decimal("0.01")),
                    price_gros=(cost * Decimal("1.3")).quantize(Decimal("0.01")),
                    price_super_gros=(cost * Decimal("1.2")).quantize(Decimal("0.01")),
                    stock_quantity=0,
                    low_stock_threshold=random.randint(5, 20)
                )
            )
            prods.append(prod)

        # 3. Customers
        print("Seeding Customers (100)...")
        custs = []
        for i in range(1, 101):
            cust = customers.create_customer(
                db,
                CustomerCreate(
                    store_id=store.id,
                    name=f"Client Audit {i:03d}",
                    phone=f"05{i:08d}",
                    note=f"Note client {i}" if random.random() > 0.7 else None
                )
            )
            custs.append(cust)

        # 4. Suppliers
        print("Seeding Suppliers (20)...")
        supps = []
        for i in range(1, 21):
            supp = suppliers.create_supplier(
                db,
                SupplierCreate(
                    store_id=store.id,
                    name=f"Fournisseur Audit {i:02d}",
                    phone=f"07{i:08d}"
                )
            )
            supps.append(supp)

        # 5. Purchases (to increment stock)
        print("Seeding Purchases (50)...")
        for i in range(50):
            supp = random.choice(supps)
            num_items = random.randint(5, 15)
            items = []
            chosen_prods = random.sample(prods, num_items)
            total = Decimal("0.00")
            for p in chosen_prods:
                qty = random.randint(20, 100)
                cost = p.cost_price
                total += (cost * qty)
                items.append(PurchaseOrderItemCreate(
                    product_id=p.id,
                    quantity=qty,
                    unit_cost=cost
                ))
            
            paid = total if random.random() < 0.8 else total * Decimal("0.5")
            
            purchasing.receive_stock(
                db,
                PurchaseOrderCreate(
                    store_id=store.id,
                    supplier_id=supp.id,
                    items=items,
                    payment_amount=paid.quantize(Decimal("0.01"))
                )
            )
        
        # 6. Sales (to deduct stock, create debts, etc.)
        print("Seeding Sales (200)...")
        for i in range(200):
            num_items = random.randint(1, 10)
            chosen_prods = random.sample(prods, num_items)
            items = []
            for p in chosen_prods:
                qty = random.randint(1, 5)
                db.refresh(p)
                if p.stock_quantity >= qty:
                    price_level = random.choice(["detail", "gros", "super_gros"])
                    items.append(CartItem(
                        product_id=p.id,
                        quantity=qty,
                        price_level=price_level
                    ))
            
            if not items:
                continue
                
            cust = random.choice(custs) if random.random() > 0.5 else None
            req = CheckoutRequest(store_id=store.id, items=items)
            
            if cust:
                req.payment = PaymentInfo(
                    mode="partial" if random.random() > 0.5 else "full",
                    amount_paid=Decimal("100.00") if random.random() > 0.5 else None,
                    customer_id=cust.id
                )
            
            try:
                sales.finalize_sale(db, req)
            except Exception as e:
                db.rollback()
                pass

    print("Stress seed complete.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
