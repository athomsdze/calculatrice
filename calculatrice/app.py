"""Fenêtre principale : barre latérale, pages animées, thème et tâches en arrière-plan."""

from __future__ import annotations

import sys
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable

from PySide6.QtCore import QEasingCurve, QKeyCombination, QObject, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QGuiApplication, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QMainWindow, QVBoxLayout, QWidget,
)

from . import APP_NAME, __version__
from .storage import Settings, resource_path
from .ui.calculator_view import CalculatorView
from .ui.currency_view import CurrencyView
from .ui.theme import BOLD, SEMIBOLD, THEME, font
from .ui.units_view import UnitsView
from .ui.widgets import (
    Centered, FadeOverlay, LogoMark, PillList, SegmentedControl, Toast, TransitionStack,
    make_label, supports_window_opacity,
)

APPEARANCES = {"Clair": "Light", "Sombre": "Dark", "Système": "System"}

# clé, icône, libellé, classe, largeur maximale du contenu
PAGES = [
    ("calc", "±", "Calculatrice", CalculatorView, 1500),
    ("currency", "€", "Devises", CurrencyView, 1500),
    ("units", "↔", "Unités", UnitsView, 1400),
]


def set_dark_title_bar(widget: QWidget, dark: bool) -> None:
    """Barre de titre Windows assortie au thème (Windows 10 20H1+ / 11)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        hwnd = int(widget.winId())
        value = ctypes.c_int(1 if dark else 0)
        for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (nouvelle puis ancienne valeur)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                break
        # force Windows à redessiner le cadre (SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)
    except Exception:
        pass


class _Bridge(QObject):
    """Ramène les résultats des threads dans le thread de l'interface."""

    done = Signal(object)


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self._closing = False
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="calc")
        self._bridge = _Bridge()
        # toujours différé : un résultat immédiat ne doit pas arriver pendant la construction
        self._bridge.done.connect(self._deliver, Qt.ConnectionType.QueuedConnection)
        self._fade_in: QPropertyAnimation | None = None

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(str(resource_path("assets/icon.png"))))
        self.resize(1240, 800)
        self.setMinimumSize(940, 600)

        root = QWidget(objectName="Root")
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_sidebar())

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(26, 24, 26, 24)
        self.stack = TransitionStack()
        content_layout.addWidget(self.stack)
        layout.addWidget(content, 1)

        self.views: dict[str, QWidget] = {}
        self._keys: list[str] = []
        for key, _, _, view_class, max_width in PAGES:
            view = view_class(self)
            self.views[key] = view
            self._keys.append(key)
            self.stack.add_page(Centered(view, max_width))
        self.toast_widget = Toast(root)

        self._install_shortcuts()
        last = settings.get("last_view")
        self.show_view(last if last in self.views else "calc", animate=False)
        THEME.changed.connect(self._on_theme_changed)

    # ------------------------------------------------------------------
    def _build_sidebar(self) -> QWidget:
        bar = QFrame(objectName="Sidebar")
        bar.setFixedWidth(236)
        layout = QVBoxLayout(bar)
        layout.setContentsMargins(16, 24, 16, 18)
        layout.setSpacing(0)
        brand = QHBoxLayout()
        brand.setContentsMargins(4, 0, 0, 0)
        brand.setSpacing(12)
        brand.addWidget(LogoMark(40))
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(make_label("Calculatrice", 17, BOLD))
        names.addWidget(make_label("Pro", 12, BOLD, role="accent"))
        brand.addLayout(names, 1)
        layout.addLayout(brand)
        layout.addSpacing(28)
        self.nav = PillList([(k, label, icon) for k, icon, label, _, _ in PAGES], item_height=46)
        self.nav.selected.connect(self.show_view)
        layout.addWidget(self.nav)
        layout.addStretch(1)
        layout.addWidget(make_label("Thème", 12, role="muted"))
        layout.addSpacing(6)
        current = next((k for k, v in APPEARANCES.items() if v == THEME.mode), "Sombre")
        self.theme_selector = SegmentedControl(list(APPEARANCES), current)
        self.theme_selector.changed.connect(lambda label: self.set_appearance(APPEARANCES[label]))
        layout.addWidget(self.theme_selector)
        layout.addSpacing(12)
        version = make_label(f"Version {__version__}  ·  Ctrl+1/2/3", 11, role="muted")
        layout.addWidget(version)
        return bar

    def _install_shortcuts(self) -> None:
        azerty = ["&", "é", '"']
        for index, key in enumerate(self._keys, start=1):
            sequences = [f"Ctrl+{index}", f"Ctrl+{azerty[index - 1]}"]
            for seq in sequences:
                QShortcut(QKeySequence(seq), self, activated=lambda k=key: self.show_view(k))
            keypad = QKeyCombination(
                Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.KeypadModifier,
                Qt.Key(Qt.Key.Key_0.value + index))
            QShortcut(QKeySequence(keypad), self, activated=lambda k=key: self.show_view(k))

    # ------------------------------------------------------------------
    def _on_theme_changed(self) -> None:
        set_dark_title_bar(self, THEME.is_dark)

    @property
    def current_view(self) -> str:
        return self._keys[self.stack.current_index()]

    def show_view(self, key: str, animate: bool = True) -> None:
        self.nav.set_current(key, animate)
        self.stack.set_current(self._keys.index(key), animate)
        self.settings.set("last_view", key, save=False)
        self.views[key].on_show()

    def set_appearance(self, mode: str) -> None:
        central = self.centralWidget()
        snapshot = central.grab() if self.isVisible() else None
        THEME.set_mode(mode)
        self.settings.set("appearance", mode)
        if snapshot is not None:
            FadeOverlay(central, snapshot)

    def toast(self, message: str) -> None:
        self.toast_widget.show_message(message)

    def clipboard_set(self, text: str) -> None:
        QGuiApplication.clipboard().setText(text)

    def fit_to_screen(self) -> None:
        """Taille de départ adaptée aux petits écrans, fenêtre centrée."""
        screen = self.screen().availableGeometry()
        width = min(1240, int(screen.width() * 0.92))
        height = min(800, int(screen.height() * 0.9))
        self.resize(max(width, self.minimumWidth()), max(height, self.minimumHeight()))
        self.move(screen.center() - self.rect().center())

    def show_animated(self) -> None:
        self.fit_to_screen()
        set_dark_title_bar(self, THEME.is_dark)
        if not supports_window_opacity():
            self.show()
            return
        self.setWindowOpacity(0.0)
        self.show()
        self._fade_in = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_in.setDuration(220)
        self._fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.start()

    # ------------------------------------------------------------------
    def run_async(self, func: Callable[..., Any], callback: Callable[[Any, Exception | None], None],
                  *args: Any) -> None:
        """Exécute ``func`` dans un thread ; ``callback(résultat, erreur)`` est appelé dans l'UI."""
        future = self._pool.submit(func, *args)
        future.add_done_callback(lambda f: self._bridge.done.emit((callback, f)))

    def _deliver(self, payload: tuple[Callable, Future]) -> None:
        callback, future = payload
        if self._closing or future.cancelled():
            return
        error = future.exception()
        try:
            callback(None if error else future.result(), error)
        except Exception:
            traceback.print_exc()

    def closeEvent(self, event) -> None:
        self._closing = True
        self.settings.save()
        self._pool.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(event)


def create_application(argv: list[str]) -> QApplication:
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setFont(font(14))
    return app


def apply_saved_theme(settings: Settings) -> None:
    THEME.set_mode(settings.get("appearance"))
    hints = QGuiApplication.styleHints()
    hints.colorSchemeChanged.connect(
        lambda _scheme: THEME.mode == "System" and THEME.set_mode("System"))
