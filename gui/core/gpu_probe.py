"""
GPU VRAM probe — determines the optimal chunk size for DeepFilterNet
based on available GPU memory.

Uses total VRAM (not free) with a conservative lookup table to avoid OOM.
Empirical calibration:
  - GTX 1650 Ti (4 GB)  → max reliable ~165 s → table gives 90 s (safe margin)
  - RTX 3060 (12 GB)    → ~300 s
"""
from __future__ import annotations

import sys
from typing import Tuple
from pathlib import Path

# (total_vram_MB_upper_bound, chunk_seconds)
# Chosen conservatively so the auto value leaves headroom below the real limit.
_VRAM_CHUNK_TABLE = [
    (1024,        20),   # ≤ 1 GB  → 20 s
    (2048,        30),   # ≤ 2 GB  → 30 s
    (4096,        90),   # ≤ 4 GB  → 90 s  (GTX 1650 / 1650 Ti)
    (6144,       120),   # ≤ 6 GB  → 120 s (RTX 2060 / GTX 1660 Ti)
    (8192,       180),   # ≤ 8 GB  → 180 s (RTX 3070)
    (12288,      240),   # ≤ 12 GB → 240 s (RTX 3080 10 GB, 3060)
    (float("inf"), 300), # > 12 GB → 300 s
]


def get_gpu_info() -> Tuple[int, int]:
    """
    Returns (free_bytes, total_bytes) for the first CUDA device.
    Returns (0, 0) if CUDA is unavailable.
    """
    from gui.core.dependency_manager import get_python_bin
    python_bin = get_python_bin()
    if not Path(python_bin).exists():
        return 0, 0

    script = (
        "import torch;"
        "print(f'{torch.cuda.mem_get_info(0)[0]},{torch.cuda.mem_get_info(0)[1]}') "
        "if torch.cuda.is_available() else print('0,0')"
    )
    try:
        import subprocess
        res = subprocess.run(
            [python_bin, "-c", script],
            capture_output=True, text=True, timeout=3
        )
        if res.returncode == 0:
            free_str, total_str = res.stdout.strip().split(",")
            return int(free_str), int(total_str)
    except Exception:
        pass
    return 0, 0


def get_auto_chunk_size() -> int:
    """
    Return conservative chunk size in seconds based on GPU total VRAM.
    Falls back to 120 s (CPU / no GPU detected).
    """
    _, total_bytes = get_gpu_info()

    if total_bytes == 0:
        return 120  # CPU fallback

    total_mb = total_bytes / (1024 * 1024)

    for vram_limit_mb, chunk_s in _VRAM_CHUNK_TABLE:
        if total_mb <= vram_limit_mb:
            return chunk_s

    return 300  # should not reach here


def get_gpu_description() -> str:
    """Human-readable GPU description for display in the UI."""
    from gui.core.dependency_manager import get_python_bin
    python_bin = get_python_bin()
    if not Path(python_bin).exists():
        return "Python environment unavailable"

    script = (
        "import torch;"
        "print(f'{torch.cuda.get_device_name(0)}|{torch.cuda.mem_get_info(0)[0]}|{torch.cuda.mem_get_info(0)[1]}') "
        "if torch.cuda.is_available() else print('CPU')"
    )
    try:
        import subprocess
        res = subprocess.run(
            [python_bin, "-c", script],
            capture_output=True, text=True, timeout=3
        )
        if res.returncode == 0:
            out = res.stdout.strip()
            if out == "CPU":
                return "No GPU detected — CPU mode (auto chunk: 120 s)"
            
            name, free_str, total_str = out.split("|")
            free_mb = int(free_str) / (1024 * 1024)
            total_mb = int(total_str) / (1024 * 1024)
            chunk = get_auto_chunk_size()
            return (
                f"{name}  |  {free_mb:.0f} MB free / {total_mb:.0f} MB total"
                f"  →  auto chunk: {chunk} s"
            )
    except Exception:
        pass
    return "GPU info unavailable"


if __name__ == "__main__":
    print(get_gpu_description())
    print(f"Auto chunk size: {get_auto_chunk_size()} s")
