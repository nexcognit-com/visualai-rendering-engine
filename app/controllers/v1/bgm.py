"""Bundled BGM track enumeration (spec 010).

Distinct from upstream MPT's ``/api/v1/musics`` endpoint — this one is
enriched with ``duration_seconds`` per track so the wizard can show
"track is shorter / longer than your video" hints. Reads
``resource/songs/`` at request time; small library (~30 files) makes
caching unnecessary at v1.
"""

from __future__ import annotations

import glob
import os
from pathlib import Path
from typing import Any

from fastapi import Depends, HTTPException, Request
from loguru import logger

from app.controllers.v1.base import new_router
from app.controllers.v1.uploads import _probe_audio_duration
from app.middleware.jwt_auth import jwt_required
from app.utils import utils

router = new_router()


@router.get(
    "/bgm/tracks",
    summary="List bundled BGM tracks with duration metadata (spec 010)",
)
def list_bgm_tracks(
    request: Request,
    _: dict = Depends(jwt_required),
) -> dict[str, Any]:
    song_dir = utils.song_dir()
    if not os.path.isdir(song_dir):
        raise HTTPException(
            status_code=500,
            detail={
                "detail": "BGM library unavailable.",
                "error_code": "library_missing",
            },
        )

    # Enumerate all bundled audio files (mp3/wav/ogg/m4a). Sort alphabetically
    # for deterministic dropdown order across requests.
    extensions = ("mp3", "wav", "ogg", "m4a")
    files: list[str] = []
    for ext in extensions:
        files.extend(glob.glob(os.path.join(song_dir, f"*.{ext}")))
    files.sort(key=lambda p: os.path.basename(p).lower())

    tracks = []
    for f in files:
        rel_path = os.path.relpath(f, utils.root_dir())
        name = Path(f).stem  # filename without extension — UI label
        duration = _probe_audio_duration(f)
        tracks.append(
            {
                "name": name,
                "path": rel_path,
                "duration_seconds": round(duration, 2) if duration else 0.0,
            }
        )

    logger.info(f"bgm/tracks: {len(tracks)} bundled tracks enumerated")
    return {"tracks": tracks, "count": len(tracks)}
