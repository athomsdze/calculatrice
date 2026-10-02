from datetime import date

import pytest

from calculatrice.core.currency import (
    CURRENCY_NAMES, FALLBACK_RATES, CurrencyError, CurrencyService, RateTable, currency_label,
)


def make_fetch(responses, calls=None):
    def fetch(url):
        if calls is not None:
            calls.append(url)
        for prefix, payload in responses.items():
            if url.startswith(prefix):
                if isinstance(payload, Exception):
                    raise payload
                return payload
        raise OSError(f"pas de réseau pour {url}")
    return fetch


OPEN_ER = {
    "result": "success",
    "time_last_update_unix": 1790000000,
    "rates": {code: 1.0 + i for i, code in enumerate(sorted(CURRENCY_NAMES))} | {"USD": 1},
}


def test_rate_table_conversion():
    table = RateTable({"USD": 1.0, "EUR": 0.5, "JPY": 100.0}, "2026-01-01", "test")
    assert table.convert(10, "USD", "EUR") == 5
    assert table.convert(10, "EUR", "USD") == 20
    assert table.rate("EUR", "JPY") == 200
    with pytest.raises(CurrencyError):
        table.rate("EUR", "XYZ")
    assert table.updated_label() == "01/01/2026"


def test_fallback_when_no_cache(tmp_path):
    service = CurrencyService(tmp_path / "rates.json", make_fetch({}))
    table = service.load_cached()
    assert table.offline
    assert table.rates == FALLBACK_RATES


def test_fetch_latest_saves_cache(tmp_path):
    cache = tmp_path / "rates.json"
    service = CurrencyService(cache, make_fetch({"https://open.er-api.com": OPEN_ER}))
    table = service.fetch_latest()
    assert table.source == "open.er-api.com"
    assert not table.offline
    assert cache.exists()
    cached = CurrencyService(cache, make_fetch({})).load_cached()
    assert cached.offline
    assert cached.rates == table.rates


def test_fetch_latest_falls_back_to_other_providers(tmp_path):
    frankfurter = {"base": "USD", "date": "2026-10-01",
                   "rates": {c: 2.0 for c in ["EUR", "GBP", "JPY", "CHF", "CAD", "AUD",
                                              "CNY", "SEK", "NOK", "DKK", "PLN"]}}
    service = CurrencyService(tmp_path / "r.json", make_fetch({
        "https://open.er-api.com": OSError("down"),
        "https://api.frankfurter.dev": frankfurter,
    }))
    table = service.fetch_latest()
    assert table.source.startswith("Frankfurter")
    assert table.rates["USD"] == 1.0

    currency_api = {"date": "2026-10-01",
                    "usd": {c.lower(): 3.0 for c in list(CURRENCY_NAMES)[:40]} | {"btc": 0.00001}}
    service = CurrencyService(tmp_path / "r2.json", make_fetch({
        "https://cdn.jsdelivr.net": currency_api,
    }))
    table = service.fetch_latest()
    assert "BTC" not in table.rates
    assert table.source == "currency-api"


def test_fetch_latest_all_fail(tmp_path):
    service = CurrencyService(tmp_path / "r.json", make_fetch({}))
    with pytest.raises(CurrencyError):
        service.fetch_latest()


def test_history_frankfurter(tmp_path):
    payload = {"rates": {"2026-09-01": {"USD": 1.1}, "2026-09-02": {"USD": 1.2}}}
    calls = []
    service = CurrencyService(tmp_path / "r.json",
                              make_fetch({"https://api.frankfurter.dev": payload}, calls))
    points = service.fetch_history("EUR", "USD", 30)
    assert points == [(date(2026, 9, 1), 1.1), (date(2026, 9, 2), 1.2)]
    service.fetch_history("EUR", "USD", 30)
    assert len(calls) == 1  # deuxième appel servi par le cache mémoire


def test_history_sampled_for_non_ecb_currency(tmp_path):
    service = CurrencyService(tmp_path / "r.json",
                              make_fetch({"https://cdn.jsdelivr.net": {"eur": {"mad": 10.5}}}))
    points = service.fetch_history("EUR", "MAD", 30)
    assert len(points) > 10
    assert all(v == 10.5 for _, v in points)


def test_history_unavailable(tmp_path):
    service = CurrencyService(tmp_path / "r.json", make_fetch({}))
    with pytest.raises(CurrencyError):
        service.fetch_history("EUR", "MAD", 30)


def test_labels():
    assert currency_label("EUR") == "EUR — Euro"
    assert currency_label("ABC") == "ABC"
