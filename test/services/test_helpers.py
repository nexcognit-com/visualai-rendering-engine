"""Shared test fixture helpers for VisualAI feature smoke tests.

Created by spec 010 (music-control); spec 009 (brand-overlays) extends with
visual-overlay helpers when it ships. Everything in this file MUST be:

- Synthetic-only (no committed binary fixtures).
- Fast — keep generation under 1 s of wall clock per fixture.
- Deterministic for a given input — same args produce identical bytes.
"""

from __future__ import annotations

import math
import struct
import subprocess
from pathlib import Path


def make_synthetic_audio(
    path: str | Path,
    duration_s: float = 1.0,
    format: str = "wav",
    frequency_hz: float = 440.0,
    sample_rate: int = 44100,
) -> str:
    """Generate a synthetic sine-wave audio file.

    Args:
        path: output filepath. Extension MUST match ``format`` (e.g. ``foo.wav``
            with ``format="wav"``); the caller is responsible for matching.
        duration_s: track length in seconds. Default 1.0.
        format: one of ``"wav"`` (native), ``"mp3"``, ``"ogg"``, ``"m4a"``.
            Non-WAV formats convert via ``ffmpeg`` (which is a hard system
            requirement per the constitution).
        frequency_hz: tone frequency. Default 440 Hz (A4).
        sample_rate: PCM sample rate. Default 44100.

    Returns:
        Absolute path to the produced audio file.

    Raises:
        RuntimeError: if ``ffmpeg`` is required (non-WAV) but not on PATH.
    """
    out = Path(path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    # Always start by writing a WAV — it's the simplest format we can produce
    # without external tooling.
    if format == "wav":
        wav_path = out
    else:
        wav_path = out.with_suffix(".wav")

    _write_sine_wav(wav_path, duration_s, frequency_hz, sample_rate)

    if format == "wav":
        return str(out)

    # Convert via ffmpeg for non-WAV formats.
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",  # overwrite without prompting
                "-i",
                str(wav_path),
                "-loglevel",
                "error",
                str(out),
            ],
            check=True,
            capture_output=True,
            timeout=10,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise RuntimeError(
            f"ffmpeg conversion to {format} failed: {exc}"
        ) from exc
    finally:
        # Remove the intermediate WAV; only the requested format remains.
        if wav_path != out and wav_path.exists():
            wav_path.unlink()

    return str(out)


def _write_sine_wav(
    path: Path,
    duration_s: float,
    frequency_hz: float,
    sample_rate: int,
) -> None:
    """Write a 16-bit mono PCM WAV containing a sine tone."""
    n_samples = int(duration_s * sample_rate)
    amplitude = 0.5  # half-scale to avoid clipping on conversion

    # PCM samples — int16, mono.
    samples = bytearray()
    for i in range(n_samples):
        t = i / sample_rate
        value = int(amplitude * 32767 * math.sin(2 * math.pi * frequency_hz * t))
        samples.extend(struct.pack("<h", value))

    # WAV header (44 bytes).
    byte_rate = sample_rate * 2  # 16-bit mono
    data_size = len(samples)
    riff_size = 36 + data_size

    with path.open("wb") as f:
        # RIFF chunk
        f.write(b"RIFF")
        f.write(struct.pack("<I", riff_size))
        f.write(b"WAVE")
        # fmt chunk
        f.write(b"fmt ")
        f.write(struct.pack("<I", 16))  # subchunk1 size
        f.write(struct.pack("<H", 1))  # PCM
        f.write(struct.pack("<H", 1))  # mono
        f.write(struct.pack("<I", sample_rate))
        f.write(struct.pack("<I", byte_rate))
        f.write(struct.pack("<H", 2))  # block align (1 channel * 2 bytes)
        f.write(struct.pack("<H", 16))  # bits per sample
        # data chunk
        f.write(b"data")
        f.write(struct.pack("<I", data_size))
        f.write(samples)
