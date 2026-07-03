"""Market-basket analysis modules.

Architecture: each algorithm is a self-contained sibling module with the
same generic interface — a sequence of baskets (sets of hashable items) in,
frequent itemsets + association rules out. Adding FP-Growth or similar
later means adding a module here, without touching any caller.
"""
