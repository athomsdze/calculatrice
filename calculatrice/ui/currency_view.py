"""Page « Devises » : conversion, taux du jour, favoris et historique."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, Qt, QTimer, QVariantAnimation
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from ..core.currency import (
    CURRENCY_NAMES, HISTORY_PERIODS, POPULAR, CurrencyError, CurrencyService, RateTable,
    currency_label,
)
from ..core.evaluator import NBSP, CalcError, format_fixed, format_number, parse_user_number
from ..storage import user_data_dir
from .theme import BOLD, SEMIBOLD, font
from .widgets import (
    AnimatedButton, Card, ClickableLabel, ElidedLabel, HoverRow, LineChart, PickerPopup,
    SegmentedControl, SelectButton, SmoothScrollArea, SwapButton, make_label, set_role,
)


def elided(text: str, px: int, weight=None, role: str | None = None) -> ElidedLabel:
    label = ElidedLabel()
    label.setFont(font(px, weight) if weight is not None else font(px))
    if role:
        label.setProperty("role", role)
    label.setText(text)
    return label

PERIOD_LABELS = {"1S": "1 semaine", "1M": "1 mois", "3M": "3 mois", "6M": "6 mois", "1A": "1 an"}
RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


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


def describe_currency(code: str) -> tuple[str, str]:
    return code, CURRENCY_NAMES.get(code, "")


class FavoriteRow(HoverRow):
    def __init__(self, code: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.code = code
        grid = QGridLayout(self)
        grid.setContentsMargins(12, 7, 6, 7)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(0)
        grid.addWidget(make_label(code, 14, BOLD), 0, 0)
        grid.addWidget(elided(CURRENCY_NAMES.get(code, ""), 12, role="muted"), 1, 0)
        grid.setColumnStretch(0, 1)
        self.value_label = make_label("", 14, BOLD, align=RIGHT)
        self.rate_label = make_label("", 11, role="muted", align=RIGHT)
        grid.addWidget(self.value_label, 0, 1)
        grid.addWidget(self.rate_label, 1, 1)
        grid.setColumnStretch(1, 1)
        self.remove_button = AnimatedButton("×", "ghost", font_px=17, radius=14)
        self.remove_button.setFixedSize(28, 28)
        self.remove_button.setToolTip("Retirer des favoris")
        grid.addWidget(self.remove_button, 0, 2, 2, 1)
        self.setToolTip("Double-clic : convertir vers cette devise")


class CurrencyView(QWidget):
    def __init__(self, app) -> None:
        super().__init__()
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
        self.favorites = [c for c in settings.get("currency_favorites") if c in CURRENCY_NAMES]
        self.period = settings.get("chart_period")
        if self.period not in HISTORY_PERIODS:
            self.period = "1M"
        self._history_request = 0
        self._rows: dict[str, FavoriteRow] = {}
        self._shown_result: float | None = None
        self._result_anim = QVariantAnimation(self)
        self._result_anim.setDuration(420)
        self._result_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._result_anim.valueChanged.connect(lambda v: self._show_result(float(v)))

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)
        root.addLayout(self._build_header())
        root.addWidget(self._build_converter())
        bottom = QHBoxLayout()
        bottom.setSpacing(14)
        bottom.addWidget(self._build_chart(), 3)
        bottom.addWidget(self._build_favorites(), 2)
        root.addLayout(bottom, 1)

        self.amount_edit.setText(settings.get("currency_amount"))
        self._update_selectors()
        self._rebuild_favorites()
        self._recalculate(animate=False)
        self._update_status()
        self._load_history()
        QTimer.singleShot(400, self.refresh_rates)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(make_label("Convertisseur de devises", 26, BOLD))
        self.status_label = elided("", 13, role="muted")
        titles.addWidget(self.status_label)
        header.addLayout(titles, 1)
        self.refresh_button = AnimatedButton("↻  Actualiser", "soft", font_px=13, radius=10)
        self.refresh_button.setFixedSize(140, 38)
        self.refresh_button.clicked.connect(self.refresh_rates)
        header.addWidget(self.refresh_button, 0, Qt.AlignmentFlag.AlignTop)
        return header

    def _build_converter(self) -> QWidget:
        card = Card()
        grid = QGridLayout(card)
        grid.setContentsMargins(20, 16, 20, 14)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        grid.addWidget(make_label("Montant", 13, role="muted"), 0, 0)
        grid.addWidget(make_label("Résultat", 13, role="muted"), 0, 2)
        self.amount_edit = QLineEdit()
        self.amount_edit.setFont(font(30, BOLD))
        self.amount_edit.setFixedHeight(60)
        self.amount_edit.textEdited.connect(lambda _t: self._recalculate(animate=False))
        grid.addWidget(self.amount_edit, 1, 0)
        self.swap_button = SwapButton()
        self.swap_button.clicked.connect(self.swap)
        grid.addWidget(self.swap_button, 1, 1, 2, 1, Qt.AlignmentFlag.AlignCenter)
        self.result_label = ClickableLabel()
        self.result_label.setObjectName("ResultBox")
        self.result_label.setFont(font(30, BOLD))
        self.result_label.setFixedHeight(60)
        self.result_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.result_label.setToolTip("Cliquer pour copier le résultat")
        self.result_label.clicked.connect(self._copy_result)
        grid.addWidget(self.result_label, 1, 2)
        placeholder = "Rechercher une devise (ex. dollar, MAD)…"
        self.from_select = SelectButton(placeholder=placeholder, describe=describe_currency)
        self.to_select = SelectButton(placeholder=placeholder, describe=describe_currency)
        self.from_select.changed.connect(lambda c: self._on_pick("from", c))
        self.to_select.changed.connect(lambda c: self._on_pick("to", c))
        grid.addWidget(self.from_select, 2, 0)
        grid.addWidget(self.to_select, 2, 2)
        self.rate_label = make_label("", 14, role="muted", align=Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(self.rate_label, 3, 0, 1, 3)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(2, 1)
        return card

    def _build_chart(self) -> QWidget:
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 14, 12)
        layout.setSpacing(4)
        head = QHBoxLayout()
        self.chart_title = elided("", 17, SEMIBOLD)
        head.addWidget(self.chart_title, 1)
        self.period_selector = SegmentedControl(list(HISTORY_PERIODS), self.period)
        self.period_selector.changed.connect(self._set_period)
        head.addWidget(self.period_selector)
        layout.addLayout(head)
        self.chart_stats = elided(" ", 13, role="muted")
        layout.addWidget(self.chart_stats)
        self.chart = LineChart(format_rate)
        layout.addWidget(self.chart, 1)
        return card

    def _build_favorites(self) -> QWidget:
        card = Card()
        card.setMinimumWidth(280)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 14, 6, 10)
        head = QHBoxLayout()
        head.setContentsMargins(8, 0, 8, 0)
        head.addWidget(make_label("Autres devises", 17, SEMIBOLD), 1)
        self.add_button = AnimatedButton("+ Ajouter", "soft", font_px=12, radius=8)
        self.add_button.setFixedSize(92, 30)
        self.add_button.clicked.connect(self._open_add_favorite)
        head.addWidget(self.add_button)
        layout.addLayout(head)
        self.fav_scroll = SmoothScrollArea()
        container = QWidget()
        self.fav_layout = QVBoxLayout(container)
        self.fav_layout.setContentsMargins(0, 4, 6, 4)
        self.fav_layout.setSpacing(2)
        self.fav_layout.addStretch(1)
        self.fav_scroll.setWidget(container)
        layout.addWidget(self.fav_scroll, 1)
        self.fav_empty = make_label("Ajoutez des devises à comparer\navec « + Ajouter ».", 13,
                                    role="muted", align=Qt.AlignmentFlag.AlignCenter)
        self.fav_empty.setContentsMargins(0, 30, 0, 0)
        self.fav_layout.insertWidget(0, self.fav_empty)
        return card

    # ------------------------------------------------------------------
    # Sélection des devises
    # ------------------------------------------------------------------
    def _picker_items(self, exclude: set[str] | None = None) -> list[tuple[str, str]]:
        exclude = exclude or set()
        codes = [c for c in self.rates.codes() if c not in exclude]
        ordered = [c for c in POPULAR if c in codes] + [c for c in codes if c not in POPULAR]
        return [(c, currency_label(c)) for c in ordered]

    def _update_selectors(self) -> None:
        items = self._picker_items()
        self.from_select.set_items(items, self.frm)
        self.to_select.set_items(items, self.to)
        self.chart_title.setText(f"Évolution {self.frm} → {self.to}")

    def _on_pick(self, target: str, code: str) -> None:
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
        self._update_selectors()
        self._rebuild_favorites()
        self._recalculate(animate=True)
        self._load_history()

    def _open_add_favorite(self) -> PickerPopup:
        popup = PickerPopup(self._picker_items(set(self.favorites)), None, self.window(),
                            placeholder="Ajouter une devise…")
        popup.picked.connect(self._add_favorite)
        popup.popup_below(self.add_button, min_width=320)
        return popup

    # ------------------------------------------------------------------
    # Favoris
    # ------------------------------------------------------------------
    def _add_favorite(self, code: str) -> None:
        if code not in self.favorites:
            self.favorites.append(code)
            self.app.settings.set("currency_favorites", self.favorites)
            self._rebuild_favorites()
            self._recalculate(animate=False)

    def _remove_favorite(self, code: str) -> None:
        if code in self.favorites:
            self.favorites.remove(code)
            self.app.settings.set("currency_favorites", self.favorites)
            self._rebuild_favorites()
            self._recalculate(animate=False)

    def _rebuild_favorites(self) -> None:
        for row in self._rows.values():
            self.fav_layout.removeWidget(row)
            row.hide()
            row.deleteLater()
        self._rows.clear()
        shown = [c for c in self.favorites if c != self.frm and c in self.rates.rates]
        for index, code in enumerate(shown):
            row = FavoriteRow(code)
            row.remove_button.clicked.connect(lambda _=False, c=code: self._remove_favorite(c))
            row.double_clicked.connect(lambda c=code: self._on_pick("to", c))
            self.fav_layout.insertWidget(index, row)
            self._rows[code] = row
        self.fav_empty.setVisible(not shown)

    # ------------------------------------------------------------------
    # Calculs
    # ------------------------------------------------------------------
    def _amount(self) -> float | None:
        try:
            return parse_user_number(self.amount_edit.text())
        except CalcError:
            return None

    def _show_result(self, value: float | None) -> None:
        self._shown_result = value
        text = "—" if value is None else f"{format_money(value)} {self.to}"
        self.result_label.setText(text)

    def _recalculate(self, animate: bool) -> None:
        self.app.settings.set("currency_amount", self.amount_edit.text(), save=False)
        amount = self._amount()
        try:
            rate = self.rates.rate(self.frm, self.to)
        except CurrencyError as err:
            self._result_anim.stop()
            self._show_result(None)
            self.rate_label.setText(str(err))
            return
        target = None if amount is None else amount * rate
        self._result_anim.stop()
        if animate and target is not None and self._shown_result is not None:
            self._result_anim.setStartValue(float(self._shown_result))
            self._result_anim.setEndValue(float(target))
            self._result_anim.start()
        else:
            self._show_result(target)
        self.rate_label.setText(
            f"1 {self.frm} = {format_rate(rate)} {self.to}      •      "
            f"1 {self.to} = {format_rate(1 / rate)} {self.frm}")
        for code, row in self._rows.items():
            try:
                fav_rate = self.rates.rate(self.frm, code)
            except CurrencyError:
                continue
            value = "—" if amount is None else format_money(amount * fav_rate)
            row.value_label.setText(f"{value} {code}")
            row.rate_label.setText(f"1 {self.frm} = {format_rate(fav_rate)}")

    def _copy_result(self) -> None:
        amount = self._amount()
        if amount is None:
            return
        try:
            value = self.rates.convert(amount, self.frm, self.to)
        except CurrencyError:
            return
        self.app.clipboard_set(format_fixed(value, 2, group=""))
        self.app.toast("Résultat copié dans le presse-papiers")

    # ------------------------------------------------------------------
    # Taux du jour
    # ------------------------------------------------------------------
    def refresh_rates(self) -> None:
        self.refresh_button.setEnabled(False)
        self.refresh_button.setText("Mise à jour…")
        self.app.run_async(self.service.fetch_latest, self._on_rates)

    def _on_rates(self, table: RateTable | None, error: Exception | None) -> None:
        self.refresh_button.setEnabled(True)
        self.refresh_button.setText("↻  Actualiser")
        if table is not None:
            self.rates = table
            self._update_selectors()
            self._rebuild_favorites()
            self._recalculate(animate=True)
        self._update_status(failed=error is not None)

    def _update_status(self, failed: bool = False) -> None:
        if self.rates.source == "taux intégrés":
            text = ("●  Hors ligne : taux approximatifs intégrés. "
                    "Connectez-vous à Internet puis cliquez sur Actualiser.")
            role = "danger"
        elif self.rates.offline:
            prefix = "Hors ligne" if failed else "Derniers taux enregistrés"
            text = f"●  {prefix} · taux du {self.rates.updated_label()} ({self.rates.source})"
            role = "danger" if failed else "muted"
        else:
            text = f"●  Taux du {self.rates.updated_label()} · source : {self.rates.source}"
            role = "success"
        set_role(self.status_label, role)
        self.status_label.setText(text)

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
        self.chart.set_loading()
        self.chart_stats.setText(" ")
        frm, to, days, period = self.frm, self.to, HISTORY_PERIODS[self.period], self.period

        def done(points, error) -> None:
            if request != self._history_request:
                return  # une demande plus récente a été lancée
            if error is not None or not points:
                message = (str(error) if isinstance(error, CurrencyError)
                           else "Historique indisponible (connexion Internet ?)")
                self.chart.set_message(message)
                return
            self.chart.set_points(points)
            first, last = points[0][1], points[-1][1]
            values = [v for _, v in points]
            change = (last - first) / first * 100 if first else 0.0
            sign = "+" if change >= 0 else "−"
            set_role(self.chart_stats, "success" if change >= 0 else "danger")
            self.chart_stats.setText(
                f"{sign}{format_fixed(abs(change), 2)} % sur {PERIOD_LABELS[period]}"
                f"   ·   min {format_rate(min(values))}   ·   max {format_rate(max(values))}")

        self.app.run_async(self.service.fetch_history, done, frm, to, days)

    def on_show(self) -> None:
        self.amount_edit.setFocus()
