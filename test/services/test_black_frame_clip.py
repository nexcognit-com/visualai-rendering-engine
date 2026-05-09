"""Spec 019 — _write_black_frame_clip ffmpeg integration test.

Single integration test that actually invokes ffmpeg. Verifies the
placeholder produced by ``app.services.material._write_black_frame_clip``
matches FR-004's operational contract:
    - codec: h264
    - pixel format: yuv420p
    - duration: target ± 0.05s
    - no audio stream
    - resolution 1280x720 @ 30fps (per data-model.md §BlackFramePlaceholderClip)

This test is skipped if ffmpeg + ffprobe are not on PATH.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.services import material


def _ffprobe_streams(path: str) -> list[dict]:
    """Return the list of stream dicts ffprobe sees in `path`."""
    out = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-print_format", "json",
            "-show_streams",
            "-show_format",
            path,
        ],
        check=True, capture_output=True, text=True,
    )
    return json.loads(out.stdout)


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg / ffprobe not on PATH",
)
def test_write_black_frame_clip_produces_valid_mp4(tmp_path: Path) -> None:
    """FR-004 / data-model.md §BlackFramePlaceholderClip — real ffmpeg round-trip."""
    out_path = tmp_path / "placeholder.mp4"
    material._write_black_frame_clip(str(out_path), duration_seconds=3.5)

    assert out_path.exists(), "Placeholder file must be written"
    assert out_path.stat().st_size > 0, "Placeholder must not be empty"

    probe = _ffprobe_streams(str(out_path))
    streams = probe["streams"]

    # Exactly one stream (no audio, FR-004 "no audio track").
    assert len(streams) == 1, f"Expected 1 stream, got {len(streams)}: {streams}"
    video = streams[0]
    assert video["codec_type"] == "video"
    assert video["codec_name"] == "h264", f"FR-004 codec mismatch: {video.get('codec_name')}"
    assert video["pix_fmt"] == "yuv420p", f"FR-004 pix_fmt mismatch: {video.get('pix_fmt')}"
    assert int(video["width"]) == 1280
    assert int(video["height"]) == 720

    # Frame rate: ffprobe reports r_frame_rate as a fraction string ("30/1").
    num, den = video["r_frame_rate"].split("/")
    fps = int(num) / int(den)
    assert abs(fps - 30) < 0.5, f"Expected 30fps, got {fps}"

    # Duration: prefer format.duration (container-level) — FR-004 ±0.05s.
    duration = float(probe["format"]["duration"])
    assert abs(duration - 3.5) < 0.05, f"FR-004 duration mismatch: {duration} vs target 3.5"
