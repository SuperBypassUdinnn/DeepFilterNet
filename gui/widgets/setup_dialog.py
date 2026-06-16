"""
SetupDialog — A modal dialog that runs on first launch to download and install
the required DeepFilterNet runtime (PyTorch, deepfilterlib, etc.)
"""
from __future__ import annotations

import threading

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPlainTextEdit,
    QProgressBar, QPushButton, QVBoxLayout,
)

from gui.core import dependency_manager


class SetupDialog(QDialog):
    # Signals to communicate from the worker thread to the GUI thread
    log_line = pyqtSignal(str)
    progress_update = pyqtSignal(int, int, str)
    install_finished = pyqtSignal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DeepFilterNet Setup")
        self.setFixedSize(600, 450)
        # Block the rest of the application until setup completes
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint)

        self._cancelled = False
        self._thread = None

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Title / Description
        title = QLabel("Initial Setup Required")
        title.setObjectName("accent")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        desc = QLabel(
            "DeepFilterNet requires heavy machine learning libraries (PyTorch). "
            "To keep the application size small, these are downloaded once on first launch.\n\n"
            "This will download ~200 MB (CPU) or ~2.5 GB (GPU) depending on your system."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Progress bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setValue(0)
        layout.addWidget(self._progress_bar)

        self._status_label = QLabel("Waiting to start...")
        self._status_label.setObjectName("subtext")
        layout.addWidget(self._status_label)

        # Log view
        self._log_view = QPlainTextEdit()
        self._log_view.setObjectName("log_view")
        self._log_view.setReadOnly(True)
        layout.addWidget(self._log_view)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._btn_cancel = QPushButton("Cancel")
        self._btn_cancel.clicked.connect(self._on_cancel)
        
        self._btn_start = QPushButton("Start Download")
        self._btn_start.setObjectName("btn_primary")
        self._btn_start.clicked.connect(self._on_start)

        btn_layout.addWidget(self._btn_cancel)
        btn_layout.addWidget(self._btn_start)
        layout.addLayout(btn_layout)

    def _connect_signals(self):
        self.log_line.connect(self._on_log_line)
        self.progress_update.connect(self._on_progress_update)
        self.install_finished.connect(self._on_install_finished)

    @pyqtSlot()
    def _on_start(self):
        self._btn_start.setEnabled(False)
        self._btn_cancel.setText("Cancel Setup")
        self._log_view.clear()
        
        self._thread = threading.Thread(target=self._run_install, daemon=True)
        self._thread.start()

    @pyqtSlot()
    def _on_cancel(self):
        if self._thread is not None and self._thread.is_alive():
            self._cancelled = True
            self._btn_cancel.setEnabled(False)
            self._status_label.setText("Cancelling... please wait.")
        else:
            self.reject()

    def _run_install(self):
        ok, msg = dependency_manager.install_runtime(
            log_cb=lambda s: self.log_line.emit(s),
            progress_cb=lambda c, t, l: self.progress_update.emit(c, t, l),
            cancelled=lambda: self._cancelled,
        )
        self.install_finished.emit(ok, msg)

    @pyqtSlot(str)
    def _on_log_line(self, line: str):
        self._log_view.appendPlainText(line)

    @pyqtSlot(int, int, str)
    def _on_progress_update(self, current: int, total: int, label: str):
        self._progress_bar.setMaximum(total)
        self._progress_bar.setValue(current)
        self._status_label.setText(label)

    @pyqtSlot(bool, str)
    def _on_install_finished(self, ok: bool, msg: str):
        self._btn_cancel.setEnabled(True)
        self._btn_cancel.setText("Close")
        if ok:
            self.accept()
        else:
            self._btn_start.setEnabled(True)
            self._btn_start.setText("Retry")
            self._status_label.setText("Installation failed.")
            self._log_view.appendPlainText(f"\n[ERROR] {msg}")

    # Prevent closing by X button during install
    def closeEvent(self, event):
        if self._thread is not None and self._thread.is_alive():
            event.ignore()
            self._on_cancel()
        else:
            event.accept()
