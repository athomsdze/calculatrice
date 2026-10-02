"""Vue « Unités » : conversion dans les deux sens et tableau de toutes les unités."""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from ..core.evaluator import CalcError, format_pretty, parse_user_number
from ..core.units import CATEGORIES, CATEGORY_BY_KEY, Category, convert
from . import theme
from .widgets import Card


class UnitsView(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.choices: dict[str, list[str]] = dict(app.settings.get("unit_choices"))
        self.category: Category = CATEGORY_BY_KEY.get(app.settings.get("unit_category"),
                                                      CATEGORIES[0])
        self.from_key = self.to_key = ""
        self._updating = False
        self._last_edited = "from"
        self._category_buttons: dict[str, ctk.CTkButton] = {}
        self._all_rows: dict[str, ctk.CTkLabel] = {}

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_categories()
        self._build_main()
        self.select_category(self.category.key)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build_categories(self) -> None:
        card = Card(self, width=230)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        card.grid_rowconfigure(1, weight=1)
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(card, text="Catégories", font=theme.font(17, "bold"), text_color=theme.TEXT,
                     anchor="w").grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 6))
        frame = ctk.CTkScrollableFrame(card, fg_color="transparent", width=200)
        frame.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 10))
        for category in CATEGORIES:
            btn = ctk.CTkButton(
                frame, text=category.name, anchor="w", height=38, corner_radius=10,
                fg_color="transparent", hover_color=theme.NAV_HOVER, text_color=theme.TEXT,
                font=theme.font(14), command=lambda k=category.key: self.select_category(k),
            )
            btn.pack(fill="x", pady=1, padx=4)
            self._category_buttons[category.key] = btn

    def _entry(self, parent, variable) -> ctk.CTkEntry:
        return ctk.CTkEntry(
            parent, textvariable=variable, font=theme.font(28, "bold"), height=58,
            corner_radius=12, border_width=1, border_color=theme.BORDER, fg_color=theme.CARD_ALT,
            text_color=theme.TEXT,
        )

    def _menu(self, parent, command) -> ctk.CTkOptionMenu:
        return ctk.CTkOptionMenu(
            parent, values=[""], command=command, height=42, corner_radius=12,
            dynamic_resizing=False, fg_color=theme.BTN_FN, button_color=theme.BTN_FN,
            button_hover_color=theme.BTN_FN_HOVER, text_color=theme.TEXT, font=theme.font(14),
            dropdown_font=theme.font(13),
        )

    def _build_main(self) -> None:
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)

        card = Card(main)
        card.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        card.grid_columnconfigure((0, 2), weight=1, uniform="side")
        self.title_label = ctk.CTkLabel(card, text="", font=theme.font(26, "bold"),
                                        text_color=theme.TEXT, anchor="w")
        self.title_label.grid(row=0, column=0, columnspan=3, sticky="ew", padx=20, pady=(16, 4))

        self.from_var, self.to_var = tk.StringVar(value="1"), tk.StringVar()
        left = ctk.CTkFrame(card, fg_color="transparent")
        left.grid(row=1, column=0, sticky="nsew", padx=(20, 8))
        left.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(left, text="De", font=theme.font(13), text_color=theme.MUTED,
                     anchor="w").grid(row=0, column=0, sticky="w")
        self.from_entry = self._entry(left, self.from_var)
        self.from_entry.grid(row=1, column=0, sticky="ew", pady=(4, 8))
        self.from_menu = self._menu(left, lambda label: self._on_unit_change("from", label))
        self.from_menu.grid(row=2, column=0, sticky="ew")

        ctk.CTkButton(
            card, text="⇄", width=48, height=48, corner_radius=24, font=theme.font(22, "bold"),
            fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER, text_color=theme.ON_ACCENT,
            command=self.swap,
        ).grid(row=1, column=1, padx=6, pady=(22, 0))

        right = ctk.CTkFrame(card, fg_color="transparent")
        right.grid(row=1, column=2, sticky="nsew", padx=(8, 20))
        right.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(right, text="Vers", font=theme.font(13), text_color=theme.MUTED,
                     anchor="w").grid(row=0, column=0, sticky="w")
        self.to_entry = self._entry(right, self.to_var)
        self.to_entry.grid(row=1, column=0, sticky="ew", pady=(4, 8))
        self.to_menu = self._menu(right, lambda label: self._on_unit_change("to", label))
        self.to_menu.grid(row=2, column=0, sticky="ew")

        self.formula_label = ctk.CTkLabel(card, text="", font=theme.font(14), text_color=theme.MUTED)
        self.formula_label.grid(row=2, column=0, columnspan=3, sticky="ew", padx=20, pady=(10, 16))

        all_card = Card(main)
        all_card.grid(row=1, column=0, sticky="nsew")
        all_card.grid_columnconfigure(0, weight=1)
        all_card.grid_rowconfigure(1, weight=1)
        self.all_title = ctk.CTkLabel(all_card, text="", font=theme.font(17, "bold"),
                                      text_color=theme.TEXT, anchor="w")
        self.all_title.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 4))
        self.all_frame = ctk.CTkScrollableFrame(all_card, fg_color="transparent")
        self.all_frame.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 10))
        self.all_frame.grid_columnconfigure(0, weight=1)

        self.from_var.trace_add("write", lambda *_: self._on_value_change("from"))
        self.to_var.trace_add("write", lambda *_: self._on_value_change("to"))

    # ------------------------------------------------------------------
    # Catégories et unités
    # ------------------------------------------------------------------
    def select_category(self, key: str) -> None:
        self.category = CATEGORY_BY_KEY[key]
        self.app.settings.set("unit_category", key, save=False)
        for k, btn in self._category_buttons.items():
            active = k == key
            btn.configure(fg_color=theme.NAV_ACTIVE if active else "transparent",
                          text_color=theme.ACCENT_TEXT if active else theme.TEXT,
                          font=theme.font(14, "bold" if active else "normal"))
        saved = self.choices.get(key, [])
        keys = {u.key for u in self.category.units}
        if len(saved) == 2 and saved[0] in keys and saved[1] in keys:
            self.from_key, self.to_key = saved
        else:
            self.from_key, self.to_key = self.category.default_from, self.category.default_to
        labels = [u.label for u in self.category.units]
        self.from_menu.configure(values=labels)
        self.to_menu.configure(values=labels)
        self.title_label.configure(text=self.category.name)
        self.all_title.configure(text="Toutes les unités")
        self._build_all_rows()
        self._sync_menus()
        self._recompute()

    def _build_all_rows(self) -> None:
        for child in self.all_frame.winfo_children():
            child.destroy()
        self._all_rows.clear()
        for i, unit in enumerate(self.category.units):
            row = ctk.CTkFrame(self.all_frame, corner_radius=10,
                               fg_color=theme.CARD_ALT if i % 2 == 0 else "transparent")
            row.grid(row=i, column=0, sticky="ew", pady=1)
            row.grid_columnconfigure(1, weight=1)
            name = ctk.CTkLabel(row, text=unit.name, font=theme.font(14), text_color=theme.TEXT,
                                anchor="w", cursor="hand2")
            name.grid(row=0, column=0, sticky="w", padx=12, pady=7)
            value = ctk.CTkLabel(row, text="", font=theme.font(14, "bold"), text_color=theme.TEXT,
                                 anchor="e", cursor="hand2")
            value.grid(row=0, column=1, sticky="e", padx=12, pady=7)
            for widget in (row, name, value):
                widget.bind("<Button-1>", lambda _e, k=unit.key: self._set_to_unit(k))
            self._all_rows[unit.key] = value

    def _sync_menus(self) -> None:
        self.from_menu.set(self.category.get(self.from_key).label)
        self.to_menu.set(self.category.get(self.to_key).label)
        self.choices[self.category.key] = [self.from_key, self.to_key]
        self.app.settings.set("unit_choices", self.choices, save=False)

    def _on_unit_change(self, side: str, label: str) -> None:
        unit = self.category.by_label(label)
        if side == "from":
            self.from_key = unit.key
        else:
            self.to_key = unit.key
        self._sync_menus()
        self._recompute()

    def _set_to_unit(self, key: str) -> None:
        self.to_key = key
        self._last_edited = "from"
        self._sync_menus()
        self._recompute()

    def swap(self) -> None:
        self.from_key, self.to_key = self.to_key, self.from_key
        self._updating = True
        from_text, to_text = self.from_var.get(), self.to_var.get()
        self.from_var.set(to_text)
        self.to_var.set(from_text)
        self._updating = False
        self._last_edited = "from"
        self._sync_menus()
        self._recompute()

    # ------------------------------------------------------------------
    # Calculs
    # ------------------------------------------------------------------
    def _on_value_change(self, side: str) -> None:
        if self._updating:
            return
        self._last_edited = side
        self._recompute()

    def _recompute(self) -> None:
        source_var, target_var = (self.from_var, self.to_var) if self._last_edited == "from" \
            else (self.to_var, self.from_var)
        src_key, dst_key = (self.from_key, self.to_key) if self._last_edited == "from" \
            else (self.to_key, self.from_key)
        self._updating = True
        try:
            value = parse_user_number(source_var.get())
            target_var.set(format_pretty(convert(value, self.category, src_key, dst_key)))
            base_value = value if self._last_edited == "from" else \
                convert(value, self.category, src_key, self.from_key)
            error = None
        except CalcError as err:
            target_var.set("")
            base_value, error = None, str(err)
        finally:
            self._updating = False
        self._update_formula(error)
        self._update_all_rows(base_value)

    def _update_formula(self, error: str | None) -> None:
        if error:
            self.formula_label.configure(text=error, text_color=theme.DANGER)
            return
        src = self.category.get(self.from_key)
        dst = self.category.get(self.to_key)
        try:
            if self.category.minimum_base is not None:  # échelle décalée : deux repères
                refs = [(v, convert(v, self.category, src.key, dst.key)) for v in (0.0, 100.0)]
                text = "      ·      ".join(
                    f"{format_pretty(v)} {src.symbol} = {format_pretty(r)} {dst.symbol}"
                    for v, r in refs
                )
            else:
                one = convert(1.0, self.category, src.key, dst.key)
                text = f"1 {src.symbol} = {format_pretty(one)} {dst.symbol}"
        except CalcError:
            text = ""
        self.formula_label.configure(text=text, text_color=theme.MUTED)

    def _update_all_rows(self, value: float | None) -> None:
        for key, label in self._all_rows.items():
            unit = self.category.get(key)
            if value is None:
                label.configure(text="—")
                continue
            try:
                converted = convert(value, self.category, self.from_key, key)
                label.configure(text=f"{format_pretty(converted)} {unit.symbol}")
            except CalcError:
                label.configure(text="—")

    def on_show(self) -> None:
        self.from_entry.focus_set()
