"""Thème clair / sombre : palettes, polices et feuille de style Qt."""

from __future__ import annotations

import sys
from functools import lru_cache

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication

PALETTES: dict[str, dict[str, str]] = {
    "dark": {
        "bg": "#0E1015", "sidebar": "#12151C", "card": "#191D27", "card_alt": "#151922",
        "input": "#141821", "border": "#262B37", "text": "#ECEEF3", "muted": "#8A93A6",
        "accent": "#7C78FF", "accent_hover": "#8F8BFF", "accent_soft": "#25254D",
        "accent_soft_hover": "#2F2F66", "accent_text": "#ABA8FF", "on_accent": "#FFFFFF",
        "danger": "#FF6B6B", "success": "#4ADE80",
        "btn_num": "#242936", "btn_num_hover": "#2F3545", "btn_fn": "#1D212D",
        "btn_fn_hover": "#282E3D", "nav_active": "#23233F", "nav_hover": "#1B1F29",
        "scroll": "#353B4A",
    },
    "light": {
        "bg": "#EEF0F5", "sidebar": "#FFFFFF", "card": "#FFFFFF", "card_alt": "#F5F6FA",
        "input": "#F5F6FA", "border": "#E3E6ED", "text": "#141824", "muted": "#6B7280",
        "accent": "#5B57F0", "accent_hover": "#4A46DE", "accent_soft": "#E8E7FF",
        "accent_soft_hover": "#DAD8FF", "accent_text": "#4F46E5", "on_accent": "#FFFFFF",
        "danger": "#DC2626", "success": "#16A34A",
        "btn_num": "#FFFFFF", "btn_num_hover": "#F1F2F7", "btn_fn": "#E4E7EF",
        "btn_fn_hover": "#D9DDE8", "nav_active": "#ECEBFF", "nav_hover": "#F2F3F7",
        "scroll": "#CDD2DC",
    },
}

if sys.platform == "win32":
    FAMILIES = ["Segoe UI Variable Text", "Segoe UI"]
    DISPLAY_FAMILIES = ["Segoe UI Variable Display", "Segoe UI"]
elif sys.platform == "darwin":
    FAMILIES = DISPLAY_FAMILIES = [".AppleSystemUIFont", "Helvetica Neue"]
else:
    FAMILIES = DISPLAY_FAMILIES = ["Inter", "Cantarell", "DejaVu Sans"]

NORMAL = QFont.Weight.Normal
LIGHT = QFont.Weight.Light
MEDIUM = QFont.Weight.Medium
SEMIBOLD = QFont.Weight.DemiBold
BOLD = QFont.Weight.Bold


@lru_cache(maxsize=512)
def font(px: int, weight: QFont.Weight = NORMAL, display: bool = False) -> QFont:
    """Police à taille en pixels logiques (mise en cache, ne pas modifier)."""
    f = QFont()
    f.setFamilies(DISPLAY_FAMILIES if display else FAMILIES)
    f.setPixelSize(max(1, int(px)))
    f.setWeight(weight)
    return f


def mix(a: QColor, b: QColor, t: float) -> QColor:
    """Interpolation linéaire entre deux couleurs (alpha compris)."""
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
        round(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


def with_alpha(color: QColor, alpha: float) -> QColor:
    c = QColor(color)
    c.setAlphaF(max(0.0, min(1.0, alpha)))
    return c


class Theme(QObject):
    """Thème courant. ``changed`` est émis après chaque changement de palette."""

    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.mode = "Dark"  # réglage : Light, Dark ou System
        self.name = "dark"  # palette effective

    @property
    def colors(self) -> dict[str, str]:
        return PALETTES[self.name]

    @property
    def is_dark(self) -> bool:
        return self.name == "dark"

    def color(self, key: str) -> QColor:
        return QColor(PALETTES[self.name][key])

    def resolve(self, mode: str) -> str:
        if mode == "Light":
            return "light"
        if mode == "System":
            app = QGuiApplication.instance()
            if app is not None and app.styleHints().colorScheme() == Qt.ColorScheme.Light:
                return "light"
        return "dark"

    def set_mode(self, mode: str) -> None:
        self.mode = mode if mode in ("Light", "Dark", "System") else "Dark"
        self.name = self.resolve(self.mode)
        app = QGuiApplication.instance()
        if app is not None:
            app.setStyleSheet(stylesheet(self.colors))
        self.changed.emit()


THEME = Theme()


def stylesheet(c: dict[str, str]) -> str:
    """Feuille de style des widgets standard (les widgets dessinés à la main lisent THEME)."""
    return f"""
    QWidget#Root {{ background: {c['bg']}; }}
    QFrame#Sidebar {{ background: {c['sidebar']}; border: none; border-right: 1px solid {c['border']}; }}
    QFrame#Card {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 18px; }}
    QLabel {{ color: {c['text']}; background: transparent; }}
    QLabel[role="muted"] {{ color: {c['muted']}; }}
    QLabel[role="accent"] {{ color: {c['accent_text']}; }}
    QLabel[role="danger"] {{ color: {c['danger']}; }}
    QLabel[role="success"] {{ color: {c['success']}; }}
    QLabel#ResultBox {{ background: {c['accent_soft']}; color: {c['accent_text']};
                        border-radius: 12px; padding: 0 16px; }}
    QLineEdit {{ background: {c['input']}; color: {c['text']}; border: 1px solid {c['border']};
                 border-radius: 12px; padding: 4px 14px;
                 selection-background-color: {c['accent']}; selection-color: #FFFFFF; }}
    QLineEdit:focus {{ border: 1px solid {c['accent']}; }}
    QLineEdit#Display {{ background: transparent; border: none; padding: 0 4px; }}
    QLineEdit#Search {{ border-radius: 10px; padding: 4px 12px; }}
    QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px 4px 0; }}
    QScrollBar::handle:vertical {{ background: {c['scroll']}; border-radius: 4px; min-height: 36px; }}
    QScrollBar::handle:vertical:hover {{ background: {c['muted']}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
    QScrollBar:horizontal {{ height: 0; }}
    QFrame#Popup {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 14px; }}
    QListWidget {{ background: transparent; border: none; outline: 0; color: {c['text']}; }}
    QListWidget::item {{ padding: 7px 10px; border-radius: 8px; }}
    QListWidget::item:hover {{ background: {c['nav_hover']}; }}
    QListWidget::item:selected {{ background: {c['accent']}; color: #FFFFFF; }}
    QToolTip {{ background: {c['card']}; color: {c['text']}; border: 1px solid {c['border']};
                padding: 4px 8px; }}
    """
