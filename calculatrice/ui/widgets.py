"""Widgets réutilisables : carte, graphique en courbe, sélecteur avec recherche."""

from __future__ import annotations

import bisect
import tkinter as tk
import unicodedata
from datetime import date
from typing import Callable, Sequence

import customtkinter as ctk

from . import theme


class Card(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        kwargs.setdefault("fg_color", theme.CARD)
        kwargs.setdefault("corner_radius", 18)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", theme.BORDER)
        super().__init__(master, **kwargs)


def _fold(text: str) -> str:
    """Minuscules sans accents, pour la recherche."""
    normalized = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn")


class LineChart(ctk.CTkFrame):
    """Courbe avec zone remplie, axes et info-bulle au survol."""

    def __init__(self, master, value_formatter: Callable[[float], str], height: int = 240):
        super().__init__(master, fg_color="transparent")
        self.value_formatter = value_formatter
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0, height=height)
        self.canvas.pack(fill="both", expand=True)
        self.points: Sequence[tuple[date, float]] = []
        self.message = ""
        self._xs: list[float] = []
        self._ys: list[float] = []
        self.canvas.bind("<Configure>", lambda _e: self.redraw())
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", lambda _e: self.canvas.delete("hover"))
        ctk.AppearanceModeTracker.add(self._on_appearance_change, self)

    def _on_appearance_change(self, _mode: str) -> None:
        self.after(20, self.redraw)

    def destroy(self) -> None:
        ctk.AppearanceModeTracker.remove(self._on_appearance_change)
        super().destroy()

    def set_points(self, points: Sequence[tuple[date, float]]) -> None:
        self.points, self.message = list(points), ""
        self.redraw()

    def set_message(self, message: str) -> None:
        self.points, self.message = [], message
        self.redraw()

    def _font(self, size: int, weight: str = "normal"):
        return (theme.FAMILY, size, weight)

    def redraw(self) -> None:
        c = self.canvas
        c.delete("all")
        bg = theme.resolve(theme.CARD)
        muted = theme.resolve(theme.MUTED)
        c.configure(bg=bg)
        width, height = c.winfo_width(), c.winfo_height()
        self._xs, self._ys = [], []
        if width < 60 or height < 60:
            return
        if self.message or len(self.points) < 2:
            c.create_text(width / 2, height / 2, text=self.message or "Aucune donnée",
                          fill=muted, font=self._font(11))
            return

        left, right, top, bottom = 70, 14, 14, 30
        plot_w, plot_h = width - left - right, height - top - bottom
        values = [v for _, v in self.points]
        vmin, vmax = min(values), max(values)
        if vmax - vmin < 1e-12:
            pad = abs(vmax) * 0.01 or 1.0
        else:
            pad = (vmax - vmin) * 0.12
        vmin, vmax = vmin - pad, vmax + pad

        def y_of(v: float) -> float:
            return top + plot_h * (1 - (v - vmin) / (vmax - vmin))

        first_day = self.points[0][0]
        span = max(1, (self.points[-1][0] - first_day).days)

        def x_of(d: date) -> float:
            return left + plot_w * (d - first_day).days / span

        grid = theme.resolve(theme.BORDER)
        for i in range(5):
            v = vmin + (vmax - vmin) * i / 4
            y = y_of(v)
            c.create_line(left, y, width - right, y, fill=grid)
            c.create_text(left - 8, y, text=self.value_formatter(v), anchor="e",
                          fill=muted, font=self._font(9))

        date_format = "%d/%m" if span <= 120 else "%m/%Y"
        for i in range(5):
            d_index = round(i * (len(self.points) - 1) / 4)
            d = self.points[d_index][0]
            anchor = "w" if i == 0 else "e" if i == 4 else "center"
            c.create_text(x_of(d), height - bottom + 14, text=d.strftime(date_format),
                          anchor=anchor, fill=muted, font=self._font(9))

        self._xs = [x_of(d) for d, _ in self.points]
        self._ys = [y_of(v) for v in values]
        coords = [coord for xy in zip(self._xs, self._ys) for coord in xy]

        rising = values[-1] >= values[0]
        line_color = theme.resolve(theme.SUCCESS if rising else theme.DANGER)
        base_y = top + plot_h
        fill_color = theme.blend(bg, line_color, 0.14)
        c.create_polygon(self._xs[0], base_y, *coords, self._xs[-1], base_y,
                         fill=fill_color, outline="")
        c.create_line(*coords, fill=line_color, width=2.2, capstyle="round", joinstyle="round")
        c.create_oval(self._xs[-1] - 4, self._ys[-1] - 4, self._xs[-1] + 4, self._ys[-1] + 4,
                      fill=line_color, outline=bg, width=2)

    def _on_motion(self, event) -> None:
        c = self.canvas
        c.delete("hover")
        if not self._xs:
            return
        i = bisect.bisect_left(self._xs, event.x)
        if i >= len(self._xs) or (i > 0 and event.x - self._xs[i - 1] < self._xs[i] - event.x):
            i -= 1
        i = max(0, min(i, len(self._xs) - 1))
        x, y = self._xs[i], self._ys[i]
        day, value = self.points[i]
        text_color = theme.resolve(theme.TEXT)
        accent = theme.resolve(theme.ACCENT)
        c.create_line(x, 14, x, c.winfo_height() - 30, fill=theme.resolve(theme.MUTED),
                      dash=(3, 3), tags="hover")
        c.create_oval(x - 5, y - 5, x + 5, y + 5, fill=accent, outline=theme.resolve(theme.CARD),
                      width=2, tags="hover")
        label = f"{day.strftime('%d/%m/%Y')}   {self.value_formatter(value)}"
        text_id = c.create_text(0, 0, text=label, fill=text_color, font=self._font(10, "bold"),
                                anchor="nw", tags="hover")
        x1, y1, x2, y2 = c.bbox(text_id)
        w, h = x2 - x1 + 16, y2 - y1 + 10
        tx = min(max(x - w / 2, 4), c.winfo_width() - w - 4)
        ty = max(y - h - 12, 4)
        c.coords(text_id, tx + 8, ty + 5)
        box = c.create_rectangle(tx, ty, tx + w, ty + h, fill=theme.resolve(theme.CARD_ALT),
                                 outline=theme.resolve(theme.BORDER), tags="hover")
        c.tag_raise(text_id, box)


class PickerOverlay(ctk.CTkFrame):
    """Liste avec champ de recherche, affichée par-dessus la fenêtre principale.

    Un seul sélecteur est ouvert à la fois ; un clic en dehors le ferme.
    """

    current: "PickerOverlay | None" = None
    _hooked: set[str] = set()

    def __init__(self, anchor: tk.Misc, items: list[tuple[str, str]],
                 on_select: Callable[[str], None], placeholder: str = "Rechercher…",
                 width: int = 360, height: int = 380):
        top = anchor.winfo_toplevel()
        super().__init__(top, width=width, height=height, fg_color=theme.CARD, corner_radius=14,
                         border_width=1, border_color=theme.BORDER)
        if PickerOverlay.current is not None:
            PickerOverlay.current.close()
        PickerOverlay.current = self
        self.anchor = anchor
        self.items = items
        self.on_select = on_select
        self.visible: list[tuple[str, str]] = []
        self.grid_propagate(False)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.search = ctk.CTkEntry(self, placeholder_text=placeholder, height=36,
                                   corner_radius=10, font=theme.font(14))
        self.search.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 8))
        self.listbox = tk.Listbox(
            self, activestyle="none", bd=0, highlightthickness=0, exportselection=False,
            font=(theme.FAMILY, 11), relief="flat",
        )
        self.listbox.grid(row=1, column=0, sticky="nsew", padx=(12, 0), pady=(0, 12))
        scrollbar = ctk.CTkScrollbar(self, command=self.listbox.yview)
        scrollbar.grid(row=1, column=1, sticky="ns", padx=(2, 6), pady=(0, 12))
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self._apply_colors()

        self.search.bind("<KeyRelease>", self._on_search_key)
        self.search.bind("<Return>", lambda _e: self._choose(0))
        self.search.bind("<Down>", self._focus_list)
        self.search.bind("<Escape>", lambda _e: self.close())
        self.listbox.bind("<ButtonRelease-1>", lambda _e: self._choose_selected())
        self.listbox.bind("<Return>", lambda _e: self._choose_selected())
        self.listbox.bind("<Escape>", lambda _e: self.close())

        if str(top) not in PickerOverlay._hooked:
            top.bind("<Button-1>", PickerOverlay._dispatch_click, add="+")
            PickerOverlay._hooked.add(str(top))

        self._filter("")
        self._place(top, width, height)
        self.search.focus_set()

    def _apply_colors(self) -> None:
        self.listbox.configure(
            bg=theme.resolve(theme.CARD), fg=theme.resolve(theme.TEXT),
            selectbackground=theme.resolve(theme.ACCENT), selectforeground="#FFFFFF",
        )

    def _place(self, top: tk.Misc, width: int, height: int) -> None:
        top.update_idletasks()
        scale = ctk.ScalingTracker.get_widget_scaling(self)
        w, h = width * scale, height * scale
        x = self.anchor.winfo_rootx() - top.winfo_rootx()
        y = self.anchor.winfo_rooty() - top.winfo_rooty() + self.anchor.winfo_height() + 6
        x = min(x, top.winfo_width() - w - 10)
        if y + h > top.winfo_height() - 10:
            y = max(10, self.anchor.winfo_rooty() - top.winfo_rooty() - h - 6)
        self.place(x=max(10, x) / scale, y=y / scale)
        self.lift()

    def _on_search_key(self, event) -> None:
        if event.keysym in ("Return", "Down", "Escape"):
            return
        self._filter(self.search.get())

    @staticmethod
    def _rank(query: str, item: tuple[str, str]) -> int | None:
        """Pertinence d'un élément (plus petit = meilleur), None s'il ne correspond pas."""
        value, label = _fold(item[0]), _fold(item[1])
        if not query:
            return 0
        if value == query:
            return 0
        if value.startswith(query):
            return 1
        words = label.replace("(", " ").replace("—", " ").split()
        if any(w.startswith(query) for w in words):
            return 2
        if query in label:
            return 3
        return None

    def _filter(self, query: str) -> None:
        q = _fold(query.strip())
        ranked = [(self._rank(q, item), i, item) for i, item in enumerate(self.items)]
        self.visible = [item for rank, _, item in sorted(
            (r for r in ranked if r[0] is not None), key=lambda r: (r[0], r[1]))]
        self.listbox.delete(0, "end")
        for _, label in self.visible:
            self.listbox.insert("end", "  " + label)
        if self.visible:
            self.listbox.selection_set(0)

    def _focus_list(self, _event=None) -> str:
        if self.visible:
            self.listbox.focus_set()
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(0)
            self.listbox.activate(0)
        return "break"

    def _choose_selected(self) -> None:
        selection = self.listbox.curselection()
        if selection:
            self._choose(selection[0])

    def _choose(self, index: int) -> None:
        if 0 <= index < len(self.visible):
            value = self.visible[index][0]
            self.close()
            self.on_select(value)

    def close(self) -> None:
        if PickerOverlay.current is self:
            PickerOverlay.current = None
        self.destroy()

    @staticmethod
    def _contains(widget: tk.Misc, path: str) -> bool:
        return path == str(widget) or path.startswith(str(widget) + ".")

    @classmethod
    def _dispatch_click(cls, event) -> None:
        picker = cls.current
        if picker is None or not picker.winfo_exists():
            return
        path = str(event.widget)
        if cls._contains(picker, path) or cls._contains(picker.anchor, path):
            return
        picker.close()

    @classmethod
    def is_open_for(cls, anchor: tk.Misc) -> bool:
        return cls.current is not None and cls.current.anchor is anchor
