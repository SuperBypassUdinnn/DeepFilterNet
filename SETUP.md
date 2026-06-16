# DeepFilterNet — Development Setup Guide

Panduan ini menjelaskan cara menyiapkan environment untuk menjalankan dan mengembangkan project ini dari source.

---

## Prasyarat Sistem

| Kebutuhan | Versi | Catatan |
|-----------|-------|---------|
| **Python** | 3.10 – 3.12 | Disarankan 3.11 |
| **Rust + Cargo** | ≥ 1.70 | Untuk build `libDF` (Rust crate) |
| **CUDA Toolkit** | 12.x (opsional) | Untuk akselerasi GPU |
| **ffmpeg** | ≥ 4.x | Untuk CLI wrapper `deepFilter` |
| **pip** | ≥ 23 | `pip install --upgrade pip` |

---

## Langkah Persiapan

### 1. Buat Virtual Environment

```bash
cd /path/to/DeepFilterNet
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# atau
.venv\Scripts\activate           # Windows
```

### 2. Upgrade pip & Install maturin

`maturin` dibutuhkan untuk membangun `DeepFilterLib` (wrapper Rust → Python):

```bash
pip install --upgrade pip
pip install "maturin>=1.3,<1.5"
```

### 3. Install PyTorch (dengan CUDA)

```bash
# CUDA 13 (sesuai lingkungan saat ini)
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128

# CPU only
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
```

> ⚠️ Versi `torch` dan `torchaudio` harus kompatibel satu sama lain.

### 4. Build & Install DeepFilterLib (Rust crate)

```bash
cd pyDF
pip install -e .        # build otomatis via maturin
cd ..
```

### 5. Install DeepFilterNet (Python package)

```bash
cd DeepFilterNet
pip install -e ".[soundfile]"    # termasuk soundfile sebagai loader utama
cd ..
```

### 6. Verifikasi Instalasi

```bash
python -c "from df.enhance import init_df; print('OK')"
deepFilter --version
```

---

## Menjalankan deepFilter dari CLI

```bash
deepFilter input.flac
deepFilter input.flac -o output/ --pf
deepFilter input.flac --atten-lim 30
```

---

## Patch yang Diterapkan (Kompatibilitas)

File yang telah dimodifikasi: `DeepFilterNet/df/io.py`

| Masalah | Solusi |
|---------|--------|
| `torchaudio.backend.common.AudioMetaData` dihapus di torchaudio ≥ 2.9 | Diganti dengan fallback berlapis: coba `torchaudio.AudioMetaData` → `torchaudio.backend.common.AudioMetaData` → dataclass buatan sendiri |
| `torchaudio.save` di versi baru hanya menerima float32 | Konversi dtype otomatis sebelum menyimpan |
| Format audio tertentu (FLAC, OGG) gagal dibaca oleh torchaudio | `soundfile` dijadikan loader utama, torchaudio sebagai fallback |
| Konstanta resample method berbeda antar versi torchaudio | Konstanta dipilih secara dinamis saat runtime |

---

## Build Wheel untuk Distribusi

Untuk membuat file `.whl` yang bisa diinstal tanpa kompilasi:

```bash
# Build libDF wheel
cd pyDF
maturin build --release
# Output: target/wheels/DeepFilterLib-*.whl

# Build DeepFilterNet wheel  
cd ../DeepFilterNet
pip install build
python -m build --wheel
# Output: dist/DeepFilterNet-*.whl
```

---

## Catatan Penting

- `soundfile` **wajib** diinstal agar format FLAC dan AAC bisa dibaca dengan benar
- `libDF` adalah Rust extension — butuh `rustc` dan `cargo` saat build, tapi tidak saat runtime (sudah compiled)
- Untuk pengembangan GUI, tambahkan dependensi sesuai framework yang dipilih (misal `PyQt6`)
