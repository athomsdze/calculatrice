import math

import pytest

from calculatrice.core.evaluator import (
    DEG, GRAD, RAD, CalcError, evaluate, format_fixed, format_number, parse_user_number,
)


@pytest.mark.parametrize("expr, expected", [
    ("1+2×3", 7),
    ("(1+2)×3", 9),
    ("10÷4", 2.5),
    ("2^10", 1024),
    ("2^3^2", 512),
    ("-2^2", -4),
    ("2^-1", 0.5),
    ("7 mod 3", 1),
    ("5!", 120),
    ("3²", 9),
    ("2³", 8),
    ("4⁻¹", 0.25),
    ("√(16)", 4),
    ("√16+1", 5),
    ("∛(-27)", -3),
    ("2π", 2 * math.pi),
    ("3(1+2)", 9),
    ("(1+2)(3+4)", 21),
    ("2sin(30)", 1),
    ("1,5+1.5", 3),
    ("1,5E3", 1500),
    ("2E-3", 0.002),
    ("200+10%", 220),
    ("200−10%", 180),
    ("50%", 0.5),
    ("50%×200", 100),
    ("ln(e)", 1),
    ("log(1000)", 3),
    ("log(8;2)", 3),
    ("log₂(8)", 3),
    ("e^(0)", 1),
    ("10^(3)", 1000),
    ("abs(-4)", 4),
    ("nCr(5;2)", 10),
    ("nPr(5;2)", 20),
    ("(-8)^(1/3)", -2),
    ("(-8)^(2/3)", 4),
    ("(1+2", 3),
    ("sin(30", 0.5),
    ("round(2,567;2)", 2.57),
    ("2**3", 8),
    ("π", math.pi),
])
def test_evaluate(expr, expected):
    assert evaluate(expr) == pytest.approx(expected)


def test_trigonometry_modes():
    assert evaluate("sin(90)", DEG) == 1
    assert evaluate("cos(90)", DEG) == 0
    assert evaluate("tan(45)", DEG) == 1
    assert evaluate("sin(π)", RAD) == 0
    assert evaluate("cos(π)", RAD) == pytest.approx(-1)
    assert evaluate("sin(100)", GRAD) == 1
    assert evaluate("sin(30)×2−1", DEG) == 0
    assert evaluate("sin⁻¹(1)", DEG) == pytest.approx(90)
    assert evaluate("sin⁻¹(1)", RAD) == pytest.approx(math.pi / 2)
    assert evaluate("tan⁻¹(1)", GRAD) == pytest.approx(50)
    assert evaluate("cosh(0)") == 1
    assert evaluate("sinh⁻¹(0)") == 0


def test_ans():
    assert evaluate("Ans×2", ans=21) == 42
    assert evaluate("ans+1", ans=1) == 2


@pytest.mark.parametrize("expr, message", [
    ("1÷0", "Division par zéro"),
    ("√(-1)", "Racine"),
    ("ln(0)", "domaine"),
    ("tan(90)", "non définie"),
    ("", "vide"),
    ("2+", "incomplète"),
    ("(1+2))", "Parenthèse"),
    ("2 3", "syntaxe"),
    ("1#2", "inconnu"),
    ("171!", "Dépassement"),
    ("10^400", "Dépassement"),
    ("(-1)!", "domaine"),
    ("sin⁻¹(2)", "domaine"),
    ("nCr(2;5)", "domaine"),
    ("nCr(100000;50000)", "Dépassement"),
    ("0^-1", "Division par zéro"),
    ("(-2)^0,5", "domaine"),
])
def test_errors(expr, message):
    with pytest.raises(CalcError, match=message):
        evaluate(expr)


@pytest.mark.parametrize("value, expected", [
    (0, "0"),
    (-0.0, "0"),
    (0.1 + 0.2, "0,3"),
    (1 / 3, "0,33333333333333"),
    (1234567.5, "1234567,5"),
    (-42, "-42"),
    (1e20, "1E+20"),
    (1.5e-9, "1,5E-9"),
    (123456789012345.0, "123456789012345"),
])
def test_format_number(value, expected):
    assert format_number(value) == expected


def test_format_grouping():
    assert format_number(1234567.891, sig=10, group=" ") == "1 234 567,891"
    assert format_fixed(1234.5, 2, group=" ") == "1 234,50"
    assert format_fixed(-0.001, 2) == "0,00"


def test_parse_user_number():
    assert parse_user_number("1 234,5") == 1234.5
    assert parse_user_number("1 000") == 1000
    assert parse_user_number("2×3") == 6
    with pytest.raises(CalcError):
        parse_user_number("  ")
