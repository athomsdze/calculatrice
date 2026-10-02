"""Point d'entrée de Calculatrice Pro.

Usage :
    python main.py                      lance l'application
    python main.py --self-test FICHIER  ouvre la fenêtre, vérifie les pages puis se ferme
                                        (utilisé par l'intégration continue)
"""

from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path


def _self_test(report: Path) -> int:
    os.environ["CALCULATRICE_DATA_DIR"] = tempfile.mkdtemp(prefix="calculatrice-test-")
    from PySide6.QtCore import QTimer

    from calculatrice.app import MainWindow, apply_saved_theme, create_application
    from calculatrice.storage import Settings

    app = create_application(sys.argv)
    settings = Settings()
    apply_saved_theme(settings)
    window = MainWindow(settings)
    window.show_animated()
    outcome = {"code": 1, "log": ""}

    def run_checks() -> None:
        try:
            calc = window.views["calc"]
            for key in ("2", "×", "sin(", "30"):
                calc.insert(key)
            calc.evaluate()
            assert calc.text() == "1", calc.text()
            window.show_view("currency")
            currency = window.views["currency"]
            currency.amount_edit.setText("100")
            currency._recalculate(animate=False)
            assert currency.result_label.text() != "—", currency.result_label.text()
            window.show_view("units")
            units = window.views["units"]
            units.select_category("temperature")
            units.from_edit.setText("100")
            units._on_edited("from")
            assert units.to_edit.text() == "212", units.to_edit.text()
            for mode in ("Light", "Dark"):
                window.set_appearance(mode)
                app.processEvents()
            outcome["code"], outcome["log"] = 0, "OK"
        except Exception:
            outcome["log"] = traceback.format_exc()
        finally:
            QTimer.singleShot(300, app.quit)

    QTimer.singleShot(1500, run_checks)
    app.exec()
    report.write_text(outcome["log"], encoding="utf-8")
    return outcome["code"]


def _show_fatal_error(details: str, log: Path | None) -> None:
    message = "Une erreur inattendue est survenue."
    message += f"\n\nDétails enregistrés dans :\n{log}" if log else f"\n\n{details[-1500:]}"
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        if QApplication.instance() is None:
            QApplication(sys.argv)
        QMessageBox.critical(None, "Calculatrice Pro", message)
    except Exception:
        if sys.platform == "win32":
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, "Calculatrice Pro", 0x10)


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "--self-test":
        return _self_test(Path(sys.argv[2]))
    try:
        from calculatrice.app import MainWindow, apply_saved_theme, create_application
        from calculatrice.storage import Settings

        app = create_application(sys.argv)
        settings = Settings()
        apply_saved_theme(settings)
        window = MainWindow(settings)
        window.show_animated()
        return app.exec()
    except Exception:
        details = traceback.format_exc()
        log = None
        try:
            from calculatrice.storage import user_data_dir

            log = user_data_dir() / "crash.log"
            log.write_text(details, encoding="utf-8")
        except Exception:
            pass
        _show_fatal_error(details, log)
        return 1


if __name__ == "__main__":
    sys.exit(main())
