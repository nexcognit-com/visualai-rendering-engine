# Implementation Plan: Music Track Control + Custom Uploads

**Branch**: `010-music-control` | **Date**: 2026-05-02 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/010-music-control/spec.md`

## Summary

Surface the existing MPT BGM mixing pipeline (`app/services/video.py:545-557`, with `get_bgm_file()` helper at `video.py:185-198`) through the VisualAI Mode 2 wizard. Add a Music selector in Step 3 with three modes — Preset (incl. Random + bundled-track dropdown), Upload (custom MP3/WAV/OGG/M4A up to 10 MB), None — plus a 0–100 % volume slider that maps to the existing `bgm_volume` field. New endpoint `POST /api/v1/uploads/audio` mirrors spec 009's logo upload but accepts audio MIMEs and probes via `ffprobe` (or MoviePy's `AudioFileClip.duration`) to surface track duration in the wizard. The endpoint returns `{path, size_bytes, mime_type, duration_seconds}` so the wizard can warn "your track is shorter/longer than your video — it will loop / be truncated." NO new fields on `VideoParams` — `bgm_type`, `bgm_file`, `bgm_volume` already exist; this feature wires them. NO touches to `app/services/video.py` (Principle II keeps upstream MoviePy assembly code rebase-clean) — the existing silent-fallback on mixing failure is inherited as a documented v1 limitation. Spec 009 (visual overlays) and this spec are parallel-deliverable; they share an upload-endpoint pattern but no files.

## Technical Context

**Language/Version**: Python 3.11/3.12 (matches constitution); TypeScript / React (Next.js 16 + React 19) on the frontend.
**Primary Dependencies**: MoviePy + Pillow (already pinned upstream — used for `AudioFileClip` duration probe at upload time); FastAPI multipart (already used by spec 009's logo endpoint); `python-multipart` (transitive). **Optional but recommended**: `ffprobe` (part of FFmpeg, already a hard system requirement per the constitution) for fast metadata-only duration extraction without decoding the full audio. **No new runtime dependency.**
**Storage**: Filesystem at `storage/uploads/<uuid>.<ext>` for uploaded audio (same dir spec 009's logos use). Bundled BGM stays at `resource/songs/output000.mp3`–`output028.mp3` (29 files). When debt #2 (multi-tenant) repays in Step 2, both audio and logo uploads scope to `storage/uploads/<tenant_id>/<uuid>.<ext>` via the same path-rewrite.
**Testing**: pytest smoke tests covering the upload endpoint (per FR-006) and the schema-forward-compat assertion (SC-006). Manual end-to-end via the wizard for SC-002..SC-005 (audio audibility, volume measurability — these need ear-listening + ffprobe loudness measurement, not unit tests). Per the constitution, "new mode code requires at least one smoke test exercising the rendering path with mocked Layer 2 inputs" — covered by reusing spec 009's stub-video helper from `test/services/test_helpers.py` plus a synthetic 1 s sine-wave WAV.
**Target Platform**: GPU-capable host for production (per constitution); CPU-only for the audio mixing step (negligible cost — already in upstream pipeline). Browser: HTML5 file input with `accept="audio/mpeg,audio/wav,audio/ogg,audio/mp4"`.
**Project Type**: Layer 3 rendering-engine surface + Layer 1 wizard surface — same shape as spec 009.
**Performance Goals**: Upload endpoint responds within 2 s for ≤ 10 MB files (depends on disk + ffprobe; ffprobe is fast — milliseconds). Render-time: zero added time vs. today, since the audio mixing step already runs on every render — this feature only changes which `bgm_type`/`bgm_file`/`bgm_volume` values arrive at it.
**Constraints**: MUST NOT modify `app/services/video.py` (Principle II — keep upstream MoviePy code rebase-clean). MUST NOT add fields to `VideoParams` (the existing fields cover the v1 surface). MUST preserve byte-equivalence for renders that omit music fields entirely (FR-010, SC-007). Wizard MUST NOT preview audio in-browser at v1 (deferred per spec assumption).
**Scale/Scope**: 1 audio track per render; 1 wizard music panel per Mode 2 surface. Modes 1/3/4/5 inherit the same `bgm_*` fields when they ship via their own feature branches; this spec only delivers Mode 2's wizard surface. Bundled BGM library is fixed at v1 (29 tracks); curating/swapping the bundled set is out of scope.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Verdict | Reasoning |
|---|---|---|
| **I. Layer 3 Scope — Rendering Only (NON-NEGOTIABLE)** | PASS | Layer 3 portion is exactly an upload endpoint that persists a file to disk — rendering-adjacent, not user/billing logic. The audio mixing itself already exists in `video.py`. Layer 1 wizard is Layer 1's job by design. |
| **II. Surgical Fork Discipline** | PASS, with continuation of existing debts | Touches **fork-surface files**: `app/controllers/v1/uploads.py` (already a NEW file from spec 009 — extending it for audio is allowed). **Does NOT touch** `app/services/video.py` (BGM mixing logic — kept rebase-clean). **Does NOT add fields to `app/models/schema.py`** — uses existing `bgm_type`/`bgm_file`/`bgm_volume` fields. **Does NOT touch `app/services/task.py`** — the existing `combine_videos` call already passes `params` through, so the new wizard fields flow without code changes in task.py. **Net: no new fork-surface touches beyond extending spec 009's uploads controller.** |
| **III. Multi-Tenant Context Propagation** | PASS, via existing debt | Audio uploads land in shared `storage/uploads/` without tenant scoping — same shared infrastructure as spec 009. Continuation of debt #2 (no `tenant_id` on requests). When debt #2 repays in Step 2, uploads scope per-tenant via the same path-rewrite that spec 009 inherits. No new debt. |
| **IV. External Asset Acceptance Over Direct API Calls** | PASS | No external APIs. Audio comes from user uploads (filesystem) or bundled `resource/songs/` (filesystem). v2 with Brand Library is still tenant-scoped storage, not API calls. |
| **V. Mode-Aware Rendering Contract** | PASS, via existing debt | Music UI is wired into Mode 2 directly via the wizard, not via the (yet-to-exist) `app/services/modes/` registry. Continuation of debt #4. When the registry lands at Step 3, music-mode-applicability moves into the registry. No new debt. |
| **§Technology Constraints — Runtime** | PASS | Python 3.11/3.12; uses MoviePy + Pillow + FFmpeg (all already pinned). No new dependency. |
| **§Technology Constraints — Database** | N/A | Filesystem only. |
| **§Technology Constraints — Observability** | PASS | The new upload endpoint uses loguru with `task_id`-style request-id tagging to match MPT's existing logging discipline. Failures log at ERROR; successful uploads log at INFO. |
| **§Technology Constraints — Secrets** | PASS | No API keys. |
| **§Development Workflow — fork-surface PR rule** | APPLIES | This PR touches the fork-surface controllers directory (extending `app/controllers/v1/uploads.py`). Per the constitution, "PRs touching the five fork-surface files MUST reference the affected Agent Mode(s) and cite the relevant Master Spec section in the PR body." The implementation PR for this spec MUST cite Mode 2 (Short Marketing Video) and Master Spec §3 (Five Agent Modes). |
| **§Development Workflow — pytest gate** | APPLIES | Smoke tests for the audio upload endpoint MUST exist before this feature merges; mirrors the requirement spec 009 already satisfies. |

**Inherited asymmetry (documented in spec §Constitutional Impact)**: spec 009 forbids silent fallbacks on overlay-mixing failures (FR-013); this spec preserves the silent fallback on BGM-mixing failures because tightening it requires editing `video.py` (forbidden by Principle II). Step 3's mode registry will rewrite the audio path and naturally fix this.

**Gate result**: PASS. No NEW debts. Two existing debts (#2, #4) gain one more burndown task each. Re-check post-Phase 1.

## Project Structure

### Documentation (this feature, in this repo)

```text
specs/010-music-control/
├── plan.md                    # This file
├── research.md                # Phase 0 — duration probe choice, multi-MIME validation, volume mapping, no-regression strategy
├── data-model.md              # Phase 1 — Audio Upload Asset, Music Configuration entities + validation rules
├── quickstart.md              # Phase 1 — operator runbook covering SC-001 through SC-007
├── contracts/
│   ├── audio-upload-endpoint.md     # POST /api/v1/uploads/audio HTTP contract
│   └── music-config-contract.md     # bgm_type / bgm_file / bgm_volume wire-shape contract (existing fields, but documented for client reuse)
├── checklists/
│   └── requirements.md        # Spec quality checklist (already created)
├── spec.md                    # Feature specification
└── tasks.md                   # Phase 2 — produced by /speckit.tasks (NOT here)
```

### Source code changes (Layer 3 — this repo)

```text
app/
└── controllers/v1/
    └── uploads.py                   # MODIFIED: extend with POST /api/v1/uploads/audio (parallel to /logo). Both endpoints share a common multipart-validation helper inside this same file.
                                     # NOTE: this file is shared with spec 009. The order in which 009 and 010 land determines who creates the file and who extends it; either order works.
storage/
└── uploads/<uuid>.<ext>             # SHARED with spec 009 — audio gets `.mp3`/`.wav`/`.ogg`/`.m4a`; logos get `.png`/`.jpg`/`.webp`. UUID4 filenames prevent collision across types.
resource/
└── songs/                            # UNTOUCHED — bundled BGM library used by `get_bgm_file(bgm_type="random")`
test/
└── controllers/
    └── test_uploads_audio.py        # NEW — smoke tests for the audio upload endpoint (mirrors test_uploads.py for logos)
```

**Files explicitly NOT touched**:

- `app/services/video.py` — Principle II (BGM mixing logic stays upstream-rebase-clean)
- `app/models/schema.py` — no new fields; uses existing `bgm_type`/`bgm_file`/`bgm_volume`
- `app/services/task.py` — existing `combine_videos(params, ...)` call already wires every `VideoParams` field through

### Source code changes (Layer 1 — `visualai-frontend/`)

```text
visualai-frontend/src/
└── app/
    ├── modes/short-video/
    │   └── page.tsx                 # MODIFIED: append "Music" panel to Step 3 — three-mode selector (Preset / Upload / None) + bundled-track dropdown when Preset, file picker + duration display when Upload, volume slider with 80%-warning copy
    └── api/
        ├── generate/route.ts        # MODIFIED: pass `bgm_type`, `bgm_file`, `bgm_volume` through to MPT alongside the existing fields
        └── upload-audio/
            └── route.ts             # NEW: multipart proxy to MPT's /api/v1/uploads/audio (mirrors spec 009's /api/upload-logo)
```

**Structure Decision**: Layer 1 changes localize to the wizard page and a new API proxy route. Layer 3 changes localize to extending the existing uploads controller (created by spec 009) plus one new test file. The upstream `video.py` is left untouched, satisfying Principle II's rebase-clean requirement. The bundled `resource/songs/` directory is untouched. The `storage/uploads/` directory is shared with spec 009; UUID4 filenames prevent any collision.

## Cross-spec coordination with spec 009

- **Shared file**: `app/controllers/v1/uploads.py` is created by whichever feature ships first. The PR-merge order determines who establishes the controller skeleton:
  - If 009 lands first: 010's PR extends `uploads.py` with the `/api/v1/uploads/audio` endpoint and reuses the multipart-validation helper.
  - If 010 lands first: 009's PR similarly extends. The MIME-validation tables differ (image vs audio); everything else is shared.
- **Shared helper**: Both endpoints SHOULD use a common `_validate_upload(file: UploadFile, allowed_mimes: set[str], max_bytes: int) -> tuple[bytes, str, str]` helper that returns `(file_bytes, validated_mime, file_extension)`. This avoids drift between the two endpoints' size-cap and MIME-validation behavior.
- **Shared test fixture**: `test/services/test_helpers.py` (introduced in spec 009 task T002) gains a `_make_synthetic_audio(path, duration_s, format)` helper for audio tests. Reusing the same file keeps fixtures discoverable.
- **No frontend conflict**: Spec 009's wizard panel is "Overlays"; this spec's is "Music". They live in separate JSX subtrees inside Step 3 with no shared state.

## Complexity Tracking

> No NEW Constitution violations. Section minimal.

This feature deliberately rejects four heavier alternatives:

- **In-browser audio preview before submission** — rejected per spec assumption: needs HTML5 audio element with cross-browser codec compat; loading states; permission prompts on iOS Safari. Adds ~3–4 hours of UI work. Creator hears the music for the first time in the rendered output at v1; v2 may layer this on without changing the schema.
- **Multi-track music** (intro + outro + main) — rejected: scope creep. Mode 2 is short-form; one BGM track is enough. Multi-track support naturally lives in Mode 3 (long-form) when it ships.
- **Per-section volume automation** (duck the music when voiceover is active) — rejected: requires real audio analysis (compressor / sidechain) which the upstream pipeline doesn't have. v1's static volume mix is intentional; sidechain support is a v2+ research item.
- **Tightening the silent-fallback to a typed error** — rejected per Principle II rebase-clean rule. Documented as v1 limitation in spec §Edge Cases; addressed when Step 3's mode registry rewrites the audio path.

## Re-evaluation post-Phase 1

After data-model + contracts + quickstart land, re-check the gates:

- Principle I: still PASS — no Layer 3 business logic added.
- Principle II: still PASS — `video.py` and `schema.py` untouched; only `uploads.py` extended.
- Principles III, IV, V: still PASS via debts #2, #4 (no new debts).
- §Technology Constraints: confirmed no new dependency; ffprobe already a hard system requirement; FFmpeg/MoviePy already pinned.

The post-design check has nothing new to flag. Plan is implementation-ready.
