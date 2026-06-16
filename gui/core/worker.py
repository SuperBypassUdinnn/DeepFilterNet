"""
ProcessWorker — QThread that drives the deepFilter pipeline for one ProcessTask.

Pipeline per file:
  1. ffprobe   → get duration
  2. ffmpeg    → split into chunks (if duration > threshold)
  3. deepFilter → process each chunk in a separate subprocess (one at a time)
  4. ffmpeg    → concatenate enhanced chunks
  5. ffmpeg    → optional output format conversion (WAV/FLAC/MP3)

Pause/Resume is implemented via psutil.suspend() / psutil.resume() on the
currently running subprocess, which sends SIGSTOP/SIGCONT on Linux and uses
NtSuspendThread on Windows.
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

import psutil
from PyQt6.QtCore import QThread, pyqtSignal

from gui.core.gpu_probe import get_auto_chunk_size
from gui.core.task import (
    AUDIO_EXTENSIONS,
    CHUNK_THRESHOLD_SECONDS,
    ProcessTask,
    TaskStatus,
)

from gui.core.dependency_manager import get_deepfilter_bin

_DEEPFILTER_BIN = get_deepfilter_bin()
_FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
_FFPROBE = shutil.which("ffprobe") or "ffprobe"

# ffmpeg codec maps for output formats
_FORMAT_CODEC: dict[str, list[str]] = {
    "FLAC": ["-c:a", "flac"],
    "WAV":  ["-c:a", "pcm_s16le"],
    "MP3":  ["-c:a", "libmp3lame", "-q:a", "2"],
}


class ProcessWorker(QThread):
    """
    Signals:
      log_line(task_id, line)        — one line of log output
      chunk_progress(task_id, current, total)
      merge_stats(task_id, stats_line)  — raw ffmpeg -stats line
      task_done(task_id)
      task_error(task_id, message)
    """

    log_line = pyqtSignal(str, str)
    chunk_progress = pyqtSignal(str, int, int)
    merge_stats = pyqtSignal(str, str)
    task_done = pyqtSignal(str)
    task_error = pyqtSignal(str, str)

    def __init__(self, task: ProcessTask, parent=None):
        super().__init__(parent)
        self.task = task
        self._paused = False
        self._stopped = False
        self._current_proc: Optional[subprocess.Popen] = None
        self._current_psutil: Optional[psutil.Process] = None

    # ------------------------------------------------------------------
    # Public control API (called from main thread via QueueManager)
    # ------------------------------------------------------------------

    def pause(self):
        """Suspend the currently running subprocess."""
        self._paused = True
        if self._current_psutil is not None:
            try:
                self._current_psutil.suspend()
                self._log(f"[Worker] Process suspended (PID {self._current_psutil.pid})")
            except Exception as e:
                self._log(f"[Worker] Pause warning: {e}")

    def resume(self):
        """Resume the suspended subprocess."""
        self._paused = False
        if self._current_psutil is not None:
            try:
                self._current_psutil.resume()
                self._log(f"[Worker] Process resumed (PID {self._current_psutil.pid})")
            except Exception as e:
                self._log(f"[Worker] Resume warning: {e}")

    def stop(self):
        """Kill the current subprocess immediately."""
        self._stopped = True
        self._paused = False
        if self._current_psutil is not None:
            try:
                # Resume first so it can receive SIGKILL on Linux
                self._current_psutil.resume()
            except Exception:
                pass
            try:
                self._current_psutil.kill()
                self._log("[Worker] Process killed.")
            except Exception as e:
                self._log(f"[Worker] Kill warning: {e}")

    # ------------------------------------------------------------------
    # QThread entry point
    # ------------------------------------------------------------------

    def run(self):
        task = self.task
        failed = False
        fail_msg = ""
        try:
            for idx, input_file in enumerate(task.input_files):
                if self._stopped:
                    break
                task.current_file_index = idx
                self._log(f"\n{'='*60}")
                self._log(f"File {idx + 1}/{len(task.input_files)}: {input_file}")
                self._log(f"{'='*60}")
                ok, msg = self._process_file(input_file)
                if not ok:
                    failed = True
                    fail_msg = msg
                    break

            if self._stopped:
                pass  # status set to STOPPED by QueueManager.stop_current()
            elif failed:
                self.task_error.emit(task.id, fail_msg or "Processing failed — check log.")
            else:
                self.task_done.emit(task.id)
        except Exception as exc:
            self.task_error.emit(task.id, str(exc))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _log(self, line: str):
        self.log_line.emit(self.task.id, line)

    def _run_subprocess(self, cmd: List[str], **kwargs) -> int:
        """
        Run a command as a subprocess, streaming stdout/stderr to log.
        Supports pause/resume via psutil.
        Returns exit code.
        """
        self._log(f"[CMD] {' '.join(str(c) for c in cmd)}")
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            **kwargs,
        )
        self._current_proc = proc
        try:
            self._current_psutil = psutil.Process(proc.pid)
        except Exception:
            self._current_psutil = None

        for line in proc.stdout:  # type: ignore[union-attr]
            line = line.rstrip()
            if line:
                self._log(line)
                # Forward ffmpeg stats lines to merge_stats signal
                if "time=" in line and "bitrate=" in line:
                    self.merge_stats.emit(self.task.id, line)

        proc.wait()
        self._current_proc = None
        self._current_psutil = None
        return proc.returncode

    def _run_deepfilter_chunk(self, chunk_path: str, out_dir: str) -> int:
        """Run deepFilter on a single chunk file."""
        cmd = [_DEEPFILTER_BIN, "--no-suffix", "-o", out_dir]
        cmd += self.task.to_deepfilter_args()
        cmd.append(chunk_path)
        return self._run_subprocess(cmd)

    def _get_duration(self, path: str) -> float:
        """Return audio duration in seconds via ffprobe."""
        result = subprocess.run(
            [_FFPROBE, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True,
        )
        try:
            return float(result.stdout.strip())
        except ValueError:
            return 0.0

    def _determine_chunk_size(self) -> int:
        """Return actual chunk size in seconds (resolve 'auto')."""
        if self.task.chunk_size > 0:
            return self.task.chunk_size
        return get_auto_chunk_size()

    def _output_ext(self, input_path: str) -> str:
        """Return output file extension based on output_format setting."""
        fmt = self.task.output_format
        if fmt == "Same as input":
            return Path(input_path).suffix.lower()
        return {"FLAC": ".flac", "WAV": ".wav", "MP3": ".mp3"}.get(fmt, Path(input_path).suffix)

    def _convert_format(self, src: str, dst: str) -> int:
        """Convert audio to the requested output format via ffmpeg."""
        fmt = self.task.output_format
        codec_args = _FORMAT_CODEC.get(fmt, ["-c:a", "copy"])
        cmd = [_FFMPEG, "-y", "-i", src] + codec_args + [dst]
        return self._run_subprocess(cmd)

    def _process_file(self, input_file: str):
        """
        Main logic for a single input file. Returns (ok: bool, error_msg: str).

        If the input is not WAV, it is first converted to a temporary WAV file
        (stored in a temp dir) which is automatically cleaned up when the method
        returns, regardless of success, failure, or stop.
        """
        if not os.path.isfile(input_file):
            msg = f"File not found: {input_file}"
            self._log(f"[Error] {msg}")
            return False, msg

        in_ext = Path(input_file).suffix.lower()
        tmp_conv_dir: Optional[str] = None
        actual_input = input_file

        # ── Pre-conversion: non-WAV → WAV for broadest deepFilter compatibility ──
        if in_ext != ".wav":
            try:
                tmp_conv_dir = tempfile.mkdtemp(prefix="dfgui_conv_")
                wav_path = os.path.join(tmp_conv_dir, Path(input_file).stem + ".wav")
                self._log(f"[Pre-process] Converting {in_ext} → WAV for compatibility...")
                rc = self._run_subprocess([
                    _FFMPEG, "-y", "-i", input_file,
                    "-c:a", "pcm_s16le",
                    wav_path,
                ])
                if self._stopped:
                    return True, ""
                if rc != 0:
                    msg = f"Pre-conversion {in_ext}→WAV failed (exit {rc})"
                    self._log(f"[Error] {msg}")
                    return False, msg
                actual_input = wav_path
                self._log(f"[Pre-process] Conversion done → {wav_path}")
            except Exception as e:
                msg = f"Pre-conversion error: {e}"
                self._log(f"[Error] {msg}")
                return False, msg

        try:
            duration = self._get_duration(actual_input)
            self._log(f"Duration: {duration:.1f} s")

            stem = Path(input_file).stem          # use original stem for output name
            out_ext = self._output_ext(input_file)
            suffix = f"_{self.task.model}"
            out_filename = stem + suffix + out_ext
            out_path = os.path.join(self.task.output_dir, out_filename)

            os.makedirs(self.task.output_dir, exist_ok=True)

            chunk_size = self._determine_chunk_size()
            self._log(f"Chunk size: {chunk_size} s")

            if duration > CHUNK_THRESHOLD_SECONDS:
                return self._process_chunked(actual_input, out_path, ".wav", chunk_size)
            else:
                return self._process_direct(actual_input, out_path, out_ext)
        finally:
            # Always clean up the temporary WAV, even on failure or stop
            if tmp_conv_dir:
                shutil.rmtree(tmp_conv_dir, ignore_errors=True)
                self._log("[Pre-process] Temporary WAV cleaned up.")

    def _process_direct(self, input_file: str, out_path: str, out_ext: str):
        """Process a short file directly with deepFilter (no chunking). Returns (ok, msg)."""
        self._log("File is short — processing directly (no chunking).")
        self.task.total_chunks = 1
        self.task.current_chunk = 0
        self.chunk_progress.emit(self.task.id, 0, 1)

        tmp_dir = tempfile.mkdtemp(prefix="dfgui_")
        try:
            in_ext = Path(input_file).suffix.lower()
            tmp_out = os.path.join(tmp_dir, Path(input_file).stem + in_ext)

            cmd = [_DEEPFILTER_BIN, "--no-suffix", "-o", tmp_dir]
            cmd += self.task.to_deepfilter_args()
            cmd.append(input_file)
            rc = self._run_subprocess(cmd)

            if self._stopped:
                return True, ""  # stopped intentionally
            if rc != 0:
                return False, f"deepFilter exited with code {rc}"

            self.task.current_chunk = 1
            self.chunk_progress.emit(self.task.id, 1, 1)

            if self.task.output_format != "Same as input" and Path(tmp_out).suffix.lower() != Path(out_path).suffix.lower():
                self._log(f"Converting to {self.task.output_format}...")
                self._convert_format(tmp_out, out_path)
            else:
                shutil.move(tmp_out, out_path)

            self._log(f"Done! Saved to: {out_path}")
            return True, ""
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _process_chunked(self, input_file: str, out_path: str, in_ext: str, chunk_size: int):
        """Split → filter each chunk → merge → (convert). Returns (ok, msg)."""
        tmp_dir = tempfile.mkdtemp(prefix="dfgui_")
        try:
            chunk_in_dir = os.path.join(tmp_dir, "input")
            chunk_out_dir = os.path.join(tmp_dir, "enhanced")
            os.makedirs(chunk_in_dir)
            os.makedirs(chunk_out_dir)

            # 1. Split
            self._log(f"Step 1/3 — Splitting into {chunk_size}-second segments...")
            split_cmd = [
                _FFMPEG, "-i", input_file,
                "-f", "segment",
                "-segment_time", str(chunk_size),
                "-c", "copy",
                os.path.join(chunk_in_dir, f"chunk_%03d{in_ext}"),
            ]
            rc = self._run_subprocess(split_cmd)
            if self._stopped:
                return True, ""
            if rc != 0:
                return False, f"ffmpeg split failed (exit {rc})"

            chunks = sorted(glob.glob(os.path.join(chunk_in_dir, f"chunk_*{in_ext}")))
            if not chunks:
                msg = "No segments were created by ffmpeg split."
                self._log(f"[Error] {msg}")
                return False, msg

            total = len(chunks)
            self.task.total_chunks = total
            self._log(f"Step 2/3 — Processing {total} segments sequentially...")

            # 2. Filter each chunk one by one
            for i, chunk_path in enumerate(chunks):
                if self._stopped:
                    return True, ""
                self.task.current_chunk = i
                self.chunk_progress.emit(self.task.id, i + 1, total)
                self._log(f"  [{i + 1}/{total}] {os.path.basename(chunk_path)}")

                rc = self._run_deepfilter_chunk(chunk_path, chunk_out_dir)
                if self._stopped:
                    return True, ""
                if rc != 0:
                    msg = f"deepFilter failed on chunk {i + 1}/{total} (exit {rc})"
                    self._log(f"[Error] {msg}")
                    return False, msg

            self.task.current_chunk = total
            self.chunk_progress.emit(self.task.id, total, total)

            # 3. Merge
            self._log("Step 3/3 — Merging processed segments...")
            concat_txt = os.path.join(tmp_dir, "concat.txt")
            enhanced_chunks = sorted(
                glob.glob(os.path.join(chunk_out_dir, f"chunk_*{in_ext}"))
            )
            with open(concat_txt, "w") as f:
                for c in enhanced_chunks:
                    f.write(f"file '{os.path.abspath(c)}'\n")

            need_convert = (
                self.task.output_format != "Same as input"
                and Path(out_path).suffix.lower() != in_ext
            )
            merge_target = out_path
            if need_convert:
                merge_target = os.path.join(tmp_dir, f"merged{in_ext}")

            merge_cmd = [
                _FFMPEG, "-hide_banner", "-v", "error", "-stats",
                "-f", "concat", "-safe", "0",
                "-i", concat_txt,
                merge_target,
            ]
            rc = self._run_subprocess(merge_cmd)
            if self._stopped:
                return True, ""
            if rc != 0:
                msg = f"ffmpeg merge failed (exit {rc})"
                self._log(f"[Error] {msg}")
                return False, msg

            if need_convert:
                self._log(f"Converting to {self.task.output_format}...")
                self._convert_format(merge_target, out_path)

            self._log(f"\nAll done! Saved to: {out_path}")
            return True, ""
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
