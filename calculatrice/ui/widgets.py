"""Widgets dessinés à la main, animés et adaptés au thème."""

from __future__ import annotations

import bisect
import math
from datetime import date
from typing import Callable, Sequence

from PySide6.QtCore import (
    QEasingCurve, QEvent, QObject, QPoint, QPointF, QPropertyAnimation, QRect, QRectF, QSize, Qt,
    QTimer, QVariantAnimation, Signal,
)
from PySide6.QtGui import (
    QColor, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractButton, QFrame, QGraphicsDropShadowEffect, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QScrollArea, QSizePolicy, QStackedLayout, QVBoxLayout, QWidget,
)

from ..core.search import filter_items
from .theme import BOLD, NORMAL, SEMIBOLD, THEME, font, mix, with_alpha

OUT_CUBIC = QEasingCurve.Type.OutCubic
WIDGET_MAX = 16_777_215
POINTING = Qt.CursorShape.PointingHandCursor
ANTIALIAS = QPainter.RenderHint.Antialiasing
CENTER = Qt.AlignmentFlag.AlignCenter
LEFT_V = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
RIGHT_V = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


def supports_window_opacity() -> bool:
    from PySide6.QtGui import QGuiApplication

    return QGuiApplication.platformName() not in ("offscreen", "minimal")


def set_role(label: QWidget, role: str) -> None:
    """Change la couleur d'un QLabel via la propriété ``role`` de la feuille de style."""
    if label.property("role") == role:
        return
    label.setProperty("role", role)
    label.style().unpolish(label)
    label.style().polish(label)


def make_label(text: str = "", px: int = 14, weight=NORMAL, role: str | None = None,
               align=LEFT_V) -> QLabel:
    label = QLabel(text)
    label.setFont(font(px, weight))
    label.setAlignment(align)
    if role:
        label.setProperty("role", role)
    return label


class AnimatedValue(QObject):
    """Nombre animé : appelle ``on_change`` à chaque image de l'animation."""

    def __init__(self, owner: QObject, value: float = 0.0, duration: int = 150,
                 on_change: Callable[[], None] | None = None, easing=OUT_CUBIC):
        super().__init__(owner)
        self.value = value
        self._on_change = on_change or owner.update
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(duration)
        self.anim.setEasingCurve(easing)
        self.anim.valueChanged.connect(self._step)

    def _step(self, v) -> None:
        self.value = float(v)
        self._on_change()

    def to(self, target: float, duration: int | None = None) -> None:
        running = self.anim.state() == QVariantAnimation.State.Running
        if not running and abs(target - self.value) < 1e-4:
            return
        self.anim.stop()
        if duration is not None:
            self.anim.setDuration(duration)
        self.anim.setStartValue(float(self.value))
        self.anim.setEndValue(float(target))
        self.anim.start()

    def snap(self, value: float) -> None:
        self.anim.stop()
        self.value = value
        self._on_change()


class RectAnimator(QObject):
    """Rectangle animé (pastille de sélection qui glisse)."""

    def __init__(self, owner: QWidget, duration: int = 240):
        super().__init__(owner)
        self.rect = QRectF()
        self._owner = owner
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(duration)
        self._anim.setEasingCurve(OUT_CUBIC)
        self._anim.valueChanged.connect(self._step)

    def _step(self, r) -> None:
        self.rect = QRectF(r)
        self._owner.update()

    def to(self, target: QRectF, animate: bool = True) -> None:
        if not animate or self.rect.isNull() or not self._owner.isVisible():
            self._anim.stop()
            self.rect = QRectF(target)
            self._owner.update()
            return
        self._anim.stop()
        self._anim.setStartValue(QRectF(self.rect))
        self._anim.setEndValue(QRectF(target))
        self._anim.start()


def fit_font_px(text: str, max_px: float, width: float, weight=NORMAL, min_px: int = 10,
                display: bool = False) -> int:
    """Plus grande taille ≤ ``max_px`` pour laquelle ``text`` tient dans ``width``."""
    px = int(max_px)
    while px > min_px and QFontMetrics(font(px, weight, display)).horizontalAdvance(text) > width:
        px -= 1
    return max(px, min_px)


# ---------------------------------------------------------------------------
# Boutons
# ---------------------------------------------------------------------------

BUTTON_STYLES = {
    # type : (fond, fond survolé, texte)
    "num": ("btn_num", "btn_num_hover", "text"),
    "fn": ("btn_fn", "btn_fn_hover", "text"),
    "op": ("accent_soft", "accent_soft_hover", "accent_text"),
    "eq": ("accent", "accent_hover", "on_accent"),
    "danger": ("btn_fn", "btn_fn_hover", "danger"),
    "soft": ("accent_soft", "accent_soft_hover", "accent_text"),
    "mem": (None, "btn_fn_hover", "muted"),
    "ghost": (None, "btn_fn_hover", "muted"),
}


class AnimatedButton(QAbstractButton):
    """Bouton arrondi : fondu au survol, léger enfoncement au clic, texte ajusté à la taille."""

    def __init__(self, text: str = "", kind: str = "num", parent: QWidget | None = None, *,
                 font_px: int | None = None, max_font_px: int = 30, radius: int = 14,
                 bold: bool | None = None, width_ratio: float = 0.34):
        super().__init__(parent)
        self._kind = kind
        self._font_px = font_px
        self._max_font_px = max_font_px
        self._width_ratio = width_ratio
        self._radius = radius
        self._bold = kind in ("op", "eq", "danger", "soft") if bold is None else bold
        self._fit_key: tuple | None = None
        self._fit_px = 12
        self._hover = AnimatedValue(self, duration=160)
        self._press = AnimatedValue(self, duration=110)
        self._checked = AnimatedValue(self, duration=200)
        self.setText(text)
        self.toggled.connect(lambda on: self._checked.to(1.0 if on else 0.0))
        self.setCursor(POINTING)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        THEME.changed.connect(self.update)

    def sizeHint(self) -> QSize:
        return QSize(64, 50)

    def minimumSizeHint(self) -> QSize:
        return QSize(34, 32)

    def enterEvent(self, event) -> None:
        self._hover.to(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover.to(0.0)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press.to(1.0, 70)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._press.to(0.0, 220)
        super().mouseReleaseEvent(event)

    def setText(self, text: str) -> None:  # noqa: N802 (API Qt)
        super().setText(text)
        self._fit_key = None
        self.update()

    def _colors(self) -> tuple[QColor, QColor]:
        base_key, hover_key, text_key = BUTTON_STYLES[self._kind]
        hover = THEME.color(hover_key)
        base = THEME.color(base_key) if base_key else with_alpha(hover, 0.0)
        bg = mix(base, hover, self._hover.value)
        fg = THEME.color(text_key)
        if self.isCheckable():
            bg = mix(bg, THEME.color("accent"), self._checked.value)
            fg = mix(fg, THEME.color("on_accent"), self._checked.value)
        if not self.isEnabled():
            fg = with_alpha(fg, 0.45)
        return bg, fg

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(ANTIALIAS)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        scale = 1.0 - 0.05 * self._press.value
        if scale != 1.0:
            p.translate(r.center())
            p.scale(scale, scale)
            p.translate(-r.center())
        bg, fg = self._colors()
        if bg.alpha():
            radius = min(self._radius, r.height() / 2)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(r, radius, radius)
        weight = BOLD if self._bold else NORMAL
        if self._font_px:
            px = self._font_px
        else:
            key = (self.text(), int(r.width()), int(r.height()))
            if key != self._fit_key:
                # même taille pour tous les boutons de même dimension ; réduite seulement si besoin
                start = min(r.height() * 0.42, r.width() * self._width_ratio, self._max_font_px)
                self._fit_px = fit_font_px(self.text(), start, r.width() * 0.84, weight)
                self._fit_key = key
            px = self._fit_px
        p.setFont(font(px, weight))
        p.setPen(fg)
        p.drawText(r, CENTER, self.text())


class SwapButton(QAbstractButton):
    """Bouton rond « ⇄ » qui pivote à chaque clic."""

    def __init__(self, parent: QWidget | None = None, size: int = 48):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setCursor(POINTING)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setToolTip("Inverser")
        self._angle = AnimatedValue(self, duration=420)
        self._hover = AnimatedValue(self, duration=160)
        self.clicked.connect(lambda: self._angle.to(round(self._angle.value / 180) * 180 + 180))
        THEME.changed.connect(self.update)

    def enterEvent(self, event) -> None:
        self._hover.to(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover.to(0.0)
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(ANTIALIAS)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(mix(THEME.color("accent"), THEME.color("accent_hover"), self._hover.value))
        p.drawEllipse(r)
        p.translate(r.center())
        p.rotate(self._angle.value)
        p.setPen(THEME.color("on_accent"))
        p.setFont(font(int(r.height() * 0.45), BOLD))
        p.drawText(QRectF(-r.width() / 2, -r.height() / 2, r.width(), r.height()), CENTER, "⇄")


# ---------------------------------------------------------------------------
# Sélecteurs
# ---------------------------------------------------------------------------

class SegmentedControl(QWidget):
    """Choix exclusif avec une pastille qui glisse vers l'option choisie."""

    changed = Signal(str)

    def __init__(self, options: Sequence[str], current: str | None = None,
                 parent: QWidget | None = None, height: int = 30, font_px: int = 12):
        super().__init__(parent)
        self._options = list(options)
        self._index = self._options.index(current) if current in self._options else 0
        self._hover_index = -1
        self._font_px = font_px
        self._pill = RectAnimator(self, 260)
        self._hover = AnimatedValue(self, duration=140)
        self.setFixedHeight(height)
        self.setMouseTracking(True)
        self.setCursor(POINTING)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        THEME.changed.connect(self.update)

    @property
    def value(self) -> str:
        return self._options[self._index]

    def sizeHint(self) -> QSize:
        fm = QFontMetrics(font(self._font_px, BOLD))
        widest = max(fm.horizontalAdvance(o) for o in self._options)
        return QSize((widest + 26) * len(self._options) + 6, self.height())

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def _segment(self, i: int) -> QRectF:
        w = (self.width() - 6) / len(self._options)
        return QRectF(3 + i * w, 3, w, self.height() - 6)

    def _index_at(self, x: float) -> int:
        w = (self.width() - 6) / len(self._options)
        return max(0, min(len(self._options) - 1, int((x - 3) // w)))

    def set_value(self, value: str, animate: bool = True) -> None:
        if value in self._options:
            self._index = self._options.index(value)
            self._pill.to(self._segment(self._index), animate)

    def resizeEvent(self, event) -> None:
        self._pill.to(self._segment(self._index), animate=False)
        super().resizeEvent(event)

    def mousePressEvent(self, event) -> None:
        i = self._index_at(event.position().x())
        if i != self._index:
            self._index = i
            self._pill.to(self._segment(i))
            self.changed.emit(self._options[i])

    def mouseMoveEvent(self, event) -> None:
        i = self._index_at(event.position().x())
        if i != self._hover_index:
            self._hover_index = i
            self._hover.snap(0.0)
            self._hover.to(1.0)

    def leaveEvent(self, event) -> None:
        self._hover.to(0.0)
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(ANTIALIAS)
        r = QRectF(self.rect())
        radius = 9
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(THEME.color("btn_fn"))
        p.drawRoundedRect(r, radius, radius)
        if 0 <= self._hover_index != self._index and self._hover.value > 0:
            p.setBrush(with_alpha(THEME.color("btn_fn_hover"), self._hover.value))
            p.drawRoundedRect(self._segment(self._hover_index), radius - 2, radius - 2)
        p.setBrush(THEME.color("accent"))
        p.drawRoundedRect(self._pill.rect, radius - 2, radius - 2)
        p.setFont(font(self._font_px, BOLD))
        for i, option in enumerate(self._options):
            seg = self._segment(i)
            overlap = seg.intersected(self._pill.rect).width() / max(seg.width(), 1)
            p.setPen(mix(THEME.color("text"), THEME.color("on_accent"), overlap))
            p.drawText(seg, CENTER, option)


class PillList(QWidget):
    """Liste verticale d'entrées avec une pastille de sélection animée (menu, catégories)."""

    selected = Signal(str)

    def __init__(self, items: Sequence[tuple[str, str, str | None]], parent: QWidget | None = None,
                 item_height: int = 44, font_px: int = 15, spacing: int = 4):
        super().__init__(parent)
        self._items = list(items)
        self._h, self._spacing, self._font_px = item_height, spacing, font_px
        self._current = 0
        self._hover_index = -1
        self._hover = AnimatedValue(self, duration=150)
        self._pill = RectAnimator(self, 300)
        self.setMouseTracking(True)
        self.setCursor(POINTING)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(len(self._items) * (item_height + spacing))
        THEME.changed.connect(self.update)

    @property
    def current(self) -> str:
        return self._items[self._current][0]

    def sizeHint(self) -> QSize:
        return QSize(200, self.height())

    def _rect(self, i: int) -> QRectF:
        return QRectF(0, i * (self._h + self._spacing), self.width(), self._h)

    def _index_at(self, y: float) -> int:
        i = int(y // (self._h + self._spacing))
        return i if 0 <= i < len(self._items) else -1

    def set_current(self, key: str, animate: bool = True) -> None:
        for i, item in enumerate(self._items):
            if item[0] == key:
                self._current = i
                self._pill.to(self._rect(i), animate)
                return

    def resizeEvent(self, event) -> None:
        self._pill.to(self._rect(self._current), animate=False)
        super().resizeEvent(event)

    def mouseMoveEvent(self, event) -> None:
        i = self._index_at(event.position().y())
        if i != self._hover_index:
            self._hover_index = i
            self._hover.snap(0.0)
            self._hover.to(1.0)

    def leaveEvent(self, event) -> None:
        self._hover.to(0.0)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        i = self._index_at(event.position().y())
        if i >= 0 and i != self._current:
            self._current = i
            self._pill.to(self._rect(i))
            self.selected.emit(self._items[i][0])

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(ANTIALIAS)
        p.setPen(Qt.PenStyle.NoPen)
        if 0 <= self._hover_index != self._current and self._hover.value > 0:
            p.setBrush(with_alpha(THEME.color("nav_hover"), self._hover.value))
            p.drawRoundedRect(self._rect(self._hover_index), 12, 12)
        p.setBrush(THEME.color("nav_active"))
        p.drawRoundedRect(self._pill.rect, 12, 12)
        has_icons = any(icon for _, _, icon in self._items)
        for i, (_, label, icon) in enumerate(self._items):
            r = self._rect(i)
            amount = r.intersected(self._pill.rect).height() / self._h
            x = 16
            if has_icons:
                p.setFont(font(self._font_px + 2, BOLD))
                p.setPen(mix(THEME.color("muted"), THEME.color("accent_text"), amount))
                p.drawText(QRectF(r.x() + 12, r.y(), 26, r.height()), CENTER, icon or "")
                x = 52
            p.setFont(font(self._font_px, SEMIBOLD if amount > 0.5 else NORMAL))
            p.setPen(mix(THEME.color("text"), THEME.color("accent_text"), amount))
            p.drawText(QRectF(r.x() + x, r.y(), r.width() - x - 8, r.height()), LEFT_V, label)


class PickerPopup(QFrame):
    """Fenêtre surgissante avec recherche ; se ferme d'un clic à l'extérieur."""

    picked = Signal(str)
    closed = Signal()

    def __init__(self, items: list[tuple[str, str]], current: str | None, parent: QWidget,
                 searchable: bool = True, placeholder: str = "Rechercher…"):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._items = items
        self._current = current
        self._animations: list[QPropertyAnimation] = []
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 8, 14, 20)  # place pour l'ombre
        panel = QFrame(objectName="Popup")
        shadow = QGraphicsDropShadowEffect(panel)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 110 if THEME.is_dark else 45))
        panel.setGraphicsEffect(shadow)
        outer.addWidget(panel)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        self.search: QLineEdit | None = None
        if searchable:
            self.search = QLineEdit(objectName="Search")
            self.search.setPlaceholderText(placeholder)
            self.search.setFont(font(14))
            self.search.setFixedHeight(38)
            self.search.textChanged.connect(self.filter)
            self.search.installEventFilter(self)
            layout.addWidget(self.search)
        self.list = QListWidget()
        self.list.setFont(font(14))
        self.list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list.itemClicked.connect(self.choose)
        self.list.itemActivated.connect(self.choose)
        layout.addWidget(self.list)
        self.filter("")

    def visible_values(self) -> list[str]:
        return [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())]

    def filter(self, text: str) -> None:
        self.list.clear()
        for value, label in filter_items(text, self._items):
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, value)
            self.list.addItem(item)
            if value == self._current and not text:
                self.list.setCurrentItem(item)
        if self.list.currentRow() < 0 and self.list.count():
            self.list.setCurrentRow(0)
        if self.list.currentItem() is not None:
            self.list.scrollToItem(self.list.currentItem(), QListWidget.ScrollHint.PositionAtCenter)

    def choose(self, item: QListWidgetItem) -> None:
        value = item.data(Qt.ItemDataRole.UserRole)
        self.close()
        self.picked.emit(value)

    def eventFilter(self, obj, event) -> bool:
        if obj is self.search and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                row = self.list.currentRow() + (1 if key == Qt.Key.Key_Down else -1)
                self.list.setCurrentRow(max(0, min(self.list.count() - 1, row)))
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self.list.currentItem() is not None:
                    self.choose(self.list.currentItem())
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        self.closed.emit()
        super().closeEvent(event)

    def popup_below(self, anchor: QWidget, min_width: int = 340, max_height: int = 420) -> None:
        rows = min(len(self._items), 10)
        height = rows * 36 + 22 + 28 + (46 if self.search else 0)
        height = min(max_height, max(height, 120))
        width = max(anchor.width() + 28, min_width)
        screen = anchor.screen().availableGeometry()
        pos = anchor.mapToGlobal(QPoint(-14, anchor.height() - 2))
        if pos.y() + height > screen.bottom():
            pos = anchor.mapToGlobal(QPoint(-14, -height + 4))
        pos.setX(max(screen.left(), min(pos.x(), screen.right() - width)))
        self.setGeometry(QRect(pos, QSize(width, height)))
        fading = supports_window_opacity()
        if fading:
            self.setWindowOpacity(0.0)
        self.show()
        fade = QPropertyAnimation(self, b"windowOpacity", self)
        fade.setDuration(150)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        slide = QPropertyAnimation(self, b"pos", self)
        slide.setDuration(200)
        slide.setEasingCurve(OUT_CUBIC)
        slide.setStartValue(pos - QPoint(0, 8))
        slide.setEndValue(pos)
        self._animations = [fade, slide]
        if fading:
            fade.start()
        slide.start()
        (self.search or self.list).setFocus()


class SelectButton(QAbstractButton):
    """Bouton affichant la valeur choisie ; ouvre un :class:`PickerPopup` au clic."""

    changed = Signal(str)

    def __init__(self, parent: QWidget | None = None, *, searchable: bool = True,
                 placeholder: str = "Rechercher…",
                 describe: Callable[[str], tuple[str, str]] | None = None):
        super().__init__(parent)
        self._items: list[tuple[str, str]] = []
        self._value: str | None = None
        self._searchable = searchable
        self._placeholder = placeholder
        self._describe = describe or (lambda v: (self._label_of(v), ""))
        self._hover = AnimatedValue(self, duration=160)
        self._open = AnimatedValue(self, duration=220)
        self.popup: PickerPopup | None = None
        self.setFixedHeight(46)
        self.setCursor(POINTING)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.clicked.connect(self.open_popup)
        THEME.changed.connect(self.update)

    @property
    def value(self) -> str | None:
        return self._value

    def _label_of(self, value: str | None) -> str:
        return next((label for v, label in self._items if v == value), value or "")

    def set_items(self, items: list[tuple[str, str]], value: str | None = None) -> None:
        self._items = list(items)
        if value is not None:
            self._value = value
        self.update()

    def set_value(self, value: str) -> None:
        self._value = value
        self.update()

    def open_popup(self) -> PickerPopup:
        self.popup = PickerPopup(self._items, self._value, self.window(), self._searchable,
                                 self._placeholder)
        self.popup.picked.connect(self._on_pick)
        self.popup.closed.connect(self._on_closed)
        self._open.to(1.0)
        self.popup.popup_below(self)
        return self.popup

    def _on_closed(self) -> None:
        self._open.to(0.0)
        self.popup = None

    def _on_pick(self, value: str) -> None:
        if value != self._value:
            self._value = value
            self.update()
            self.changed.emit(value)

    def enterEvent(self, event) -> None:
        self._hover.to(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover.to(0.0)
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(ANTIALIAS)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(mix(THEME.color("btn_fn"), THEME.color("btn_fn_hover"), self._hover.value))
        p.drawRoundedRect(r, 12, 12)
        main, secondary = self._describe(self._value or "")
        main_font = font(15, SEMIBOLD)
        fm = QFontMetrics(main_font)
        text_rect = r.adjusted(16, 0, -44, 0)
        main_text = fm.elidedText(main, Qt.TextElideMode.ElideRight, int(text_rect.width()))
        p.setFont(main_font)
        p.setPen(THEME.color("text"))
        p.drawText(text_rect, LEFT_V, main_text)
        if secondary:
            rest = text_rect.adjusted(fm.horizontalAdvance(main_text) + 10, 0, 0, 0)
            sec = QFontMetrics(font(14)).elidedText(secondary, Qt.TextElideMode.ElideRight,
                                                     int(max(rest.width(), 0)))
            p.setFont(font(14))
            p.setPen(THEME.color("muted"))
            p.drawText(rest, LEFT_V, sec)
        # chevron qui pivote quand la liste est ouverte
        p.translate(QPointF(r.right() - 22, r.center().y()))
        p.rotate(180 * self._open.value)
        pen = QPen(THEME.color("muted"), 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath(QPointF(-5, -2.5))
        path.lineTo(0, 2.5)
        path.lineTo(5, -2.5)
        p.drawPath(path)


# ---------------------------------------------------------------------------
# Conteneurs
# ---------------------------------------------------------------------------

class Card(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Card")


class HoverRow(QWidget):
    """Ligne cliquable dont le fond apparaît en fondu au survol."""

    clicked = Signal()
    double_clicked = Signal()

    def __init__(self, parent: QWidget | None = None, base_key: str | None = None):
        super().__init__(parent)
        self._base_key = base_key
        self._hover = AnimatedValue(self, duration=150)
        self.setCursor(POINTING)
        THEME.changed.connect(self.update)

    def set_base(self, key: str | None) -> None:
        self._base_key = key
        self.update()

    def enterEvent(self, event) -> None:
        self._hover.to(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover.to(0.0)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if (event.button() == Qt.MouseButton.LeftButton
                and self.rect().contains(event.position().toPoint())):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, _event) -> None:
        hover = THEME.color("btn_fn")
        base = THEME.color(self._base_key) if self._base_key else with_alpha(hover, 0.0)
        color = mix(base, hover, self._hover.value)
        if color.alpha():
            p = QPainter(self)
            p.setRenderHint(ANTIALIAS)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(QRectF(self.rect()), 10, 10)


class SmoothScrollArea(QScrollArea):
    """Zone de défilement : la molette fait glisser le contenu en douceur."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._target = 0
        self._anim = QPropertyAnimation(self.verticalScrollBar(), b"value", self)
        self._anim.setDuration(260)
        self._anim.setEasingCurve(OUT_CUBIC)

    def wheelEvent(self, event) -> None:
        if not event.pixelDelta().isNull() or event.angleDelta().y() == 0:
            super().wheelEvent(event)  # pavé tactile : défilement déjà progressif
            return
        bar = self.verticalScrollBar()
        running = self._anim.state() == QPropertyAnimation.State.Running
        start = self._target if running else bar.value()
        step = -event.angleDelta().y() / 120 * 110
        self._target = int(max(bar.minimum(), min(bar.maximum(), start + step)))
        self._anim.stop()
        self._anim.setStartValue(bar.value())
        self._anim.setEndValue(self._target)
        self._anim.start()
        event.accept()

    def scroll_to_top(self) -> None:
        self._anim.stop()
        self._target = 0
        self._anim.setStartValue(self.verticalScrollBar().value())
        self._anim.setEndValue(0)
        self._anim.start()


class Centered(QWidget):
    """Centre son contenu horizontalement en limitant sa largeur (confort en plein écran)."""

    def __init__(self, child: QWidget, max_width: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.child = child
        self.max_width = max_width
        child.setParent(self)

    def sizeHint(self) -> QSize:
        return self.child.sizeHint()

    def minimumSizeHint(self) -> QSize:
        return self.child.minimumSizeHint()

    def resizeEvent(self, event) -> None:
        w = min(self.width(), self.max_width)
        self.child.setGeometry((self.width() - w) // 2, 0, w, self.height())
        super().resizeEvent(event)


class ElidedLabel(QLabel):
    """QLabel qui tronque son texte avec « … » au lieu d'élargir la mise en page."""

    def __init__(self, text: str = "", mode=Qt.TextElideMode.ElideRight, parent=None):
        super().__init__(parent)
        self._full = text
        self._mode = mode
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802
        self._full = text
        self._apply()

    def full_text(self) -> str:
        return self._full

    def _apply(self) -> None:
        fm = QFontMetrics(self.font())
        super().setText(fm.elidedText(self._full, self._mode, max(self.width() - 2, 10)))

    def resizeEvent(self, event) -> None:
        self._apply()
        super().resizeEvent(event)


class ClickableLabel(QLabel):
    clicked = Signal()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


# ---------------------------------------------------------------------------
# Transitions et superpositions
# ---------------------------------------------------------------------------

def render_widget(widget: QWidget) -> QPixmap:
    """Capture d'un widget sur le fond de la fenêtre (pour les transitions)."""
    ratio = widget.devicePixelRatioF()
    pix = QPixmap(widget.size() * ratio)
    pix.setDevicePixelRatio(ratio)
    pix.fill(THEME.color("bg"))
    widget.render(pix, QPoint(), widget.rect(), QWidget.RenderFlag.DrawChildren)
    return pix


class _TransitionOverlay(QWidget):
    def __init__(self, parent: QWidget, old: QPixmap, new: QPixmap, direction: int):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._old, self._new, self._dir = old, new, direction
        self.progress = AnimatedValue(self, duration=300)
        self.setGeometry(parent.rect())
        self.show()
        self.raise_()

    def paintEvent(self, _event) -> None:
        t = self.progress.value
        p = QPainter(self)
        p.fillRect(self.rect(), THEME.color("bg"))
        shift = 28 * self._dir
        p.setOpacity(1.0 - t)
        p.drawPixmap(QPointF(0, -shift * t), self._old)
        p.setOpacity(t)
        p.drawPixmap(QPointF(0, shift * (1.0 - t)), self._new)


class TransitionStack(QWidget):
    """Pages empilées ; le changement de page glisse et se fond (via des captures, donc fluide)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._layout = QStackedLayout(self)
        self._overlay: _TransitionOverlay | None = None

    def add_page(self, widget: QWidget) -> int:
        return self._layout.addWidget(widget)

    def current_index(self) -> int:
        return self._layout.currentIndex()

    def set_current(self, index: int, animate: bool = True) -> None:
        old_index = self._layout.currentIndex()
        self._finish()
        if index == old_index:
            return
        if not animate or not self.isVisible() or old_index < 0:
            self._layout.setCurrentIndex(index)
            return
        old_pix = render_widget(self._layout.currentWidget())
        self._layout.setCurrentIndex(index)
        new = self._layout.currentWidget()
        if new.layout() is not None:
            new.layout().activate()
        new_pix = render_widget(new)
        self._overlay = _TransitionOverlay(self, old_pix, new_pix, 1 if index > old_index else -1)
        self._overlay.progress.anim.finished.connect(self._finish)
        self._overlay.progress.to(1.0)

    def _finish(self) -> None:
        if self._overlay is not None:
            self._overlay.deleteLater()
            self._overlay = None

    def resizeEvent(self, event) -> None:
        self._finish()
        super().resizeEvent(event)


class FadeOverlay(QWidget):
    """Capture figée qui s'efface en fondu (changement de thème sans à-coup)."""

    def __init__(self, parent: QWidget, pixmap: QPixmap, duration: int = 320):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._pixmap = pixmap
        self._opacity = AnimatedValue(self, 1.0, duration=duration)
        self._opacity.anim.finished.connect(self.deleteLater)
        self.setGeometry(parent.rect())
        self.show()
        self.raise_()
        self._opacity.to(0.0)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setOpacity(self._opacity.value)
        p.drawPixmap(0, 0, self._pixmap)


class Toast(QWidget):
    """Petit message temporaire qui apparaît en glissant en bas de la fenêtre."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.text = ""
        self._shown = AnimatedValue(self, duration=240, on_change=self._reposition)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self._shown.to(0.0))
        self.hide()

    def show_message(self, text: str, duration_ms: int = 1800) -> None:
        self.text = text
        self.resize(QFontMetrics(font(13, SEMIBOLD)).horizontalAdvance(text) + 40, 40)
        self.show()
        self.raise_()
        self._shown.to(1.0)
        self._timer.start(duration_ms)

    def _reposition(self) -> None:
        parent = self.parentWidget()
        t = self._shown.value
        self.move((parent.width() - self.width()) // 2,
                  parent.height() - int((self.height() + 28) * t))
        if t <= 0.001:
            self.hide()
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(ANTIALIAS)
        p.setOpacity(self._shown.value)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(THEME.color("text"))
        p.drawRoundedRect(QRectF(self.rect()), 12, 12)
        p.setPen(THEME.color("bg"))
        p.setFont(font(13, SEMIBOLD))
        p.drawText(QRectF(self.rect()), CENTER, self.text)


# ---------------------------------------------------------------------------
# Graphique
# ---------------------------------------------------------------------------

class LineChart(QWidget):
    """Courbe avec dégradé, apparition animée et info-bulle au survol."""

    def __init__(self, formatter: Callable[[float], str], parent: QWidget | None = None):
        super().__init__(parent)
        self._fmt = formatter
        self.points: list[tuple[date, float]] = []
        self.message = ""
        self.loading = False
        self._reveal = AnimatedValue(self, 1.0, duration=750)
        self._hover_x: float | None = None
        self._xs: list[float] = []
        self._ys: list[float] = []
        self._spin = 0.0
        self._spinner = QTimer(self)
        self._spinner.setInterval(16)
        self._spinner.timeout.connect(self._tick)
        self.setMouseTracking(True)
        self.setMinimumHeight(170)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        THEME.changed.connect(self.update)

    def _tick(self) -> None:
        self._spin = (self._spin + 7) % 360
        self.update()

    def set_loading(self) -> None:
        self.loading, self.message = True, ""
        self._spinner.start()
        self.update()

    def set_points(self, points: Sequence[tuple[date, float]]) -> None:
        self.loading, self.message = False, ""
        self._spinner.stop()
        self.points = list(points)
        self._reveal.snap(0.0)
        self._reveal.to(1.0)

    def set_message(self, message: str) -> None:
        self.loading, self.message, self.points = False, message, []
        self._spinner.stop()
        self.update()

    def mouseMoveEvent(self, event) -> None:
        self._hover_x = event.position().x()
        self.update()

    def leaveEvent(self, event) -> None:
        self._hover_x = None
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(ANTIALIAS)
        w, h = self.width(), self.height()
        muted = THEME.color("muted")
        if self.loading:
            size = 30
            arc = QRectF(w / 2 - size / 2, h / 2 - size / 2 - 12, size, size)
            pen = QPen(THEME.color("accent"), 3)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawArc(arc, int(-self._spin * 16), 270 * 16)
            p.setPen(muted)
            p.setFont(font(13))
            p.drawText(QRectF(0, h / 2 + 14, w, 24), CENTER, "Chargement de l'historique…")
            return
        if self.message or len(self.points) < 2:
            p.setPen(muted)
            p.setFont(font(13))
            p.drawText(QRectF(self.rect()), int(CENTER) | int(Qt.TextFlag.TextWordWrap),
                       self.message or "Aucune donnée")
            return

        values = [v for _, v in self.points]
        vmin, vmax = min(values), max(values)
        pad = (vmax - vmin) * 0.12 if vmax - vmin > 1e-12 else (abs(vmax) * 0.01 or 1.0)
        vmin, vmax = vmin - pad, vmax + pad
        label_font = font(11)
        fm = QFontMetrics(label_font)
        labels = [self._fmt(vmin + (vmax - vmin) * i / 4) for i in range(5)]
        left = max(fm.horizontalAdvance(t) for t in labels) + 16
        plot = QRectF(left, 14, w - left - 12, h - 14 - 28)
        if plot.width() < 40 or plot.height() < 40:
            return
        first = self.points[0][0]
        span = max(1, (self.points[-1][0] - first).days)
        self._xs = [plot.left() + plot.width() * (d - first).days / span for d, _ in self.points]
        self._ys = [plot.bottom() - plot.height() * (v - vmin) / (vmax - vmin) for v in values]

        p.setFont(label_font)
        for i, text in enumerate(labels):
            y = plot.bottom() - plot.height() * i / 4
            p.setPen(QPen(THEME.color("border"), 1))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(muted)
            p.drawText(QRectF(0, y - 9, left - 10, 18), RIGHT_V, text)
        date_format = "%d/%m" if span <= 120 else "%m/%Y"
        for i in range(5):
            idx = round(i * (len(self.points) - 1) / 4)
            x = self._xs[idx]
            if i == 0:
                box, align = QRectF(x, plot.bottom() + 6, 70, 18), LEFT_V
            elif i == 4:
                box, align = QRectF(x - 70, plot.bottom() + 6, 70, 18), RIGHT_V
            else:
                box, align = QRectF(x - 35, plot.bottom() + 6, 70, 18), CENTER
            p.drawText(box, align, self.points[idx][0].strftime(date_format))

        rising = values[-1] >= values[0]
        line_color = THEME.color("success" if rising else "danger")
        line = QPainterPath(QPointF(self._xs[0], self._ys[0]))
        for x, y in zip(self._xs[1:], self._ys[1:]):
            line.lineTo(x, y)
        area = QPainterPath(line)
        area.lineTo(self._xs[-1], plot.bottom())
        area.lineTo(self._xs[0], plot.bottom())
        area.closeSubpath()
        gradient = QLinearGradient(0, plot.top(), 0, plot.bottom())
        gradient.setColorAt(0.0, with_alpha(line_color, 0.28))
        gradient.setColorAt(1.0, with_alpha(line_color, 0.0))

        p.save()
        p.setClipRect(QRectF(0, 0, plot.left() + plot.width() * self._reveal.value + 3, h))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(gradient)
        p.drawPath(area)
        pen = QPen(line_color, 2.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(line)
        p.restore()

        if self._reveal.value < 0.999:
            return
        p.setPen(QPen(THEME.color("card"), 2))
        p.setBrush(line_color)
        p.drawEllipse(QPointF(self._xs[-1], self._ys[-1]), 4.5, 4.5)

        hx = self._hover_x
        if hx is None or not (plot.left() - 10 <= hx <= plot.right() + 10):
            return
        i = bisect.bisect_left(self._xs, hx)
        if i >= len(self._xs) or (i > 0 and hx - self._xs[i - 1] < self._xs[i] - hx):
            i -= 1
        i = max(0, min(i, len(self._xs) - 1))
        x, y = self._xs[i], self._ys[i]
        p.setPen(QPen(muted, 1, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
        p.setPen(QPen(THEME.color("card"), 2))
        p.setBrush(THEME.color("accent"))
        p.drawEllipse(QPointF(x, y), 5.5, 5.5)
        day, value = self.points[i]
        text = f"{day.strftime('%d/%m/%Y')}   {self._fmt(value)}"
        tip_font = font(12, SEMIBOLD)
        tw = QFontMetrics(tip_font).horizontalAdvance(text) + 22
        tip = QRectF(min(max(x - tw / 2, 4), w - tw - 4), max(y - 46, 4), tw, 30)
        p.setPen(QPen(THEME.color("border"), 1))
        p.setBrush(THEME.color("card_alt"))
        p.drawRoundedRect(tip, 8, 8)
        p.setPen(THEME.color("text"))
        p.setFont(tip_font)
        p.drawText(tip, CENTER, text)


class LogoMark(QWidget):
    """Logo de l'application (carré arrondi dégradé avec « = »)."""

    def __init__(self, size: int = 40, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(size, size)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(ANTIALIAS)
        r = QRectF(self.rect())
        gradient = QLinearGradient(0, 0, 0, r.height())
        gradient.setColorAt(0, QColor("#7C78FF"))
        gradient.setColorAt(1, QColor("#4F46E5"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(gradient)
        p.drawRoundedRect(r, r.width() * 0.28, r.width() * 0.28)
        p.setPen(QColor("#FFFFFF"))
        p.setFont(font(int(r.height() * 0.55), BOLD))
        p.drawText(r.adjusted(0, -2, 0, 0), CENTER, "=")


def shake_offset(t: float, amplitude: float = 10.0) -> float:
    """Décalage d'une secousse amortie (t de 0 à 1)."""
    return amplitude * math.sin(t * math.pi * 6) * (1.0 - t)
