"""Vue « Devises » : conversion, taux du jour, favoris et historique."""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from ..core.currency import (
    CURRENCY_NAMES, HISTORY_PERIODS, POPULAR, CurrencyError, CurrencyService, RateTable,
    currency_label,
)
from ..core.evaluator import NBSP, CalcError, format_fixed, format_number, parse_user_number
from ..storage import user_data_dir
from . import theme
from .widgets import Card, LineChart, PickerOverlay

PERIOD_LABELS = {"1S": "1 semaine", "1M": "1 mois", "3M": "3 mois", "6M": "6 mois", "1A": "1 an"}


def format_money(x: float) -> str:
    if abs(x) >= 1 or x == 0:
        return format_fixed(x, 2)
    return format_number(x, sig=4, group=NBSP)


def format_rate(x: float) -> str:
    ax = abs(x)
    if ax >= 1000:
        return format_fixed(x, 2)
    if ax >= 1:
        return format_fixed(x, 4)
    return format_number(x, sig=5)


class CurrencyView(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        settings = app.settings
        self.service = CurrencyService(user_data_dir() / "rates_cache.json")
        self.rates: RateTable = self.service.load_cached()
        self.frm = settings.get("currency_from")
        self.to = settings.get("currency_to")
        if self.frm not in self.rates.rates:
            self.frm = "EUR"
        if self.to not in self.rates.rates:
            self.to = "USD"
        self.favorites: list[str] = [c for c in settings.get("currency_favorites")
                                     if c in CURRENCY_NAMES]
        self.period = settings.get("chart_period")
        if self.period not in HISTORY_PERIODS:
            self.period = "1M"
        self._history_request = 0
        self._favorite_rows: dict[str, tuple[ctk.CTkLabel, ctk.CTkLabel]] = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._build_header()
        self._build_converter()
        self._build_bottom()

        self.amount_var.set(settings.get("currency_amount"))
        self._update_currency_buttons()
        self._rebuild_favorites()
        self._recalculate()
        self._update_status()
        self._load_history()
        self.after(300, self.refresh_rates)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Convertisseur de devises", font=theme.font(26, "bold"),
                     text_color=theme.TEXT, anchor="w").grid(row=0, column=0, sticky="w")
        self.status_label = ctk.CTkLabel(header, text="", font=theme.font(13),
                                         text_color=theme.MUTED, anchor="w")
        self.status_label.grid(row=1, column=0, sticky="w")
        self.refresh_button = ctk.CTkButton(
            header, text="↻  Actualiser", width=130, height=36, corner_radius=10,
            fg_color=theme.ACCENT_SOFT, hover_color=theme.ACCENT_SOFT_HOVER,
            text_color=theme.ACCENT_TEXT, font=theme.font(13, "bold"), command=self.refresh_rates,
        )
        self.refresh_button.grid(row=0, column=1, rowspan=2, sticky="e")

    def _currency_button(self, parent, command) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent, text="", height=46, corner_radius=12, anchor="w", command=command,
            fg_color=theme.BTN_FN, hover_color=theme.BTN_FN_HOVER, text_color=theme.TEXT,
            font=theme.font(15),
        )

    def _build_converter(self) -> None:
        card = Card(self)
        card.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        card.grid_columnconfigure((0, 2), weight=1, uniform="side")

        left = ctk.CTkFrame(card, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(20, 8), pady=(18, 6))
        left.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(left, text="Montant", font=theme.font(13), text_color=theme.MUTED,
                     anchor="w").grid(row=0, column=0, sticky="w")
        self.amount_var = tk.StringVar()
        self.amount_entry = ctk.CTkEntry(
            left, textvariable=self.amount_var, font=theme.font(30, "bold"), height=58,
            corner_radius=12, border_width=1, border_color=theme.BORDER,
            fg_color=theme.CARD_ALT, text_color=theme.TEXT,
        )
        self.amount_entry.grid(row=1, column=0, sticky="ew", pady=(4, 8))
        self.from_button = self._currency_button(left, lambda: self._open_picker("from"))
        self.from_button.grid(row=2, column=0, sticky="ew")

        self.swap_button = ctk.CTkButton(
            card, text="⇄", width=48, height=48, corner_radius=24, font=theme.font(22, "bold"),
            fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER, text_color=theme.ON_ACCENT,
            command=self.swap,
        )
        self.swap_button.grid(row=0, column=1, padx=6, pady=(30, 0))

        right = ctk.CTkFrame(card, fg_color="transparent")
        right.grid(row=0, column=2, sticky="nsew", padx=(8, 20), pady=(18, 6))
        right.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(right, text="Résultat", font=theme.font(13), text_color=theme.MUTED,
                     anchor="w").grid(row=0, column=0, sticky="w")
        self.result_label = ctk.CTkLabel(
            right, text="", font=theme.font(30, "bold"), height=58, corner_radius=12,
            fg_color=theme.ACCENT_SOFT, text_color=theme.ACCENT_TEXT, anchor="w",
        )
        self.result_label.grid(row=1, column=0, sticky="ew", pady=(4, 8))
        self.result_label.configure(cursor="hand2")
        self.result_label.bind("<Button-1>", lambda _e: self._copy_result())
        self.to_button = self._currency_button(right, lambda: self._open_picker("to"))
        self.to_button.grid(row=2, column=0, sticky="ew")

        self.rate_label = ctk.CTkLabel(card, text="", font=theme.font(14), text_color=theme.MUTED)
        self.rate_label.grid(row=1, column=0, columnspan=3, sticky="ew", padx=20, pady=(4, 16))

        self.amount_var.trace_add("write", lambda *_: self._recalculate())

    def _build_bottom(self) -> None:
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(row=2, column=0, sticky="nsew")
        bottom.grid_columnconfigure(0, weight=3, uniform="bottom")
        bottom.grid_columnconfigure(1, weight=2, uniform="bottom")
        bottom.grid_rowconfigure(0, weight=1)

        chart_card = Card(bottom)
        chart_card.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        chart_card.grid_columnconfigure(0, weight=1)
        chart_card.grid_rowconfigure(2, weight=1)
        head = ctk.CTkFrame(chart_card, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 0))
        head.grid_columnconfigure(0, weight=1)
        self.chart_title = ctk.CTkLabel(head, text="", font=theme.font(17, "bold"),
                                        text_color=theme.TEXT, anchor="w")
        self.chart_title.grid(row=0, column=0, sticky="w")
        self.period_selector = ctk.CTkSegmentedButton(
            head, values=list(HISTORY_PERIODS), command=self._set_period, height=28,
            font=theme.font(12, "bold"), selected_color=theme.ACCENT,
            selected_hover_color=theme.ACCENT_HOVER, unselected_color=theme.BTN_FN,
            unselected_hover_color=theme.BTN_FN_HOVER, fg_color=theme.BTN_FN,
            text_color=theme.TEXT,
        )
        self.period_selector.set(self.period)
        self.period_selector.grid(row=0, column=1, sticky="e")
        self.chart_stats = ctk.CTkLabel(chart_card, text="", font=theme.font(13),
                                        text_color=theme.MUTED, anchor="w")
        self.chart_stats.grid(row=1, column=0, sticky="ew", padx=18)
        self.chart = LineChart(chart_card, format_rate)
        self.chart.grid(row=2, column=0, sticky="nsew", padx=10, pady=(4, 12))

        fav_card = Card(bottom)
        fav_card.grid(row=0, column=1, sticky="nsew")
        fav_card.grid_columnconfigure(0, weight=1)
        fav_card.grid_rowconfigure(1, weight=1)
        fav_head = ctk.CTkFrame(fav_card, fg_color="transparent")
        fav_head.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 4))
        fav_head.grid_columnconfigure(0, weight=1)
        self.fav_title = ctk.CTkLabel(fav_head, text="Autres devises", font=theme.font(17, "bold"),
                                      text_color=theme.TEXT, anchor="w")
        self.fav_title.grid(row=0, column=0, sticky="w")
        self.add_fav_button = ctk.CTkButton(
            fav_head, text="+ Ajouter", width=90, height=28, corner_radius=8,
            fg_color=theme.ACCENT_SOFT, hover_color=theme.ACCENT_SOFT_HOVER,
            text_color=theme.ACCENT_TEXT, font=theme.font(12, "bold"),
            command=lambda: self._open_picker("favorite"),
        )
        self.add_fav_button.grid(row=0, column=1, sticky="e")
        self.fav_frame = ctk.CTkScrollableFrame(fav_card, fg_color="transparent")
        self.fav_frame.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 10))

    # ------------------------------------------------------------------
    # Sélection des devises
    # ------------------------------------------------------------------
    def _picker_items(self, exclude: set[str] | None = None) -> list[tuple[str, str]]:
        exclude = exclude or set()
        codes = [c for c in self.rates.codes() if c not in exclude]
        ordered = [c for c in POPULAR if c in codes] + [c for c in codes if c not in POPULAR]
        return [(c, currency_label(c)) for c in ordered]

    def _open_picker(self, target: str) -> None:
        anchor = {"from": self.from_button, "to": self.to_button,
                  "favorite": self.add_fav_button}[target]
        if PickerOverlay.is_open_for(anchor):
            PickerOverlay.current.close()
            return
        exclude = set(self.favorites) if target == "favorite" else None
        PickerOverlay(anchor, self._picker_items(exclude),
                      lambda code: self._on_pick(target, code),
                      placeholder="Rechercher une devise (ex. dollar, MAD)…")

    def _on_pick(self, target: str, code: str) -> None:
        if target == "favorite":
            self.favorites.append(code)
            self.app.settings.set("currency_favorites", self.favorites)
            self._rebuild_favorites()
            self._recalculate()
            return
        if target == "from":
            if code == self.to:
                self.to = self.frm
            self.frm = code
        else:
            if code == self.frm:
                self.frm = self.to
            self.to = code
        self._currencies_changed()

    def swap(self) -> None:
        self.frm, self.to = self.to, self.frm
        self._currencies_changed()

    def _currencies_changed(self) -> None:
        self.app.settings.set("currency_from", self.frm, save=False)
        self.app.settings.set("currency_to", self.to)
        self._update_currency_buttons()
        self._rebuild_favorites()
        self._recalculate()
        self._load_history()

    def _update_currency_buttons(self) -> None:
        for button, code in ((self.from_button, self.frm), (self.to_button, self.to)):
            name = CURRENCY_NAMES.get(code, "")
            button.configure(text=f"  {code}   {name}")
        self.chart_title.configure(text=f"Évolution {self.frm} → {self.to}")

    # ------------------------------------------------------------------
    # Favoris
    # ------------------------------------------------------------------
    def _rebuild_favorites(self) -> None:
        for child in self.fav_frame.winfo_children():
            child.destroy()
        self._favorite_rows.clear()
        shown = [c for c in self.favorites if c != self.frm and c in self.rates.rates]
        if not shown:
            ctk.CTkLabel(self.fav_frame, text="Ajoutez des devises à comparer\navec « + Ajouter ».",
                         font=theme.font(13), text_color=theme.MUTED).pack(pady=30)
            return
        for code in shown:
            row = ctk.CTkFrame(self.fav_frame, fg_color="transparent", corner_radius=10)
            row.pack(fill="x", pady=1)
            row.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(row, text=code, font=theme.font(14, "bold"), text_color=theme.TEXT,
                         width=44, anchor="w").grid(row=0, column=0, sticky="w", padx=(10, 6), pady=(6, 0))
            ctk.CTkLabel(row, text=CURRENCY_NAMES.get(code, ""), font=theme.font(12),
                         text_color=theme.MUTED, anchor="w").grid(row=1, column=0, columnspan=2,
                                                                  sticky="w", padx=10, pady=(0, 6))
            value = ctk.CTkLabel(row, text="", font=theme.font(14, "bold"), text_color=theme.TEXT,
                                 anchor="e")
            value.grid(row=0, column=1, sticky="e", pady=(6, 0))
            unit = ctk.CTkLabel(row, text="", font=theme.font(11), text_color=theme.MUTED, anchor="e")
            unit.grid(row=1, column=1, sticky="e", pady=(0, 6))
            remove = ctk.CTkButton(row, text="×", width=26, height=26, corner_radius=13,
                                   fg_color="transparent", hover_color=theme.BTN_FN_HOVER,
                                   text_color=theme.MUTED, font=theme.font(16),
                                   command=lambda c=code: self._remove_favorite(c))
            remove.grid(row=0, column=2, rowspan=2, padx=(6, 6))
            for widget in (row, value, unit):
                widget.bind("<Double-Button-1>", lambda _e, c=code: self._on_pick("to", c))
            self._favorite_rows[code] = (value, unit)

    def _remove_favorite(self, code: str) -> None:
        if code in self.favorites:
            self.favorites.remove(code)
            self.app.settings.set("currency_favorites", self.favorites)
            self._rebuild_favorites()
            self._recalculate()

    # ------------------------------------------------------------------
    # Calculs
    # ------------------------------------------------------------------
    def _amount(self) -> float | None:
        try:
            return parse_user_number(self.amount_var.get())
        except CalcError:
            return None

    def _recalculate(self) -> None:
        self.app.settings.set("currency_amount", self.amount_var.get(), save=False)
        amount = self._amount()
        try:
            rate = self.rates.rate(self.frm, self.to)
        except CurrencyError as err:
            self.result_label.configure(text="  —")
            self.rate_label.configure(text=str(err))
            return
        if amount is None:
            self.result_label.configure(text="  —")
        else:
            self.result_label.configure(text=f"  {format_money(amount * rate)} {self.to}")
        self.rate_label.configure(
            text=f"1 {self.frm} = {format_rate(rate)} {self.to}      •      "
                 f"1 {self.to} = {format_rate(1 / rate)} {self.frm}"
        )
        for code, (value_label, unit_label) in self._favorite_rows.items():
            try:
                fav_rate = self.rates.rate(self.frm, code)
            except CurrencyError:
                continue
            shown = format_money(amount * fav_rate) if amount is not None else "—"
            value_label.configure(text=f"{shown} {code}")
            unit_label.configure(text=f"1 {self.frm} = {format_rate(fav_rate)}")

    def _copy_result(self) -> None:
        amount = self._amount()
        if amount is None:
            return
        try:
            value = self.rates.convert(amount, self.frm, self.to)
        except CurrencyError:
            return
        self.clipboard_clear()
        self.clipboard_append(format_fixed(value, 2, group=""))
        self.app.toast("Résultat copié dans le presse-papiers")

    # ------------------------------------------------------------------
    # Taux du jour
    # ------------------------------------------------------------------
    def refresh_rates(self) -> None:
        self.refresh_button.configure(state="disabled", text="Mise à jour…")
        self.app.run_async(self.service.fetch_latest, self._on_rates)

    def _on_rates(self, table: RateTable | None, error: Exception | None) -> None:
        self.refresh_button.configure(state="normal", text="↻  Actualiser")
        if table is not None:
            self.rates = table
            self._rebuild_favorites()
            self._recalculate()
        self._update_status(failed=error is not None)

    def _update_status(self, failed: bool = False) -> None:
        if self.rates.source == "taux intégrés":
            text = ("●  Hors ligne : taux approximatifs intégrés. "
                    "Connectez-vous à Internet puis cliquez sur Actualiser.")
            color = theme.DANGER
        elif self.rates.offline:
            prefix = "Hors ligne" if failed else "Derniers taux enregistrés"
            text = f"●  {prefix} · taux du {self.rates.updated_label()} ({self.rates.source})"
            color = theme.MUTED if not failed else theme.DANGER
        else:
            text = f"●  Taux du {self.rates.updated_label()} · source : {self.rates.source}"
            color = theme.SUCCESS
        self.status_label.configure(text=text, text_color=color)

    # ------------------------------------------------------------------
    # Historique
    # ------------------------------------------------------------------
    def _set_period(self, period: str) -> None:
        self.period = period
        self.app.settings.set("chart_period", period)
        self._load_history()

    def _load_history(self) -> None:
        self._history_request += 1
        request = self._history_request
        self.chart.set_message("Chargement de l'historique…")
        self.chart_stats.configure(text=" ")
        frm, to, days = self.frm, self.to, HISTORY_PERIODS[self.period]

        def done(points, error):
            if request != self._history_request:
                return  # une requête plus récente a été lancée
            if error is not None or not points:
                message = str(error) if isinstance(error, CurrencyError) else \
                    "Historique indisponible (connexion Internet ?)"
                self.chart.set_message(message)
                self.chart_stats.configure(text=" ")
                return
            self.chart.set_points(points)
            first, last = points[0][1], points[-1][1]
            values = [v for _, v in points]
            change = (last - first) / first * 100 if first else 0.0
            sign = "+" if change >= 0 else "−"
            self.chart_stats.configure(
                text=f"{sign}{format_fixed(abs(change), 2)} % sur {PERIOD_LABELS[self.period]}"
                     f"   ·   min {format_rate(min(values))}   ·   max {format_rate(max(values))}",
                text_color=theme.SUCCESS if change >= 0 else theme.DANGER,
            )

        self.app.run_async(self.service.fetch_history, done, frm, to, days)

    def on_show(self) -> None:
        self.amount_entry.focus_set()
