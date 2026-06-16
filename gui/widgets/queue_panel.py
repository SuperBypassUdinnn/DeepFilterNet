"""
QueuePanel — queue table with selection-driven controls.

Behaviours:
  • Tasks displayed newest-first (reverse insertion order).
  • Pause/Resume/Retry button is one adaptive button:
      - Selected RUNNING   → "⏸  Pause"
      - Selected PAUSED    → "▶  Resume"
      - Selected ERROR/STOPPED → "🔄  Retry"
      - Anything else      → disabled
  • Stop All removed; single "⏹ Stop" opens the confirmation dialog.
  • ▲ / ▼ reorder only PENDING tasks.
"""
from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from gui.core.task import ProcessTask, TaskStatus

# Column indices
COL_ID     = 0
COL_FILES  = 1
COL_MODEL  = 2
COL_CHUNK  = 3
COL_STATUS = 4

_STATUS_COLORS = {
    TaskStatus.PENDING:  ("#455a64", "#e0e6f0"),
    TaskStatus.RUNNING:  ("#0d3a6e", "#4fc3f7"),
    TaskStatus.PAUSED:   ("#5d4037", "#ffcc80"),
    TaskStatus.DONE:     ("#1b5e20", "#a5d6a7"),
    TaskStatus.ERROR:    ("#b71c1c", "#ef9a9a"),
    TaskStatus.STOPPED:  ("#e65100", "#ffcc80"),
}

_ACTION_LABELS = {
    TaskStatus.RUNNING: ("⏸  Pause",  "btn_warning"),
    TaskStatus.PAUSED:  ("▶  Resume", "btn_primary"),
    TaskStatus.ERROR:   ("🔄  Retry",  "btn_icon"),
    TaskStatus.STOPPED: ("🔄  Retry",  "btn_icon"),
}


class QueuePanel(QWidget):
    request_move_up      = pyqtSignal(str)
    request_move_down    = pyqtSignal(str)
    request_remove       = pyqtSignal(str)
    request_pause        = pyqtSignal()      # pause active worker
    request_resume       = pyqtSignal()      # resume active worker
    request_retry        = pyqtSignal(str)   # retry task by id
    request_stop         = pyqtSignal()      # stop current (opens dialog in main_window)
    request_clear_done   = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tasks: List[ProcessTask] = []   # current snapshot (newest-first)
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("Processing Queue")
        title.setObjectName("accent")
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        # ── Table ──────────────────────────────────────────────────────
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["#", "Files", "Model", "Chunk", "Status"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(False)
        self._table.setShowGrid(False)

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(COL_ID,     QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(COL_FILES,  QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(COL_MODEL,  QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(COL_CHUNK,  QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeMode.ResizeToContents)

        self._table.selectionModel().selectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._table)

        # ── Control buttons ────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._btn_up = QPushButton("▲")
        self._btn_up.setObjectName("btn_icon")
        self._btn_up.setToolTip("Move selected pending task up (runs earlier)")
        self._btn_up.setFixedWidth(36)
        self._btn_up.clicked.connect(self._on_move_up)

        self._btn_down = QPushButton("▼")
        self._btn_down.setObjectName("btn_icon")
        self._btn_down.setToolTip("Move selected pending task down (runs later)")
        self._btn_down.setFixedWidth(36)
        self._btn_down.clicked.connect(self._on_move_down)

        # Adaptive Pause / Resume / Retry button
        self._btn_action = QPushButton("⏸  Pause")
        self._btn_action.setObjectName("btn_warning")
        self._btn_action.setFixedWidth(110)
        self._btn_action.setEnabled(False)
        self._btn_action.clicked.connect(self._on_action_clicked)

        self._btn_stop = QPushButton("⏹  Stop")
        self._btn_stop.setObjectName("btn_danger")
        self._btn_stop.setToolTip("Stop the currently running task")
        self._btn_stop.setFixedWidth(90)
        self._btn_stop.clicked.connect(self.request_stop)

        self._btn_remove = QPushButton("✕  Remove")
        self._btn_remove.setObjectName("btn_icon")
        self._btn_remove.setToolTip("Remove selected pending task from queue")
        self._btn_remove.setFixedWidth(90)
        self._btn_remove.clicked.connect(self._on_remove)

        self._btn_clear_done = QPushButton("Clear Done")
        self._btn_clear_done.setObjectName("btn_icon")
        self._btn_clear_done.setToolTip("Remove finished / stopped / failed tasks")
        self._btn_clear_done.clicked.connect(self.request_clear_done)

        btn_row.addWidget(self._btn_up)
        btn_row.addWidget(self._btn_down)
        btn_row.addWidget(self._btn_action)
        btn_row.addWidget(self._btn_stop)
        btn_row.addStretch()
        btn_row.addWidget(self._btn_remove)
        btn_row.addWidget(self._btn_clear_done)
        layout.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @pyqtSlot(list)
    def refresh(self, tasks: List[ProcessTask]):
        """
        Rebuild table from task list, showing newest entries at the top.
        Preserves the selection across refreshes.
        """
        selected_id = self._selected_task_id()
        # Show newest first
        display = list(reversed(tasks))
        self._tasks = display

        self._table.setRowCount(len(display))
        for row, task in enumerate(display):
            chunk_str = "Auto" if task.chunk_size == 0 else f"{task.chunk_size} s"
            cells = [
                (COL_ID,     task.id),
                (COL_FILES,  task.display_name),
                (COL_MODEL,  task.model),
                (COL_CHUNK,  chunk_str),
                (COL_STATUS, task.status.name.capitalize()),
            ]
            bg, fg = _STATUS_COLORS.get(task.status, ("#1a1a2e", "#e0e6f0"))
            for col, text in cells:
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, task.id)
                item.setBackground(QColor(bg))
                item.setForeground(QColor(fg))
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignCenter
                    if col != COL_FILES
                    else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                )
                self._table.setItem(row, col, item)

            if task.id == selected_id:
                self._table.selectRow(row)

        self._update_action_button()

    def set_running(self, running: bool):
        self._btn_stop.setEnabled(running)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _selected_task_id(self) -> Optional[str]:
        items = self._table.selectedItems()
        return items[0].data(Qt.ItemDataRole.UserRole) if items else None

    def _selected_task(self) -> Optional[ProcessTask]:
        tid = self._selected_task_id()
        if tid is None:
            return None
        return next((t for t in self._tasks if t.id == tid), None)

    @pyqtSlot()
    def _on_selection_changed(self):
        self._update_action_button()
        self._update_remove_button()

    def _update_action_button(self):
        """Reconfigure the adaptive action button based on selected task status."""
        task = self._selected_task()
        if task is None or task.status not in _ACTION_LABELS:
            self._btn_action.setEnabled(False)
            self._btn_action.setText("⏸  Pause")
            self._btn_action.setObjectName("btn_warning")
            self._btn_action.setStyleSheet("")
            return

        label, obj_name = _ACTION_LABELS[task.status]
        self._btn_action.setText(label)
        self._btn_action.setObjectName(obj_name)
        self._btn_action.setEnabled(True)
        # Force style refresh (objectName change needs a polish)
        self._btn_action.style().unpolish(self._btn_action)
        self._btn_action.style().polish(self._btn_action)

    def _update_remove_button(self):
        """Disable Remove when the selected task is actively running or paused."""
        task = self._selected_task()
        if task is None:
            self._btn_remove.setEnabled(True)
            return
        blocked = task.status in (TaskStatus.RUNNING, TaskStatus.PAUSED)
        self._btn_remove.setEnabled(not blocked)
        self._btn_remove.setToolTip(
            "Cannot remove a running or paused task — stop it first"
            if blocked else
            "Remove selected task from queue"
        )

    @pyqtSlot()
    def _on_action_clicked(self):
        task = self._selected_task()
        if task is None:
            return
        if task.status == TaskStatus.RUNNING:
            self.request_pause.emit()
        elif task.status == TaskStatus.PAUSED:
            self.request_resume.emit()
        elif task.status in (TaskStatus.ERROR, TaskStatus.STOPPED):
            self.request_retry.emit(task.id)

    def _on_move_up(self):
        tid = self._selected_task_id()
        if tid:
            self.request_move_up.emit(tid)

    def _on_move_down(self):
        tid = self._selected_task_id()
        if tid:
            self.request_move_down.emit(tid)

    def _on_remove(self):
        tid = self._selected_task_id()
        if tid:
            self.request_remove.emit(tid)
