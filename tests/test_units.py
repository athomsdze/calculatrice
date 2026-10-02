import pytest

from calculatrice.core.evaluator import CalcError
from calculatrice.core.units import CATEGORIES, CATEGORY_BY_KEY, convert


def cat(key):
    return CATEGORY_BY_KEY[key]


@pytest.mark.parametrize("category, value, src, dst, expected", [
    ("length", 1, "km", "m", 1000),
    ("length", 1, "mi", "km", 1.609344),
    ("length", 12, "in", "ft", 1),
    ("mass", 1, "kg", "lb", 2.20462262185),
    ("temperature", 100, "c", "f", 212),
    ("temperature", 32, "f", "c", 0),
    ("temperature", 0, "c", "k", 273.15),
    ("temperature", -40, "c", "f", -40),
    ("area", 1, "ha", "m2", 10000),
    ("volume", 1, "gal_us", "l", 3.785411784),
    ("volume", 1, "m3", "l", 1000),
    ("speed", 100, "kmh", "mps", 27.7777777778),
    ("time", 2, "h", "min", 120),
    ("data", 1, "GiB", "MiB", 1024),
    ("data", 8, "bit", "B", 1),
    ("energy", 1, "kwh", "kj", 3600),
    ("power", 1, "ch", "w", 735.49875),
    ("pressure", 1, "atm", "hpa", 1013.25),
    ("angle", 180, "deg", "rad", 3.14159265359),
    ("frequency", 60, "rpm", "hz", 1),
    ("force", 1, "kgf", "n", 9.80665),
    ("fuel", 5, "l100", "kml", 20),
    ("fuel", 20, "kml", "l100", 5),
    ("fuel", 10, "l100", "mpg_us", 23.5214583),
])
def test_conversions(category, value, src, dst, expected):
    assert convert(value, cat(category), src, dst) == pytest.approx(expected)


def test_round_trip_every_unit():
    for category in CATEGORIES:
        ref = category.get(category.default_from)
        for unit in category.units:
            there = convert(7.5, category, ref.key, unit.key)
            back = convert(there, category, unit.key, ref.key)
            assert back == pytest.approx(7.5), (category.key, unit.key)


def test_defaults_and_unique_keys():
    for category in CATEGORIES:
        keys = [u.key for u in category.units]
        assert len(keys) == len(set(keys)), category.key
        labels = [u.label for u in category.units]
        assert len(labels) == len(set(labels)), category.key
        category.get(category.default_from)
        category.get(category.default_to)


def test_absolute_zero_and_zero_consumption():
    with pytest.raises(CalcError, match="zéro absolu"):
        convert(-300, cat("temperature"), "c", "k")
    with pytest.raises(CalcError):
        convert(0, cat("fuel"), "l100", "kml")
