"""Page « Unités » : conversion dans les deux sens et tableau de toutes les unités."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from ..core.evaluator import CalcError, format_pretty, parse_user_number
from ..core.units import CATEGORIES, CATEGORY_BY_KEY, Category, convert
from .theme import BOLD, SEMIBOLD, font
from .widgets import (
    Card, HoverRow, PillList, SelectButton, SmoothScrollArea, SwapButton, make_label, set_role,
)

RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


class UnitRow(HoverRow):
    def __init__(self, key: str, name: str, striped: bool, parent: QWidget | None = None):
        super().__init__(parent, base_key="card_alt" if striped else None)
        self.key = key
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 9, 14, 9)
        layout.addWidget(make_label(name, 14), 1)
        self.value_label = make_label("", 14, BOLD, align=RIGHT)
        layout.addWidget(self.value_label)
        self.setToolTip("Cliquer pour convertir vers cette unité")


class UnitsView(QWidget):
    def __init__(self, app) -> None:
        super().__init__()
        self.app = app
        self.choices: dict[str, list[str]] = dict(app.settings.get("unit_choices"))
        self.category: Category = CATEGORY_BY_KEY.get(app.settings.get("unit_category"),
                                                      CATEGORIES[0])
        self.from_key = self.to_key = ""
        self._last_edited = "from"
        self._rows: dict[str, UnitRow] = {}

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)
        root.addWidget(self._build_categories())
        main = QVBoxLayout()
        main.setSpacing(14)
        main.addWidget(self._build_converter())
        main.addWidget(self._build_all_units(), 1)
        root.addLayout(main, 1)
        self.select_category(self.category.key, animate=False)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build_categories(self) -> QWidget:
        card = Card()
        card.setFixedWidth(232)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 14, 6, 10)
        title = make_label("Catégories", 17, SEMIBOLD)
        title.setContentsMargins(8, 0, 0, 4)
        layout.addWidget(title)
        scroll = SmoothScrollArea()
        container = QWidget()
        inner = QVBoxLayout(container)
        inner.setContentsMargins(0, 2, 6, 2)
        self.category_list = PillList([(c.key, c.name, None) for c in CATEGORIES],
                                      item_height=38, font_px=14, spacing=3)
        self.category_list.selected.connect(self.select_category)
        inner.addWidget(self.category_list)
        inner.addStretch(1)
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)
        return card

    def _line_edit(self) -> QLineEdit:
        edit = QLineEdit()
        edit.setFont(font(28, BOLD))
        edit.setFixedHeight(60)
        return edit

    def _build_converter(self) -> QWidget:
        card = Card()
        grid = QGridLayout(card)
        grid.setContentsMargins(20, 16, 20, 14)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        self.title_label = make_label("", 26, BOLD)
        grid.addWidget(self.title_label, 0, 0, 1, 3)
        grid.addWidget(make_label("De", 13, role="muted"), 1, 0)
        grid.addWidget(make_label("Vers", 13, role="muted"), 1, 2)
        self.from_edit = self._line_edit()
        self.to_edit = self._line_edit()
        self.from_edit.setText("1")
        self.from_edit.textEdited.connect(lambda _t: self._on_edited("from"))
        self.to_edit.textEdited.connect(lambda _t: self._on_edited("to"))
        grid.addWidget(self.from_edit, 2, 0)
        grid.addWidget(self.to_edit, 2, 2)
        swap = SwapButton()
        swap.clicked.connect(self.swap)
        grid.addWidget(swap, 2, 1, 2, 1, Qt.AlignmentFlag.AlignCenter)
        self.from_select = SelectButton(searchable=False, describe=self._describe_unit)
        self.to_select = SelectButton(searchable=False, describe=self._describe_unit)
        self.from_select.changed.connect(lambda k: self._on_unit_change("from", k))
        self.to_select.changed.connect(lambda k: self._on_unit_change("to", k))
        grid.addWidget(self.from_select, 3, 0)
        grid.addWidget(self.to_select, 3, 2)
        self.formula_label = make_label("", 14, role="muted", align=Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(self.formula_label, 4, 0, 1, 3)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(2, 1)
        return card

    def _describe_unit(self, key: str) -> tuple[str, str]:
        try:
            unit = self.category.get(key)
        except KeyError:
            return key, ""
        return unit.symbol, unit.name

    def _build_all_units(self) -> QWidget:
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 14, 6, 10)
        title = make_label("Toutes les unités", 17, SEMIBOLD)
        title.setContentsMargins(8, 0, 0, 4)
        layout.addWidget(title)
        self.rows_scroll = SmoothScrollArea()
        container = QWidget()
        self.rows_layout = QVBoxLayout(container)
        self.rows_layout.setContentsMargins(0, 2, 6, 2)
        self.rows_layout.setSpacing(1)
        self.rows_layout.addStretch(1)
        self.rows_scroll.setWidget(container)
        layout.addWidget(self.rows_scroll, 1)
        return card

    # ------------------------------------------------------------------
    # Catégories et unités
    # ------------------------------------------------------------------
    def select_category(self, key: str, animate: bool = True) -> None:
        self.category = CATEGORY_BY_KEY[key]
        self.category_list.set_current(key, animate)
        self.app.settings.set("unit_category", key, save=False)
        saved = self.choices.get(key, [])
        keys = {u.key for u in self.category.units}
        if len(saved) == 2 and saved[0] in keys and saved[1] in keys:
            self.from_key, self.to_key = saved
        else:
            self.from_key, self.to_key = self.category.default_from, self.category.default_to
        items = [(u.key, u.label) for u in self.category.units]
        self.from_select.set_items(items, self.from_key)
        self.to_select.set_items(items, self.to_key)
        self.title_label.setText(self.category.name)
        self._build_rows()
        self._remember_choice()
        self._recompute()

    def _build_rows(self) -> None:
        for row in self._rows.values():
            self.rows_layout.removeWidget(row)
            row.hide()
            row.deleteLater()
        self._rows.clear()
        for i, unit in enumerate(self.category.units):
            row = UnitRow(unit.key, unit.name, striped=i % 2 == 0)
            row.clicked.connect(lambda k=unit.key: self._set_to_unit(k))
            self.rows_layout.insertWidget(i, row)
            self._rows[unit.key] = row
        self.rows_scroll.verticalScrollBar().setValue(0)

    def _remember_choice(self) -> None:
        self.from_select.set_value(self.from_key)
        self.to_select.set_value(self.to_key)
        self.choices[self.category.key] = [self.from_key, self.to_key]
        self.app.settings.set("unit_choices", self.choices, save=False)

    def _on_unit_change(self, side: str, key: str) -> None:
        if side == "from":
            self.from_key = key
        else:
            self.to_key = key
        self._remember_choice()
        self._recompute()

    def _set_to_unit(self, key: str) -> None:
        self.to_key = key
        self._last_edited = "from"
        self._remember_choice()
        self._recompute()

    def swap(self) -> None:
        self.from_key, self.to_key = self.to_key, self.from_key
        from_text, to_text = self.from_edit.text(), self.to_edit.text()
        self.from_edit.setText(to_text)
        self.to_edit.setText(from_text)
        self._last_edited = "from"
        self._remember_choice()
        self._recompute()

    # ------------------------------------------------------------------
    # Calculs
    # ------------------------------------------------------------------
    def _on_edited(self, side: str) -> None:
        self._last_edited = side
        self._recompute()

    def _recompute(self) -> None:
        if self._last_edited == "from":
            source, target, src_key, dst_key = self.from_edit, self.to_edit, self.from_key, self.to_key
        else:
            source, target, src_key, dst_key = self.to_edit, self.from_edit, self.to_key, self.from_key
        try:
            value = parse_user_number(source.text())
            target.setText(format_pretty(convert(value, self.category, src_key, dst_key)))
            from_value = value if source is self.from_edit else convert(
                value, self.category, src_key, self.from_key)
            error = None
        except CalcError as err:
            target.setText("")
            from_value, error = None, str(err)
        self._update_formula(error)
        self._update_rows(from_value)

    def _update_formula(self, error: str | None) -> None:
        if error:
            set_role(self.formula_label, "danger")
            self.formula_label.setText(error)
            return
        src = self.category.get(self.from_key)
        dst = self.category.get(self.to_key)
        try:
            if self.category.minimum_base is not None:  # échelle décalée : deux repères
                text = "      ·      ".join(
                    f"{format_pretty(v)} {src.symbol} = "
                    f"{format_pretty(convert(v, self.category, src.key, dst.key))} {dst.symbol}"
                    for v in (0.0, 100.0))
            else:
                one = convert(1.0, self.category, src.key, dst.key)
                text = f"1 {src.symbol} = {format_pretty(one)} {dst.symbol}"
        except CalcError:
            text = ""
        set_role(self.formula_label, "muted")
        self.formula_label.setText(text)

    def _update_rows(self, value: float | None) -> None:
        for key, row in self._rows.items():
            unit = self.category.get(key)
            if value is None:
                row.value_label.setText("—")
                continue
            try:
                converted = convert(value, self.category, self.from_key, key)
                row.value_label.setText(f"{format_pretty(converted)} {unit.symbol}")
            except CalcError:
                row.value_label.setText("—")

    def on_show(self) -> None:
        self.from_edit.setFocus()
