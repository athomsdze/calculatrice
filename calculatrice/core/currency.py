"""Taux de change : téléchargement, cache local et historique.

Sources gratuites, sans clé d'API :

* taux du jour : open.er-api.com, puis Frankfurter (BCE), puis
  fawazahmed0/currency-api (jsDelivr) en secours ;
* historique : Frankfurter pour les ~30 devises suivies par la BCE,
  sinon échantillonnage quotidien de fawazahmed0/currency-api.

Sans connexion, le dernier cache est utilisé, ou à défaut une table de taux
approximatifs intégrée à l'application.
"""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .. import __version__
from ..storage import read_json, write_json


class CurrencyError(Exception):
    """Échec de récupération des taux (message affichable)."""


CURRENCY_NAMES: dict[str, str] = {
    "AED": "Dirham des Émirats", "AFN": "Afghani afghan", "ALL": "Lek albanais",
    "AMD": "Dram arménien", "ANG": "Florin des Antilles", "AOA": "Kwanza angolais",
    "ARS": "Peso argentin", "AUD": "Dollar australien", "AWG": "Florin arubais",
    "AZN": "Manat azerbaïdjanais", "BAM": "Mark convertible bosnien",
    "BBD": "Dollar barbadien", "BDT": "Taka bangladais", "BGN": "Lev bulgare",
    "BHD": "Dinar bahreïni", "BIF": "Franc burundais", "BMD": "Dollar bermudien",
    "BND": "Dollar de Brunei", "BOB": "Boliviano", "BRL": "Real brésilien",
    "BSD": "Dollar bahaméen", "BTN": "Ngultrum bhoutanais", "BWP": "Pula botswanais",
    "BYN": "Rouble biélorusse", "BZD": "Dollar bélizien", "CAD": "Dollar canadien",
    "CDF": "Franc congolais", "CHF": "Franc suisse", "CLP": "Peso chilien",
    "CNY": "Yuan chinois", "COP": "Peso colombien", "CRC": "Colón costaricien",
    "CUP": "Peso cubain", "CVE": "Escudo cap-verdien", "CZK": "Couronne tchèque",
    "DJF": "Franc djiboutien", "DKK": "Couronne danoise", "DOP": "Peso dominicain",
    "DZD": "Dinar algérien", "EGP": "Livre égyptienne", "ERN": "Nakfa érythréen",
    "ETB": "Birr éthiopien", "EUR": "Euro", "FJD": "Dollar fidjien",
    "FKP": "Livre des Malouines", "FOK": "Couronne féroïenne", "GBP": "Livre sterling",
    "GEL": "Lari géorgien", "GGP": "Livre de Guernesey", "GHS": "Cedi ghanéen",
    "GIP": "Livre de Gibraltar", "GMD": "Dalasi gambien", "GNF": "Franc guinéen",
    "GTQ": "Quetzal guatémaltèque", "GYD": "Dollar guyanien", "HKD": "Dollar de Hong Kong",
    "HNL": "Lempira hondurien", "HRK": "Kuna croate", "HTG": "Gourde haïtienne",
    "HUF": "Forint hongrois", "IDR": "Roupie indonésienne", "ILS": "Shekel israélien",
    "IMP": "Livre de l'île de Man", "INR": "Roupie indienne", "IQD": "Dinar irakien",
    "IRR": "Rial iranien", "ISK": "Couronne islandaise", "JEP": "Livre de Jersey",
    "JMD": "Dollar jamaïcain", "JOD": "Dinar jordanien", "JPY": "Yen japonais",
    "KES": "Shilling kényan", "KGS": "Som kirghize", "KHR": "Riel cambodgien",
    "KID": "Dollar de Kiribati", "KMF": "Franc comorien", "KRW": "Won sud-coréen",
    "KWD": "Dinar koweïtien", "KYD": "Dollar des Caïmans", "KZT": "Tenge kazakh",
    "LAK": "Kip laotien", "LBP": "Livre libanaise", "LKR": "Roupie srilankaise",
    "LRD": "Dollar libérien", "LSL": "Loti lesothan", "LYD": "Dinar libyen",
    "MAD": "Dirham marocain", "MDL": "Leu moldave", "MGA": "Ariary malgache",
    "MKD": "Denar macédonien", "MMK": "Kyat birman", "MNT": "Tugrik mongol",
    "MOP": "Pataca macanaise", "MRU": "Ouguiya mauritanien", "MUR": "Roupie mauricienne",
    "MVR": "Rufiyaa maldivienne", "MWK": "Kwacha malawite", "MXN": "Peso mexicain",
    "MYR": "Ringgit malaisien", "MZN": "Metical mozambicain", "NAD": "Dollar namibien",
    "NGN": "Naira nigérian", "NIO": "Córdoba nicaraguayen", "NOK": "Couronne norvégienne",
    "NPR": "Roupie népalaise", "NZD": "Dollar néo-zélandais", "OMR": "Rial omanais",
    "PAB": "Balboa panaméen", "PEN": "Sol péruvien", "PGK": "Kina papouasien",
    "PHP": "Peso philippin", "PKR": "Roupie pakistanaise", "PLN": "Złoty polonais",
    "PYG": "Guaraní paraguayen", "QAR": "Riyal qatari", "RON": "Leu roumain",
    "RSD": "Dinar serbe", "RUB": "Rouble russe", "RWF": "Franc rwandais",
    "SAR": "Riyal saoudien", "SBD": "Dollar des Salomon", "SCR": "Roupie seychelloise",
    "SDG": "Livre soudanaise", "SEK": "Couronne suédoise", "SGD": "Dollar de Singapour",
    "SHP": "Livre de Sainte-Hélène", "SLE": "Leone sierra-léonais",
    "SLL": "Ancien leone sierra-léonais", "SOS": "Shilling somalien",
    "SRD": "Dollar surinamais", "SSP": "Livre sud-soudanaise", "STN": "Dobra santoméen",
    "SYP": "Livre syrienne", "SZL": "Lilangeni swazi", "THB": "Baht thaïlandais",
    "TJS": "Somoni tadjik", "TMT": "Manat turkmène", "TND": "Dinar tunisien",
    "TOP": "Pa'anga tongien", "TRY": "Livre turque", "TTD": "Dollar de Trinité-et-Tobago",
    "TVD": "Dollar tuvaluan", "TWD": "Dollar taïwanais", "TZS": "Shilling tanzanien",
    "UAH": "Hryvnia ukrainienne", "UGX": "Shilling ougandais", "USD": "Dollar américain",
    "UYU": "Peso uruguayen", "UZS": "Sum ouzbek", "VES": "Bolívar vénézuélien",
    "VND": "Dông vietnamien", "VUV": "Vatu vanuatais", "WST": "Tala samoan",
    "XAF": "Franc CFA (BEAC)", "XCD": "Dollar des Caraïbes orientales",
    "XCG": "Florin caribéen", "XDR": "Droits de tirage spéciaux",
    "XOF": "Franc CFA (BCEAO)", "XPF": "Franc pacifique", "YER": "Rial yéménite",
    "ZAR": "Rand sud-africain", "ZMW": "Kwacha zambien", "ZWL": "Dollar zimbabwéen",
    "ZWG": "Or du Zimbabwe",
}

# Devises suivies par la Banque centrale européenne (historique via Frankfurter).
ECB_CURRENCIES = {
    "AUD", "BGN", "BRL", "CAD", "CHF", "CNY", "CZK", "DKK", "EUR", "GBP", "HKD",
    "HUF", "IDR", "ILS", "INR", "ISK", "JPY", "KRW", "MXN", "MYR", "NOK", "NZD",
    "PHP", "PLN", "RON", "SEK", "SGD", "THB", "TRY", "USD", "ZAR",
}

# Taux approximatifs (unités pour 1 USD), utilisés uniquement hors ligne au
# premier lancement, avant tout téléchargement.
FALLBACK_DATE = "2025-07-01"
FALLBACK_RATES: dict[str, float] = {
    "USD": 1.0, "EUR": 0.85, "GBP": 0.73, "CHF": 0.80, "JPY": 144.0, "CAD": 1.36,
    "AUD": 1.52, "NZD": 1.65, "CNY": 7.17, "HKD": 7.85, "SGD": 1.27, "INR": 85.7,
    "KRW": 1360.0, "MXN": 18.8, "BRL": 5.45, "ARS": 1200.0, "CLP": 935.0,
    "COP": 4050.0, "PEN": 3.55, "ZAR": 17.7, "RUB": 78.5, "TRY": 39.8, "SEK": 9.5,
    "NOK": 10.1, "DKK": 6.35, "PLN": 3.6, "CZK": 21.1, "HUF": 340.0, "RON": 4.32,
    "BGN": 1.66, "ISK": 121.0, "UAH": 41.8, "ILS": 3.37, "SAR": 3.75, "AED": 3.6725,
    "QAR": 3.64, "KWD": 0.305, "BHD": 0.376, "OMR": 0.385, "JOD": 0.709,
    "EGP": 49.5, "MAD": 9.0, "DZD": 130.0, "TND": 2.93, "LYD": 5.4, "XOF": 557.0,
    "XAF": 557.0, "XPF": 101.3, "NGN": 1530.0, "GHS": 10.4, "KES": 129.0,
    "ETB": 135.0, "MGA": 4450.0, "MUR": 45.0, "CDF": 2880.0, "THB": 32.6,
    "IDR": 16200.0, "MYR": 4.22, "PHP": 56.5, "VND": 26100.0, "PKR": 284.0,
    "BDT": 122.0, "LKR": 300.0, "TWD": 29.2, "KZT": 520.0, "HTG": 131.0,
}

POPULAR = ["EUR", "USD", "GBP", "CHF", "JPY", "CAD", "CNY", "MAD", "XOF", "DZD", "TND"]

FetchJson = Callable[[str], Any]


def currency_label(code: str) -> str:
    name = CURRENCY_NAMES.get(code)
    return f"{code} — {name}" if name else code


def _ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    try:  # certificats de certifi en complément du magasin système
        import certifi

        context.load_verify_locations(certifi.where())
    except (ImportError, OSError):
        pass
    return context


def http_get_json(url: str, timeout: float = 10.0) -> Any:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": f"CalculatricePro/{__version__}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout, context=_ssl_context()) as resp:
        return json.loads(resp.read().decode("utf-8"))


@dataclass
class RateTable:
    """Taux exprimés en unités de devise pour 1 USD."""

    rates: dict[str, float]
    updated: str  # date ISO (AAAA-MM-JJ ou horodatage complet)
    source: str
    offline: bool = False

    def codes(self) -> list[str]:
        return sorted(self.rates)

    def rate(self, frm: str, to: str) -> float:
        try:
            return self.rates[to] / self.rates[frm]
        except KeyError as missing:
            raise CurrencyError(f"Devise inconnue : {missing.args[0]}") from None

    def convert(self, amount: float, frm: str, to: str) -> float:
        return amount * self.rate(frm, to)

    def updated_label(self) -> str:
        try:
            moment = datetime.fromisoformat(self.updated)
        except ValueError:
            return self.updated
        if moment.tzinfo is not None:
            moment = moment.astimezone()
            return moment.strftime("%d/%m/%Y à %H:%M")
        return moment.strftime("%d/%m/%Y")

    def to_json(self) -> dict[str, Any]:
        return {"rates": self.rates, "updated": self.updated, "source": self.source}


def _clean_rates(raw: dict[str, Any], lowercase: bool = False) -> dict[str, float]:
    rates: dict[str, float] = {}
    for code, value in raw.items():
        code = code.upper() if lowercase else code
        if not isinstance(value, (int, float)) or value <= 0:
            continue
        if lowercase and code not in CURRENCY_NAMES:
            continue  # écarte cryptomonnaies et métaux de la source de secours
        if len(code) == 3 and code.isalpha():
            rates[code] = float(value)
    rates["USD"] = 1.0
    return rates


def _from_open_er_api(fetch: FetchJson) -> RateTable:
    data = fetch("https://open.er-api.com/v6/latest/USD")
    if data.get("result") != "success":
        raise CurrencyError("Réponse invalide de open.er-api.com")
    updated = datetime.fromtimestamp(int(data["time_last_update_unix"]), tz=timezone.utc)
    return RateTable(_clean_rates(data["rates"]), updated.isoformat(), "open.er-api.com")


def _from_frankfurter(fetch: FetchJson) -> RateTable:
    data = fetch("https://api.frankfurter.dev/v1/latest?base=USD")
    return RateTable(_clean_rates(data["rates"]), data["date"], "Frankfurter (BCE)")


def _from_currency_api(fetch: FetchJson) -> RateTable:
    data = fetch("https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json")
    return RateTable(_clean_rates(data["usd"], lowercase=True), data["date"], "currency-api")


LATEST_PROVIDERS = (_from_open_er_api, _from_frankfurter, _from_currency_api)

HISTORY_PERIODS = {"1S": 7, "1M": 30, "3M": 91, "6M": 182, "1A": 365}


class CurrencyService:
    def __init__(self, cache_path: Path, fetch: FetchJson | None = None):
        self.cache_path = cache_path
        self.fetch = fetch or http_get_json
        self._history_cache: dict[tuple[str, str, int], list[tuple[date, float]]] = {}

    # ---- taux du jour -------------------------------------------------
    def load_cached(self) -> RateTable:
        data = read_json(self.cache_path)
        if isinstance(data, dict) and isinstance(data.get("rates"), dict):
            rates = _clean_rates(data["rates"])
            if len(rates) > 1:
                return RateTable(
                    rates, str(data.get("updated", "")), str(data.get("source", "cache")),
                    offline=True,
                )
        return RateTable(dict(FALLBACK_RATES), FALLBACK_DATE, "taux intégrés", offline=True)

    def fetch_latest(self) -> RateTable:
        for provider in LATEST_PROVIDERS:
            try:
                table = provider(self.fetch)
            except Exception:  # réseau, JSON, clé manquante... : source suivante
                continue
            if len(table.rates) > 10:
                write_json(self.cache_path, table.to_json())
                return table
        raise CurrencyError("Impossible de récupérer les taux (connexion Internet ?)")

    # ---- historique ---------------------------------------------------
    def fetch_history(self, frm: str, to: str, days: int) -> list[tuple[date, float]]:
        key = (frm, to, days)
        if key in self._history_cache:
            return self._history_cache[key]
        end = date.today()
        start = end - timedelta(days=days)
        if frm == to:
            points = [(start, 1.0), (end, 1.0)]
        else:
            points = []
            if frm in ECB_CURRENCIES and to in ECB_CURRENCIES:
                try:
                    points = self._history_frankfurter(frm, to, start, end)
                except Exception:
                    points = []
            if len(points) < 2:
                points = self._history_sampled(frm, to, start, end)
        if len(points) < 2:
            raise CurrencyError("Historique indisponible pour cette paire")
        self._history_cache[key] = points
        return points

    def _history_frankfurter(self, frm: str, to: str, start: date, end: date):
        url = (
            f"https://api.frankfurter.dev/v1/{start.isoformat()}..{end.isoformat()}"
            f"?base={frm}&symbols={to}"
        )
        data = self.fetch(url)
        points = []
        for day, values in data.get("rates", {}).items():
            if to in values:
                points.append((date.fromisoformat(day), float(values[to])))
        return sorted(points)

    def _history_sampled(self, frm: str, to: str, start: date, end: date, samples: int = 24):
        span = (end - start).days
        step = max(1, span // (samples - 1))
        days = sorted({start + timedelta(days=i) for i in range(0, span, step)} | {end})
        base, target = frm.lower(), to.lower()

        def one_day(day: date):
            for template in (
                "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@{d}/v1/currencies/{b}.json",
                "https://{d}.currency-api.pages.dev/v1/currencies/{b}.json",
            ):
                try:
                    data = self.fetch(template.format(d=day.isoformat(), b=base))
                    value = float(data[base][target])
                    return (day, value) if value > 0 else None
                except Exception:
                    continue
            return None

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(one_day, days))
        return sorted(p for p in results if p is not None)
