"""
LogPanel — scrolling verbose log viewer.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QColor, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QPlainTextEdit,
    QVBoxLayout, QWidget,
)

_LEVEL_COLORS = {
    "ERROR":   "#ef5350",
    "WARNING": "#ff9800",
    "INFO":    "#4fc3f7",
    "DEBUG":   "#8899aa",
    "[CMD]":   "#a5d6a7",
    "[Worker]":"#ce93d8",
    "Done":    "#4caf50",
    "Step":    "#80cbc4",
}


class LogPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._task_logs: dict[str, list[str]] = {}  # task_id → lines
        self._active_task_id: str | None = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Header row
        header = QHBoxLayout()
        label = QLabel("Process Log")
        label.setObjectName("accent")
        header.addWidget(label)
        header.addStretch()

        btn_clear = QPushButton("Clear")
        btn_clear.setObjectName("btn_icon")
        btn_clear.setFixedWidth(60)
        btn_clear.setToolTip("Clear visible log")
        btn_clear.clicked.connect(self._on_clear)
        header.addWidget(btn_clear)

        btn_copy = QPushButton("Copy")
        btn_copy.setObjectName("btn_icon")
        btn_copy.setFixedWidth(60)
        btn_copy.setToolTip("Copy all log text")
        btn_copy.clicked.connect(self._on_copy)
        header.addWidget(btn_copy)

        layout.addLayout(header)

        self._text = QPlainTextEdit()
        self._text.setObjectName("log_view")
        self._text.setReadOnly(True)
        self._text.setMaximumBlockCount(5000)
        layout.addWidget(self._text)

    @pyqtSlot(str, str)
    def append_line(self, task_id: str, line: str):
        """Append a log line from a worker. Colorised by keyword."""
        # Store per-task
        self._task_logs.setdefault(task_id, []).append(line)

        if self._active_task_id is not None and task_id != self._active_task_id:
            return  # Don't show logs from non-active task

        self._append_colored(line)

    def show_task_log(self, task_id: str):
        """Switch log view to a specific task."""
        self._active_task_id = task_id
        self._text.clear()
        for line in self._task_logs.get(task_id, []):
            self._append_colored(line)

    def show_all(self):
        """Show logs from all tasks merged."""
        self._active_task_id = None
        self._text.clear()
        for task_id, lines in self._task_logs.items():
            self._append_colored(f"── Task {task_id} ──")
            for line in lines:
                self._append_colored(line)

    def _append_colored(self, line: str):
        cursor = self._text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        fmt = QTextCharFormat()
        color = "#a8c8e8"  # default
        for keyword, col in _LEVEL_COLORS.items():
            if keyword in line:
                color = col
                break
        fmt.setForeground(QColor(color))

        cursor.insertText(line + "\n", fmt)
        self._text.setTextCursor(cursor)
        self._text.ensureCursorVisible()

    def _on_clear(self):
        self._text.clear()

    def _on_copy(self):
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(self._text.toPlainText())
