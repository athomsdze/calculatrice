"""Emplacement des données utilisateur et réglages persistants."""

from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path
from typing import Any

DEFAULT_SETTINGS: dict[str, Any] = {
    "appearance": "Dark",
    "last_view": "calc",
    "angle_mode": "DEG",
    "memory": 0.0,
    "history": [],
    "currency_from": "EUR",
    "currency_to": "USD",
    "currency_amount": "100",
    "currency_favorites": [
        "USD", "EUR", "GBP", "CHF", "JPY", "CAD", "CNY", "MAD", "XOF", "DZD", "TND", "AED",
    ],
    "chart_period": "1M",
    "unit_category": "length",
    "unit_choices": {},
}

HISTORY_LIMIT = 200


def user_data_dir() -> Path:
    """Dossier de données : %APPDATA%\\CalculatricePro sous Windows."""
    override = os.environ.get("CALCULATRICE_DATA_DIR")
    if override:
        path = Path(override)
    elif sys.platform == "win32":
        path = Path(os.environ.get("APPDATA", Path.home())) / "CalculatricePro"
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / "CalculatricePro"
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
        path = Path(base) / "calculatrice-pro"
    path.mkdir(parents=True, exist_ok=True)
    return path


def resource_path(relative: str) -> Path:
    """Chemin d'une ressource embarquée (fonctionne aussi dans l'exécutable PyInstaller)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / relative


def read_json(path: Path) -> Any:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except OSError:
        pass


class Settings:
    """Réglages persistés en JSON dans le dossier utilisateur."""

    def __init__(self, path: Path | None = None):
        self.path = path or (user_data_dir() / "settings.json")
        self.data = copy.deepcopy(DEFAULT_SETTINGS)
        stored = read_json(self.path)
        if isinstance(stored, dict):
            for key, value in stored.items():
                if key in DEFAULT_SETTINGS and isinstance(value, type(DEFAULT_SETTINGS[key])):
                    self.data[key] = value
                elif key == "memory" and isinstance(value, (int, float)):
                    self.data[key] = float(value)

    def get(self, key: str) -> Any:
        return self.data.get(key, copy.deepcopy(DEFAULT_SETTINGS.get(key)))

    def set(self, key: str, value: Any, save: bool = True) -> None:
        self.data[key] = value
        if save:
            self.save()

    def save(self) -> None:
        write_json(self.path, self.data)
