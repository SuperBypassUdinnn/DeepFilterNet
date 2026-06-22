"""
app.py — QApplication setup: dark theme, font, high-DPI.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QFontDatabase, QIcon
from PyQt6.QtWidgets import QApplication

_GUI_DIR = Path(__file__).parent
_QSS_PATH = _GUI_DIR / "style.qss"


def create_app(argv=None) -> QApplication:
    if argv is None:
        argv = sys.argv

    # Enable high-DPI scaling before creating QApplication
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    # Force native OS file dialogs (GTK on GNOME, KDE on Plasma)
    # This gives the user the proper themed file picker instead of Qt's built-in one.
    if not os.environ.get("QT_QPA_PLATFORMTHEME"):
        # Prefer gtk3 theme for native GTK file dialogs on GNOME/KDE
        os.environ["QT_QPA_PLATFORMTHEME"] = "gtk3"

    app = QApplication(argv)
    app.setApplicationName("DeepFilterNet GUI")
    app.setApplicationDisplayName("DeepFilterNet — Noise Suppression")
    app.setOrganizationName("DeepFilterNet")

    # Load stylesheet
    if _QSS_PATH.exists():
        app.setStyleSheet(_QSS_PATH.read_text(encoding="utf-8"))

    # Font: prefer Inter, fall back to system sans-serif
    _load_font(app)

    return app


def _load_font(app: QApplication):
    """Try to load Inter from a bundled location, otherwise use system font."""
    # Look for Inter in common locations
    search_dirs = [
        _GUI_DIR / "assets" / "fonts",
        Path.home() / ".fonts",
        Path("/usr/share/fonts"),
    ]
    for d in search_dirs:
        for ttf in d.glob("**/*Inter*.ttf") if d.exists() else []:
            QFontDatabase.addApplicationFont(str(ttf))
            break

    preferred = ["Inter", "Segoe UI", "Ubuntu", "Cantarell", "Arial"]
    chosen = None
    for name in preferred:
        if name in QFontDatabase.families():
            chosen = name
            break

    font = QFont(chosen or "Sans Serif", 10)
    app.setFont(font)
