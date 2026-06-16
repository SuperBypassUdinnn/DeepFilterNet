"""
QueueManager — orchestrates the task queue.
Runs on the main thread; starts/stops ProcessWorker threads.
"""
from __future__ import annotations

import copy
from typing import List, Optional

from PyQt6.QtCore import QObject, pyqtSignal

from gui.core.task import ProcessTask, TaskStatus
from gui.core.worker import ProcessWorker


class QueueManager(QObject):
    # Emitted whenever the queue list or a task status changes
    queue_changed = pyqtSignal()
    # Emitted when a new worker starts
    active_task_changed = pyqtSignal(object)

    # Forwarded from ProcessWorker
    log_line = pyqtSignal(str, str)            # task_id, line
    chunk_progress = pyqtSignal(str, int, int)  # task_id, current, total
    merge_stats = pyqtSignal(str, str)          # task_id, ffmpeg stats line
    task_done = pyqtSignal(str)
    task_error = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._queue: List[ProcessTask] = []
        self._worker: Optional[ProcessWorker] = None
        self._id_counter: int = 0

    # ------------------------------------------------------------------
    # Queue inspection
    # ------------------------------------------------------------------

    @property
    def tasks(self) -> List[ProcessTask]:
        return list(self._queue)

    @property
    def active_task(self) -> Optional[ProcessTask]:
        return self._worker.task if self._worker else None

    @property
    def is_running(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    # ------------------------------------------------------------------
    # Queue manipulation
    # ------------------------------------------------------------------

    def _next_id(self) -> str:
        self._id_counter += 1
        return str(self._id_counter)

    def add(self, task: ProcessTask):
        task.id = self._next_id()
        self._queue.append(task)
        self.queue_changed.emit()
        self._start_next_if_idle()

    _REMOVABLE = {TaskStatus.PENDING, TaskStatus.DONE, TaskStatus.ERROR, TaskStatus.STOPPED}

    def remove(self, task_id: str):
        """Remove a task by id if it is not actively running or paused."""
        self._queue = [
            t for t in self._queue
            if not (t.id == task_id and t.status in self._REMOVABLE)
        ]
        self.queue_changed.emit()

    def move_up(self, task_id: str):
        idx = self._index_of(task_id)
        if idx > 0 and self._queue[idx].status == TaskStatus.PENDING:
            self._queue[idx - 1], self._queue[idx] = self._queue[idx], self._queue[idx - 1]
            self.queue_changed.emit()

    def move_down(self, task_id: str):
        idx = self._index_of(task_id)
        if idx < len(self._queue) - 1 and self._queue[idx].status == TaskStatus.PENDING:
            self._queue[idx + 1], self._queue[idx] = self._queue[idx], self._queue[idx + 1]
            self.queue_changed.emit()

    def retry(self, task_id: str):
        """
        Clone a failed/stopped task, assign a new ID, and insert it at the
        beginning of the PENDING tasks (so it runs next).
        """
        original = self._find(task_id)
        if original is None:
            return

        new_task = copy.copy(original)
        new_task.id = self._next_id()
        new_task.status = TaskStatus.PENDING
        new_task.error_message = ""
        new_task.current_file_index = 0
        new_task.current_chunk = 0
        new_task.total_chunks = 0

        # Insert right after the last RUNNING/PAUSED task (i.e. at top of pending)
        insert_at = 0
        for i, t in enumerate(self._queue):
            if t.status in (TaskStatus.RUNNING, TaskStatus.PAUSED):
                insert_at = i + 1
            elif t.status == TaskStatus.PENDING:
                insert_at = i
                break
            else:
                insert_at = i + 1

        self._queue.insert(insert_at, new_task)
        # Remove the original failed entry so the list doesn't accumulate duplicates
        self._queue = [t for t in self._queue if t.id != task_id]
        self.queue_changed.emit()
        self._start_next_if_idle()

    def _index_of(self, task_id: str) -> int:
        for i, t in enumerate(self._queue):
            if t.id == task_id:
                return i
        return -1

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    def pause(self):
        if self._worker:
            self._worker.pause()
            if self._worker.task:
                self._worker.task.status = TaskStatus.PAUSED
            self.queue_changed.emit()

    def resume(self):
        if self._worker:
            self._worker.resume()
            if self._worker.task:
                self._worker.task.status = TaskStatus.RUNNING
            self.queue_changed.emit()

    def stop_current(self):
        """Kill current worker and leave the rest of the queue intact."""
        if self._worker:
            self._worker.stop()
            self._worker.wait(3000)
            if self._worker.task:
                self._worker.task.status = TaskStatus.STOPPED
            self._worker = None
            self.queue_changed.emit()
            self._start_next_if_idle()

    def stop_all(self):
        """Kill current worker and mark all pending tasks as STOPPED."""
        # Mark pending first so _start_next_if_idle (called inside stop_current) won't
        # pick up a new task right after the worker is killed.
        for t in self._queue:
            if t.status == TaskStatus.PENDING:
                t.status = TaskStatus.STOPPED
        self.stop_current()

    def clear_done(self):
        """Remove finished/stopped/error tasks from the list."""
        self._queue = [
            t for t in self._queue
            if t.status not in (TaskStatus.DONE, TaskStatus.ERROR, TaskStatus.STOPPED)
        ]
        self.queue_changed.emit()

    # ------------------------------------------------------------------
    # Internal scheduling
    # ------------------------------------------------------------------

    def _start_next_if_idle(self):
        if self.is_running:
            return
        next_task = next(
            (t for t in self._queue if t.status == TaskStatus.PENDING), None
        )
        if next_task is None:
            return
        self._start_worker(next_task)

    def _start_worker(self, task: ProcessTask):
        task.status = TaskStatus.RUNNING
        self.queue_changed.emit()

        worker = ProcessWorker(task)
        worker.log_line.connect(self.log_line)
        worker.chunk_progress.connect(self._on_chunk_progress)
        worker.merge_stats.connect(self.merge_stats)
        worker.task_done.connect(self._on_task_done)
        worker.task_error.connect(self._on_task_error)
        self._worker = worker
        self.active_task_changed.emit(task)
        worker.start()

    def _on_chunk_progress(self, task_id: str, current: int, total: int):
        self.chunk_progress.emit(task_id, current, total)
        self.queue_changed.emit()

    def _on_task_done(self, task_id: str):
        task = self._find(task_id)
        if task:
            task.status = TaskStatus.DONE
        self._worker = None
        self.queue_changed.emit()
        self.task_done.emit(task_id)
        self._start_next_if_idle()

    def _on_task_error(self, task_id: str, msg: str):
        task = self._find(task_id)
        if task:
            task.status = TaskStatus.ERROR
            task.error_message = msg
        self._worker = None
        self.queue_changed.emit()
        self.task_error.emit(task_id, msg)
        self._start_next_if_idle()

    def _find(self, task_id: str) -> Optional[ProcessTask]:
        return next((t for t in self._queue if t.id == task_id), None)
