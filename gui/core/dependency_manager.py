"""
dependency_manager.py — Manages the DeepFilterNet runtime environment.

The runtime (torch + torchaudio + deepfilterlib + soundfile + deepFilter CLI)
is installed on first launch into a managed virtualenv at:
  Linux/macOS : ~/.local/share/deepfilternet/runtime/
  Windows     : %APPDATA%\\deepfilternet\\runtime\\

This keeps the GUI binary small (~100 MB) while the heavy ML deps are
downloaded once and reused across updates.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, List, Optional, Tuple


# ── Runtime location ──────────────────────────────────────────────────────────

def _runtime_base() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "deepfilternet" / "runtime"


RUNTIME_DIR = _runtime_base()
_IS_WIN = sys.platform == "win32"
_BIN = RUNTIME_DIR / ("Scripts" if _IS_WIN else "bin")
_RUNTIME_PYTHON    = _BIN / ("python.exe" if _IS_WIN else "python")
_RUNTIME_PIP       = _BIN / ("pip.exe"    if _IS_WIN else "pip")
_RUNTIME_DEEPFILTER = _BIN / ("deepFilter.exe" if _IS_WIN else "deepFilter")

# Minimum package versions to consider the runtime valid
_REQUIRED_PACKAGES = ["torch", "torchaudio", "deepfilterlib", "soundfile"]


# ── Public API ────────────────────────────────────────────────────────────────

def is_runtime_installed() -> bool:
    """Return True if the runtime is installed, or if we are running from source."""
    if getattr(sys, 'frozen', False):
        return _RUNTIME_DEEPFILTER.exists() and _RUNTIME_PYTHON.exists()
    else:
        # Running from source, we assume the active venv has everything
        return True


def get_python_bin() -> str:
    """Return the python executable to use for subprocesses."""
    if getattr(sys, 'frozen', False):
        return str(_RUNTIME_PYTHON)
    return sys.executable


def get_deepfilter_bin() -> str:
    """Return the path to the deepFilter binary to use as subprocess."""
    if getattr(sys, 'frozen', False):
        return str(_RUNTIME_DEEPFILTER)
    
    # Priority when running from source:
    candidates = [
        Path(sys.executable).parent / ("deepFilter.exe" if _IS_WIN else "deepFilter"),
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return shutil.which("deepFilter") or "deepFilter"


def detect_cuda() -> Optional[str]:
    """
    Probe nvidia-smi to detect installed CUDA version.
    Returns PyTorch CUDA wheel tag (e.g. "cu121"), or None for CPU-only.
    """
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None

        # Probe CUDA version from nvidia-smi output
        ver_result = subprocess.run(
            ["nvidia-smi"],
            capture_output=True, text=True, timeout=5,
        )
        output = ver_result.stdout
        # Look for "CUDA Version: X.Y"
        for line in output.splitlines():
            if "CUDA Version:" in line:
                parts = line.split("CUDA Version:")
                if len(parts) > 1:
                    ver_str = parts[1].strip().split()[0]  # e.g. "12.1"
                    major, minor = ver_str.split(".")[:2]
                    cuda_tag = f"cu{major}{minor}"
                    # Map to supported PyTorch CUDA tags
                    supported = {"cu118": "cu118", "cu121": "cu121", "cu124": "cu124"}
                    # Use the highest supported tag <= detected
                    tag = None
                    for t in sorted(supported.keys()):
                        if cuda_tag >= t:
                            tag = supported[t]
                    return tag
        return None
    except Exception:
        return None


def _torch_install_args(cuda_tag: Optional[str]) -> List[str]:
    """Return pip install args for torch based on CUDA availability."""
    pkgs = ["torch", "torchaudio"]
    if cuda_tag:
        index_url = f"https://download.pytorch.org/whl/{cuda_tag}"
        return pkgs + ["--index-url", index_url]
    else:
        # CPU-only (smaller download, ~200 MB vs ~2 GB)
        return pkgs + ["--index-url", "https://download.pytorch.org/whl/cpu"]


def install_runtime(
    log_cb: Callable[[str], None],
    progress_cb: Callable[[int, int, str], None],   # (current, total, label)
    cancelled: Callable[[], bool],
) -> Tuple[bool, str]:
    """
    Create the runtime virtualenv and install all dependencies.

    Args:
        log_cb        : called with each log line
        progress_cb   : called with (current_step, total_steps, step_label)
        cancelled     : called to check if user requested cancellation

    Returns:
        (success: bool, error_message: str)
    """
    log_cb(f"Runtime location: {RUNTIME_DIR}")

    cuda_tag = detect_cuda()
    if cuda_tag:
        log_cb(f"CUDA detected: {cuda_tag} — installing GPU-accelerated torch")
    else:
        log_cb("No CUDA GPU detected — installing CPU-only torch")

    steps = [
        ("Creating virtual environment",  _step_create_venv),
        ("Upgrading pip",                 _step_upgrade_pip),
        ("Installing torch + torchaudio", lambda l, c: _step_install_torch(l, c, cuda_tag)),
        ("Installing deepfilterlib",      _step_install_deepfilter),
        ("Installing soundfile",          _step_install_soundfile),
        ("Verifying installation",        _step_verify),
    ]
    total = len(steps)

    for i, (label, fn) in enumerate(steps):
        if cancelled():
            return False, "Installation cancelled by user."
        progress_cb(i, total, label)
        log_cb(f"\n[{i+1}/{total}] {label}...")
        ok, msg = fn(log_cb, cancelled)
        if not ok:
            return False, msg

    progress_cb(total, total, "Done!")
    log_cb("\n✓ Runtime installed successfully.")
    return True, ""


def uninstall_runtime() -> Tuple[bool, str]:
    """Remove the managed runtime directory."""
    try:
        if RUNTIME_DIR.exists():
            shutil.rmtree(RUNTIME_DIR)
        return True, ""
    except Exception as e:
        return False, str(e)


def runtime_size_mb() -> float:
    """Return approximate size of the runtime directory in MB."""
    total = 0
    if RUNTIME_DIR.exists():
        for f in RUNTIME_DIR.rglob("*"):
            try:
                total += f.stat().st_size
            except OSError:
                pass
    return total / (1024 * 1024)


# ── Installation steps ────────────────────────────────────────────────────────

def _run_cmd(
    cmd: List[str],
    log_cb: Callable[[str], None],
    cancelled: Callable[[], bool],
) -> Tuple[bool, str]:
    """Run a command, streaming output to log_cb. Returns (ok, error)."""
    log_cb(f"  $ {' '.join(str(c) for c in cmd)}")
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        for line in proc.stdout:  # type: ignore[union-attr]
            line = line.rstrip()
            if line:
                log_cb(f"  {line}")
            if cancelled():
                proc.kill()
                return False, "Cancelled"
        proc.wait()
        if proc.returncode != 0:
            return False, f"Command failed with exit code {proc.returncode}"
        return True, ""
    except Exception as e:
        return False, str(e)


def _step_create_venv(log_cb, cancelled):
    if RUNTIME_DIR.exists():
        log_cb("  Runtime dir already exists — skipping venv creation.")
        return True, ""
    RUNTIME_DIR.parent.mkdir(parents=True, exist_ok=True)
    return _run_cmd([sys.executable, "-m", "venv", str(RUNTIME_DIR)], log_cb, cancelled)


def _step_upgrade_pip(log_cb, cancelled):
    return _run_cmd(
        [str(_RUNTIME_PIP), "install", "--upgrade", "pip", "wheel", "setuptools"],
        log_cb, cancelled,
    )


def _step_install_torch(log_cb, cancelled, cuda_tag):
    args = _torch_install_args(cuda_tag)
    return _run_cmd([str(_RUNTIME_PIP), "install"] + args, log_cb, cancelled)


def _step_install_deepfilter(log_cb, cancelled):
    return _run_cmd(
        [str(_RUNTIME_PIP), "install", "deepfilterlib", "deepfilter"],
        log_cb, cancelled,
    )


def _step_install_soundfile(log_cb, cancelled):
    return _run_cmd(
        [str(_RUNTIME_PIP), "install", "soundfile"],
        log_cb, cancelled,
    )


def _step_verify(log_cb, cancelled):
    if not _RUNTIME_DEEPFILTER.exists():
        return False, f"deepFilter binary not found at {_RUNTIME_DEEPFILTER}"
    log_cb(f"  deepFilter binary: {_RUNTIME_DEEPFILTER} ✓")
    ok, msg = _run_cmd(
        [str(_RUNTIME_PYTHON), "-c", "import torch; print('torch', torch.__version__)"],
        log_cb, cancelled,
    )
    return ok, msg
