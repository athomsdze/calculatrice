"""Tests de l'interface Qt, exécutés sans affichage (plateforme « offscreen »)."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QEventLoop, Qt, QTimer  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

import calculatrice.core.currency as currency_module  # noqa: E402


def offline(_url):
    raise OSError("hors ligne (test)")


def wait(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


@pytest.fixture(scope="module")
def qapp():
    from calculatrice.app import create_application

    return create_application([])


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("CALCULATRICE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(currency_module, "http_get_json", offline)
    from calculatrice.app import MainWindow, apply_saved_theme
    from calculatrice.storage import Settings

    settings = Settings()
    apply_saved_theme(settings)
    win = MainWindow(settings)
    win.resize(1240, 800)
    win.show()
    qapp.processEvents()
    yield win
    win.close()
    win.deleteLater()
    qapp.processEvents()


def test_calculator_buttons_and_history(window):
    c = window.views["calc"]
    for key in ("1", "2", "×", "3"):
        c.insert(key)
    assert c.preview_label.full_text() == "= 36"
    c.evaluate()
    assert c.text() == "36"
    assert c.previous_label.full_text() == "12×3 ="
    c.insert("+")
    c.insert("4")
    assert c.text() == "36+4"  # un opérateur prolonge le résultat
    c.evaluate()
    c.insert("5")
    assert c.text() == "5"  # un chiffre démarre un nouveau calcul
    assert len(c.history) == 2
    assert c.history[-1] == {"expr": "36+4", "result": "40"}
    c.clear_history()
    assert c.history == []


def test_calculator_editing(window):
    c = window.views["calc"]
    c.clear()
    c.insert("sin(")
    c.backspace()
    assert c.text() == ""  # « sin( » effacé d'un coup
    c.insert("2")
    c.insert(" mod ")
    c.backspace()
    assert c.text() == "2"
    c.clear()
    for key in ("5", "−", "3"):
        c.insert(key)
    c.toggle_sign()
    assert c.text() == "5−−3"
    c.toggle_sign()
    assert c.text() == "5−3"
    c.clear()
    c.insert("7")
    c.toggle_sign()
    assert c.text() == "−7"


def test_calculator_second_memory_and_errors(window):
    c = window.views["calc"]
    c.clear()
    c.second_button.click()
    c._on_function(("sin", "sin(", "sin⁻¹", "sin⁻¹("))
    assert c.text() == "sin⁻¹("
    assert not c.second_button.isChecked()  # 2nd se relâche après usage
    c.insert("1")
    c.evaluate()
    assert c.text() == "90"
    c.memory_add(1)
    assert c.memory == 90
    c.clear()
    c.memory_recall()
    assert c.text() == "90"
    c.memory_clear()
    c.clear()
    for key in ("1", "÷", "0"):
        c.insert(key)
    c.evaluate()
    assert c.preview_label.full_text() == "Division par zéro"
    c._set_angle_mode("RAD")
    c.clear()
    c.insert("cos(π)")
    c.evaluate()
    assert c.text() == "-1"


def test_calculator_keyboard(window):
    c = window.views["calc"]
    c.clear()
    c.display.setFocus()
    QTest.keyClicks(c.display, "12*3.5")
    assert c.text() == "12×3,5"
    QTest.keyClick(c.display, Qt.Key.Key_Return)
    assert c.text() == "42"
    QTest.keyClick(c.display, Qt.Key.Key_Escape)
    assert c.text() == ""
    QTest.keyClicks(c.display, "1/0")
    QTest.keyClick(c.display, Qt.Key.Key_Enter)
    assert c.preview_label.full_text() == "Division par zéro"
    QTest.keyClick(c.display, Qt.Key.Key_Backspace)
    assert c.text() == "1÷"


def test_currency(window):
    v = window.views["currency"]
    window.show_view("currency", animate=False)
    v.amount_edit.setText("1 000")
    v._recalculate(animate=False)
    assert v.result_label.text().endswith(v.to)
    popup = v.to_select.open_popup()
    popup.search.setText("marocain")
    assert popup.visible_values() == ["MAD"]
    popup.choose(popup.list.item(0))
    assert v.to == "MAD"
    v.swap()
    assert (v.frm, v.to) == ("MAD", "EUR")
    adder = v._open_add_favorite()
    adder.search.setText("rand")
    adder.choose(adder.list.item(0))
    assert v.favorites[-1] == "ZAR"
    v._remove_favorite("ZAR")
    assert "ZAR" not in v.favorites
    v.amount_edit.setText("abc")
    v._recalculate(animate=False)
    assert v.result_label.text() == "—"


def test_units(window):
    u = window.views["units"]
    window.show_view("units", animate=False)
    u.select_category("length")
    u.from_edit.setText("5")
    u._on_edited("from")
    assert u.to_edit.text() == "3,106855961"
    u.to_edit.setText("1")
    u._on_edited("to")
    assert u.from_edit.text() == "1,609344"
    u._on_unit_change("to", "m")  # la valeur saisie (côté « Vers ») est conservée
    assert u.from_edit.text() == "0,001"
    u.swap()
    assert (u.from_key, u.to_key) == ("m", "km")
    u.select_category("fuel")
    u.from_edit.setText("0")
    u._on_edited("from")
    assert u.to_edit.text() == ""
    assert u.formula_label.text() == "Division par zéro"
    u.select_category("data")
    u.from_edit.setText("1")
    u._on_edited("from")
    assert u.to_edit.text() == "1 000"
    assert len(u._rows) == len(u.category.units)


def test_navigation_and_theme(window, qapp):
    from calculatrice.ui.theme import THEME

    window.show_view("currency")
    assert window.current_view == "currency"
    assert window.stack._overlay is not None  # transition animée en cours
    wait(450)
    assert window.stack._overlay is None
    window.set_appearance("Light")
    assert THEME.name == "light"
    window.set_appearance("Dark")
    assert THEME.name == "dark"
    window.resize(1920, 1080)
    qapp.processEvents()
    window.grab()
