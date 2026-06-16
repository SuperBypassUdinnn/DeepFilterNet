"""
ProcessTask dataclass and TaskStatus enum.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional


class TaskStatus(Enum):
    PENDING = auto()
    RUNNING = auto()
    PAUSED = auto()
    DONE = auto()
    ERROR = auto()
    STOPPED = auto()


# Audio extensions recognised by deepFilter / soundfile
AUDIO_EXTENSIONS = {
    ".flac", ".wav", ".mp3", ".ogg", ".opus",
    ".m4a", ".aac", ".wma", ".aiff", ".aif",
}

# Output format options
OUTPUT_FORMATS = ["Same as input", "FLAC", "WAV", "MP3"]

PRETRAINED_MODELS = ["DeepFilterNet3", "DeepFilterNet2", "DeepFilterNet"]
DEFAULT_MODEL = "DeepFilterNet3"

# Chunk size presets (seconds). 0 = auto.
CHUNK_PRESETS = {
    "Auto": 0,
    "30 s": 30,
    "60 s": 60,
    "90 s": 90,
    "120 s": 120,
    "150 s": 150,
    "180 s": 180,
    "240 s": 240,
    "300 s": 300,
    "Custom": -1,  # sentinel — UI will show a spinbox
}

# Minimum audio duration (s) that triggers chunked processing
CHUNK_THRESHOLD_SECONDS = 120


@dataclass
class ProcessTask:
    """Represents a single queued processing job."""

    # Files to process
    input_files: List[str]

    # Output settings
    output_dir: str
    output_format: str = "Same as input"  # one of OUTPUT_FORMATS

    # Model & processing options
    model: str = DEFAULT_MODEL
    chunk_size: int = 0              # seconds; 0 = auto-detect from GPU
    atten_lim: Optional[int] = None  # dB; None = disabled
    post_filter: bool = False
    no_df_stage: bool = False
    no_delay_comp: bool = False

    # Runtime state (ID assigned by QueueManager as sequential int-string)
    id: str = field(default="")
    status: TaskStatus = field(default=TaskStatus.PENDING)
    error_message: str = ""

    # Progress tracking (updated at runtime by worker)
    current_file_index: int = 0
    current_chunk: int = 0
    total_chunks: int = 0

    @property
    def display_name(self) -> str:
        """Human-readable summary for queue table."""
        n = len(self.input_files)
        if n == 1:
            import os
            return os.path.basename(self.input_files[0])
        return f"{n} files"

    def to_deepfilter_args(self) -> List[str]:
        """Build CLI argument list for the real deepFilter binary."""
        args: List[str] = []
        args += ["--model-base-dir", self.model]
        if self.atten_lim is not None:
            args += ["--atten-lim", str(self.atten_lim)]
        if self.post_filter:
            args.append("--pf")
        if self.no_df_stage:
            args.append("--no-df-stage")
        if self.no_delay_comp:
            args.append("--no-delay-compensation")
        return args
