"""
MainWindow — top-level application window. Tab-based layout:
  Tab 1 "Processing": Input + Output + Settings + Queue + Progress
  Tab 2 "Log":        Verbose log viewer
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QMainWindow,
    QPushButton, QScrollArea, QSplitter, QStatusBar,
    QTabWidget, QVBoxLayout, QWidget,
)

from gui.core.queue_manager import QueueManager
from gui.core.task import ProcessTask, TaskStatus
from gui.widgets.dialogs import ErrorDialog, StopConfirmDialog
from gui.widgets.input_panel import InputPanel
from gui.widgets.log_panel import LogPanel
from gui.widgets.output_panel import OutputPanel
from gui.widgets.progress_panel import ProgressPanel
from gui.widgets.queue_panel import QueuePanel
from gui.widgets.settings_panel import SettingsPanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DeepFilterNet — Noise Suppression GUI")
        self.setMinimumSize(900, 640)
        self.resize(1160, 820)

        self._queue_mgr = QueueManager(self)

        self._setup_ui()
        self._connect_signals()
        self._update_control_state()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 6)
        root.setSpacing(0)

        self._tabs = QTabWidget()
        root.addWidget(self._tabs)

        self._tabs.addTab(self._build_processing_tab(), "⚙  Processing")
        self._tabs.addTab(self._build_log_tab(),        "📋  Log")
        self._tabs.currentChanged.connect(self._on_tab_changed)

        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Ready")

    def _build_processing_tab(self) -> QWidget:
        """
        Vertical splitter:

          ┌─ Top pane ──────────────────────────────────────┐  ~35%
          │  [Input 55%]  │  [Output + Settings scroll 45%] │
          └─────────────────────────────────────────────────┘
          [＋ Add to Queue]  task count
          ┌─ Bottom pane ───────────────────────────────────┐  ~65%
          │  Processing Queue (stretch)                      │
          │  Control buttons                                 │
          ├─────────────────────────────────────────────────┤
          │  Progress (fixed compact)                        │
          └─────────────────────────────────────────────────┘
        """
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(8, 8, 8, 6)
        tab_layout.setSpacing(6)

        # ── Vertical splitter ─────────────────────────────────────────
        vsplit = QSplitter(Qt.Orientation.Vertical)
        vsplit.setChildrenCollapsible(False)
        tab_layout.addWidget(vsplit, stretch=1)

        # ── TOP PANE: Input  |  Output + Settings ────────────────────
        top_widget = QWidget()
        top_layout = QHBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(8)

        # Left: Input
        input_group = QGroupBox("Input")
        input_inner = QVBoxLayout(input_group)
        input_inner.setContentsMargins(8, 6, 8, 8)
        self._input_panel = InputPanel()
        input_inner.addWidget(self._input_panel)
        top_layout.addWidget(input_group, stretch=55)

        # Right: Output (compact) + Settings (scrollable)
        right_col = QWidget()
        right_layout = QVBoxLayout(right_col)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        output_group = QGroupBox("Output")
        output_inner = QVBoxLayout(output_group)
        output_inner.setContentsMargins(8, 6, 8, 8)
        self._output_panel = OutputPanel()
        output_inner.addWidget(self._output_panel)
        right_layout.addWidget(output_group)

        # Settings inside a QScrollArea so it is never crushed
        self._settings_panel = SettingsPanel()
        settings_group = QGroupBox("Settings")
        settings_inner = QVBoxLayout(settings_group)
        settings_inner.setContentsMargins(8, 6, 8, 8)
        settings_inner.addWidget(self._settings_panel)

        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setWidget(settings_group)
        settings_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        settings_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        right_layout.addWidget(settings_scroll, stretch=1)

        top_layout.addWidget(right_col, stretch=45)
        vsplit.addWidget(top_widget)

        # ── BOTTOM PANE: Add-bar + Queue + Progress ───────────────────
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 4, 0, 0)
        bottom_layout.setSpacing(6)

        # Add-to-queue bar
        add_bar = QHBoxLayout()
        self._btn_add_queue = QPushButton("＋  Add to Queue")
        self._btn_add_queue.setObjectName("btn_primary")
        self._btn_add_queue.setFixedHeight(34)
        self._btn_add_queue.setMinimumWidth(150)
        self._btn_add_queue.clicked.connect(self._on_add_to_queue)
        self._task_count_label = QLabel("")
        self._task_count_label.setObjectName("subtext")
        add_bar.addWidget(self._btn_add_queue)
        add_bar.addWidget(self._task_count_label)
        add_bar.addStretch()
        bottom_layout.addLayout(add_bar)

        # Queue gets most of the bottom pane
        self._queue_panel = QueuePanel()
        self._queue_panel.setMinimumHeight(180)
        bottom_layout.addWidget(self._queue_panel, stretch=1)

        # Progress (compact, no stretch)
        prog_group = QGroupBox("Progress")
        prog_inner = QVBoxLayout(prog_group)
        prog_inner.setContentsMargins(8, 6, 8, 8)
        self._progress_panel = ProgressPanel()
        prog_inner.addWidget(self._progress_panel)
        bottom_layout.addWidget(prog_group)

        vsplit.addWidget(bottom_widget)

        # Initial proportions: top ~33%, bottom ~67%
        vsplit.setSizes([260, 500])

        return tab

    def _build_log_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        self._log_panel = LogPanel()
        layout.addWidget(self._log_panel)
        return tab

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self):
        mgr = self._queue_mgr

        mgr.queue_changed.connect(self._on_queue_changed)
        mgr.log_line.connect(self._on_log_line)
        mgr.chunk_progress.connect(self._progress_panel.on_chunk_progress)
        mgr.merge_stats.connect(self._progress_panel.on_merge_stats)
        mgr.task_done.connect(self._on_task_done)
        mgr.task_error.connect(self._on_task_error)

        qp = self._queue_panel
        qp.request_move_up.connect(mgr.move_up)
        qp.request_move_down.connect(mgr.move_down)
        qp.request_remove.connect(mgr.remove)
        qp.request_pause.connect(self._on_pause)
        qp.request_resume.connect(self._on_resume)
        qp.request_retry.connect(mgr.retry)
        qp.request_stop.connect(self._on_stop)
        qp.request_clear_done.connect(mgr.clear_done)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @pyqtSlot()
    def _on_add_to_queue(self):
        files = self._input_panel.get_files()
        out_dir = self._output_panel.get_output_dir()

        if not files:
            self._status_bar.showMessage("⚠  No input files selected.", 4000)
            return
        if not out_dir:
            self._status_bar.showMessage("⚠  No output directory selected.", 4000)
            return

        common_kwargs = dict(
            output_dir=out_dir,
            output_format=self._output_panel.get_output_format(),
            model=self._settings_panel.get_model(),
            chunk_size=self._settings_panel.get_chunk_size(),
            atten_lim=self._settings_panel.get_atten_lim(),
            post_filter=self._settings_panel.get_post_filter(),
            no_df_stage=self._settings_panel.get_no_df_stage(),
            no_delay_comp=self._settings_panel.get_no_delay_comp(),
        )
        first_id = None
        for f in files:
            task = ProcessTask(input_files=[f], **common_kwargs)
            self._queue_mgr.add(task)
            if first_id is None:
                first_id = task.id

        self._input_panel.clear()
        count = len(files)
        self._status_bar.showMessage(
            f"{count} task{'s' if count > 1 else ''} added to queue "
            f"(IDs {first_id}–{task.id})." if count > 1
            else f"Task {first_id} added to queue."
        )

        pending = sum(1 for t in self._queue_mgr.tasks if t.status == TaskStatus.PENDING)
        self._progress_panel.set_total_tasks(pending)


    @pyqtSlot(str, str)
    def _on_log_line(self, task_id: str, line: str):
        self._log_panel.append_line(task_id, line)
        # Flash the Log tab when it is not active
        if self._tabs.currentIndex() != 1:
            self._tabs.setTabText(1, "📋  Log ●")

    @pyqtSlot(int)
    def _on_tab_changed(self, index: int):
        if index == 1:
            # Clear the flash indicator when user opens the Log tab
            self._tabs.setTabText(1, "📋  Log")

    @pyqtSlot()
    def _on_queue_changed(self):
        tasks = self._queue_mgr.tasks
        self._queue_panel.refresh(tasks)
        self._queue_panel.set_running(self._queue_mgr.is_running)
        self._update_control_state()

        n_pending = sum(1 for t in tasks if t.status == TaskStatus.PENDING)
        n_total = len(tasks)
        self._task_count_label.setText(
            f"{n_pending} pending  /  {n_total} total" if n_total else ""
        )

    @pyqtSlot(str)
    def _on_task_done(self, task_id: str):
        self._progress_panel.on_task_done()
        self._status_bar.showMessage(f"Task {task_id} completed successfully.")

    @pyqtSlot(str, str)
    def _on_task_error(self, task_id: str, msg: str):
        task = next((t for t in self._queue_mgr.tasks if t.id == task_id), None)
        filename = task.display_name if task else task_id
        log_text = "\n".join(self._log_panel._task_logs.get(task_id, [])[-50:])
        dlg = ErrorDialog(task_id, filename, msg, log_text, parent=self)
        dlg.exec()
        self._status_bar.showMessage(f"Task {task_id} failed: {msg[:80]}")

    @pyqtSlot()
    def _on_pause(self):
        """Pause the active worker (triggered by selecting a RUNNING task and clicking Pause)."""
        if not self._queue_mgr.is_running:
            return
        self._queue_mgr.pause()
        self._status_bar.showMessage("Processing paused.")

    @pyqtSlot()
    def _on_resume(self):
        """Resume the active worker (triggered by selecting a PAUSED task and clicking Resume)."""
        self._queue_mgr.resume()
        self._status_bar.showMessage("Processing resumed.")

    @pyqtSlot()
    def _on_stop(self):
        """Stop with confirmation dialog (Stop Current | Stop All | Cancel)."""
        if not self._queue_mgr.is_running:
            return
        dlg = StopConfirmDialog(self)
        dlg.exec()
        if dlg.choice == StopConfirmDialog.STOP_CURRENT:
            self._queue_mgr.stop_current()
            self._status_bar.showMessage("Active task stopped.")
        elif dlg.choice == StopConfirmDialog.STOP_ALL:
            self._queue_mgr.stop_all()
            self._status_bar.showMessage("All tasks stopped.")

    def _update_control_state(self):
        self._queue_panel.set_running(self._queue_mgr.is_running)

    def closeEvent(self, event):
        if self._queue_mgr.is_running:
            self._queue_mgr.stop_all()
        event.accept()
