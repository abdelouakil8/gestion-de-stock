"""Normalisation de texte pour la recherche (projet francophone + arabe).

Ce module est le point unique de vérité : la même fonction est appelée à
l'écriture (services create/update, colonne ``search_text``) et dans la
backfill de migration, afin que les valeurs stockées en base soient
canoniques et comparables sans surprise (accents FR, tashkeel AR, casse).
"""

from __future__ import annotations

import re
import unicodedata

# Précompilé une seule fois : toute suite d'espaces (y compris \t, \n, NBSP…).
_WHITESPACE_RE = re.compile(r"\s+")

# Repli des lettres arabes vers une forme canonique.
# alif (أ إ آ ٱ) -> ا  ;  alif maksura (ى) -> ي  ;  ta marbuta (ة) -> ه.
_ARABIC_FOLDING = {
    "أ": "ا",  # أ
    "إ": "ا",  # إ
    "آ": "ا",  # آ
    "ٱ": "ا",  # ٱ
    "ى": "ي",  # ى -> ي
    "ة": "ه",  # ة -> ه
}
# Tatweel (U+0640) : ornement d'étirement, aucun sens sémantique -> supprimé.
_ARABIC_TATWEEL = "ـ"


def normalize_text(value: str | None) -> str:
    """Retourne une forme canonique pour la recherche.

    Étapes : None/vide -> "" ; NFKC ; casefold ; suppression des marques
    combinantes (catégorie "Mn" — retire les accents français et le tashkeel
    arabe) ; repli des lettres arabes équivalentes ; suppression du tatweel ;
    espaces réduits à un seul et coupés en bord. Les chiffres et la
    ponctuation sont conservés (téléphones, codes-barres avec ``-`` ou ``/``).
    """
    if not value:
        return ""

    # NFKC unifie les formes de compatibilité (chiffres arabes-indiens, etc.).
    text = unicodedata.normalize("NFKC", value)
    text = text.casefold()

    # Décomposition NFD puis filtrage des marques combinantes : retire d'un
    # coup les accents français (é, à, ç…) ET le tashkeel arabe (ً ٌ ٍ َ ُ ِ ّ ْ).
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")

    # Repli arabe + tatweel : après NFD/casefold, on opère caractère par caractère.
    folded_chars: list[str] = []
    for ch in text:
        if ch == _ARABIC_TATWEEL:
            continue
        folded_chars.append(_ARABIC_FOLDING.get(ch, ch))
    text = "".join(folded_chars)

    # Toute séquence d'espaces -> un seul espace, puis strip.
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text


def tokenize(value: str | None) -> list[str]:
    """Découpe le texte normalisé en tokens non vides (utilisé par la recherche)."""
    normalized = normalize_text(value)
    if not normalized:
        return []
    return [token for token in normalized.split(" ") if token]
