"""
ProgressPanel — shows per-chunk progress for the active task.
Overall progress removed since each file has its own queue entry.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget,
)


class ProgressPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # ── Chunk progress ────────────────────────────────────────────
        chunk_header = QHBoxLayout()
        self._chunk_label = QLabel("Chunk progress")
        self._chunk_label.setObjectName("accent")
        self._chunk_counter = QLabel("")
        self._chunk_counter.setObjectName("subtext")
        self._chunk_counter.setAlignment(Qt.AlignmentFlag.AlignRight)
        chunk_header.addWidget(self._chunk_label)
        chunk_header.addStretch()
        chunk_header.addWidget(self._chunk_counter)
        layout.addLayout(chunk_header)

        self._chunk_bar = QProgressBar()
        self._chunk_bar.setTextVisible(True)
        self._chunk_bar.setValue(0)
        layout.addWidget(self._chunk_bar)

        # ── Merge stats (ffmpeg output during concat step) ────────────
        self._merge_label = QLabel("")
        self._merge_label.setObjectName("subtext")
        self._merge_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self._merge_label)

    # ------------------------------------------------------------------
    # Public slots
    # ------------------------------------------------------------------

    @pyqtSlot(str, int, int)
    def on_chunk_progress(self, task_id: str, current: int, total: int):
        if total > 0:
            pct = int(current * 100 / total)
            self._chunk_bar.setValue(pct)
            self._chunk_counter.setText(f"chunk {current} / {total}")
        else:
            self._chunk_bar.setValue(0)
            self._chunk_counter.setText("")
        self._merge_label.setText("")

    @pyqtSlot(str, str)
    def on_merge_stats(self, task_id: str, stats_line: str):
        """Display raw ffmpeg stats line during merge."""
        parts = []
        for token in stats_line.split():
            if token.startswith(("time=", "bitrate=", "size=")):
                parts.append(token)
        self._merge_label.setText("Merging: " + "  ".join(parts))

    def on_task_done(self):
        self._chunk_bar.setValue(100)
        self._chunk_counter.setText("Done")
        self._merge_label.setText("")

    # No-op kept for backward compat — no-op since overall is removed
    def set_total_tasks(self, total: int):
        pass

    def reset(self):
        self._chunk_bar.setValue(0)
        self._chunk_counter.setText("")
        self._merge_label.setText("")
