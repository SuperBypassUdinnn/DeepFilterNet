"""
InputPanel — file list with numbered ordering, add/remove/reorder buttons
and drag-and-drop support (individual files and folders).

Numbering: top = item 1 = first to be processed (queue adds them in order,
           and since queue is newest-at-top, item 1 ends up at the bottom
           of the queue but is processed first when the queue drains FIFO).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QAbstractItemView, QFileDialog, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget,
)

from gui.core.task import AUDIO_EXTENSIONS


class InputPanel(QWidget):
    files_changed = pyqtSignal(list)  # emits current file list

    def __init__(self, parent=None):
        super().__init__(parent)
        self._files: List[str] = []
        self._setup_ui()
        self.setAcceptDrops(True)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Header row
        header = QHBoxLayout()
        title = QLabel("Input Files")
        title.setObjectName("accent")
        header.addWidget(title)
        header.addStretch()
        self._count_label = QLabel("0 files")
        self._count_label.setObjectName("subtext")
        header.addWidget(self._count_label)
        layout.addLayout(header)

        # File list
        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._list.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        layout.addWidget(self._list)

        # Hint
        hint = QLabel("Drag & drop audio files or folders here")
        hint.setObjectName("subtext")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

        # Button row: [Add Files] [Add Folder] [▲] [▼]   [Remove] [Clear All]
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        btn_add_files = QPushButton("＋ Add Files")
        btn_add_files.setToolTip("Select audio files to add")
        btn_add_files.clicked.connect(self._add_files_dialog)

        btn_add_folder = QPushButton("📁 Add Folder")
        btn_add_folder.setToolTip("Scan a folder for all audio files")
        btn_add_folder.clicked.connect(self._add_folder_dialog)

        self._btn_up = QPushButton("▲")
        self._btn_up.setObjectName("btn_icon")
        self._btn_up.setToolTip("Move selected file(s) up in processing order")
        self._btn_up.setFixedWidth(32)
        self._btn_up.clicked.connect(self._move_up)

        self._btn_down = QPushButton("▼")
        self._btn_down.setObjectName("btn_icon")
        self._btn_down.setToolTip("Move selected file(s) down in processing order")
        self._btn_down.setFixedWidth(32)
        self._btn_down.clicked.connect(self._move_down)

        btn_remove = QPushButton("✕ Remove")
        btn_remove.setToolTip("Remove selected files from the list")
        btn_remove.clicked.connect(self._remove_selected)

        btn_clear = QPushButton("Clear All")
        btn_clear.clicked.connect(self._clear_all)

        btn_row.addWidget(btn_add_files)
        btn_row.addWidget(btn_add_folder)
        btn_row.addWidget(self._btn_up)
        btn_row.addWidget(self._btn_down)
        btn_row.addStretch()
        btn_row.addWidget(btn_remove)
        btn_row.addWidget(btn_clear)
        layout.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_files(self) -> List[str]:
        """Return files in display order (item 1 = first to process)."""
        return list(self._files)

    def clear(self):
        self._files.clear()
        self._list.clear()
        self._update_count()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _add_files_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Audio Files", "",
            "Audio Files (*.flac *.wav *.mp3 *.ogg *.opus *.m4a *.aac *.aiff *.aif *.wma);;"
            "All Files (*)",
        )
        self._add_paths(paths)

    def _add_folder_dialog(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            self._scan_folder(folder)

    def _remove_selected(self):
        selected = {item.data(Qt.ItemDataRole.UserRole) for item in self._list.selectedItems()}
        self._files = [f for f in self._files if f not in selected]
        self._rebuild_list()

    def _clear_all(self):
        self.clear()

    def _move_up(self):
        """Move each selected item up by one position."""
        selected_rows = sorted({self._list.row(item) for item in self._list.selectedItems()})
        if not selected_rows or selected_rows[0] == 0:
            return
        for row in selected_rows:
            self._files[row - 1], self._files[row] = self._files[row], self._files[row - 1]
        new_rows = [r - 1 for r in selected_rows]
        self._rebuild_list(select_rows=new_rows)

    def _move_down(self):
        """Move each selected item down by one position."""
        selected_rows = sorted({self._list.row(item) for item in self._list.selectedItems()})
        if not selected_rows or selected_rows[-1] == len(self._files) - 1:
            return
        for row in reversed(selected_rows):
            self._files[row + 1], self._files[row] = self._files[row], self._files[row + 1]
        new_rows = [r + 1 for r in selected_rows]
        self._rebuild_list(select_rows=new_rows)

    # ------------------------------------------------------------------
    # Drag & drop
    # ------------------------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        paths = []
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            if os.path.isdir(local):
                self._scan_folder(local)
            elif os.path.isfile(local):
                paths.append(local)
        self._add_paths(paths)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _scan_folder(self, folder: str):
        """Recursively collect all audio files inside a folder."""
        collected = []
        for root, _, files in os.walk(folder):
            for fname in sorted(files):
                if Path(fname).suffix.lower() in AUDIO_EXTENSIONS:
                    collected.append(os.path.join(root, fname))
        self._add_paths(collected)

    def _add_paths(self, paths: List[str]):
        added = 0
        for p in paths:
            if p not in self._files and Path(p).suffix.lower() in AUDIO_EXTENSIONS:
                self._files.append(p)
                added += 1
        if added:
            self._rebuild_list()

    def _rebuild_list(self, select_rows: List[int] | None = None):
        self._list.clear()
        for idx, path in enumerate(self._files, start=1):
            # Display: "  1.  filename.wav"
            item = QListWidgetItem(f"  {idx:>3}.  {os.path.basename(path)}")
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path)
            self._list.addItem(item)
        if select_rows:
            for row in select_rows:
                if 0 <= row < self._list.count():
                    self._list.item(row).setSelected(True)
        self._update_count()
        self.files_changed.emit(self._files)

    def _update_count(self):
        n = len(self._files)
        self._count_label.setText(f"{n} file{'s' if n != 1 else ''}")
