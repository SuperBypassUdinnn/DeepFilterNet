"""
SettingsPanel — model selector, chunk size, and CLI options.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QGroupBox, QHBoxLayout, QLabel,
    QSlider, QSpinBox, QVBoxLayout, QWidget,
)

from gui.core.gpu_probe import get_auto_chunk_size, get_gpu_description
from gui.core.task import CHUNK_PRESETS, PRETRAINED_MODELS, DEFAULT_MODEL


class SettingsPanel(QWidget):
    settings_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # ── Model ─────────────────────────────────────────────────────
        model_group = QGroupBox("Model")
        model_layout = QVBoxLayout(model_group)

        self._model_combo = QComboBox()
        self._model_combo.addItems(PRETRAINED_MODELS)
        self._model_combo.setCurrentText(DEFAULT_MODEL)
        self._model_combo.setToolTip("Pretrained DeepFilterNet model to use")
        self._model_combo.currentTextChanged.connect(self.settings_changed)
        model_layout.addWidget(self._model_combo)

        layout.addWidget(model_group)

        # ── Chunk size ────────────────────────────────────────────────
        chunk_group = QGroupBox("Chunk Size (long-file splitting)")
        chunk_layout = QVBoxLayout(chunk_group)

        self._chunk_combo = QComboBox()
        for label in CHUNK_PRESETS:
            self._chunk_combo.addItem(label)
        self._chunk_combo.setCurrentText("Auto")
        self._chunk_combo.setToolTip(
            "Audio is split into chunks before processing to avoid GPU OOM.\n"
            "'Auto' probes available VRAM to pick the best size."
        )
        self._chunk_combo.currentTextChanged.connect(self._on_chunk_preset_changed)
        chunk_layout.addWidget(self._chunk_combo)

        # Custom spinbox (hidden unless 'Custom' is selected)
        custom_row = QHBoxLayout()
        self._custom_label = QLabel("Custom (seconds):")
        self._custom_spin = QSpinBox()
        self._custom_spin.setRange(10, 600)
        self._custom_spin.setValue(120)
        self._custom_spin.setSuffix(" s")
        self._custom_spin.valueChanged.connect(self.settings_changed)
        custom_row.addWidget(self._custom_label)
        custom_row.addWidget(self._custom_spin)
        custom_row.addStretch()
        self._custom_label.setVisible(False)
        self._custom_spin.setVisible(False)
        chunk_layout.addLayout(custom_row)

        # GPU info label
        self._gpu_label = QLabel(get_gpu_description())
        self._gpu_label.setObjectName("gpu_info")
        self._gpu_label.setWordWrap(True)
        chunk_layout.addWidget(self._gpu_label)

        layout.addWidget(chunk_group)

        # ── Processing options ─────────────────────────────────────────
        opts_group = QGroupBox("Processing Options")
        opts_layout = QVBoxLayout(opts_group)

        # Attenuation limit
        atten_row = QHBoxLayout()
        self._atten_check = QCheckBox("Attenuation Limit")
        self._atten_check.setToolTip(
            "Limit noise attenuation by mixing enhanced signal with original.\n"
            "Lower values = more natural sound, less aggressive filtering."
        )
        self._atten_spin = QSpinBox()
        self._atten_spin.setRange(0, 100)
        self._atten_spin.setValue(30)
        self._atten_spin.setSuffix(" dB")
        self._atten_spin.setEnabled(False)
        self._atten_spin.setFixedWidth(80)
        self._atten_check.toggled.connect(self._atten_spin.setEnabled)
        self._atten_check.toggled.connect(self.settings_changed)
        self._atten_spin.valueChanged.connect(self.settings_changed)
        atten_row.addWidget(self._atten_check)
        atten_row.addStretch()
        atten_row.addWidget(self._atten_spin)
        opts_layout.addLayout(atten_row)

        # Post-filter
        self._pf_check = QCheckBox("Post-filter (--pf)")
        self._pf_check.setToolTip(
            "Apply a post-filter that slightly over-attenuates very noisy sections.\n"
            "Can improve speech clarity in very noisy recordings."
        )
        self._pf_check.toggled.connect(self.settings_changed)
        opts_layout.addWidget(self._pf_check)

        # No DF stage
        self._no_df_check = QCheckBox("No DF Stage (--no-df-stage)")
        self._no_df_check.setToolTip(
            "Disable the deep filtering stage. Uses only ERB features.\n"
            "Faster but lower quality."
        )
        self._no_df_check.toggled.connect(self.settings_changed)
        opts_layout.addWidget(self._no_df_check)

        # No delay compensation
        self._no_delay_check = QCheckBox("No Delay Compensation (--no-delay-compensation)")
        self._no_delay_check.setToolTip(
            "Don't add padding to compensate the real-time STFT/ISTFT delay.\n"
            "Use when processing offline (not real-time)."
        )
        self._no_delay_check.toggled.connect(self.settings_changed)
        opts_layout.addWidget(self._no_delay_check)

        layout.addWidget(opts_group)
        layout.addStretch()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_chunk_preset_changed(self, text: str):
        is_custom = text == "Custom"
        self._custom_label.setVisible(is_custom)
        self._custom_spin.setVisible(is_custom)
        self.settings_changed.emit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_model(self) -> str:
        return self._model_combo.currentText()

    def get_chunk_size(self) -> int:
        """Returns chunk size in seconds. 0 = auto."""
        preset = self._chunk_combo.currentText()
        if preset == "Custom":
            return self._custom_spin.value()
        return CHUNK_PRESETS.get(preset, 0)

    def get_atten_lim(self):
        if self._atten_check.isChecked():
            return self._atten_spin.value()
        return None

    def get_post_filter(self) -> bool:
        return self._pf_check.isChecked()

    def get_no_df_stage(self) -> bool:
        return self._no_df_check.isChecked()

    def get_no_delay_comp(self) -> bool:
        return self._no_delay_check.isChecked()

    def refresh_gpu_info(self):
        self._gpu_label.setText(get_gpu_description())
