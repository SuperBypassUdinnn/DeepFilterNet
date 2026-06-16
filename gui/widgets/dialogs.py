"""
Reusable dialogs: stop confirmation, error details.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
    QPlainTextEdit, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)


class StopConfirmDialog(QDialog):
    """
    Ask the user whether to stop only the current task or all queued tasks.
    Accepted result codes:
      0 → Cancel (rejected)
      1 → Stop Current
      2 → Stop All
    """

    STOP_CURRENT = 1
    STOP_ALL = 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Stop Processing?")
        self.setMinimumWidth(400)
        self._choice = 0

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 20, 24, 16)

        icon_row = QHBoxLayout()
        warning_label = QLabel("⚠")
        warning_label.setStyleSheet("font-size: 32px; color: #ff9800;")
        icon_row.addWidget(warning_label)
        icon_row.addStretch()
        layout.addLayout(icon_row)

        title = QLabel("Stop Processing?")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #ff9800;")
        layout.addWidget(title)

        body = QLabel(
            "Stopping will abort the current chunk being processed.\n"
            "The output file for the active task will be incomplete.\n\n"
            "What would you like to stop?"
        )
        body.setWordWrap(True)
        body.setStyleSheet("color: #c0ccd8;")
        layout.addWidget(body)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)

        btn_current = QPushButton("Stop Current")
        btn_current.setObjectName("btn_warning")
        btn_current.clicked.connect(lambda: self._accept(self.STOP_CURRENT))

        btn_all = QPushButton("Stop All")
        btn_all.setObjectName("btn_danger")
        btn_all.clicked.connect(lambda: self._accept(self.STOP_ALL))

        btn_layout.addWidget(btn_cancel)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_current)
        btn_layout.addWidget(btn_all)
        layout.addLayout(btn_layout)

    def _accept(self, choice: int):
        self._choice = choice
        self.accept()

    @property
    def choice(self) -> int:
        return self._choice


class ErrorDialog(QDialog):
    """Display a processing error with an expandable log section."""

    def __init__(self, task_id: str, filename: str, error_msg: str,
                 log_text: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Processing Error")
        self.setMinimumWidth(500)
        self.setMinimumHeight(260)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 20, 24, 16)

        header = QLabel("✕  Processing Error")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #ef5350;")
        layout.addWidget(header)

        info = QLabel(f"<b>Task #{task_id}</b> — {filename}")
        info.setStyleSheet("color: #c0ccd8;")
        layout.addWidget(info)

        err_box = QPlainTextEdit()
        err_box.setReadOnly(True)
        err_box.setPlainText(error_msg)
        err_box.setMaximumHeight(80)
        err_box.setObjectName("log_view")
        layout.addWidget(err_box)

        if log_text:
            log_label = QLabel("Error log:")
            log_label.setObjectName("subtext")
            layout.addWidget(log_label)

            log_view = QPlainTextEdit()
            log_view.setReadOnly(True)
            log_view.setPlainText(log_text)
            log_view.setObjectName("log_view")
            layout.addWidget(log_view)

        btn_layout = QHBoxLayout()

        btn_copy = QPushButton("Copy Log")
        btn_copy.clicked.connect(lambda: self._copy(error_msg + "\n" + log_text))

        btn_ok = QPushButton("OK")
        btn_ok.setObjectName("btn_primary")
        btn_ok.clicked.connect(self.accept)

        btn_layout.addWidget(btn_copy)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_ok)
        layout.addLayout(btn_layout)

    def _copy(self, text: str):
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)
