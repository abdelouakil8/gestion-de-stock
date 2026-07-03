"""Apriori module: hand-verifiable itemsets/rules on crafted baskets, plus
the basket provider that feeds it from sale_items.

The fixture numbers below are chosen so every support/confidence/lift can
be checked by hand: 10 baskets, A appears in 8, B in 7, {A,B} in 6.
    support({A,B}) = 0.6
    conf(A→B) = 6/8 = 0.75         lift = 0.75 / 0.7  = 1.0714… > 1
    conf(B→A) = 6/7 ≈ 0.857        lift = 0.857 / 0.8 = 1.0714… > 1
"""

from datetime import datetime
from decimal import Decimal

import pytest

from app.schemas.product import ProductCreate
from app.schemas.sale import CartItem, CheckoutRequest
from app.schemas.store import StoreCreate
from app.services import products, sales, stores
from app.services.analysis import apriori, baskets

BASKETS = [
    {"A", "B"},
    {"A", "B"},
    {"A", "B"},
    {"A", "B"},
    {"A", "B", "C"},
    {"A", "B", "C"},
    {"A"},
    {"A", "C"},
    {"B"},
    {"C"},
]


def rule(result, antecedent, consequent):
    return next(
        r
        for r in result.rules
        if r.antecedent == frozenset(antecedent)
        and r.consequent == frozenset(consequent)
    )


def itemset(result, items):
    return next(i for i in result.itemsets if i.items == frozenset(items))


def test_known_rules_on_hand_crafted_baskets():
    result = apriori.mine(BASKETS, min_support=0.2, min_confidence=0.5)
    assert result.basket_count == 10

    assert itemset(result, {"A"}).count == 8
    assert itemset(result, {"B"}).support == 0.7
    ab = itemset(result, {"A", "B"})
    assert ab.count == 6 and ab.support == 0.6

    a_to_b = rule(result, {"A"}, {"B"})
    assert a_to_b.support == 0.6
    assert a_to_b.confidence == 0.75
    assert a_to_b.lift == pytest.approx(0.75 / 0.7)
    assert a_to_b.lift > 1  # A and B genuinely go together

    b_to_a = rule(result, {"B"}, {"A"})
    assert b_to_a.confidence == pytest.approx(6 / 7)
    assert b_to_a.lift == pytest.approx((6 / 7) / 0.8)


def test_min_support_and_min_confidence_filter():
    result = apriori.mine(BASKETS, min_support=0.65, min_confidence=0.5)
    # Only A (0.8) and B (0.7) survive support 0.65 — no pairs, no rules.
    assert {frozenset(i.items) for i in result.itemsets} == {
        frozenset({"A"}),
        frozenset({"B"}),
    }
    assert result.rules == []

    strict = apriori.mine(BASKETS, min_support=0.2, min_confidence=0.8)
    # conf(A→B)=0.75 < 0.8 filtered; conf(B→A)=0.857 kept.
    assert all(r.confidence >= 0.8 for r in strict.rules)
    assert frozenset({"B"}) in {r.antecedent for r in strict.rules}


def test_three_way_itemset_and_composite_rules():
    result = apriori.mine(BASKETS, min_support=0.2, min_confidence=0.2)
    abc = itemset(result, {"A", "B", "C"})
    assert abc.count == 2 and abc.support == 0.2
    # Rule with a 2-item antecedent: {A,B} → C, conf = 2/6.
    ab_to_c = rule(result, {"A", "B"}, {"C"})
    assert ab_to_c.confidence == pytest.approx(2 / 6)
    # lift vs support(C)=0.5 → below 1: C is NOT pulled by {A,B}.
    assert ab_to_c.lift < 1


def test_empty_input_and_parameter_validation():
    empty = apriori.mine([], min_support=0.5, min_confidence=0.5)
    assert empty.basket_count == 0
    assert empty.itemsets == [] and empty.rules == []

    for bad in (0, -0.1, 1.5):
        with pytest.raises(ValueError):
            apriori.mine(BASKETS, min_support=bad)
        with pytest.raises(ValueError):
            apriori.mine(BASKETS, min_confidence=bad)


def test_duplicate_items_in_one_basket_count_once():
    result = apriori.mine([["A", "A", "B"], ["A", "B"]], min_support=0.5)
    assert itemset(result, {"A"}).count == 2
    assert itemset(result, {"A", "B"}).count == 2


# --------------------------------------------------- basket provider


JAN_15 = datetime(2026, 1, 15, 12, 0)


def make_product(db, store, name):
    return products.create_product(
        db,
        ProductCreate(
            store_id=store.id,
            name=name,
            cost_price=Decimal("5.00"),
            price_detail=Decimal("10.00"),
            price_gros=Decimal("9.00"),
            price_super_gros=Decimal("8.00"),
            stock_quantity=1000,
        ),
    )


def test_sale_baskets_group_by_sale_and_exclude_deleted(db):
    store = stores.create_store(db, StoreCreate(name="Boutique Paniers"))
    a = make_product(db, store, "A")
    b = make_product(db, store, "B")

    def make_sale(items):
        sale = sales.finalize_sale(
            db,
            CheckoutRequest(
                store_id=store.id,
                items=[CartItem(product_id=p.id, quantity=q) for p, q in items],
            ),
        )
        sale.created_at = JAN_15
        db.commit()
        return sale

    make_sale([(a, 2), (b, 1)])  # basket {A, B} — quantity is irrelevant
    make_sale([(a, 1)])
    deleted = make_sale([(b, 1)])
    sales.soft_delete_sale(db, deleted.id)

    result = baskets.sale_baskets(
        db, store.id, datetime(2026, 1, 1), datetime(2026, 1, 31)
    )
    assert sorted(result, key=len) == [frozenset({a.id}), frozenset({a.id, b.id})]

    # Feeding the provider output into the miner works end to end.
    mined = apriori.mine(result, min_support=0.4, min_confidence=0.4)
    assert mined.basket_count == 2
