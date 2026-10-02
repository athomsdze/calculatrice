"""Palette de couleurs (clair, sombre) et polices."""

from __future__ import annotations

import sys

import customtkinter as ctk

# Chaque couleur est un couple (thème clair, thème sombre).
BG = ("#EEF0F5", "#0E1015")
SIDEBAR = ("#FFFFFF", "#14171F")
CARD = ("#FFFFFF", "#1A1E28")
CARD_ALT = ("#F5F6FA", "#151922")
BORDER = ("#E3E6ED", "#262B37")
TEXT = ("#141824", "#ECEEF3")
MUTED = ("#6B7280", "#8A93A6")
ACCENT = ("#5B57F0", "#7C78FF")
ACCENT_HOVER = ("#4A46DE", "#8E8AFF")
ACCENT_SOFT = ("#E7E6FF", "#262650")
ACCENT_SOFT_HOVER = ("#DAD8FF", "#30306A")
ACCENT_TEXT = ("#4F46E5", "#A9A6FF")
ON_ACCENT = ("#FFFFFF", "#FFFFFF")
DANGER = ("#DC2626", "#FF6B6B")
SUCCESS = ("#16A34A", "#4ADE80")

BTN_NUM = ("#FFFFFF", "#242936")
BTN_NUM_HOVER = ("#F1F2F7", "#2E3443")
BTN_FN = ("#E3E6EF", "#1E2230")
BTN_FN_HOVER = ("#D8DCE7", "#282D3C")
NAV_ACTIVE = ("#ECEBFF", "#22223F")
NAV_HOVER = ("#F2F3F7", "#1C2029")

if sys.platform == "win32":
    FAMILY = "Segoe UI"
    DISPLAY_FAMILY = "Segoe UI Light"
elif sys.platform == "darwin":
    FAMILY = DISPLAY_FAMILY = "Helvetica Neue"
else:
    FAMILY = DISPLAY_FAMILY = "DejaVu Sans"

_fonts: dict[tuple, ctk.CTkFont] = {}


def font(size: int, weight: str = "normal", family: str | None = None) -> ctk.CTkFont:
    """Police CTk mise en cache (à appeler après la création de la fenêtre)."""
    key = (family or FAMILY, size, weight)
    if key not in _fonts:
        _fonts[key] = ctk.CTkFont(family=key[0], size=size, weight=weight)
    return _fonts[key]


def is_dark() -> bool:
    return ctk.get_appearance_mode() == "Dark"


def resolve(color: tuple[str, str] | str) -> str:
    """Couleur effective selon le thème courant (pour les widgets Tk natifs)."""
    if isinstance(color, str):
        return color
    return color[1] if is_dark() else color[0]


def blend(color_a: str, color_b: str, t: float) -> str:
    """Mélange deux couleurs hexadécimales (t=0 → a, t=1 → b)."""
    a = [int(color_a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(color_b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))
