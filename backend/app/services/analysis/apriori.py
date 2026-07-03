"""Apriori frequent-itemset mining and association rules — pure Python.

No database access, no heavy dependencies: input is any iterable of
baskets (each basket a set of hashable items — the caller decides what an
"item" is), output is plain dataclasses. Callers resolve display names.

Definitions (n = number of baskets):
    support(X)    = count(X) / n
    confidence(A -> C) = support(A ∪ C) / support(A)
    lift(A -> C)  = confidence(A -> C) / support(C)
                    (> 1 means A and C appear together more than chance)
"""

from collections.abc import Hashable, Iterable
from dataclasses import dataclass, field
from itertools import combinations

Item = Hashable


@dataclass(frozen=True)
class FrequentItemset:
    items: frozenset
    support: float
    count: int


@dataclass(frozen=True)
class AssociationRule:
    antecedent: frozenset
    consequent: frozenset
    support: float
    confidence: float
    lift: float


@dataclass
class AprioriResult:
    basket_count: int
    itemsets: list[FrequentItemset] = field(default_factory=list)
    rules: list[AssociationRule] = field(default_factory=list)


def _frequent_itemsets(
    baskets: list[frozenset], min_support: float, max_len: int | None
) -> dict[frozenset, int]:
    """Classic level-wise Apriori: candidates of size k are joined from
    frequent itemsets of size k-1 and pruned by downward closure before
    counting (every subset of a frequent itemset is frequent)."""
    n = len(baskets)
    min_count = min_support * n

    # L1 — frequent single items.
    counts: dict[frozenset, int] = {}
    for basket in baskets:
        for item in basket:
            key = frozenset((item,))
            counts[key] = counts.get(key, 0) + 1
    frequent = {s: c for s, c in counts.items() if c >= min_count}
    all_frequent = dict(frequent)

    k = 2
    while frequent and (max_len is None or k <= max_len):
        # Join step: union pairs of (k-1)-itemsets differing by one item.
        previous = sorted(frequent, key=lambda s: sorted(map(repr, s)))
        candidates: set[frozenset] = set()
        for i, a in enumerate(previous):
            for b in previous[i + 1 :]:
                union = a | b
                if len(union) == k:
                    candidates.add(union)
        # Prune step: drop candidates with an infrequent (k-1)-subset.
        candidates = {
            c
            for c in candidates
            if all(frozenset(sub) in frequent for sub in combinations(c, k - 1))
        }
        if not candidates:
            break

        counts = dict.fromkeys(candidates, 0)
        for basket in baskets:
            for candidate in candidates:
                if candidate <= basket:
                    counts[candidate] += 1
        frequent = {s: c for s, c in counts.items() if c >= min_count}
        all_frequent.update(frequent)
        k += 1

    return all_frequent


def mine(
    baskets: Iterable[Iterable[Item]],
    min_support: float = 0.05,
    min_confidence: float = 0.3,
    max_len: int | None = None,
) -> AprioriResult:
    """Mine frequent itemsets and association rules from baskets.

    min_support and min_confidence are fractions in (0, 1]."""
    if not 0 < min_support <= 1:
        raise ValueError("min_support must be in (0, 1]")
    if not 0 < min_confidence <= 1:
        raise ValueError("min_confidence must be in (0, 1]")

    normalized = [frozenset(basket) for basket in baskets]
    normalized = [b for b in normalized if b]
    n = len(normalized)
    if n == 0:
        return AprioriResult(basket_count=0)

    frequent = _frequent_itemsets(normalized, min_support, max_len)

    itemsets = sorted(
        (FrequentItemset(items=s, support=c / n, count=c) for s, c in frequent.items()),
        key=lambda f: (-f.support, len(f.items)),
    )

    rules: list[AssociationRule] = []
    for itemset, count in frequent.items():
        if len(itemset) < 2:
            continue
        support = count / n
        # Every non-empty proper subset is a candidate antecedent; by
        # downward closure its support (and the consequent's) is known.
        for size in range(1, len(itemset)):
            for antecedent_tuple in combinations(sorted(itemset, key=repr), size):
                antecedent = frozenset(antecedent_tuple)
                consequent = itemset - antecedent
                confidence = count / frequent[antecedent]
                if confidence < min_confidence:
                    continue
                consequent_support = frequent[consequent] / n
                rules.append(
                    AssociationRule(
                        antecedent=antecedent,
                        consequent=consequent,
                        support=support,
                        confidence=confidence,
                        lift=confidence / consequent_support,
                    )
                )
    rules.sort(key=lambda r: (-r.lift, -r.confidence, -r.support))

    return AprioriResult(basket_count=n, itemsets=itemsets, rules=rules)
