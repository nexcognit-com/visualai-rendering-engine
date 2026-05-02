"""Smoke tests for GET /api/v1/bgm/tracks (spec 010, MC-8)."""

from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.asgi import get_application
from app.utils import utils

client = TestClient(get_application())


def test_mc8_bgm_tracks_enumeration() -> None:
    """MC-8: endpoint returns the correct shape + sorted track list."""
    response = client.get("/api/v1/bgm/tracks")
    assert response.status_code == 200

    data = response.json()
    assert "tracks" in data
    assert "count" in data
    assert isinstance(data["tracks"], list)
    assert isinstance(data["count"], int)

    # Count matches the actual song dir contents (filtered by allowed extensions).
    song_dir = utils.song_dir()
    expected = [
        f for f in os.listdir(song_dir)
        if f.lower().endswith((".mp3", ".wav", ".ogg", ".m4a"))
    ]
    assert data["count"] == len(expected)
    assert len(data["tracks"]) == data["count"]


def test_mc8_tracks_have_required_fields() -> None:
    """Each track entry MUST have name + path + duration_seconds."""
    response = client.get("/api/v1/bgm/tracks")
    assert response.status_code == 200

    tracks = response.json()["tracks"]
    if not tracks:
        return  # empty bundled set is acceptable; rest is vacuous

    for t in tracks:
        assert isinstance(t["name"], str) and t["name"]
        assert t["path"].startswith("resource/songs/")
        assert isinstance(t["duration_seconds"], (int, float))
        assert t["duration_seconds"] >= 0  # 0 is allowed (probe failure)


def test_mc8_tracks_sorted_alphabetically() -> None:
    """Determinism: alphabetical sort by name."""
    response = client.get("/api/v1/bgm/tracks")
    tracks = response.json()["tracks"]
    if len(tracks) <= 1:
        return

    names = [t["name"] for t in tracks]
    assert names == sorted(names, key=str.lower), \
        "tracks MUST be sorted alphabetically by name"
