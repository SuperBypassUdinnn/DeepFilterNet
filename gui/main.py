"""
main.py — entry point for DeepFilterNet GUI.

Run via:
  python -m gui.main
or via the installed script:
  deepfilter-gui
"""
from __future__ import annotations

import sys


def main():
    from gui.app import create_app
    from gui.widgets.main_window import MainWindow

    app = create_app(sys.argv)

    # ── Runtime check ──
    from gui.core.dependency_manager import is_runtime_installed
    if not is_runtime_installed():
        from gui.widgets.setup_dialog import SetupDialog
        dlg = SetupDialog()
        # Modal execution
        if dlg.exec() != SetupDialog.DialogCode.Accepted:
            print("Setup cancelled or failed. Exiting.")
            sys.exit(1)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
