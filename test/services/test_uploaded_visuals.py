"""Material.py dispatch tests for spec 006 — MD-1..MD-10.

Covers the user_uploaded branch in download_videos, the Ken Burns helper,
audit-log writes, and per-clip duration math. MoviePy rendering is
mocked at _make_kenburns_clip so tests stay offline (~1s total).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from app.models.schema import VideoAspect
from app.services import material
from app.utils import utils


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def task_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    """Set up a synthetic repo root with storage/tasks + storage/uploads
    + a real script.json so audit-log writes don't blow up."""
    repo = tmp_path
    (repo / "storage" / "tasks").mkdir(parents=True)
    (repo / "storage" / "uploads").mkdir(parents=True)
    monkeypatch.chdir(repo)
    # Patch utils.task_dir + utils.storage_dir to point under tmp_path
    task_id = "test-task-006"
    task_dir = repo / "storage" / "tasks" / task_id
    task_dir.mkdir()
    (task_dir / "script.json").write_text(json.dumps({
        "params": {}, "script": "test", "terms": ["a", "b"]
    }))
    monkeypatch.setattr(utils, "task_dir", lambda tid, create=False: str(
        repo / "storage" / "tasks" / tid
    ))
    return {"repo": repo, "task_id": task_id, "task_dir": task_dir}


def _write_sidecar(task_dir: Path, **kwargs) -> Path:
    p = task_dir / "visuals.json"
    p.write_text(json.dumps(kwargs))
    return p


def _make_image_file(path: Path) -> Path:
    """Create a small JPEG so SHA-256 has real bytes to hash."""
    from io import BytesIO

    from PIL import Image
    img = Image.new("RGB", (100, 178), color="red")  # 9:16 ratio for sanity
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=88)
    path.write_bytes(buf.getvalue())
    return path


def _stub_kenburns(image_path: str, duration: float, output_path: str, seed: int) -> None:
    """Replacement for _make_kenburns_clip: writes a placeholder bytes."""
    Path(output_path).write_bytes(b"FAKE_MP4_BYTES")


# ---------------------------------------------------------------------------
# MD-1..MD-3 — sidecar dispatch
# ---------------------------------------------------------------------------


def test_md1_sidecar_absent_legacy_path(task_env, monkeypatch) -> None:
    """MD-1: no visuals.json → legacy Pexels path runs."""
    legacy_called = {"hit": False}

    def fake_pexels(*a, **kw):
        legacy_called["hit"] = True
        return []

    monkeypatch.setattr(material, "search_videos_pexels", fake_pexels)
    # Also stub save_video so we don't actually download.
    monkeypatch.setattr(material, "save_video", lambda **kw: "")

    paths = material.download_videos(
        task_id=task_env["task_id"],
        search_terms=["sunrise"],
        source="pexels",
        audio_duration=30.0,
    )
    assert legacy_called["hit"] is True
    assert paths == []


def test_md2_sidecar_auto_still_legacy(task_env, monkeypatch) -> None:
    """MD-2: visuals.json with mode='auto' → legacy path (mode wins)."""
    _write_sidecar(task_env["task_dir"], visuals_mode="auto")
    legacy_called = {"hit": False}

    def fake_pexels(*a, **kw):
        legacy_called["hit"] = True
        return []

    monkeypatch.setattr(material, "search_videos_pexels", fake_pexels)
    monkeypatch.setattr(material, "save_video", lambda **kw: "")
    material.download_videos(
        task_id=task_env["task_id"],
        search_terms=["x"],
        source="pexels",
        audio_duration=30.0,
    )
    assert legacy_called["hit"] is True


def test_md3_user_uploaded_one_product(task_env, monkeypatch) -> None:
    """MD-3: sidecar with 1 product → 1 clip path returned + clip file exists."""
    p1 = _make_image_file(task_env["repo"] / "storage" / "uploads" / "p1.cropped.jpg")
    _write_sidecar(
        task_env["task_dir"],
        visuals_mode="user_uploaded",
        uploaded_model_path=None,
        uploaded_product_paths=[str(p1.relative_to(task_env["repo"]))],
    )
    monkeypatch.setattr(material, "_make_kenburns_clip", _stub_kenburns)

    paths = material.download_videos(
        task_id=task_env["task_id"],
        search_terms=["irrelevant"],
        source="pexels",
        audio_duration=30.0,
    )
    assert len(paths) == 1
    assert paths[0].endswith("uploaded-1.mp4")
    assert os.path.exists(paths[0])
    assert Path(paths[0]).read_bytes() == b"FAKE_MP4_BYTES"


# ---------------------------------------------------------------------------
# MD-5..MD-8 — duration math + seeding
# ---------------------------------------------------------------------------


def test_md5_empty_products_raises(task_env, monkeypatch) -> None:
    """MD-5: sidecar with user_uploaded but no product paths → ValueError."""
    _write_sidecar(
        task_env["task_dir"],
        visuals_mode="user_uploaded",
        uploaded_model_path=None,
        uploaded_product_paths=[],
    )
    monkeypatch.setattr(material, "_make_kenburns_clip", _stub_kenburns)
    with pytest.raises(ValueError, match="no_product_assets"):
        material.download_videos(
            task_id=task_env["task_id"],
            search_terms=[],
            source="pexels",
            audio_duration=10.0,
        )


def test_md6_per_clip_duration_30s_3products(task_env, monkeypatch) -> None:
    """MD-6: 30s audio, 3 product clips, no model → each clip is 10s."""
    paths = []
    for i in range(3):
        p = _make_image_file(task_env["repo"] / "storage" / "uploads" / f"p{i}.cropped.jpg")
        paths.append(str(p.relative_to(task_env["repo"])))
    _write_sidecar(
        task_env["task_dir"],
        visuals_mode="user_uploaded",
        uploaded_model_path=None,
        uploaded_product_paths=paths,
    )
    captured = []

    def capture(image_path, duration, output_path, seed):
        captured.append(duration)
        Path(output_path).write_bytes(b"FAKE")

    monkeypatch.setattr(material, "_make_kenburns_clip", capture)
    material.download_videos(
        task_id=task_env["task_id"],
        search_terms=[],
        source="pexels",
        audio_duration=30.0,
    )
    assert len(captured) == 3
    for d in captured:
        assert d == pytest.approx(10.0, rel=0.01)


def test_md7_short_audio_minimum_2s(task_env, monkeypatch) -> None:
    """MD-7: 4s audio, 3 product clips → each clip exactly 2s (FR-014 floor)."""
    paths = []
    for i in range(3):
        p = _make_image_file(task_env["repo"] / "storage" / "uploads" / f"p{i}.cropped.jpg")
        paths.append(str(p.relative_to(task_env["repo"])))
    _write_sidecar(
        task_env["task_dir"],
        visuals_mode="user_uploaded",
        uploaded_model_path=None,
        uploaded_product_paths=paths,
    )
    captured = []
    monkeypatch.setattr(
        material, "_make_kenburns_clip",
        lambda i, d, o, s: (captured.append(d), Path(o).write_bytes(b"X"))
    )
    material.download_videos(
        task_id=task_env["task_id"],
        search_terms=[],
        source="pexels",
        audio_duration=4.0,
    )
    for d in captured:
        assert d == pytest.approx(2.0, rel=0.01)


def test_md8_seeding_idempotent(task_env, monkeypatch) -> None:
    """MD-8: same image path → same seed (idempotent renders)."""
    s1 = material._compute_seed("storage/uploads/abc.cropped.jpg")
    s2 = material._compute_seed("storage/uploads/abc.cropped.jpg")
    s3 = material._compute_seed("storage/uploads/different.cropped.jpg")
    assert s1 == s2
    assert s1 != s3


# ---------------------------------------------------------------------------
# MD-9, MD-10 — audit log
# ---------------------------------------------------------------------------


def test_md9_audit_log_user_uploaded(task_env, monkeypatch) -> None:
    """MD-9: user_uploaded run writes asset_audit to script.json."""
    p1 = _make_image_file(task_env["repo"] / "storage" / "uploads" / "p1.cropped.jpg")
    p2 = _make_image_file(task_env["repo"] / "storage" / "uploads" / "p2.cropped.jpg")
    _write_sidecar(
        task_env["task_dir"],
        visuals_mode="user_uploaded",
        uploaded_model_path=None,
        uploaded_product_paths=[
            str(p1.relative_to(task_env["repo"])),
            str(p2.relative_to(task_env["repo"])),
        ],
    )
    monkeypatch.setattr(material, "_make_kenburns_clip", _stub_kenburns)
    material.download_videos(
        task_id=task_env["task_id"],
        search_terms=[],
        source="pexels",
        audio_duration=20.0,
    )
    audit = json.loads((task_env["task_dir"] / "script.json").read_text())["asset_audit"]
    assert audit["visuals_mode"] == "user_uploaded"
    assert audit["auto_pexels_used"] is False
    assert audit["pexels_clip_count"] == 0
    assert audit["model_asset"] is None
    assert len(audit["product_assets"]) == 2
    assert audit["product_assets"][0]["filename"] == "p1.cropped.jpg"
    assert audit["product_assets"][0]["content_hash"].startswith("sha256:")
    assert audit["product_assets"][0]["placement"] == "middle-1"
    assert audit["product_assets"][0]["screen_time_seconds"] == pytest.approx(10.0, rel=0.01)


def test_md4_bookend_with_model(task_env, monkeypatch) -> None:
    """MD-4 (US2): 1 model + 3 products → 5-clip ordered list [m, p1, p2, p3, m].

    The opening + closing model clip is the SAME mp4 file (deduplicated),
    so the returned list has 5 entries but only 4 unique paths.
    Audit log records placement="opening+closing" on the model_asset and
    screen_time_seconds equal to TWO segment durations (opening + closing).
    """
    model = _make_image_file(
        task_env["repo"] / "storage" / "uploads" / "model.cropped.jpg"
    )
    products = []
    for i in range(3):
        p = _make_image_file(task_env["repo"] / "storage" / "uploads" / f"p{i}.cropped.jpg")
        products.append(str(p.relative_to(task_env["repo"])))
    _write_sidecar(
        task_env["task_dir"],
        visuals_mode="user_uploaded",
        uploaded_model_path=str(model.relative_to(task_env["repo"])),
        uploaded_product_paths=products,
    )
    monkeypatch.setattr(material, "_make_kenburns_clip", _stub_kenburns)

    paths = material.download_videos(
        task_id=task_env["task_id"],
        search_terms=[],
        source="pexels",
        audio_duration=25.0,  # n_clips=5, per_clip=5s
    )
    assert len(paths) == 5
    # Bookend: first and last are the same model clip path.
    assert paths[0] == paths[-1]
    # Middle three are unique product clips.
    assert len({paths[1], paths[2], paths[3]}) == 3
    # All should end with `uploaded-N.mp4`.
    for p in paths:
        assert p.endswith(".mp4")

    # Audit log:
    audit = json.loads((task_env["task_dir"] / "script.json").read_text())["asset_audit"]
    assert audit["model_asset"] is not None
    assert audit["model_asset"]["placement"] == "opening+closing"
    # opening + closing → 2 × per_clip duration (5s each = 10s total).
    assert audit["model_asset"]["screen_time_seconds"] == pytest.approx(10.0, rel=0.01)
    assert len(audit["product_assets"]) == 3
    for i, entry in enumerate(audit["product_assets"], start=1):
        assert entry["placement"] == f"middle-{i}"


def test_md10_audit_log_auto_path(task_env, monkeypatch) -> None:
    """MD-10: auto path also writes audit (FR-021 — both modes)."""
    monkeypatch.setattr(
        material, "search_videos_pexels", lambda **kw: []  # no clips found
    )
    monkeypatch.setattr(material, "save_video", lambda **kw: "")
    material.download_videos(
        task_id=task_env["task_id"],
        search_terms=["x"],
        source="pexels",
        audio_duration=30.0,
    )
    audit = json.loads((task_env["task_dir"] / "script.json").read_text())["asset_audit"]
    assert audit["visuals_mode"] == "auto"
    assert audit["auto_pexels_used"] is True
    assert audit["pexels_clip_count"] == 0
    assert audit["model_asset"] is None
    assert audit["product_assets"] == []


# ---------------------------------------------------------------------------
# Phase 7 — hybrid mode (MD-11..MD-15)
# ---------------------------------------------------------------------------


class _FakeStockItem:
    """Minimal stand-in for material.MaterialInfo for tests."""
    def __init__(self, url: str, duration: int = 5, provider: str = "pexels"):
        self.url = url
        self.duration = duration
        self.provider = provider


def _stub_stock_search(material, monkeypatch, pexels_pool, pixabay_pool):
    """Patch Pexels + Pixabay search to deterministic per-query result lists."""
    def fake_pexels(search_term, **kw):
        items = pexels_pool.get(search_term, [])
        return [_FakeStockItem(u, provider="pexels") for u in items]

    def fake_pixabay(search_term, **kw):
        items = pixabay_pool.get(search_term, [])
        return [_FakeStockItem(u, provider="pixabay") for u in items]

    monkeypatch.setattr(material, "search_videos_pexels", fake_pexels)
    monkeypatch.setattr(material, "search_videos_pixabay", fake_pixabay)
    # save_video returns a fake local path mirroring the URL
    monkeypatch.setattr(material, "save_video",
                        lambda video_url, save_dir="": f"/fake/saved/{video_url.replace('/','_')}.mp4")


def test_md11_hybrid_one_product_no_model(task_env, monkeypatch) -> None:
    """MD-11: hybrid + 1 product → [stock, user, stock_closing]."""
    p1 = _make_image_file(task_env["repo"] / "storage" / "uploads" / "p1.cropped.jpg")
    _write_sidecar(
        task_env["task_dir"],
        visuals_mode="hybrid",
        uploaded_model_path=None,
        uploaded_product_paths=[str(p1.relative_to(task_env["repo"]))],
        setting_tag="manufacturing",
        stock_queries=["worker on factory floor", "automated assembly line"],
    )
    _stub_stock_search(material, monkeypatch,
        pexels_pool={
            "worker on factory floor": ["https://p.example/clip-a"],
            "automated assembly line": ["https://p.example/clip-b"],
        },
        pixabay_pool={},
    )
    monkeypatch.setattr(material, "_make_kenburns_clip", _stub_kenburns)

    paths = material.download_videos(
        task_id=task_env["task_id"],
        search_terms=[],
        source="pexels",
        audio_duration=20.0,
    )
    # Expect 3 clips: [stock-0, user-0, stock-closing]
    assert len(paths) == 3
    assert "uploaded-0" in paths[1]   # user clip in middle
    audit = json.loads((task_env["task_dir"] / "script.json").read_text())["asset_audit"]
    assert audit["visuals_mode"] == "hybrid"
    assert audit["setting_tag"] == "manufacturing"
    assert len(audit["stock_assets"]) == 2  # one between, one closing
    assert audit["stock_assets"][0]["placement"] == "stock-0"
    assert audit["stock_assets"][1]["placement"] == "closing"
    assert len(audit["product_assets"]) == 1
    assert audit["pexels_empty_fallback"] is False


def test_md12_hybrid_model_plus_three_products(task_env, monkeypatch) -> None:
    """MD-12: hybrid + 1 model + 3 products → 9-clip alternation pattern."""
    model = _make_image_file(task_env["repo"] / "storage" / "uploads" / "model.cropped.jpg")
    products = []
    for i in range(3):
        p = _make_image_file(task_env["repo"] / "storage" / "uploads" / f"p{i}.cropped.jpg")
        products.append(str(p.relative_to(task_env["repo"])))
    _write_sidecar(
        task_env["task_dir"],
        visuals_mode="hybrid",
        uploaded_model_path=str(model.relative_to(task_env["repo"])),
        uploaded_product_paths=products,
        setting_tag="healthcare",
        stock_queries=["clinic waiting room", "doctor consultation",
                       "hospital corridor", "medical staff team",
                       "patient receiving care"],
    )
    pexels_pool = {q: [f"https://p.example/{q.replace(' ','-')}-{i}"
                       for i in range(2)]
                   for q in ["clinic waiting room", "doctor consultation",
                             "hospital corridor", "medical staff team",
                             "patient receiving care"]}
    _stub_stock_search(material, monkeypatch, pexels_pool=pexels_pool, pixabay_pool={})
    monkeypatch.setattr(material, "_make_kenburns_clip", _stub_kenburns)

    paths = material.download_videos(
        task_id=task_env["task_id"],
        search_terms=[],
        source="pexels",
        audio_duration=45.0,
    )
    # n_user = 4 (model + 3 products), n_stock = 5 → total 9
    assert len(paths) == 9
    audit = json.loads((task_env["task_dir"] / "script.json").read_text())["asset_audit"]
    assert audit["visuals_mode"] == "hybrid"
    assert audit["setting_tag"] == "healthcare"
    assert len(audit["stock_assets"]) == 5
    assert audit["model_asset"]["placement"] == "hybrid-slot-2"
    assert [p["placement"] for p in audit["product_assets"]] == [
        "hybrid-product-1", "hybrid-product-2", "hybrid-product-3"
    ]


def test_md13_hybrid_pexels_empty_falls_back(task_env, monkeypatch) -> None:
    """MD-13: zero stock available → user-only fallback + audit flag."""
    p1 = _make_image_file(task_env["repo"] / "storage" / "uploads" / "p1.cropped.jpg")
    _write_sidecar(
        task_env["task_dir"],
        visuals_mode="hybrid",
        uploaded_model_path=None,
        uploaded_product_paths=[str(p1.relative_to(task_env["repo"]))],
        setting_tag="manufacturing",
        stock_queries=["never matches anything"],
    )
    _stub_stock_search(material, monkeypatch, pexels_pool={}, pixabay_pool={})
    monkeypatch.setattr(material, "_make_kenburns_clip", _stub_kenburns)

    paths = material.download_videos(
        task_id=task_env["task_id"],
        search_terms=[],
        source="pexels",
        audio_duration=10.0,
    )
    # Falls back to user-only: 1 user clip
    assert len(paths) == 1
    audit = json.loads((task_env["task_dir"] / "script.json").read_text())["asset_audit"]
    assert audit["visuals_mode"] == "hybrid"
    assert audit["pexels_empty_fallback"] is True


def test_md14_dual_source_dedupes(task_env, monkeypatch) -> None:
    """MD-14: Pixabay + Pexels both queried, deduped by URL, Pixabay-first.

    Ordering changed: Pixabay returns first because its free-tier business
    inventory is denser. Pexels fills gaps where Pixabay didn't cover a term.
    """
    pexels_pool = {"q1": ["https://shared.example/clip"]}
    pixabay_pool = {"q1": ["https://shared.example/clip", "https://only-pixabay.example/x"]}
    _stub_stock_search(material, monkeypatch, pexels_pool=pexels_pool, pixabay_pool=pixabay_pool)
    out = material._search_stock_dual_source("q1", "9:16", 5)
    urls = [it.url for it in out]
    providers = [it.provider for it in out]
    # The deduped shared clip is sourced from Pixabay (queried first).
    assert urls == ["https://shared.example/clip", "https://only-pixabay.example/x"]
    assert providers == ["pixabay", "pixabay"]


def test_md_saliency_center_finds_high_contrast_region(task_env) -> None:
    """Saliency heuristic returns the high-contrast region of an image.

    Build a 1024×768 image that's 95% solid gray + a 200×200 high-contrast
    pattern in the upper-right quadrant. The saliency center should land
    close to the pattern's center (x≈0.7, y≈0.3), not the image center.
    """
    import numpy as np
    from PIL import Image

    img = Image.new("RGB", (1024, 768), color=(128, 128, 128))
    arr = np.array(img)
    # Inject high-contrast checkerboard in upper-right quadrant
    for y in range(100, 300, 4):
        for x in range(700, 900, 4):
            arr[y:y + 4, x:x + 4] = (255, 255, 255) if (x // 4 + y // 4) % 2 else (0, 0, 0)
    img = Image.fromarray(arr)

    x, y = material._detect_saliency_center(img, np, Image)
    # Pattern center is at (800/1024, 200/768) ≈ (0.78, 0.26)
    assert 0.5 < x < 1.0, f"x_norm={x} should be in right half"
    assert 0.0 < y < 0.5, f"y_norm={y} should be in upper half"


def test_md_kenburns_branches_on_aspect(tmp_path, monkeypatch) -> None:
    """Source > 1.4 aspect → contain-fit-with-blur; ≤ 1.4 → cover-fit-saliency.

    Mocks write_videofile so we can inspect which composition path was used
    via the layer-meta returned from the helper, without rendering.
    """
    import numpy as np
    from PIL import Image, ImageFilter

    # Wide source (1648×892, aspect ~1.85) → screenshot path
    wide = Image.new("RGB", (1648, 892), color="red")
    layers, meta = material._kb_layers_contain_with_blur(
        wide, np, ImageFilter, Image, 1080, 1920,
    )
    assert meta["fit_mode"] == "contain_blur"
    assert "bg" in layers
    fg_w, fg_h = meta["fg_size"]
    # Contain-fit: width fills (1080), height proportional → 1080 / 1.85 ≈ 583
    assert fg_w == 1080
    assert 580 <= fg_h <= 590

    # Square source (1000×1000, aspect 1.0) → photo path
    square = Image.new("RGB", (1000, 1000), color="blue")
    layers, meta = material._kb_layers_cover_with_saliency(
        square, np, Image, 1080, 1920,
    )
    assert meta["fit_mode"] == "cover_saliency"
    assert "bg" not in layers
    # Cover-fit fills the entire 1080×1920 frame
    assert meta["fg_size"] == (1080, 1920)
    assert layers["fg"].shape == (1920, 1080, 3)

    # Portrait source (800×1200, aspect 0.67) → photo path
    portrait = Image.new("RGB", (800, 1200), color="green")
    layers, meta = material._kb_layers_cover_with_saliency(
        portrait, np, Image, 1080, 1920,
    )
    assert meta["fit_mode"] == "cover_saliency"
    assert meta["fg_size"] == (1080, 1920)


def test_md15_hybrid_audit_records_provider_and_query(task_env, monkeypatch) -> None:
    """MD-15: audit log records provider + query per stock clip + tier used."""
    p1 = _make_image_file(task_env["repo"] / "storage" / "uploads" / "p1.cropped.jpg")
    _write_sidecar(
        task_env["task_dir"],
        visuals_mode="hybrid",
        uploaded_model_path=None,
        uploaded_product_paths=[str(p1.relative_to(task_env["repo"]))],
        setting_tag="office",
        stock_queries=["q1", "q2"],
    )
    _stub_stock_search(material, monkeypatch,
        pexels_pool={"q1": ["https://p.example/x1"]},
        pixabay_pool={"q2": ["https://b.example/y1"]},
    )
    monkeypatch.setattr(material, "_make_kenburns_clip", _stub_kenburns)
    material.download_videos(
        task_id=task_env["task_id"],
        search_terms=[],
        source="pexels",
        audio_duration=12.0,
    )
    audit = json.loads((task_env["task_dir"] / "script.json").read_text())["asset_audit"]
    providers = sorted([s["provider"] for s in audit["stock_assets"]])
    queries = sorted([s["query"] for s in audit["stock_assets"]])
    assert providers == ["pexels", "pixabay"]
    assert queries == ["q1", "q2"]
    assert audit["retry_tier_used"] == 1
    assert audit["pexels_clip_count"] == 1
    assert audit["pixabay_clip_count"] == 1
