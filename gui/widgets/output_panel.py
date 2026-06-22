"""
OutputPanel — output directory picker + output format selector.
"""
from __future__ import annotations

import os

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from gui.core.task import OUTPUT_FORMATS


class OutputPanel(QWidget):
    output_changed = pyqtSignal(str, str)  # (output_dir, output_format)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # ── Output directory ──────────────────────────────────────────
        dir_label = QLabel("Output Directory")
        dir_label.setObjectName("accent")
        layout.addWidget(dir_label)

        dir_row = QHBoxLayout()
        self._dir_edit = QLineEdit()
        self._dir_edit.setReadOnly(True)
        self._dir_edit.setPlaceholderText("Select output folder…")
        self._dir_edit.textChanged.connect(self._emit_changed)
        dir_row.addWidget(self._dir_edit)

        btn_browse = QPushButton("Browse")
        btn_browse.setFixedWidth(80)
        btn_browse.clicked.connect(self._browse)
        dir_row.addWidget(btn_browse)
        layout.addLayout(dir_row)

        # ── Output format ──────────────────────────────────────────────
        fmt_row = QHBoxLayout()
        fmt_label = QLabel("Output Format:")
        fmt_label.setFixedWidth(110)
        fmt_row.addWidget(fmt_label)

        self._fmt_combo = QComboBox()
        self._fmt_combo.addItems(OUTPUT_FORMATS)
        self._fmt_combo.setToolTip(
            "Output audio format.\n"
            "'Same as input' keeps the original format.\n"
            "FLAC / WAV / MP3 re-encode after noise filtering."
        )
        self._fmt_combo.currentTextChanged.connect(self._emit_changed)
        fmt_row.addWidget(self._fmt_combo)
        fmt_row.addStretch()
        layout.addLayout(fmt_row)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_output_dir(self) -> str:
        return self._dir_edit.text().strip()

    def get_output_format(self) -> str:
        return self._fmt_combo.currentText()

    def set_output_dir(self, path: str):
        self._dir_edit.setText(path)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _browse(self):
        start = self._dir_edit.text() or os.path.expanduser("~")
        dlg = QFileDialog(self, "Select Output Directory")
        dlg.setStyleSheet("")
        dlg.setFileMode(QFileDialog.FileMode.Directory)
        dlg.setOption(QFileDialog.Option.ShowDirsOnly, True)
        dlg.setDirectory(start)
        if dlg.exec():
            folders = dlg.selectedFiles()
            if folders:
                self._dir_edit.setText(folders[0])


    def _emit_changed(self, *_):
        self.output_changed.emit(self.get_output_dir(), self.get_output_format())
