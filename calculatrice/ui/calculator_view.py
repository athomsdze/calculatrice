"""Vue « Calculatrice » : calculatrice scientifique avec historique et mémoire."""

from __future__ import annotations

import re
from typing import Callable

import customtkinter as ctk

from ..core.evaluator import ANGLE_MODES, FUNCTIONS, CalcError, evaluate, format_number
from ..storage import HISTORY_LIMIT
from . import theme
from .widgets import Card

# Saisies qui prolongent le résultat affiché au lieu de commencer un nouveau calcul.
CONTINUATIONS = ("+", "−", "×", "÷", "^", "%", "!", "²", "³", "⁻¹", " mod ")

# Jetons effacés d'un bloc par la touche ⌫.
_ERASE_TOKENS = sorted(
    {name + "(" for name in FUNCTIONS} | {"nCr(", "nPr(", " mod ", "Ans", "⁻¹"},
    key=len, reverse=True,
)
_PLAIN_NUMBER = re.compile(r"^\s*[-−]?[\d.,]+(E[+-]?\d+)?\s*$")
_TRAILING_NUMBER = re.compile(r"(\d+(?:[.,]\d*)?(?:E[+-]?\d+)?|[.,]\d+)$")

# Touches de fonction : (libellé, texte inséré, libellé 2nd, texte 2nd)
_SCIENTIFIC_ROWS = [
    [("2nd", None, None, None), ("π", "π", None, None), ("e", "e", None, None),
     ("(", "(", None, None), (")", ")", None, None)],
    [("sin", "sin(", "sin⁻¹", "sin⁻¹("), ("cos", "cos(", "cos⁻¹", "cos⁻¹("),
     ("tan", "tan(", "tan⁻¹", "tan⁻¹("), ("x²", "²", None, None), ("x³", "³", None, None)],
    [("sinh", "sinh(", "sinh⁻¹", "sinh⁻¹("), ("cosh", "cosh(", "cosh⁻¹", "cosh⁻¹("),
     ("tanh", "tanh(", "tanh⁻¹", "tanh⁻¹("), ("xʸ", "^", None, None), ("1/x", "⁻¹", None, None)],
    [("ln", "ln(", None, None), ("log", "log(", None, None), ("log₂", "log₂(", None, None),
     ("eˣ", "e^(", None, None), ("10ˣ", "10^(", None, None)],
    [("√x", "√(", None, None), ("∛x", "∛(", None, None), ("n!", "!", None, None),
     ("|x|", "abs(", None, None), ("EXP", "E", None, None)],
    [("nCr", "nCr(", None, None), ("nPr", "nPr(", None, None), ("mod", " mod ", None, None),
     (";", ";", None, None), ("Ans", "Ans", None, None)],
]


class CalculatorView(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        settings = app.settings
        self.angle_mode = settings.get("angle_mode")
        if self.angle_mode not in ANGLE_MODES:
            self.angle_mode = "DEG"
        self.memory: float = float(settings.get("memory"))
        self.history: list[dict] = list(settings.get("history"))[-HISTORY_LIMIT:]
        self.ans = 0.0
        self.second = False
        self.just_evaluated = False
        self._error_for: str | None = None  # expression dont l'erreur est affichée
        self._second_buttons: list[tuple[ctk.CTkButton, tuple]] = []
        self._history_items: list[ctk.CTkFrame] = []

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0, minsize=280)
        self.grid_rowconfigure(0, weight=1)

        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)

        self._build_display(main)
        self._build_keypad(main)
        self._build_history()
        self._refresh()

    # ------------------------------------------------------------------
    # Construction de l'interface
    # ------------------------------------------------------------------
    def _build_display(self, parent) -> None:
        card = Card(parent)
        card.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        card.grid_columnconfigure(0, weight=1)

        bar = ctk.CTkFrame(card, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 0))
        bar.grid_columnconfigure(2, weight=1)
        self.angle_selector = ctk.CTkSegmentedButton(
            bar, values=list(ANGLE_MODES), command=self._set_angle_mode, height=28,
            font=theme.font(12, "bold"), selected_color=theme.ACCENT,
            selected_hover_color=theme.ACCENT_HOVER, unselected_color=theme.BTN_FN,
            unselected_hover_color=theme.BTN_FN_HOVER, fg_color=theme.BTN_FN,
            text_color=theme.TEXT,
        )
        self.angle_selector.set(self.angle_mode)
        self.angle_selector.grid(row=0, column=0, sticky="w")
        self.memory_badge = ctk.CTkLabel(bar, text="", font=theme.font(12, "bold"),
                                         text_color=theme.ACCENT_TEXT)
        self.memory_badge.grid(row=0, column=1, sticky="w", padx=12)
        self.previous_label = ctk.CTkLabel(bar, text="", font=theme.font(15),
                                           text_color=theme.MUTED, anchor="e")
        self.previous_label.grid(row=0, column=2, sticky="ew")

        self.entry = ctk.CTkEntry(
            card, font=theme.font(44, family=theme.DISPLAY_FAMILY), justify="right",
            border_width=0, fg_color="transparent", text_color=theme.TEXT, height=72,
        )
        self.entry.grid(row=1, column=0, sticky="ew", padx=10, pady=(4, 0))
        self.preview_label = ctk.CTkLabel(card, text="", font=theme.font(18),
                                          text_color=theme.MUTED, anchor="e", height=26)
        self.preview_label.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 14))

        self.entry.bind("<KeyPress>", self._on_key)
        self.entry.bind("<KeyRelease>", lambda _e: self._refresh())

    def _make_button(self, parent, text: str, command: Callable[[], None], kind: str,
                     font_size: int) -> ctk.CTkButton:
        styles = {
            "num": (theme.BTN_NUM, theme.BTN_NUM_HOVER, theme.TEXT),
            "fn": (theme.BTN_FN, theme.BTN_FN_HOVER, theme.TEXT),
            "op": (theme.ACCENT_SOFT, theme.ACCENT_SOFT_HOVER, theme.ACCENT_TEXT),
            "eq": (theme.ACCENT, theme.ACCENT_HOVER, theme.ON_ACCENT),
            "danger": (theme.BTN_FN, theme.BTN_FN_HOVER, theme.DANGER),
            "mem": ("transparent", theme.BTN_FN_HOVER, theme.MUTED),
        }
        fg, hover, text_color = styles[kind]
        weight = "bold" if kind in ("op", "eq", "danger") else "normal"
        return ctk.CTkButton(
            parent, text=text, command=command, fg_color=fg, hover_color=hover,
            text_color=text_color, corner_radius=14, height=48, border_width=0,
            font=theme.font(font_size, weight),
        )

    def _build_keypad(self, parent) -> None:
        pad = ctk.CTkFrame(parent, fg_color="transparent")
        pad.grid(row=1, column=0, sticky="nsew")
        pad.grid_rowconfigure(0, weight=1)
        pad.grid_columnconfigure(0, weight=5, uniform="pad")
        pad.grid_columnconfigure(1, weight=4, uniform="pad")

        sci = ctk.CTkFrame(pad, fg_color="transparent")
        sci.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        for r, row in enumerate(_SCIENTIFIC_ROWS):
            sci.grid_rowconfigure(r, weight=1, uniform="row")
            for c, spec in enumerate(row):
                sci.grid_columnconfigure(c, weight=1, uniform="col")
                label, text, _, _ = spec
                if label == "2nd":
                    btn = self._make_button(sci, label, self._toggle_second, "fn", 14)
                    self.second_button = btn
                else:
                    btn = self._make_button(sci, label, lambda s=spec: self._on_function(s), "fn", 14)
                    if spec[2]:
                        self._second_buttons.append((btn, spec))
                btn.grid(row=r, column=c, sticky="nsew", padx=3, pady=3)

        num = ctk.CTkFrame(pad, fg_color="transparent")
        num.grid(row=0, column=1, sticky="nsew")
        layout = [
            [("MC", self.memory_clear, "mem"), ("MR", self.memory_recall, "mem"),
             ("M+", lambda: self.memory_add(1), "mem"), ("M−", lambda: self.memory_add(-1), "mem")],
            [("AC", self.clear, "danger"), ("⌫", self.backspace, "fn"),
             ("%", lambda: self.insert("%"), "fn"), ("÷", lambda: self.insert("÷"), "op")],
            [("7", None, "num"), ("8", None, "num"), ("9", None, "num"),
             ("×", lambda: self.insert("×"), "op")],
            [("4", None, "num"), ("5", None, "num"), ("6", None, "num"),
             ("−", lambda: self.insert("−"), "op")],
            [("1", None, "num"), ("2", None, "num"), ("3", None, "num"),
             ("+", lambda: self.insert("+"), "op")],
            [("±", self.toggle_sign, "num"), ("0", None, "num"),
             (",", lambda: self.insert(","), "num"), ("=", self.evaluate, "eq")],
        ]
        for r, row in enumerate(layout):
            num.grid_rowconfigure(r, weight=1, uniform="row")
            for c, (label, command, kind) in enumerate(row):
                num.grid_columnconfigure(c, weight=1, uniform="col")
                if command is None:
                    command = lambda d=label: self.insert(d)
                size = 14 if kind == "mem" else 22
                btn = self._make_button(num, label, command, kind, size)
                btn.grid(row=r, column=c, sticky="nsew", padx=3, pady=3)

    def _build_history(self) -> None:
        card = Card(self)
        card.grid(row=0, column=1, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 6))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Historique", font=theme.font(17, "bold"),
                     text_color=theme.TEXT, anchor="w").grid(row=0, column=0, sticky="w")
        ctk.CTkButton(header, text="Effacer", width=70, height=28, corner_radius=8,
                      fg_color="transparent", hover_color=theme.BTN_FN_HOVER,
                      text_color=theme.MUTED, font=theme.font(12),
                      command=self.clear_history).grid(row=0, column=1, sticky="e")
        self.history_frame = ctk.CTkScrollableFrame(card, fg_color="transparent")
        self.history_frame.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 10))
        self.history_empty = ctk.CTkLabel(
            self.history_frame, text="Aucun calcul pour l'instant.\nVos résultats apparaîtront ici.",
            font=theme.font(13), text_color=theme.MUTED, justify="center",
        )
        for item in self.history:
            self._add_history_widget(item)
        self._update_history_empty()

    # ------------------------------------------------------------------
    # Historique
    # ------------------------------------------------------------------
    def _add_history_widget(self, item: dict) -> None:
        row = ctk.CTkFrame(self.history_frame, fg_color="transparent", corner_radius=10)
        expr = ctk.CTkLabel(row, text=item["expr"] + " =", font=theme.font(13),
                            text_color=theme.MUTED, anchor="e", justify="right", wraplength=230,
                            cursor="hand2")
        expr.pack(fill="x", padx=10, pady=(8, 0))
        result = ctk.CTkLabel(row, text=item["result"], font=theme.font(20, "bold"),
                              text_color=theme.TEXT, anchor="e", justify="right", wraplength=230,
                              cursor="hand2")
        result.pack(fill="x", padx=10, pady=(0, 8))
        expr.bind("<Button-1>", lambda _e, it=item: self._load_expression(it["expr"]))
        result.bind("<Button-1>", lambda _e, it=item: self.insert(it["result"]))
        for widget in (row, expr, result):
            widget.bind("<Enter>", lambda _e, r=row: r.configure(fg_color=theme.BTN_FN))
            widget.bind("<Leave>", lambda _e, r=row: r.configure(fg_color="transparent"))
        if self._history_items:
            row.pack(fill="x", pady=2, before=self._history_items[-1])
        else:
            row.pack(fill="x", pady=2)
        self._history_items.append(row)

    def _update_history_empty(self) -> None:
        if self.history:
            self.history_empty.pack_forget()
        else:
            self.history_empty.pack(pady=40)

    def _push_history(self, expr: str, result: str) -> None:
        item = {"expr": expr, "result": result}
        self.history.append(item)
        self._add_history_widget(item)
        while len(self.history) > HISTORY_LIMIT:
            self.history.pop(0)
            self._history_items.pop(0).destroy()
        self._update_history_empty()
        self.app.settings.set("history", self.history)

    def clear_history(self) -> None:
        for widget in self._history_items:
            widget.destroy()
        self._history_items.clear()
        self.history.clear()
        self._update_history_empty()
        self.app.settings.set("history", self.history)

    def _load_expression(self, expr: str) -> None:
        self._set_text(expr)
        self.just_evaluated = False
        self._refresh()

    # ------------------------------------------------------------------
    # Saisie
    # ------------------------------------------------------------------
    def _set_text(self, text: str) -> None:
        self.entry.delete(0, "end")
        self.entry.insert(0, text)
        self.entry.icursor("end")

    def insert(self, text: str) -> None:
        if self.just_evaluated:
            self.just_evaluated = False
            if not text.startswith(CONTINUATIONS):
                self._set_text("")
            else:
                self.entry.icursor("end")
        if self.entry.select_present():
            self.entry.delete("sel.first", "sel.last")
        self.entry.insert("insert", text)
        if self.entry.index("insert") == len(self.entry.get()):
            self.entry.xview_moveto(1.0)
        self.entry.focus_set()
        self._refresh()

    def _on_function(self, spec: tuple) -> None:
        _, text, _, text_second = spec
        if self.second and text_second:
            self.insert(text_second)
            self._toggle_second()
        else:
            self.insert(text)

    def _toggle_second(self) -> None:
        self.second = not self.second
        for btn, (label, _, label_second, _) in self._second_buttons:
            btn.configure(text=label_second if self.second else label)
        if self.second:
            self.second_button.configure(fg_color=theme.ACCENT, text_color=theme.ON_ACCENT,
                                         hover_color=theme.ACCENT_HOVER)
        else:
            self.second_button.configure(fg_color=theme.BTN_FN, text_color=theme.TEXT,
                                         hover_color=theme.BTN_FN_HOVER)

    def clear(self) -> None:
        self._set_text("")
        self.previous_label.configure(text="")
        self.just_evaluated = False
        self.entry.focus_set()
        self._refresh()

    def backspace(self) -> None:
        if self.just_evaluated:
            self.clear()
            return
        if self.entry.select_present():
            self.entry.delete("sel.first", "sel.last")
        else:
            pos = self.entry.index("insert")
            before = self.entry.get()[:pos]
            for token in _ERASE_TOKENS:
                if before.endswith(token):
                    self.entry.delete(pos - len(token), pos)
                    break
            else:
                if pos > 0:
                    self.entry.delete(pos - 1, pos)
        self.entry.focus_set()
        self._refresh()

    def toggle_sign(self) -> None:
        self.just_evaluated = False
        text = self.entry.get()
        if not text:
            self.insert("−")
            return
        match = _TRAILING_NUMBER.search(text)
        if match:
            start = match.start()
            prefix = text[:start]
            if prefix.endswith(("−", "-")) and (len(prefix) == 1 or prefix[-2] in "(+−-×÷^;E "):
                text = prefix[:-1] + match.group(0)
            else:
                text = prefix + "−" + match.group(0)
        elif text.startswith("−(") and text.endswith(")"):
            text = text[2:-1]
        else:
            text = f"−({text})"
        self._set_text(text)
        self._refresh()

    def _on_key(self, event) -> str | None:
        replacements = {"*": "×", "/": "÷", "-": "−", ".": ","}
        if event.keysym in ("Return", "KP_Enter") or event.char == "=":
            self.evaluate()
            return "break"
        if event.keysym == "Escape":
            self.clear()
            return "break"
        if event.keysym == "BackSpace":
            self.backspace()
            return "break"
        if event.char in replacements:
            self.insert(replacements[event.char])
            return "break"
        if event.char and event.char.isprintable() and self.just_evaluated:
            self.insert(event.char)
            return "break"
        return None

    # ------------------------------------------------------------------
    # Calcul
    # ------------------------------------------------------------------
    def _set_angle_mode(self, mode: str) -> None:
        self.angle_mode = mode
        self.app.settings.set("angle_mode", mode)
        self._refresh()

    def _refresh(self) -> None:
        text = self.entry.get()
        length = len(text)
        size = 44 if length <= 16 else 34 if length <= 24 else 26 if length <= 34 else 20
        self.entry.configure(font=theme.font(size, family=theme.DISPLAY_FAMILY))
        self.memory_badge.configure(text="M" if self.memory else "")
        if text == self._error_for:
            return  # garder le message d'erreur tant que l'expression n'a pas changé
        self._error_for = None
        if self.just_evaluated or not text.strip() or _PLAIN_NUMBER.match(text):
            self.preview_label.configure(text="")
            return
        try:
            value = evaluate(text, self.angle_mode, self.ans)
            self.preview_label.configure(text="= " + format_number(value), text_color=theme.MUTED)
        except CalcError:
            self.preview_label.configure(text="")

    def evaluate(self) -> None:
        expr = self.entry.get().strip()
        if not expr or self.just_evaluated:
            return
        try:
            value = evaluate(expr, self.angle_mode, self.ans)
            result = format_number(value)
        except CalcError as err:
            self.preview_label.configure(text=str(err), text_color=theme.DANGER)
            self._error_for = self.entry.get()
            return
        missing = expr.count("(") - expr.count(")")
        if missing > 0:
            expr += ")" * missing
        self.ans = value
        shown = expr if len(expr) <= 48 else "…" + expr[-47:]
        self.previous_label.configure(text=f"{shown} =")
        self._set_text(result)
        self.just_evaluated = True
        self._push_history(expr, result)
        self._refresh()

    def current_value(self) -> float:
        try:
            return evaluate(self.entry.get(), self.angle_mode, self.ans)
        except CalcError:
            return self.ans

    # ------------------------------------------------------------------
    # Mémoire
    # ------------------------------------------------------------------
    def memory_clear(self) -> None:
        self.memory = 0.0
        self.app.settings.set("memory", self.memory)
        self._refresh()

    def memory_recall(self) -> None:
        self.insert(format_number(self.memory))

    def memory_add(self, sign: int) -> None:
        self.memory += sign * self.current_value()
        self.app.settings.set("memory", self.memory)
        self._refresh()

    def on_show(self) -> None:
        self.entry.focus_set()
