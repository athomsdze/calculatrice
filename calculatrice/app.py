"""Fenêtre principale : barre latérale de navigation et vues."""

from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
import traceback
from typing import Any, Callable

import customtkinter as ctk

from . import APP_NAME, __version__
from .storage import Settings, resource_path
from .ui import theme
from .ui.calculator_view import CalculatorView
from .ui.currency_view import CurrencyView
from .ui.units_view import UnitsView
from .ui.widgets import PickerOverlay

APPEARANCES = {"Clair": "Light", "Sombre": "Dark", "Système": "System"}

NAVIGATION = [
    ("calc", "±", "Calculatrice", CalculatorView),
    ("currency", "€", "Devises", CurrencyView),
    ("units", "↔", "Unités", UnitsView),
]


class NavItem(ctk.CTkFrame):
    """Entrée de la barre latérale : icône de largeur fixe + libellé."""

    def __init__(self, master, icon: str, label: str, command: Callable[[], None]):
        super().__init__(master, fg_color="transparent", corner_radius=12, height=46)
        self.active = False
        self.icon = ctk.CTkLabel(self, text=icon, width=26, font=theme.font(17, "bold"),
                                 text_color=theme.MUTED, cursor="hand2")
        self.icon.pack(side="left", padx=(14, 10), pady=9)
        self.label = ctk.CTkLabel(self, text=label, font=theme.font(15), text_color=theme.TEXT,
                                  anchor="w", cursor="hand2")
        self.label.pack(side="left", fill="x", expand=True)
        for widget in (self, self.icon, self.label):
            widget.bind("<Button-1>", lambda _e: command())
            widget.bind("<Enter>", lambda _e: self._hover(True))
            widget.bind("<Leave>", lambda _e: self._hover(False))

    def _hover(self, inside: bool) -> None:
        if not self.active:
            self.configure(fg_color=theme.NAV_HOVER if inside else "transparent")

    def set_active(self, active: bool) -> None:
        self.active = active
        self.configure(fg_color=theme.NAV_ACTIVE if active else "transparent")
        color = theme.ACCENT_TEXT if active else theme.TEXT
        self.label.configure(text_color=color, font=theme.font(15, "bold" if active else "normal"))
        self.icon.configure(text_color=theme.ACCENT_TEXT if active else theme.MUTED)


class App(ctk.CTk):
    def __init__(self, settings: Settings):
        appearance = settings.get("appearance")
        if appearance not in APPEARANCES.values():
            appearance = "Dark"
        ctk.set_appearance_mode(appearance)
        super().__init__()
        self.settings = settings
        self._tasks: queue.Queue = queue.Queue()
        self._toast: ctk.CTkLabel | None = None
        self._toast_job: str | None = None

        self.title(APP_NAME)
        self.geometry("1200x780")
        self.minsize(1080, 700)
        self.configure(fg_color=theme.BG)
        self._set_icon()

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar(appearance)

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=0, column=1, sticky="nsew", padx=24, pady=24)
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(0, weight=1)
        self.views: dict[str, ctk.CTkFrame] = {}
        for key, _, _, view_class in NAVIGATION:
            view = view_class(content, self)
            view.grid(row=0, column=0, sticky="nsew")
            self.views[key] = view

        # Ctrl+1/2/3 : chiffres du pavé numérique, clavier QWERTY et AZERTY (& é ")
        azerty = ["ampersand", "eacute", "quotedbl"]
        for index, (key, *_rest) in enumerate(NAVIGATION, start=1):
            for keysym in (str(index), f"KP_{index}", azerty[index - 1]):
                self.bind_all(f"<Control-Key-{keysym}>", lambda _e, k=key: self.show(k))
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(60, self._poll_tasks)
        last = settings.get("last_view")
        self.show(last if last in self.views else "calc")

    # ------------------------------------------------------------------
    def _set_icon(self) -> None:
        try:
            if sys.platform == "win32":
                self.iconbitmap(str(resource_path("assets/icon.ico")))
            else:
                self._icon_image = tk.PhotoImage(file=str(resource_path("assets/icon.png")))
                self.iconphoto(True, self._icon_image)
        except (tk.TclError, OSError):
            pass

    def _build_sidebar(self, appearance: str) -> None:
        bar = ctk.CTkFrame(self, fg_color=theme.SIDEBAR, corner_radius=0, width=230)
        bar.grid(row=0, column=0, sticky="nsw")
        bar.grid_propagate(False)
        bar.grid_columnconfigure(0, weight=1)
        bar.grid_rowconfigure(5, weight=1)

        brand = ctk.CTkFrame(bar, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=18, pady=(24, 26))
        logo = ctk.CTkLabel(brand, text="=", width=40, height=40, corner_radius=12,
                            fg_color=theme.ACCENT, text_color=theme.ON_ACCENT,
                            font=theme.font(22, "bold"))
        logo.grid(row=0, column=0, rowspan=2)
        ctk.CTkLabel(brand, text="Calculatrice", font=theme.font(17, "bold"),
                     text_color=theme.TEXT, anchor="w").grid(row=0, column=1, sticky="w", padx=10)
        ctk.CTkLabel(brand, text="Pro", font=theme.font(12, "bold"), text_color=theme.ACCENT_TEXT,
                     anchor="w").grid(row=1, column=1, sticky="w", padx=10)

        self.nav_items: dict[str, NavItem] = {}
        for row, (key, icon, label, _) in enumerate(NAVIGATION, start=1):
            item = NavItem(bar, icon, label, lambda k=key: self.show(k))
            item.grid(row=row, column=0, sticky="ew", padx=14, pady=3)
            self.nav_items[key] = item

        ctk.CTkLabel(bar, text="Thème", font=theme.font(12), text_color=theme.MUTED,
                     anchor="w").grid(row=6, column=0, sticky="ew", padx=20)
        selector = ctk.CTkSegmentedButton(
            bar, values=list(APPEARANCES), command=self._set_appearance, height=30,
            font=theme.font(12), selected_color=theme.ACCENT, selected_hover_color=theme.ACCENT_HOVER,
            unselected_color=theme.BTN_FN, unselected_hover_color=theme.BTN_FN_HOVER,
            fg_color=theme.BTN_FN, text_color=theme.TEXT,
        )
        selector.set(next(k for k, v in APPEARANCES.items() if v == appearance))
        selector.grid(row=7, column=0, sticky="ew", padx=16, pady=(4, 10))
        ctk.CTkLabel(bar, text=f"Version {__version__}  ·  Ctrl+1/2/3", font=theme.font(11),
                     text_color=theme.MUTED, anchor="w").grid(row=8, column=0, sticky="ew",
                                                              padx=20, pady=(0, 18))

    # ------------------------------------------------------------------
    def show(self, key: str) -> None:
        if PickerOverlay.current is not None:
            PickerOverlay.current.close()
        for k, item in self.nav_items.items():
            item.set_active(k == key)
        view = self.views[key]
        view.tkraise()
        self.current_view = key
        self.settings.set("last_view", key, save=False)
        self.after(10, view.on_show)

    def _set_appearance(self, label: str) -> None:
        mode = APPEARANCES[label]
        if PickerOverlay.current is not None:
            PickerOverlay.current.close()
        ctk.set_appearance_mode(mode)
        self.settings.set("appearance", mode)

    def toast(self, message: str, duration_ms: int = 1800) -> None:
        """Petit message temporaire en bas de la fenêtre."""
        if self._toast is None:
            self._toast = ctk.CTkLabel(self, text="", corner_radius=10, height=36,
                                       fg_color=theme.TEXT, text_color=theme.BG,
                                       font=theme.font(13, "bold"))
        self._toast.configure(text=f"   {message}   ")
        self._toast.place(relx=0.5, rely=1.0, y=-24, anchor="s")
        self._toast.lift()
        if self._toast_job:
            self.after_cancel(self._toast_job)
        self._toast_job = self.after(duration_ms, self._toast.place_forget)

    # ------------------------------------------------------------------
    def run_async(self, func: Callable[..., Any], callback: Callable[[Any, Exception | None], None],
                  *args: Any) -> None:
        """Exécute ``func`` dans un thread ; ``callback(résultat, erreur)`` est appelé dans l'UI."""

        def worker():
            try:
                result = func(*args)
            except Exception as exc:
                self._tasks.put((callback, None, exc))
            else:
                self._tasks.put((callback, result, None))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_tasks(self) -> None:
        try:
            while True:
                callback, result, error = self._tasks.get_nowait()
                try:
                    callback(result, error)
                except Exception:
                    traceback.print_exc()
        except queue.Empty:
            pass
        self.after(60, self._poll_tasks)

    def on_close(self) -> None:
        self.settings.save()
        self.destroy()
