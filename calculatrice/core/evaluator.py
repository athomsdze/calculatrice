"""Évaluateur d'expressions mathématiques, sans ``eval``.

L'expression est découpée en jetons, transformée en arbre puis évaluée.
Conventions (françaises) :

* la virgule et le point sont acceptés comme séparateur décimal ;
* le point-virgule sépare les arguments : ``nCr(5;2)``, ``log(8;2)`` ;
* ``E`` (majuscule) introduit l'exposant : ``1,5E3`` = 1500 ;
* la multiplication implicite est gérée : ``2π``, ``3(1+2)``, ``2sin(30)`` ;
* ``200+10%`` vaut 220 (pourcentage relatif, comme sur une calculatrice).
"""

from __future__ import annotations

import math
import re
from fractions import Fraction

DEG, RAD, GRAD = "DEG", "RAD", "GRAD"
ANGLE_MODES = (DEG, RAD, GRAD)


class CalcError(Exception):
    """Erreur de calcul dont le message peut être affiché tel quel."""


# --------------------------------------------------------------------------
# Jetons
# --------------------------------------------------------------------------

NUM, NAME, OP, POST, LPAREN, RPAREN, SEP, EOF = (
    "NUM", "NAME", "OP", "POST", "(", ")", ";", "EOF",
)

# nom saisi (en minuscules) -> nom canonique de fonction
FUNCTIONS = {
    "sin": "sin", "cos": "cos", "tan": "tan",
    "sin⁻¹": "asin", "cos⁻¹": "acos", "tan⁻¹": "atan",
    "asin": "asin", "acos": "acos", "atan": "atan",
    "arcsin": "asin", "arccos": "acos", "arctan": "atan",
    "sinh": "sinh", "cosh": "cosh", "tanh": "tanh",
    "sinh⁻¹": "asinh", "cosh⁻¹": "acosh", "tanh⁻¹": "atanh",
    "asinh": "asinh", "acosh": "acosh", "atanh": "atanh",
    "ln": "ln", "log": "log", "log₂": "log2",
    "√": "sqrt", "sqrt": "sqrt", "racine": "sqrt",
    "∛": "cbrt", "cbrt": "cbrt",
    "abs": "abs", "exp": "exp",
    "floor": "floor", "ceil": "ceil", "round": "round", "arrondi": "round",
    "ncr": "nCr", "npr": "nPr",
}

CONSTANTS = {"π": "pi", "pi": "pi", "e": "e", "ans": "ans"}

# opérateurs écrits en toutes lettres
WORD_OPERATORS = {"mod": "mod"}

_SYMBOLS = {
    "+": (OP, "+"), "-": (OP, "-"), "−": (OP, "-"), "–": (OP, "-"),
    "*": (OP, "*"), "×": (OP, "*"), "·": (OP, "*"),
    "/": (OP, "/"), "÷": (OP, "/"), ":": (OP, "/"),
    "^": (OP, "^"),
    "!": (POST, "!"), "%": (POST, "%"), "²": (POST, "²"), "³": (POST, "³"),
    "(": (LPAREN, "("), ")": (RPAREN, ")"),
    ";": (SEP, ";"),
}

_NAMES = sorted(
    list(FUNCTIONS) + list(CONSTANTS) + list(WORD_OPERATORS), key=len, reverse=True
)
_NUMBER_RE = re.compile(r"(\d+(?:[.,]\d*)?|[.,]\d+)(?:E([+-]?\d+))?")


def tokenize(text: str) -> list[tuple[str, object]]:
    tokens: list[tuple[str, object]] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if text.startswith("**", i):
            tokens.append((OP, "^"))
            i += 2
            continue
        if text.startswith("⁻¹", i):
            tokens.append((POST, "⁻¹"))
            i += 2
            continue
        m = _NUMBER_RE.match(text, i)
        if m:
            mantissa = m.group(1).replace(",", ".")
            exponent = m.group(2)
            try:
                value = float(mantissa + (f"e{exponent}" if exponent else ""))
            except (ValueError, OverflowError):
                raise CalcError("Nombre invalide") from None
            if math.isinf(value):
                raise CalcError("Dépassement de capacité")
            tokens.append((NUM, value))
            i = m.end()
            continue
        if ch in _SYMBOLS:
            tokens.append(_SYMBOLS[ch])
            i += 1
            continue
        lowered = text[i:].lower()
        for name in _NAMES:
            if lowered.startswith(name):
                if name in FUNCTIONS:
                    tokens.append((NAME, ("func", FUNCTIONS[name])))
                elif name in CONSTANTS:
                    tokens.append((NAME, ("const", CONSTANTS[name])))
                else:
                    tokens.append((OP, WORD_OPERATORS[name]))
                i += len(name)
                break
        else:
            raise CalcError(f"Symbole inconnu : « {ch} »")
    return tokens


# --------------------------------------------------------------------------
# Analyse syntaxique (descente récursive)
# --------------------------------------------------------------------------
#   expr    := term (('+'|'-') term)*
#   term    := unary (('*'|'/'|'mod') unary | <implicite> power)*
#   unary   := ('-'|'+') unary | power
#   power   := postfix ('^' unary)?          (associatif à droite)
#   postfix := primary ('!'|'%'|'²'|'³'|'⁻¹')*
#   primary := nombre | constante | fonction '(' args ')' | fonction unary | '(' expr ')'


class _Parser:
    def __init__(self, tokens: list[tuple[str, object]]):
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> tuple[str, object]:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else (EOF, None)

    def advance(self) -> tuple[str, object]:
        tok = self.peek()
        self.pos += 1
        return tok

    def parse(self):
        if not self.tokens:
            raise CalcError("Expression vide")
        node = self.expr()
        kind, _ = self.peek()
        if kind == RPAREN:
            raise CalcError("Parenthèse fermante en trop")
        if kind != EOF:
            raise CalcError("Erreur de syntaxe")
        return node

    def expr(self):
        node = self.term()
        while True:
            kind, value = self.peek()
            if kind == OP and value in ("+", "-"):
                self.advance()
                node = ("bin", value, node, self.term())
            else:
                return node

    def term(self):
        node = self.unary()
        while True:
            kind, value = self.peek()
            if kind == OP and value in ("*", "/", "mod"):
                self.advance()
                node = ("bin", value, node, self.unary())
            elif kind in (NUM, NAME, LPAREN):
                prev_kind = self.tokens[self.pos - 1][0]
                if kind == NUM and prev_kind == NUM:
                    raise CalcError("Erreur de syntaxe")
                node = ("bin", "*", node, self.power())
            else:
                return node

    def unary(self):
        kind, value = self.peek()
        if kind == OP and value == "-":
            self.advance()
            return ("neg", self.unary())
        if kind == OP and value == "+":
            self.advance()
            return self.unary()
        return self.power()

    def power(self):
        base = self.postfix()
        kind, value = self.peek()
        if kind == OP and value == "^":
            self.advance()
            return ("bin", "^", base, self.unary())
        return base

    def postfix(self):
        node = self.primary()
        while self.peek()[0] == POST:
            node = ("post", self.advance()[1], node)
        return node

    def _close_paren(self):
        kind, _ = self.peek()
        if kind == RPAREN:
            self.advance()
        elif kind != EOF:  # les parenthèses non fermées en fin d'expression sont tolérées
            raise CalcError("Parenthèse manquante")

    def primary(self):
        kind, value = self.advance()
        if kind == NUM:
            return ("num", value)
        if kind == NAME:
            category, name = value
            if category == "const":
                return ("const", name)
            if self.peek()[0] == LPAREN:
                self.advance()
                args = [self.expr()]
                while self.peek()[0] == SEP:
                    self.advance()
                    args.append(self.expr())
                self._close_paren()
                return ("call", name, args)
            if self.peek()[0] == EOF:
                raise CalcError("Expression incomplète")
            return ("call", name, [self.unary()])
        if kind == LPAREN:
            node = self.expr()
            self._close_paren()
            return node
        if kind == EOF:
            raise CalcError("Expression incomplète")
        raise CalcError("Erreur de syntaxe")


# --------------------------------------------------------------------------
# Évaluation
# --------------------------------------------------------------------------

# valeurs exactes pour les angles remarquables (en degrés, modulo 360)
_EXACT_SIN = {0: 0.0, 30: 0.5, 90: 1.0, 150: 0.5, 180: 0.0, 210: -0.5, 270: -1.0, 330: -0.5}
_EXACT_COS = {0: 1.0, 60: 0.5, 90: 0.0, 120: -0.5, 180: -1.0, 240: -0.5, 270: 0.0, 300: 0.5}
_EXACT_TAN = {0: 0.0, 45: 1.0, 90: None, 135: -1.0, 180: 0.0, 225: 1.0, 270: None, 315: -1.0}


def _to_degrees(x: float, mode: str) -> float:
    return x * 9 / 10 if mode == GRAD else x


def _angle_to_rad(x: float, mode: str) -> float:
    if mode == DEG:
        return math.radians(x)
    if mode == GRAD:
        return x * math.pi / 200
    return x


def _rad_to_angle(x: float, mode: str) -> float:
    if mode == DEG:
        return math.degrees(x)
    if mode == GRAD:
        return x * 200 / math.pi
    return x


def _trig(name: str, x: float, mode: str) -> float:
    if mode != RAD:
        deg = math.fmod(_to_degrees(x, mode), 360.0)
        if deg < 0:
            deg += 360.0
        table = {"sin": _EXACT_SIN, "cos": _EXACT_COS, "tan": _EXACT_TAN}[name]
        if deg in table:
            value = table[deg]
            if value is None:
                raise CalcError("Valeur non définie")
            return value
    result = getattr(math, name)(_angle_to_rad(x, mode))
    return 0.0 if abs(result) < 1e-15 else result


def _pow(a: float, b: float) -> float:
    if a == 0 and b < 0:
        raise CalcError("Division par zéro")
    try:
        return math.pow(a, b)
    except OverflowError:
        raise CalcError("Dépassement de capacité") from None
    except ValueError:
        # racine impaire d'un nombre négatif, ex. (-8)^(1/3) = -2
        frac = Fraction(b).limit_denominator(1000)
        if abs(float(frac) - b) < 1e-12 and frac.denominator % 2 == 1:
            sign = -1.0 if frac.numerator % 2 else 1.0
            return sign * math.pow(-a, b)
        raise CalcError("Erreur de domaine") from None


def _factorial(x: float) -> float:
    if x > 170:
        raise CalcError("Dépassement de capacité")
    if x == int(x):
        if x < 0:
            raise CalcError("Erreur de domaine")
        return float(math.factorial(int(x)))
    return math.gamma(x + 1)


def _as_int(x: float, what: str = "entier") -> int:
    if x != int(x):
        raise CalcError(f"Argument {what} attendu")
    return int(x)


def _combination(n: float, r: float, perm: bool) -> float:
    n_i, r_i = _as_int(n), _as_int(r)
    if n_i < 0 or r_i < 0 or r_i > n_i:
        raise CalcError("Erreur de domaine")
    # estimation logarithmique pour éviter de calculer des entiers gigantesques
    log_value = math.lgamma(n_i + 1) - math.lgamma(n_i - r_i + 1)
    if not perm:
        log_value -= math.lgamma(r_i + 1)
    if log_value > 709:
        raise CalcError("Dépassement de capacité")
    value = math.perm(n_i, r_i) if perm else math.comb(n_i, r_i)
    return float(value)


def _log(args: list[float]) -> float:
    x = args[0]
    if x <= 0:
        raise CalcError("Erreur de domaine")
    if len(args) == 1:
        return math.log10(x)
    base = args[1]
    if base <= 0 or base == 1:
        raise CalcError("Base de logarithme invalide")
    return math.log(x) / math.log(base)


def _round(args: list[float]) -> float:
    digits = _as_int(args[1]) if len(args) > 1 else 0
    return float(round(args[0], digits))


_ARITY = {"log": (1, 2), "round": (1, 2), "nCr": (2, 2), "nPr": (2, 2)}


def _call(name: str, args: list[float], mode: str) -> float:
    low, high = _ARITY.get(name, (1, 1))
    if not low <= len(args) <= high:
        raise CalcError(f"Nombre d'arguments incorrect pour {name}")
    x = args[0]
    if name in ("sin", "cos", "tan"):
        return _trig(name, x, mode)
    if name in ("asin", "acos", "atan"):
        return _rad_to_angle(getattr(math, name)(x), mode)
    if name in ("sinh", "cosh", "tanh", "asinh", "acosh", "atanh"):
        return getattr(math, name)(x)
    if name == "ln":
        if x <= 0:
            raise CalcError("Erreur de domaine")
        return math.log(x)
    if name == "log":
        return _log(args)
    if name == "log2":
        if x <= 0:
            raise CalcError("Erreur de domaine")
        return math.log2(x)
    if name == "sqrt":
        if x < 0:
            raise CalcError("Racine d'un nombre négatif")
        return math.sqrt(x)
    if name == "cbrt":
        return math.cbrt(x)
    if name == "abs":
        return abs(x)
    if name == "exp":
        return math.exp(x)
    if name == "floor":
        return float(math.floor(x))
    if name == "ceil":
        return float(math.ceil(x))
    if name == "round":
        return _round(args)
    if name == "nCr":
        return _combination(args[0], args[1], perm=False)
    if name == "nPr":
        return _combination(args[0], args[1], perm=True)
    raise CalcError(f"Fonction inconnue : {name}")


def _is_percent(node) -> bool:
    return node[0] == "post" and node[1] == "%"


def _eval(node, mode: str, ans: float) -> float:
    kind = node[0]
    if kind == "num":
        return node[1]
    if kind == "const":
        return {"pi": math.pi, "e": math.e, "ans": ans}[node[1]]
    if kind == "neg":
        return -_eval(node[1], mode, ans)
    if kind == "post":
        _, symbol, child = node
        v = _eval(child, mode, ans)
        if symbol == "!":
            return _factorial(v)
        if symbol == "%":
            return v / 100.0
        if symbol == "²":
            return v * v
        if symbol == "³":
            return v * v * v
        if v == 0:  # ⁻¹
            raise CalcError("Division par zéro")
        return 1.0 / v
    if kind == "bin":
        _, op, left, right = node
        if op in ("+", "-") and _is_percent(right):
            base = _eval(left, mode, ans)
            pct = _eval(right[2], mode, ans) / 100.0
            return base * (1 + pct) if op == "+" else base * (1 - pct)
        a = _eval(left, mode, ans)
        b = _eval(right, mode, ans)
        if op == "+":
            return a + b
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if op == "/":
            if b == 0:
                raise CalcError("Division par zéro")
            return a / b
        if op == "mod":
            if b == 0:
                raise CalcError("Division par zéro")
            return a % b
        return _pow(a, b)
    if kind == "call":
        _, name, arg_nodes = node
        return _call(name, [_eval(a, mode, ans) for a in arg_nodes], mode)
    raise CalcError("Erreur interne")


def evaluate(expression: str, angle_mode: str = DEG, ans: float = 0.0) -> float:
    """Évalue ``expression`` et renvoie un flottant, ou lève :class:`CalcError`."""
    if angle_mode not in ANGLE_MODES:
        raise ValueError(f"mode d'angle inconnu : {angle_mode}")
    try:
        tree = _Parser(tokenize(expression)).parse()
        result = _eval(tree, angle_mode, ans)
    except CalcError:
        raise
    except ZeroDivisionError:
        raise CalcError("Division par zéro") from None
    except OverflowError:
        raise CalcError("Dépassement de capacité") from None
    except ValueError:
        raise CalcError("Erreur de domaine") from None
    except RecursionError:
        raise CalcError("Expression trop complexe") from None
    if math.isnan(result):
        raise CalcError("Erreur de domaine")
    if math.isinf(result):
        raise CalcError("Dépassement de capacité")
    return result


# --------------------------------------------------------------------------
# Mise en forme et saisie des nombres
# --------------------------------------------------------------------------

NBSP = " "


def _group_thousands(digits: str, sep: str) -> str:
    sign = ""
    if digits.startswith("-"):
        sign, digits = "-", digits[1:]
    parts = []
    while len(digits) > 3:
        parts.insert(0, digits[-3:])
        digits = digits[:-3]
    parts.insert(0, digits)
    return sign + sep.join(parts)


def format_number(x: float, sig: int = 14, decimal: str = ",", group: str = "") -> str:
    """Formate ``x`` avec au plus ``sig`` chiffres significatifs.

    Les très grands ou très petits nombres passent en notation ``1,5E+20``.
    """
    if math.isnan(x) or math.isinf(x):
        raise CalcError("Dépassement de capacité")
    if x == 0:
        return "0"
    exponent = math.floor(math.log10(abs(x)))
    if -7 <= exponent < 15:
        decimals = max(0, sig - 1 - exponent)
        text = f"{x:.{decimals}f}"
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        int_part, _, frac = text.partition(".")
        if int_part == "-0" and not frac:
            return "0"
        if group:
            int_part = _group_thousands(int_part, group)
        return int_part + (decimal + frac if frac else "")
    mantissa, _, exp = f"{x:.{sig - 1}e}".partition("e")
    if "." in mantissa:
        mantissa = mantissa.rstrip("0").rstrip(".")
    exp_value = int(exp)
    return f"{mantissa.replace('.', decimal)}E{'+' if exp_value >= 0 else '-'}{abs(exp_value)}"


def format_fixed(x: float, decimals: int, decimal: str = ",", group: str = NBSP) -> str:
    """Formate ``x`` avec un nombre fixe de décimales et des séparateurs de milliers."""
    if math.isnan(x) or math.isinf(x):
        return "—"
    if abs(x) >= 1e15:
        return format_number(x, sig=10, decimal=decimal)
    text = f"{x:.{decimals}f}"
    int_part, _, frac = text.partition(".")
    if int_part == "-0" and not frac.strip("0"):
        int_part = "0"
    int_part = _group_thousands(int_part, group)
    return int_part + (decimal + frac if frac else "")


def format_pretty(x: float, sig: int = 10) -> str:
    """Formatage lisible (séparateur de milliers) pour les convertisseurs."""
    return format_number(x, sig=sig, group=NBSP)


def parse_user_number(text: str, angle_mode: str = DEG) -> float:
    """Lit un nombre saisi par l'utilisateur (« 1 234,5 », « 2×3 », « 1/3 »...)."""
    cleaned = text.replace(NBSP, "").replace(" ", "").replace(" ", "").strip()
    if not cleaned:
        raise CalcError("Saisie vide")
    return evaluate(cleaned, angle_mode)
