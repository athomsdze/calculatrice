from calculatrice.core.search import filter_items, fold

ITEMS = [
    ("AED", "AED — Dirham des Émirats"), ("MAD", "MAD — Dirham marocain"),
    ("USD", "USD — Dollar américain"), ("AUD", "AUD — Dollar australien"),
    ("LYD", "LYD — Dinar libyen"), ("JPY", "JPY — Yen japonais"),
]


def codes(query):
    return [value for value, _ in filter_items(query, ITEMS)]


def test_fold():
    assert fold("Émirats Ça") == "emirats ca"


def test_ranking():
    assert codes("") == [v for v, _ in ITEMS]
    assert codes("usd") == ["USD"]
    assert codes("yen") == ["JPY", "LYD"]  # début de mot avant sous-chaîne
    assert codes("dollar") == ["USD", "AUD"]
    assert codes("emirats") == ["AED"]
    assert codes("maroc") == ["MAD"]
    assert codes("zzz") == []
