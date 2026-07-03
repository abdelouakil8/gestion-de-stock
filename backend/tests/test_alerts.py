"""Phase 6 alerts feed: low-stock boundaries, outstanding credits with
age, oldest-debt-first ordering, and the badge summary counters."""

from datetime import datetime, timedelta
from decimal import Decimal

from app.schemas.customer import CustomerCreate
from app.schemas.product import ProductCreate
from app.schemas.sale import CartItem, CheckoutRequest, PaymentInfo
from app.schemas.store import StoreCreate
from app.services import alerts, customers, products, sales, stores

NOW = datetime(2026, 6, 17, 12, 0)  # naive UTC, like stored created_at


def make_store(db):
    return stores.create_store(db, StoreCreate(name="Boutique Alertes"))


def make_product(db, store, name, stock, threshold=5, active=True):
    return products.create_product(
        db,
        ProductCreate(
            store_id=store.id,
            name=name,
            cost_price=Decimal("5.00"),
            price_detail=Decimal("10.00"),
            price_gros=Decimal("9.00"),
            price_super_gros=Decimal("8.00"),
            stock_quantity=stock,
            low_stock_threshold=threshold,
            is_active=active,
        ),
    )


def make_credit_sale(db, store, product, customer, paid, days_ago, quantity=2):
    sale = sales.finalize_sale(
        db,
        CheckoutRequest(
            store_id=store.id,
            items=[CartItem(product_id=product.id, quantity=quantity)],
            payment=PaymentInfo(
                mode="partial", amount_paid=Decimal(paid), customer_id=customer.id
            ),
        ),
    )
    sale.created_at = NOW - timedelta(days=days_ago)
    db.commit()
    return sale


def test_low_stock_boundaries_and_exclusions(db):
    store = make_store(db)
    at_threshold = make_product(db, store, "Au seuil", stock=5, threshold=5)
    below = make_product(db, store, "Sous le seuil", stock=0, threshold=5)
    make_product(db, store, "Confortable", stock=6, threshold=5)
    make_product(db, store, "Inactif", stock=0, active=False)
    archived = make_product(db, store, "Archivé", stock=0)
    products.soft_delete_product(db, archived.id)
    # Custom (editable) threshold is honored per product.
    make_product(db, store, "Seuil personnalisé", stock=20, threshold=25)

    result = alerts.get_alerts(db, store.id, now=NOW)
    names = [p.name for p in result.low_stock]
    # Sorted by remaining stock, then name.
    assert names == ["Sous le seuil", "Au seuil", "Seuil personnalisé"]
    assert result.summary.low_stock_count == 3
    flagged = {p.product_id for p in result.low_stock}
    assert at_threshold.id in flagged and below.id in flagged


def test_outstanding_credits_oldest_first_with_age(db):
    store = make_store(db)
    product = make_product(db, store, "Eau", stock=100, threshold=0)
    ali = customers.create_customer(
        db, CustomerCreate(store_id=store.id, name="Ali", phone="0550000001")
    )
    lina = customers.create_customer(
        db, CustomerCreate(store_id=store.id, name="Lina", phone="0550000002")
    )

    # total 20.00 each (2 × 10.00 detail)
    make_credit_sale(db, store, product, ali, paid="5.00", days_ago=30)
    make_credit_sale(db, store, product, lina, paid="12.50", days_ago=3)
    # Fully paid sale never appears.
    sales.finalize_sale(
        db,
        CheckoutRequest(
            store_id=store.id,
            items=[CartItem(product_id=product.id, quantity=1)],
        ),
    )

    result = alerts.get_alerts(db, store.id, now=NOW)
    credits = result.outstanding_credits
    assert [c.customer_name for c in credits] == ["Ali", "Lina"]  # oldest first
    assert credits[0].age_days == 30 and credits[1].age_days == 3
    assert credits[0].customer_phone == "0550000001"
    assert credits[0].paid_amount == Decimal("5.00")
    assert credits[0].balance == Decimal("15.00")
    assert credits[1].balance == Decimal("7.50")

    assert result.summary.outstanding_credits_count == 2
    assert result.summary.outstanding_total == Decimal("22.50")


def test_alerts_empty_store_and_store_scoping(db):
    store = make_store(db)
    other = stores.create_store(db, StoreCreate(name="Autre"))
    make_product(db, store, "Vide", stock=0)

    result = alerts.get_alerts(db, other.id, now=NOW)
    assert result.summary.low_stock_count == 0
    assert result.summary.outstanding_credits_count == 0
    assert result.summary.outstanding_total == Decimal("0.00")
    assert result.low_stock == [] and result.outstanding_credits == []


def test_soft_deleted_credit_sale_leaves_the_alerts(db):
    store = make_store(db)
    product = make_product(db, store, "Eau", stock=100, threshold=0)
    ali = customers.create_customer(
        db, CustomerCreate(store_id=store.id, name="Ali", phone="0550000001")
    )
    sale = make_credit_sale(db, store, product, ali, paid="5.00", days_ago=10)
    sales.soft_delete_sale(db, sale.id)

    result = alerts.get_alerts(db, store.id, now=NOW)
    assert result.outstanding_credits == []
    assert result.summary.outstanding_total == Decimal("0.00")
