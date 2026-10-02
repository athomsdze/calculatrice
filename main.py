"""Point d'entrée de Calculatrice Pro.

Usage :
    python main.py                      lance l'application
    python main.py --self-test FICHIER  ouvre la fenêtre, vérifie les vues puis se ferme
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
    from calculatrice.app import App
    from calculatrice.storage import Settings

    app = App(Settings())
    outcome = {"code": 1, "log": ""}

    def run_checks():
        try:
            calc = app.views["calc"]
            for key in ("2", "×", "sin("):
                calc.insert(key)
            calc.insert("30")
            calc.evaluate()
            assert calc.entry.get() == "1", calc.entry.get()
            app.show("currency")
            app.update()
            currency = app.views["currency"]
            currency.amount_var.set("100")
            assert currency.result_label.cget("text").strip() != "—"
            app.show("units")
            app.update()
            units = app.views["units"]
            units.select_category("temperature")
            units.from_var.set("100")
            assert units.to_var.get() == "212", units.to_var.get()
            for mode in ("Clair", "Sombre"):
                app._set_appearance(mode)
                app.update()
            outcome["code"], outcome["log"] = 0, "OK"
        except Exception:
            outcome["log"] = traceback.format_exc()
        finally:
            app.after(200, app.destroy)

    app.after(1500, run_checks)
    app.mainloop()
    report.write_text(outcome["log"], encoding="utf-8")
    return outcome["code"]


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "--self-test":
        return _self_test(Path(sys.argv[2]))

    try:
        from calculatrice.app import App
        from calculatrice.storage import Settings

        App(Settings()).mainloop()
        return 0
    except Exception:
        details = traceback.format_exc()
        try:
            from calculatrice.storage import user_data_dir

            log = user_data_dir() / "crash.log"
            log.write_text(details, encoding="utf-8")
        except Exception:
            log = None
        try:
            from tkinter import Tk, messagebox

            root = Tk()
            root.withdraw()
            messagebox.showerror(
                "Calculatrice Pro",
                "Une erreur inattendue est survenue."
                + (f"\n\nDétails enregistrés dans :\n{log}" if log else f"\n\n{details}"),
            )
            root.destroy()
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
