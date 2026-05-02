# Phase 1 Data Model: Music Track Control + Custom Uploads

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Research**: [research.md](./research.md)

This feature introduces ONE first-class entity (Audio Upload Asset) and surfaces an EXISTING entity (Music Configuration on `VideoParams`). It deliberately adds NO new fields to `VideoParams` — the existing `bgm_type` / `bgm_file` / `bgm_volume` fields cover the v1 surface. This keeps the schema-change surface area zero.

---

## Entity 1 — Music Configuration (existing fields on `VideoParams`)

**File**: `app/models/schema.py` (existing fork-surface file — UNTOUCHED by this feature)
**Status**: pre-existing on `VideoParams` since upstream MPT. Documented here for clarity; no schema change required.

### Existing fields (verbatim from `schema.py:101-103`)

| Field | Type | Default | Source |
|---|---|---|---|
| `bgm_type` | `Optional[str]` | `"random"` | `app/models/schema.py:101` |
| `bgm_file` | `Optional[str]` | `""` | `app/models/schema.py:102` |
| `bgm_volume` | `Optional[float]` | `0.2` | `app/models/schema.py:103` |

### Wire-shape semantics (this spec's contract)

This feature defines what values these fields legally carry from the wizard. The Pydantic types stay loose (`Optional[str]`, `Optional[float]`) for backwards compat with non-VisualAI callers, but the wizard adheres to the tightened semantics below:

| Field | Allowed values from the wizard | Meaning |
|---|---|---|
| `bgm_type` | `"random"`, `"file"`, `""` (empty) | `"random"` → MPT picks a random bundled track. `"file"` → use `bgm_file` (a custom upload OR a specific bundled track path). `""` → no music (voiceover-only render). |
| `bgm_file` | `""` when `bgm_type != "file"`; non-empty path string when `bgm_type == "file"` | Path string the engine resolves. v1 acceptable values: `storage/uploads/<uuid>.<ext>` (custom upload) OR `resource/songs/output<NNN>.mp3` (specific bundled track). v2 will additionally accept `brand-library/<tenant>/music/<asset>.<ext>`. |
| `bgm_volume` | `0.0` to `1.0` (float, two-decimal precision) | Linear amplitude multiplier applied to the BGM before mixing with the voiceover. `0.0` = silent, `1.0` = full strength. |

### Validation invariants

1. If `bgm_type == "file"`, then `bgm_file` MUST be non-empty. If empty, the wizard MUST coerce `bgm_type` to `""` (None mode) before submission. Backend Pydantic validation does NOT enforce this XOR — backwards compat with non-wizard callers keeps it loose.
2. If `bgm_type == "" `, then the rendered audio is voiceover-only. `bgm_file` and `bgm_volume` are ignored by the pipeline.
3. If `bgm_type` is omitted entirely from the request, MPT defaults to `"random"` per the existing Pydantic default — preserves no-regression for legacy callers (FR-010, SC-007).
4. `bgm_volume` MUST be in `[0.0, 1.0]`. The wizard clamps slider position 0–100 to volume 0.0–1.0 by simple division — no negative or > 1.0 values can flow through.

### Lifecycle

Music Configuration is constructed once per render request inside the wizard, attached to the `/api/generate` body, passed verbatim to MPT, persisted into the task's `script.json`. It's never persisted to a DB and never mutated after submission.

### Conditional-emission rule (FR-010)

The wizard's `/api/generate` proxy MUST omit `bgm_*` fields entirely when the creator never opened the Music panel — see [research.md R4](./research.md). This guarantees byte-equivalence with today's pipeline output for unmodified flows.

---

## Entity 2 — Audio Upload Asset (filesystem artifact)

**Storage**: `storage/uploads/<uuid>.<ext>` (single shared dir at v1; tenant-scoped under `storage/uploads/<tenant_id>/<uuid>.<ext>` once debt #2 repays in Step 2). **Shared with spec 009** — UUID4 filenames prevent collision between audio (`.mp3`/`.wav`/`.ogg`/`.m4a`) and image (`.png`/`.jpg`/`.webp`) uploads.
**Format**: MP3, WAV, OGG, M4A (per FR-003).
**Lifecycle**: created by `POST /api/v1/uploads/audio`; referenced by `bgm_file`; never auto-deleted at v1 (operator does manual cleanup if disk pressure rises).
**Constraints**:
- Max size: **10 MB** per file (FR-003) — bigger than spec 009's 5 MB logo cap because realistic music files are larger than logos.
- MIME types accepted: `audio/mpeg`, `audio/wav`, `audio/x-wav`, `audio/ogg`, `audio/mp4` (per [research.md R2](./research.md)).
- Filename is a server-generated UUID4 + extension derived from MIME, NOT the user's filename (avoids path traversal, collisions).
- File MUST be probable by ffprobe (or MoviePy `AudioFileClip`) at upload time — corrupt audio rejected before render time.

### Per-render persistence

The path string lives inside the task's `script.json` artifact under `params.bgm_file`. My Assets can already display "this render had custom music" without schema changes — `/api/history` reads the field as part of its existing JSON parsing.

### Duration metadata

The upload endpoint returns a `duration_seconds: float` field alongside `path`. The wizard uses this to display "your track is N seconds — it will loop / be truncated" hints (FR-012). The duration is NOT persisted into `bgm_file` itself; the wizard discards it after display. The render pipeline reads the actual duration from the file at mix time via `AudioFileClip(bgm_file).duration` (existing behavior).

---

## Cross-entity relationships

```text
                  POST /api/v1/uploads/audio
                          │
                          ▼
                 storage/uploads/<uuid>.mp3       (Audio Upload Asset, Entity 2)
                          │
                          │ path string returned
                          ▼
              wizard state: bgm_file = "<path>"
                          │
                          ▼
        VideoParams(bgm_type="file", bgm_file="...", bgm_volume=0.4)   (Entity 1)
                          │
                          │ task.py
                          ▼
   combine_videos(...) → reads bgm_type/bgm_file/bgm_volume → AudioFileClip → mix with voiceover → final-1.mp4

   (alternative origin: bgm_file = "resource/songs/output042.mp3" when wizard picks a bundled track)
   (alternative origin: bgm_file = "" when wizard mode is None)
```

**Source-of-truth invariants**:

- `bgm_type` is the SINGLE source of truth for "is there music in this render at all?" — `""` means no, anything else means yes. The wizard never sends `bgm_volume = 0.0` to mean "silent"; it sends `bgm_type = ""` instead, so the audio mix step short-circuits cleanly.
- `bgm_file` is a free-form path string. The engine doesn't care whether it points at a per-render upload, a bundled track, or (future) a Brand Library asset. Today's resolver lives implicitly inside MPT's `get_bgm_file()` helper at `app/services/video.py:185-198`.
- The duration hint shown in the wizard is purely UX — it's NEVER passed to MPT. MPT computes duration itself when it loads the file.

---

## What is NOT modeled (deliberately)

- **Per-render audio cache** — each render re-reads the file from disk. No caching at v1 (one BGM per render is rare; the existing pipeline already amortizes the I/O).
- **Multi-track music** (intro / main / outro) — only meaningful for Mode 3 long-form; not v1 scope. No `bgm_tracks: list[...]` field.
- **Sidechain / loudness automation** — requires a `loudnorm` FFmpeg pass; v1 sticks with linear amplitude multiplier per [research.md R3](./research.md).
- **Per-overlay z-index / layering for music** — there's only one music track at a time; no z-order needed.
- **Brand Library music asset records** — handled by Step 5's feature, not by this spec. `bgm_file` accepts the future path shape today (FR-009).
- **Telemetry events** ("track played", "volume changed") — no observability infrastructure in scope; rely on existing loguru logs.
- **Audio preview state in the wizard** — preview is deferred per spec assumption; no `previewing: bool` or similar wizard-state field.

---

## Schema diff summary

For ease of audit, here's the entirety of the schema delta this feature introduces:

```diff
# app/models/schema.py
# (NO CHANGES — bgm_type, bgm_file, bgm_volume already exist)
```

That's intentional. The whole point of v1 is that MPT's BGM mixing already works; this feature just exposes it. The data model section of this spec exists to **document the wire-shape semantics** of those existing fields, not to propose new fields.
