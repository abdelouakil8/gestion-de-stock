"""Moteur de recherche « intelligent » pour produits et clients.

Stratégie en trois temps, identique pour les deux entités :

1. PRÉFILTRE SQL (``LIKE``) — bon marché et exécuté en base. Chaque token de
   la requête normalisée doit apparaître comme sous-chaîne de ``search_text``
   (clauses ANDées). Les jokers ``%`` / ``_`` et le ``\\`` de la requête sont
   échappés pour ne jamais être interprétés comme des métacaractères LIKE.
   Comme on teste chaque token indépendamment, l'ordre des mots est
   indifférent (« lait nido » == « nido lait »).

2. REPLI FLOU (``rapidfuzz``) — déclenché SEULEMENT quand le préfiltre est
   maigre (moins de ``min(limit, 5)`` lignes). On calcule alors un score
   ``WRatio`` sur ``search_text`` pour rattraper les fautes de frappe /
   translittérations que le LIKE strict manque. ``rapidfuzz`` est importé
   dans la fonction (pas au sommet du module) et l'absence de la lib est
   tolérée (préfiltre seul).

3. RE-CLASSEMENT Python — les candidats (préfiltre + flou) sont triés par
   paliers de pertinence puis, pour les clients seulement, par récence
   d'achat (dernière vente). Les produits n'ont pas de composante récence.

Note portage PostgreSQL : le préfiltre ``LIKE`` peut être remplacé par un
index trigramme (``pg_trgm`` + ``%``/``similarity``) sans toucher au
re-classement Python, qui reste la source de vérité du tri final.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.textnorm import normalize_text
from app.models import Customer, Product, Sale

# Nombre de candidats à charger depuis le préfiltre avant re-classement.
_CANDIDATE_FLOOR = 50
# Score constant attribué aux correspondances exactes/préfixe/sous-chaîne
# (le score flou WRatio est dans [0, 100] ; 100 domine donc naturellement).
_EXACT_SCORE = 100.0
# Sentinelle de récence pour un client sans vente : plus ancien que tout.
_MIN_DT = datetime.min.replace(tzinfo=UTC)


@dataclass
class _Candidate:
    """Ligne candidate (colonnes légères) accumulée avant re-classement."""

    id: UUID
    search_text: str
    name: str
    is_prefilter: bool
    fuzzy_score: float = _EXACT_SCORE


def _like_escape(token: str) -> str:
    """Échappe les métacaractères LIKE d'un token de recherche.

    Le ``\\`` d'abord (sinon on ré-échapperait les ``\\`` introduits juste
    après), puis ``%`` et ``_``. Utilisé avec ``escape="\\"`` côté SQLAlchemy.
    """
    return token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _tokens_of(search_text: str) -> set[str]:
    """Mots de ``search_text`` (déjà normalisé/espacé) — pour le palier 2."""
    return set(search_text.split())


def _compute_tier(cand: _Candidate, norm: str) -> int:
    """Palier de pertinence d'un candidat vis-à-vis de la requête normalisée."""
    if not cand.is_prefilter:
        # Candidat trouvé uniquement par le repli flou.
        return 4
    if cand.search_text == norm:
        return 1
    if cand.search_text.startswith(norm) or norm in _tokens_of(cand.search_text):
        return 2
    # Tous les tokens sont sous-chaînes (garanti par le préfiltre).
    return 3


def _rank_key(cand: _Candidate, norm: str, last_dt: datetime | None):
    """Clé de tri : palier ASC, score DESC, récence DESC (clients), nom ASC.

    ``score`` et ``last_dt`` sont niés pour obtenir un ordre décroissant tout
    en gardant un tri ascendant global (paliers puis nom en dernier recours).
    ``last_dt`` vaut None pour les produits (aucune composante récence).
    """
    tier = _compute_tier(cand, norm)
    recency = -(last_dt or _MIN_DT).timestamp() if last_dt is not None else 0.0
    return (tier, -cand.fuzzy_score, recency, cand.name)


def _customer_recency(db: Session, candidate_ids: list[UUID]) -> dict[UUID, datetime]:
    """Dernière date de vente par client (départage la récence, clients seuls).

    Une seule requête agrégée sur les ventes non supprimées ; les clients sans
    vente sont absents du dict et retombent sur la sentinelle ``_MIN_DT``.
    """
    if not candidate_ids:
        return {}
    rows = db.execute(
        select(Sale.customer_id, func.max(Sale.created_at))
        .where(Sale.customer_id.in_(candidate_ids), Sale.deleted_at.is_(None))
        .group_by(Sale.customer_id)
    ).all()
    return {cid: last_dt for cid, last_dt in rows if cid is not None}


def _search(
    db: Session,
    model,
    *,
    store_id: UUID,
    query: str | None,
    limit: int,
    active_only: bool,
    with_recency: bool,
) -> list:
    """Cœur partagé produits/clients (voir docstring du module)."""
    active_col = getattr(model, "is_active", None)

    def _base_filters(stmt):
        stmt = stmt.where(model.store_id == store_id, model.deleted_at.is_(None))
        if active_only and active_col is not None:
            stmt = stmt.where(active_col.is_(True))
        return stmt

    # (a) Pas de requête -> liste de base, triée par nom, plafonnée à limit.
    norm = normalize_text(query)
    if not norm:
        stmt = _base_filters(select(model)).order_by(model.name).limit(limit)
        return list(db.scalars(stmt))

    tokens = norm.split()

    # (b) Préfiltre SQL : chaque token doit être une sous-chaîne de search_text.
    prefilter_stmt = _base_filters(select(model.id, model.search_text, model.name))
    for token in tokens:
        prefilter_stmt = prefilter_stmt.where(
            model.search_text.like(f"%{_like_escape(token)}%", escape="\\")
        )
    candidate_cap = max(limit * 5, _CANDIDATE_FLOOR)
    prefilter_rows = db.execute(
        prefilter_stmt.order_by(model.name).limit(candidate_cap)
    ).all()

    candidates: dict[UUID, _Candidate] = {
        row.id: _Candidate(row.id, row.search_text, row.name, is_prefilter=True)
        for row in prefilter_rows
    }

    # Repli flou seulement si le préfiltre est maigre.
    if len(prefilter_rows) < min(limit, 5):
        candidates = _add_fuzzy_candidates(
            db, model, _base_filters, norm, limit, candidates
        )

    if not candidates:
        return []

    candidate_ids = list(candidates.keys())

    # (d) Départage par récence — clients uniquement, une seule requête.
    recency = _customer_recency(db, candidate_ids) if with_recency else {}

    # (c) Classement Python des candidats.
    ranked = sorted(
        candidates.values(),
        key=lambda cand: _rank_key(
            cand, norm, recency.get(cand.id) if with_recency else None
        ),
    )
    top_ids = [cand.id for cand in ranked[:limit]]

    # (e) Recharge les lignes ORM complètes, puis ré-ordonne comme le classement.
    stmt = _base_filters(select(model)).where(model.id.in_(top_ids))
    by_id_full = {row.id: row for row in db.scalars(stmt)}
    return [by_id_full[rid] for rid in top_ids if rid in by_id_full]


def _add_fuzzy_candidates(
    db: Session,
    model,
    base_filters,
    norm: str,
    limit: int,
    candidates: dict[UUID, _Candidate],
) -> dict[UUID, _Candidate]:
    """Ajoute les correspondances floues (rapidfuzz) au dict de candidats.

    Import différé et tolérant : si ``rapidfuzz`` manque, on renvoie le dict
    inchangé (préfiltre seul). Un id déjà présent (préfiltre) n'est pas écrasé.
    """
    try:
        import rapidfuzz  # noqa: PLC0415  (import différé, volontaire)
    except ImportError:
        return candidates

    all_rows = db.execute(
        base_filters(select(model.id, model.search_text, model.name))
    ).all()
    by_id = {row.id: (row.search_text, row.name) for row in all_rows}
    choices = {rid: text for rid, (text, _name) in by_id.items()}
    matches = rapidfuzz.process.extract(
        norm,
        choices,
        scorer=rapidfuzz.fuzz.WRatio,
        score_cutoff=70,
        limit=limit * 5,
    )
    for _text, score, rid in matches:
        if rid not in candidates:
            search_text, name = by_id[rid]
            candidates[rid] = _Candidate(
                rid, search_text, name, is_prefilter=False, fuzzy_score=score
            )
    return candidates


def search_customers(
    db: Session, *, store_id: UUID, query: str | None, limit: int = 20
) -> list[Customer]:
    """Recherche intelligente de clients (préfiltre LIKE + repli flou)."""
    return _search(
        db,
        Customer,
        store_id=store_id,
        query=query,
        limit=limit,
        active_only=False,
        with_recency=True,
    )


def search_products(
    db: Session,
    *,
    store_id: UUID,
    query: str | None,
    limit: int = 20,
    active_only: bool = False,
) -> list[Product]:
    """Recherche intelligente de produits (préfiltre LIKE + repli flou)."""
    return _search(
        db,
        Product,
        store_id=store_id,
        query=query,
        limit=limit,
        active_only=active_only,
        with_recency=False,
    )
