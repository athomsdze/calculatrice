"""Recherche tolérante (sans accents ni casse) pour les listes de choix."""

from __future__ import annotations

import unicodedata


def fold(text: str) -> str:
    """Minuscules sans accents."""
    normalized = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn")


def rank(query: str, value: str, label: str) -> int | None:
    """Pertinence d'un élément (plus petit = meilleur), ou None s'il ne correspond pas.

    ``query`` doit déjà être passé par :func:`fold`.
    """
    if not query:
        return 0
    value_f, label_f = fold(value), fold(label)
    if value_f == query:
        return 0
    if value_f.startswith(query):
        return 1
    words = label_f.replace("(", " ").replace("—", " ").split()
    if any(word.startswith(query) for word in words):
        return 2
    if query in label_f:
        return 3
    return None


def filter_items(query: str, items: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Éléments ``(valeur, libellé)`` correspondant à ``query``, les plus pertinents d'abord."""
    q = fold(query.strip())
    scored = []
    for index, (value, label) in enumerate(items):
        score = rank(q, value, label)
        if score is not None:
            scored.append((score, index, (value, label)))
    return [item for _, _, item in sorted(scored)]
