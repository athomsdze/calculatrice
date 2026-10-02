"""Page « Calculatrice » : calculatrice scientifique avec historique et mémoire."""

from __future__ import annotations

import re

from PySide6.QtCore import QEasingCurve, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLineEdit, QSizePolicy, QVBoxLayout, QWidget,
)

from ..core.evaluator import ANGLE_MODES, FUNCTIONS, CalcError, evaluate, format_number
from ..storage import HISTORY_LIMIT
from .theme import BOLD, LIGHT, SEMIBOLD, font
from .widgets import (
    WIDGET_MAX, AnimatedButton, AnimatedValue, Card, ElidedLabel, HoverRow, SegmentedControl,
    SmoothScrollArea, fit_font_px, make_label, set_role, shake_offset,
)

# Saisies qui prolongent le résultat affiché au lieu de commencer un nouveau calcul.
CONTINUATIONS = ("+", "−", "×", "÷", "^", "%", "!", "²", "³", "⁻¹", " mod ")

# Jetons effacés d'un bloc par la touche ⌫.
ERASE_TOKENS = sorted(
    {name + "(" for name in FUNCTIONS} | {"nCr(", "nPr(", " mod ", "Ans", "⁻¹"},
    key=len, reverse=True,
)
_PLAIN_NUMBER = re.compile(r"^\s*[-−]?[\d.,]+(E[+-]?\d+)?\s*$")
_TRAILING_NUMBER = re.compile(r"(\d+(?:[.,]\d*)?(?:E[+-]?\d+)?|[.,]\d+)$")
KEY_REPLACEMENTS = {"*": "×", "/": "÷", "-": "−", ".": ","}

# Touches scientifiques : (libellé, texte inséré, libellé 2nd, texte 2nd)
SCIENTIFIC_ROWS = [
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


class DisplayEdit(QLineEdit):
    """Écran principal : police adaptée à la longueur, secousse en cas d'erreur, « pop » au résultat."""

    key_pressed = Signal(QKeyEvent)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Display")
        self.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.setMinimumHeight(76)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._scale = AnimatedValue(self, 1.0, duration=260, on_change=self.fit_font,
                                    easing=QEasingCurve.Type.OutBack)
        self._shake = QVariantAnimation(self)
        self._shake.setDuration(420)
        self._shake.setStartValue(0.0)
        self._shake.setEndValue(1.0)
        self._shake.valueChanged.connect(
            lambda t: self.setTextMargins(0, 0, 14 + int(shake_offset(float(t), 12)), 0))
        self.setTextMargins(0, 0, 14, 0)
        self._handler = None
        self._last_px = 0
        self.textChanged.connect(lambda _t: self.fit_font())

    def set_key_handler(self, handler) -> None:
        self._handler = handler

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self._handler is not None and self._handler(event):
            return
        super().keyPressEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.fit_font()

    def fit_font(self) -> None:
        max_px = max(34, min(64, self.width() / 13))
        px = fit_font_px(self.text() or "0", max_px, self.width() - 24, LIGHT, 18, display=True)
        px = max(10, int(px * self._scale.value))
        if px != self._last_px:
            self._last_px = px
            self.setFont(font(px, LIGHT, display=True))

    def shake(self) -> None:
        self._shake.stop()
        self._shake.start()

    def pop(self) -> None:
        self._scale.snap(0.86)
        self._scale.to(1.0)


class HistoryItem(HoverRow):
    """Entrée d'historique : cliquer sur le calcul le recharge, sur le résultat l'insère."""

    expression_clicked = Signal(str)
    result_clicked = Signal(str)

    def __init__(self, expr: str, result: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.expr, self.result = expr, result
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(0)
        right = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        self.expr_label = make_label(expr + " =", 13, role="muted", align=right)
        self.expr_label.setWordWrap(True)
        self.result_label = make_label(result, 21, BOLD, align=right)
        self.result_label.setWordWrap(True)
        layout.addWidget(self.expr_label)
        layout.addWidget(self.result_label)
        self.setToolTip("Clic sur le calcul : le reprendre · clic sur le résultat : l'insérer")

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.position().toPoint())
            if child is self.expr_label:
                self.expression_clicked.emit(self.expr)
            else:
                self.result_clicked.emit(self.result)
        super().mouseReleaseEvent(event)


class CalculatorView(QWidget):
    def __init__(self, app) -> None:
        super().__init__()
        self.app = app
        settings = app.settings
        mode = settings.get("angle_mode")
        self.angle_mode = mode if mode in ANGLE_MODES else "DEG"
        self.memory = float(settings.get("memory"))
        self.history: list[dict] = list(settings.get("history"))[-HISTORY_LIMIT:]
        self.ans = 0.0
        self.second = False
        self.just_evaluated = False
        self._error_for: str | None = None
        self._second_buttons: list[tuple[AnimatedButton, tuple]] = []
        self._history_items: list[HistoryItem] = []
        self._item_animations: list[QVariantAnimation] = []

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(14)
        left.addWidget(self._build_display())
        left.addWidget(self._build_keypad(), 1)
        root.addLayout(left, 3)
        self.history_card = self._build_history()
        root.addWidget(self.history_card, 1)
        self._refresh()

    def resizeEvent(self, event) -> None:
        # fenêtre étroite : l'historique laisse toute la place au clavier
        self.history_card.setVisible(self.width() >= 820)
        super().resizeEvent(event)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build_display(self) -> QWidget:
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 12)
        layout.setSpacing(2)
        bar = QHBoxLayout()
        self.angle_selector = SegmentedControl(ANGLE_MODES, self.angle_mode, font_px=12)
        self.angle_selector.changed.connect(self._set_angle_mode)
        bar.addWidget(self.angle_selector)
        self.memory_badge = make_label("M", 13, BOLD, role="accent")
        self.memory_badge.setToolTip("Une valeur est en mémoire")
        bar.addSpacing(10)
        bar.addWidget(self.memory_badge)
        self.previous_label = ElidedLabel("", Qt.TextElideMode.ElideLeft)
        self.previous_label.setFont(font(15))
        self.previous_label.setProperty("role", "muted")
        self.previous_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        bar.addWidget(self.previous_label, 1)
        layout.addLayout(bar)
        self.display = DisplayEdit()
        self.display.set_key_handler(self.handle_key)
        self.display.textChanged.connect(lambda _t: self._refresh())
        layout.addWidget(self.display)
        self.preview_label = ElidedLabel("", Qt.TextElideMode.ElideLeft)
        self.preview_label.setFont(font(19))
        self.preview_label.setProperty("role", "muted")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.preview_label.setFixedHeight(28)
        layout.addWidget(self.preview_label)
        return card

    def _build_keypad(self) -> QWidget:
        pad = QWidget()
        row = QHBoxLayout(pad)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        sci = QGridLayout()
        sci.setSpacing(7)
        for r, specs in enumerate(SCIENTIFIC_ROWS):
            for c, spec in enumerate(specs):
                label, _, label_second, _ = spec
                btn = AnimatedButton(label, "fn", max_font_px=21)
                if label == "2nd":
                    btn.setCheckable(True)
                    btn.toggled.connect(self._on_second_toggled)
                    self.second_button = btn
                else:
                    btn.clicked.connect(lambda _=False, s=spec: self._on_function(s))
                    if label_second:
                        self._second_buttons.append((btn, spec))
                sci.addWidget(btn, r, c)
        num = QGridLayout()
        num.setSpacing(7)
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
        for r, specs in enumerate(layout):
            for c, (label, command, kind) in enumerate(specs):
                btn = AnimatedButton(label, kind, max_font_px=16 if kind == "mem" else 32,
                                     width_ratio=0.34 if kind == "mem" else 0.44)
                btn.clicked.connect(command or (lambda _=False, d=label: self.insert(d)))
                num.addWidget(btn, r, c)
        for grid in (sci, num):
            for i in range(6):
                grid.setRowStretch(i, 1)
        row.addLayout(sci, 5)
        row.addLayout(num, 4)
        return pad

    def _build_history(self) -> QWidget:
        card = Card()
        card.setMinimumWidth(250)
        card.setMaximumWidth(420)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 14, 6, 10)
        header = QHBoxLayout()
        header.setContentsMargins(8, 0, 6, 0)
        header.addWidget(make_label("Historique", 17, SEMIBOLD), 1)
        clear = AnimatedButton("Effacer", "ghost", font_px=13, radius=8)
        clear.setFixedSize(76, 30)
        clear.clicked.connect(self.clear_history)
        header.addWidget(clear)
        layout.addLayout(header)
        self.history_scroll = SmoothScrollArea()
        container = QWidget()
        self.history_layout = QVBoxLayout(container)
        self.history_layout.setContentsMargins(0, 4, 6, 4)
        self.history_layout.setSpacing(2)
        self.history_empty = make_label(
            "Aucun calcul pour l'instant.\nVos résultats apparaîtront ici.", 13, role="muted",
            align=Qt.AlignmentFlag.AlignCenter)
        self.history_empty.setContentsMargins(0, 40, 0, 0)
        self.history_layout.addWidget(self.history_empty)
        self.history_layout.addStretch(1)
        self.history_scroll.setWidget(container)
        layout.addWidget(self.history_scroll, 1)
        for item in self.history:
            self._add_history_widget(item["expr"], item["result"], animate=False)
        self._update_history_empty()
        return card

    # ------------------------------------------------------------------
    # Historique
    # ------------------------------------------------------------------
    def _add_history_widget(self, expr: str, result: str, animate: bool = True) -> None:
        item = HistoryItem(expr, result)
        item.expression_clicked.connect(self._load_expression)
        item.result_clicked.connect(self.insert)
        self.history_layout.insertWidget(0, item)
        self._history_items.append(item)
        if animate:
            target = item.sizeHint().height()
            item.setMaximumHeight(0)
            anim = QVariantAnimation(item)
            anim.setDuration(240)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.setStartValue(0)
            anim.setEndValue(target)
            anim.valueChanged.connect(lambda h, it=item: it.setMaximumHeight(int(h)))
            anim.finished.connect(lambda it=item: it.setMaximumHeight(WIDGET_MAX))
            anim.start()
            self.history_scroll.scroll_to_top()

    def _discard(self, item: HistoryItem) -> None:
        self.history_layout.removeWidget(item)
        item.hide()
        item.deleteLater()

    def _update_history_empty(self) -> None:
        self.history_empty.setVisible(not self.history)

    def _push_history(self, expr: str, result: str) -> None:
        self.history.append({"expr": expr, "result": result})
        self._add_history_widget(expr, result)
        while len(self.history) > HISTORY_LIMIT:
            self.history.pop(0)
            self._discard(self._history_items.pop(0))
        self._update_history_empty()
        self.app.settings.set("history", self.history)

    def clear_history(self) -> None:
        for item in self._history_items:
            self._discard(item)
        self._history_items.clear()
        self.history.clear()
        self._update_history_empty()
        self.app.settings.set("history", self.history)

    def _load_expression(self, expr: str) -> None:
        self.display.setText(expr)
        self.just_evaluated = False
        self.display.setFocus()

    # ------------------------------------------------------------------
    # Saisie
    # ------------------------------------------------------------------
    def text(self) -> str:
        return self.display.text()

    def insert(self, text: str) -> None:
        if self.just_evaluated:
            self.just_evaluated = False
            if text.startswith(CONTINUATIONS):
                self.display.end(False)
            else:
                self.display.clear()
        self.display.insert(text)  # remplace la sélection éventuelle
        self.display.setFocus()

    def _on_function(self, spec: tuple) -> None:
        _, text, _, text_second = spec
        if self.second and text_second:
            self.insert(text_second)
            self.second_button.setChecked(False)
        else:
            self.insert(text)

    def _on_second_toggled(self, on: bool) -> None:
        self.second = on
        for btn, (label, _, label_second, _) in self._second_buttons:
            btn.setText(label_second if on else label)

    def clear(self) -> None:
        self.display.clear()
        self.previous_label.setText("")
        self.just_evaluated = False
        self.display.setFocus()
        self._refresh()

    def backspace(self) -> None:
        if self.just_evaluated:
            self.clear()
            return
        d = self.display
        if d.hasSelectedText():
            d.del_()
        else:
            pos = d.cursorPosition()
            text = d.text()
            before = text[:pos]
            size = next((len(t) for t in ERASE_TOKENS if before.endswith(t)), 1 if pos else 0)
            if size:
                d.setText(text[:pos - size] + text[pos:])
                d.setCursorPosition(pos - size)
        d.setFocus()

    def toggle_sign(self) -> None:
        self.just_evaluated = False
        text = self.text()
        if not text:
            self.insert("−")
            return
        match = _TRAILING_NUMBER.search(text)
        if match:
            prefix = text[:match.start()]
            if prefix.endswith(("−", "-")) and (len(prefix) == 1 or prefix[-2] in "(+−-×÷^;E "):
                text = prefix[:-1] + match.group(0)
            else:
                text = prefix + "−" + match.group(0)
        elif text.startswith("−(") and text.endswith(")"):
            text = text[2:-1]
        else:
            text = f"−({text})"
        self.display.setText(text)
        self.display.setFocus()

    def handle_key(self, event: QKeyEvent) -> bool:
        mods = event.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        alt = bool(mods & Qt.KeyboardModifier.AltModifier)
        if ctrl and not alt:
            return False  # copier, coller, tout sélectionner…
        key, char = event.key(), event.text()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) or char == "=":
            self.evaluate()
            return True
        if key == Qt.Key.Key_Escape:
            self.clear()
            return True
        if key == Qt.Key.Key_Backspace:
            self.backspace()
            return True
        if char in KEY_REPLACEMENTS:
            self.insert(KEY_REPLACEMENTS[char])
            return True
        if char and char.isprintable() and self.just_evaluated:
            self.insert(char)
            return True
        return False

    # ------------------------------------------------------------------
    # Calcul
    # ------------------------------------------------------------------
    def _set_angle_mode(self, mode: str) -> None:
        self.angle_mode = mode
        self.app.settings.set("angle_mode", mode)
        self._refresh()

    def _refresh(self) -> None:
        text = self.text()
        self.memory_badge.setVisible(bool(self.memory))
        if text == self._error_for:
            return  # garder le message d'erreur tant que l'expression n'a pas changé
        self._error_for = None
        if self.just_evaluated or not text.strip() or _PLAIN_NUMBER.match(text):
            self.preview_label.setText("")
            return
        try:
            value = evaluate(text, self.angle_mode, self.ans)
            set_role(self.preview_label, "muted")
            self.preview_label.setText("= " + format_number(value))
        except CalcError:
            self.preview_label.setText("")

    def evaluate(self) -> None:
        expr = self.text().strip()
        if not expr or self.just_evaluated:
            return
        try:
            value = evaluate(expr, self.angle_mode, self.ans)
            result = format_number(value)
        except CalcError as err:
            self._error_for = self.text()
            set_role(self.preview_label, "danger")
            self.preview_label.setText(str(err))
            self.display.shake()
            return
        missing = expr.count("(") - expr.count(")")
        if missing > 0:
            expr += ")" * missing
        self.ans = value
        self.just_evaluated = True
        self.previous_label.setText(f"{expr} =")
        self.display.setText(result)
        self.display.pop()
        self._push_history(expr, result)
        self._refresh()

    def current_value(self) -> float:
        try:
            return evaluate(self.text(), self.angle_mode, self.ans)
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
        self.app.toast("Mémoire : " + format_number(self.memory))

    def on_show(self) -> None:
        self.display.setFocus()
