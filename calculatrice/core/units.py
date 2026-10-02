"""Définition des unités et conversions.

Chaque catégorie possède une unité de référence ; chaque unité sait se
convertir vers cette référence (``to_base``) et depuis celle-ci (``from_base``).
Les conversions non linéaires (températures, consommation) sont gérées de la
même façon.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

from .evaluator import CalcError


@dataclass(frozen=True)
class Unit:
    key: str
    name: str
    symbol: str
    to_base: Callable[[float], float]
    from_base: Callable[[float], float]

    @property
    def label(self) -> str:
        return f"{self.name} ({self.symbol})"


def linear(key: str, name: str, symbol: str, factor: float, offset: float = 0.0) -> Unit:
    """Unité telle que ``base = valeur × factor + offset``."""
    return Unit(
        key, name, symbol,
        to_base=lambda v: v * factor + offset,
        from_base=lambda v: (v - offset) / factor,
    )


def reciprocal(key: str, name: str, symbol: str, k: float) -> Unit:
    """Unité telle que ``base = k / valeur`` (ex. L/100 km ↔ km/L)."""

    def invert(v: float) -> float:
        if v == 0:
            raise CalcError("Division par zéro")
        return k / v

    return Unit(key, name, symbol, to_base=invert, from_base=invert)


@dataclass
class Category:
    key: str
    name: str
    units: list[Unit]
    default_from: str
    default_to: str
    minimum_base: float | None = None  # ex. zéro absolu pour les températures
    _index: dict[str, Unit] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._index = {u.key: u for u in self.units}

    def get(self, key: str) -> Unit:
        return self._index[key]

    def by_label(self, label: str) -> Unit:
        for unit in self.units:
            if unit.label == label:
                return unit
        raise KeyError(label)


LIGHT_YEAR = 9_460_730_472_580_800.0
MILE = 1609.344
GALLON_US = 3.785411784
GALLON_UK = 4.54609

CATEGORIES: list[Category] = [
    Category("length", "Longueur", [
        linear("nm", "Nanomètre", "nm", 1e-9),
        linear("um", "Micromètre", "µm", 1e-6),
        linear("mm", "Millimètre", "mm", 1e-3),
        linear("cm", "Centimètre", "cm", 1e-2),
        linear("dm", "Décimètre", "dm", 1e-1),
        linear("m", "Mètre", "m", 1.0),
        linear("km", "Kilomètre", "km", 1e3),
        linear("in", "Pouce", "in", 0.0254),
        linear("ft", "Pied", "ft", 0.3048),
        linear("yd", "Yard", "yd", 0.9144),
        linear("mi", "Mile", "mi", MILE),
        linear("nmi", "Mille marin", "NM", 1852.0),
        linear("au", "Unité astronomique", "ua", 149_597_870_700.0),
        linear("ly", "Année-lumière", "al", LIGHT_YEAR),
        linear("pc", "Parsec", "pc", 3.085_677_581_491_367e16),
    ], "km", "mi"),
    Category("mass", "Masse", [
        linear("ug", "Microgramme", "µg", 1e-9),
        linear("mg", "Milligramme", "mg", 1e-6),
        linear("g", "Gramme", "g", 1e-3),
        linear("kg", "Kilogramme", "kg", 1.0),
        linear("q", "Quintal", "q", 100.0),
        linear("t", "Tonne", "t", 1000.0),
        linear("ct", "Carat", "ct", 2e-4),
        linear("oz", "Once", "oz", 0.028_349_523_125),
        linear("lb", "Livre (anglaise)", "lb", 0.453_592_37),
        linear("st", "Stone", "st", 6.350_293_18),
        linear("ton_us", "Tonne courte (US)", "ton US", 907.184_74),
        linear("ton_uk", "Tonne longue (UK)", "ton UK", 1016.046_908_8),
    ], "kg", "lb"),
    Category("temperature", "Température", [
        linear("c", "Degré Celsius", "°C", 1.0, 273.15),
        linear("f", "Degré Fahrenheit", "°F", 5 / 9, 273.15 - 32 * 5 / 9),
        linear("k", "Kelvin", "K", 1.0),
        linear("r", "Degré Rankine", "°R", 5 / 9),
    ], "c", "f", minimum_base=0.0),
    Category("area", "Surface", [
        linear("mm2", "Millimètre carré", "mm²", 1e-6),
        linear("cm2", "Centimètre carré", "cm²", 1e-4),
        linear("m2", "Mètre carré", "m²", 1.0),
        linear("a", "Are", "a", 100.0),
        linear("ha", "Hectare", "ha", 1e4),
        linear("km2", "Kilomètre carré", "km²", 1e6),
        linear("in2", "Pouce carré", "in²", 0.000_645_16),
        linear("ft2", "Pied carré", "ft²", 0.092_903_04),
        linear("yd2", "Yard carré", "yd²", 0.836_127_36),
        linear("ac", "Acre", "ac", 4046.856_422_4),
        linear("mi2", "Mile carré", "mi²", MILE * MILE),
    ], "m2", "ft2"),
    Category("volume", "Volume", [
        linear("ml", "Millilitre", "mL", 1e-3),
        linear("cl", "Centilitre", "cL", 1e-2),
        linear("dl", "Décilitre", "dL", 1e-1),
        linear("l", "Litre", "L", 1.0),
        linear("cm3", "Centimètre cube", "cm³", 1e-3),
        linear("m3", "Mètre cube", "m³", 1000.0),
        linear("tsp", "Cuillère à café (US)", "c. à c.", GALLON_US / 768),
        linear("tbsp", "Cuillère à soupe (US)", "c. à s.", GALLON_US / 256),
        linear("floz", "Once liquide (US)", "fl oz", GALLON_US / 128),
        linear("cup", "Tasse (US)", "cup", GALLON_US / 16),
        linear("pt_us", "Pinte (US)", "pt US", GALLON_US / 8),
        linear("pt_uk", "Pinte (UK)", "pt UK", GALLON_UK / 8),
        linear("gal_us", "Gallon (US)", "gal US", GALLON_US),
        linear("gal_uk", "Gallon (UK)", "gal UK", GALLON_UK),
        linear("in3", "Pouce cube", "in³", 0.016_387_064),
        linear("ft3", "Pied cube", "ft³", 28.316_846_592),
        linear("bbl", "Baril de pétrole", "bbl", 158.987_294_928),
    ], "l", "gal_us"),
    Category("speed", "Vitesse", [
        linear("mps", "Mètre par seconde", "m/s", 1.0),
        linear("kmh", "Kilomètre par heure", "km/h", 1 / 3.6),
        linear("mph", "Mile par heure", "mph", MILE / 3600),
        linear("kn", "Nœud", "kn", 1852 / 3600),
        linear("fps", "Pied par seconde", "ft/s", 0.3048),
        linear("mach", "Mach (niveau de la mer)", "Ma", 340.29),
        linear("c", "Vitesse de la lumière", "c", 299_792_458.0),
    ], "kmh", "mph"),
    Category("time", "Temps", [
        linear("ns", "Nanoseconde", "ns", 1e-9),
        linear("us", "Microseconde", "µs", 1e-6),
        linear("ms", "Milliseconde", "ms", 1e-3),
        linear("s", "Seconde", "s", 1.0),
        linear("min", "Minute", "min", 60.0),
        linear("h", "Heure", "h", 3600.0),
        linear("d", "Jour", "j", 86_400.0),
        linear("wk", "Semaine", "sem", 604_800.0),
        linear("mo", "Mois (moyen)", "mois", 2_629_746.0),
        linear("yr", "Année (365,25 j)", "an", 31_557_600.0),
        linear("dec", "Décennie", "déc.", 315_576_000.0),
        linear("cen", "Siècle", "siècle", 3_155_760_000.0),
    ], "h", "min"),
    Category("data", "Données", [
        linear("bit", "Bit", "bit", 1 / 8),
        linear("B", "Octet", "o", 1.0),
        linear("kB", "Kilooctet", "Ko", 1e3),
        linear("MB", "Mégaoctet", "Mo", 1e6),
        linear("GB", "Gigaoctet", "Go", 1e9),
        linear("TB", "Téraoctet", "To", 1e12),
        linear("PB", "Pétaoctet", "Po", 1e15),
        linear("KiB", "Kibioctet", "Kio", 1024.0),
        linear("MiB", "Mébioctet", "Mio", 1024.0 ** 2),
        linear("GiB", "Gibioctet", "Gio", 1024.0 ** 3),
        linear("TiB", "Tébioctet", "Tio", 1024.0 ** 4),
        linear("kbit", "Kilobit", "kbit", 125.0),
        linear("Mbit", "Mégabit", "Mbit", 125_000.0),
        linear("Gbit", "Gigabit", "Gbit", 125_000_000.0),
    ], "GB", "MB"),
    Category("energy", "Énergie", [
        linear("j", "Joule", "J", 1.0),
        linear("kj", "Kilojoule", "kJ", 1e3),
        linear("mj", "Mégajoule", "MJ", 1e6),
        linear("cal", "Calorie", "cal", 4.184),
        linear("kcal", "Kilocalorie", "kcal", 4184.0),
        linear("wh", "Wattheure", "Wh", 3600.0),
        linear("kwh", "Kilowattheure", "kWh", 3.6e6),
        linear("ev", "Électronvolt", "eV", 1.602_176_634e-19),
        linear("btu", "BTU", "BTU", 1055.055_852_62),
        linear("ftlb", "Pied-livre", "ft·lbf", 1.355_817_948_331_400_4),
    ], "kcal", "kj"),
    Category("power", "Puissance", [
        linear("w", "Watt", "W", 1.0),
        linear("kw", "Kilowatt", "kW", 1e3),
        linear("mw", "Mégawatt", "MW", 1e6),
        linear("ch", "Cheval-vapeur", "ch", 735.498_75),
        linear("hp", "Horsepower (impérial)", "hp", 745.699_871_582_270_2),
        linear("btuh", "BTU par heure", "BTU/h", 0.293_071_070_172_222),
        linear("kcalh", "Kilocalorie par heure", "kcal/h", 4184 / 3600),
    ], "kw", "ch"),
    Category("pressure", "Pression", [
        linear("pa", "Pascal", "Pa", 1.0),
        linear("hpa", "Hectopascal", "hPa", 100.0),
        linear("kpa", "Kilopascal", "kPa", 1e3),
        linear("mpa", "Mégapascal", "MPa", 1e6),
        linear("mbar", "Millibar", "mbar", 100.0),
        linear("bar", "Bar", "bar", 1e5),
        linear("atm", "Atmosphère", "atm", 101_325.0),
        linear("torr", "Torr", "Torr", 101_325 / 760),
        linear("mmhg", "Millimètre de mercure", "mmHg", 133.322_387_415),
        linear("inhg", "Pouce de mercure", "inHg", 3386.389),
        linear("psi", "Livre par pouce carré", "psi", 6894.757_293_168),
    ], "bar", "psi"),
    Category("angle", "Angle", [
        linear("deg", "Degré", "°", 1.0),
        linear("rad", "Radian", "rad", 180 / math.pi),
        linear("grad", "Grade", "gon", 0.9),
        linear("arcmin", "Minute d'arc", "′", 1 / 60),
        linear("arcsec", "Seconde d'arc", "″", 1 / 3600),
        linear("mrad", "Milliradian", "mrad", 0.18 / math.pi),
        linear("turn", "Tour", "tr", 360.0),
    ], "deg", "rad"),
    Category("frequency", "Fréquence", [
        linear("hz", "Hertz", "Hz", 1.0),
        linear("khz", "Kilohertz", "kHz", 1e3),
        linear("mhz", "Mégahertz", "MHz", 1e6),
        linear("ghz", "Gigahertz", "GHz", 1e9),
        linear("rpm", "Tour par minute", "tr/min", 1 / 60),
    ], "mhz", "khz"),
    Category("force", "Force", [
        linear("n", "Newton", "N", 1.0),
        linear("kn", "Kilonewton", "kN", 1e3),
        linear("dyn", "Dyne", "dyn", 1e-5),
        linear("kgf", "Kilogramme-force", "kgf", 9.806_65),
        linear("lbf", "Livre-force", "lbf", 4.448_221_615_260_5),
    ], "n", "kgf"),
    Category("fuel", "Consommation", [
        reciprocal("l100", "Litres aux 100 km", "L/100 km", 100.0),
        linear("kml", "Kilomètres par litre", "km/L", 1.0),
        linear("mpg_us", "Miles par gallon (US)", "mpg US", MILE / 1000 / GALLON_US),
        linear("mpg_uk", "Miles par gallon (UK)", "mpg UK", MILE / 1000 / GALLON_UK),
    ], "l100", "mpg_us"),
]

CATEGORY_BY_KEY = {c.key: c for c in CATEGORIES}


def convert(value: float, category: Category, from_key: str, to_key: str) -> float:
    """Convertit ``value`` de l'unité ``from_key`` vers ``to_key``."""
    src = category.get(from_key)
    dst = category.get(to_key)
    try:
        base = src.to_base(value)
        if category.minimum_base is not None and base < category.minimum_base - 1e-9:
            raise CalcError("Valeur sous le zéro absolu")
        result = dst.from_base(base)
    except ZeroDivisionError:
        raise CalcError("Division par zéro") from None
    except OverflowError:
        raise CalcError("Dépassement de capacité") from None
    if math.isinf(result) or math.isnan(result):
        raise CalcError("Dépassement de capacité")
    return result
