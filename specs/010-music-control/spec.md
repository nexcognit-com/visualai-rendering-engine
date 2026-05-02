# Feature Specification: Music Track Control + Custom Uploads

**Feature Branch**: `010-music-control`
**Created**: 2026-05-02
**Status**: Draft
**Input**: User description: "or the music feature — kicks off feature 010 (\"Music track control + custom uploads\") An ability to upload track of music"

## Overview

Expose music-track control inside the VisualAI wizard so creators can pick a background-music (BGM) track for their Mode 2 ad, optionally upload their own audio file, and adjust the music's loudness relative to the voiceover. Today the MPT backend already supports BGM end-to-end — `VideoParams.bgm_type`/`bgm_file`/`bgm_volume` flow through to a working audio-mixing step in `app/services/video.py:545-557` that auto-loops the track to match the video's duration with a 3-second fade-out — but the VisualAI frontend never sends those fields. As a result every Mode 2 render today plays a silently-randomized BGM at MPT's hard-coded 20 % default, with no way for the creator to choose, mute, or upload their own.

This feature closes that gap with three deliverables: (1) a wizard music selector in Step 3 alongside the existing voice selector, (2) a custom audio upload endpoint that mirrors spec 009's logo upload (`POST /api/v1/uploads/audio`), and (3) a volume slider that maps to MPT's existing `bgm_volume` field. Like spec 009, the music model is forward-compatible with the future Brand Library feature: today's `source_path` points at `storage/uploads/`; tomorrow's points at `brand-library/<tenant>/music/`.

This is the audio counterpart to spec 009's visual brand overlays. Both specs were carved out together when the user asked "is there music tracks also?" during 009's clarify pass — keeping audio in its own spec preserves a clean "visual vs audio" boundary and lets the two ship in parallel without shared files.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Creator picks a music track in the wizard (Priority: P1)

A creator opens Mode 2's wizard and reaches Step 3. Alongside the existing Voice selector, a Music selector lets them choose: a specific track from the bundled library (29 BGM files in `resource/songs/`), a randomized track, or no music at all. They submit the wizard and the rendered MP4 plays the chosen music underneath their voiceover at the default volume (which keeps the voiceover intelligible). No upload required.

**Why this priority**: this is the minimum viable music UX — give the creator control over the soundtrack of every video they produce. Today the music plays randomly with no way to influence it. Without P1 this feature has no value.

**Independent Test**: Generate a Mode 2 render with the wizard's music selector set to "no music"; confirm the rendered MP4 has voiceover only, no music. Then generate a second render with a specific BGM track selected; confirm that exact track audibly plays underneath the voiceover. The two renders MUST clearly differ in their audio content.

**Acceptance Scenarios**:

1. **Given** the wizard's Step 3 is open, **When** the creator opens the Music selector, **Then** the dropdown shows "Random", "None", and a list of named bundled BGM tracks (no path strings or filename leakage in the labels).
2. **Given** the creator picks "None" and submits, **When** the render completes, **Then** the final MP4 has only the voiceover audio — no music — and no silent track of music at zero volume.
3. **Given** the creator picks a specific bundled track, **When** the render completes, **Then** the final MP4 has that track audibly mixed under the voiceover at the default volume.
4. **Given** the creator picks "Random", **When** the render completes, **Then** any one of the bundled tracks plays.

---

### User Story 2 — Creator uploads a custom music track (Priority: P2)

A creator wants their own music — a brand jingle, a licensed track they purchased, or a royalty-free piece they sourced themselves — to play instead of any bundled track. They click "Upload custom" in the music selector, pick an MP3/WAV/OGG/M4A file (up to 10 MB), and the wizard validates it before submission. The render uses their uploaded track exactly the same way it would use a bundled track: auto-looped to fit the video duration, faded out at the end, mixed with the voiceover.

**Why this priority**: real brands use their own audio identity. The bundled library is generic; without custom uploads, Mode 2 cannot serve creators with established sonic branding. Lower than P1 because a creator can ship a video with bundled music while waiting for upload support.

**Independent Test**: Upload a known MP3 file (e.g., a 60-second 8-bar loop). Generate a Mode 2 render. The rendered MP4 MUST audibly play that uploaded track underneath the voiceover, looped to fill the render's duration if the track is shorter, with the same 3-second fade-out the bundled tracks get.

**Acceptance Scenarios**:

1. **Given** the creator opens the music selector and clicks "Upload custom", **When** they pick a valid 5 MB MP3, **Then** the wizard shows the uploaded filename + a play preview button + the path is stored in wizard state for submission.
2. **Given** they pick a 12 MB MP3 (over the cap), **When** the upload starts, **Then** the wizard surfaces a "audio file must be under 10 MB" error before submission and the render does NOT start.
3. **Given** they pick a `.wma` file (unsupported format), **When** the upload starts, **Then** the wizard rejects it with a typed error naming the supported formats.
4. **Given** their upload succeeded and they submit the wizard, **When** the render completes, **Then** the uploaded track plays underneath the voiceover.

---

### User Story 3 — Creator adjusts music volume (Priority: P2)

A creator wants the music more (or less) prominent than the default 20 % under the voiceover. A slider in the music selector lets them set music volume from 0 % (silent) to 100 % (matched to voiceover). Default is 20 %, which keeps the voiceover intelligible — a value chosen to match MPT's existing default to preserve no-regression for renders without explicit music control.

**Why this priority**: same priority as upload — the bundled library at default volume covers the basic use case, but creators with branding goals want explicit volume control. Pairs naturally with US2.

**Independent Test**: Generate two Mode 2 renders with the same subject and the same music track but different volumes (20 % vs 60 %). The second render's music MUST be measurably louder relative to the voiceover.

**Acceptance Scenarios**:

1. **Given** the music selector has a track picked, **When** the creator drags the volume slider to a new value, **Then** the wizard surfaces a "preview affects rendered volume only — submit to hear" hint (since real-time audio preview is out of scope at v1).
2. **Given** they pick volume 0 %, **When** the render completes, **Then** the rendered audio is voiceover-only (effectively the same as picking "None" — both produce no audible music in the output).
3. **Given** they pick volume 100 %, **When** the render completes, **Then** the music is mixed at full strength alongside the voiceover and may overpower it (the wizard SHOULD warn at ≥80 % but does not block).

---

### User Story 4 — Brand Library forward-compat (Priority: P3, deferred implementation)

When the Brand Library feature lands (Step 5 of the build plan), a tenant's saved music tracks can be selected from a dropdown rather than uploaded fresh each render. The music model's `bgm_file` field MUST accept any path string the engine can resolve, whether it points to `storage/uploads/<uuid>.mp3` (today) or to a Brand Library asset like `brand-library/<tenant>/music/intro_v3.mp3` (future). v1 implements only per-render uploads; the spec ensures v2 won't require a schema migration.

**Why this priority**: same rationale as spec 009's matching story — schema-shape is cheap to get right today, expensive later.

**Independent Test**: Submit a synthetic render request with `bgm_file: "brand-library/tenant_abc/music/intro_v3.mp3"` (a path that doesn't exist yet). The Pydantic validation at the API layer MUST accept the value. The compositor will fail at render time because the file isn't on disk, but the schema MUST NOT reject the path shape.

---

### Edge Cases

- **Audio shorter than the video**: today's pipeline auto-loops via `AudioLoop(duration=video_clip.duration)`. v1 keeps that behavior — a 30 s upload on a 60 s video plays twice. No explicit "loop on/off" toggle in v1.
- **Audio longer than the video**: same pipeline truncates via the `AudioLoop` duration cap. The 3 s fade-out applies whether truncation happened or not.
- **Audio with weird sample rate / bitrate**: MoviePy resamples internally; existing pipeline already handles this. v1 doesn't enforce a sample-rate cap.
- **Audio with stereo vs mono**: existing pipeline handles either. No change.
- **Audio file is silent (just silence bytes)**: validates fine; renders as voiceover-only effectively. Acceptable; not worth a check.
- **Upload too large**: rejected at the upload endpoint with HTTP 413, before any disk write.
- **Upload wrong format** (e.g., `.wma`, `.flac`): rejected at the upload endpoint with HTTP 400.
- **Existing pipeline silently falls back to voiceover-only on BGM mixing failure** (current behavior at `app/services/video.py:546-557`): the v1 spec **acknowledges and preserves** this behavior because changing it requires editing `video.py` (Principle II — keep upstream rebase-clean). When a creator explicitly picked a track and the render produces voiceover-only output due to a transient mixing failure, the failure is logged but not surfaced to the user. This is documented as an accepted tradeoff and is the right behavior to revisit when Step 3's mode registry naturally rewrites the audio path. **Treated as known v1 limitation**, not a v1 deliverable to fix.
- **Voiceover disabled + music "None"**: produces a silent video. Wizard SHOULD warn ("your video will have no audio") but does not block.
- **Voiceover disabled + music selected**: music plays alone. Acceptable (some creators want music-only B-roll).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Mode 2 wizard MUST expose a Music selector inside Step 3, alongside the existing Voice selector. The selector MUST be present even when the creator's previous flow had no music UI (zero-config — picking "Random" preserves today's behavior).
- **FR-002**: The Music selector MUST offer three modes: (a) **Preset**, including a "Random" option and a list of bundled BGM tracks displayed by human-readable name; (b) **Upload custom**, opening a file picker; (c) **None**, which renders voiceover-only.
- **FR-003**: Custom audio uploads MUST accept MP3, WAV, OGG, and M4A formats up to **10 MB** per file. The bigger cap vs. spec 009's 5 MB logo cap reflects realistic music-file sizes.
- **FR-004**: A volume slider MUST be visible whenever a music mode that produces audible output is selected (i.e., not "None"). Slider range 0–100 %, default 20 %, integer steps. The wizard MUST display a "may overpower voice" warning at ≥80 % but MUST NOT block submission.
- **FR-005**: The wizard MUST pass `bgm_type` (`"random" | "file" | "" `), `bgm_file` (the upload's `source_path` when applicable), and `bgm_volume` (`0.0–1.0`, derived from the slider's percentage / 100) through `/api/generate` to MPT's `/api/v1/videos`. These fields already exist on `VideoParams` — this feature wires them, doesn't add them.
- **FR-006**: A new endpoint `POST /api/v1/uploads/audio` MUST exist (mirroring spec 009's `POST /api/v1/uploads/logo`), accepting a multipart upload, validating format + size, saving to `storage/uploads/<uuid>.<ext>`, and returning `{path, size_bytes, mime_type, duration_seconds}`. The `duration_seconds` field is new vs. logo upload — it informs the wizard's "track is shorter/longer than your video" hint.
- **FR-007**: The frontend MUST proxy audio uploads through a new `/api/upload-audio` route in `visualai-frontend` (parallel to spec 009's `/api/upload-logo`) to keep the bearer-secret-free contract intact.
- **FR-008**: Wizard MUST validate locally before submission: file format, file size, volume range, "None" + no voiceover combination producing a silent video (warn but don't block). Validation failures MUST surface inline before the render starts.
- **FR-009**: The `bgm_file` field on `VideoParams` MUST accept any path string the engine can resolve — `storage/uploads/<uuid>.<ext>` (today) or `brand-library/<tenant>/music/<asset>.<ext>` (future Brand Library), with no schema change required between v1 and v2.
- **FR-010**: The default behavior for renders that omit music fields entirely (e.g., legacy API consumers, non-VisualAI clients hitting MPT directly) MUST remain unchanged — `bgm_type` defaults to `"random"` at MPT's existing `0.2` volume. This preserves no-regression for any pipeline path that doesn't go through the new wizard surface.
- **FR-011**: When a creator picked "Upload custom" and the upload fails, the wizard MUST surface a typed error with the same vocabulary as spec 009's logo upload (`unsupported_format`, `file_too_large`, `invalid_audio`, `storage_write_failed`). The render MUST NOT proceed with a partial upload reference.
- **FR-012**: The `duration_seconds` returned by the audio upload endpoint MUST be displayed in the wizard so the creator knows whether their track will loop (track shorter than render's expected duration) or be truncated (track longer).

### Key Entities

- **Music Track Source**: a path string identifying the audio. Three v1 origins: (a) bundled — paths under `resource/songs/` like `resource/songs/output042.mp3`; (b) per-render upload — paths under `storage/uploads/<uuid>.<ext>`; (c) random — sentinel value `"random"` that MPT resolves to a random bundled file at render time. v2 adds Brand Library origin with no schema change.
- **Audio Upload Asset**: an MP3/WAV/OGG/M4A file persisted to `storage/uploads/<uuid>.<ext>`. Constraints: ≤ 10 MB; validated by both MIME type and Pillow-equivalent audio probe (probably `ffprobe` or MoviePy's `AudioFileClip` instantiation) at upload time so corrupt files are rejected before render time.
- **Music Configuration** (extension to `VideoParams`): the existing `bgm_type` / `bgm_file` / `bgm_volume` triplet. This feature does NOT add new fields to `VideoParams` — it surfaces the existing ones in the wizard with proper UX. The volume field semantics: `0.0` (silent) to `1.0` (matched to voiceover); default `0.2` (current MPT default, preserved for no-regression).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A creator can configure music for their Mode 2 render (pick a track, optionally upload a custom one, optionally adjust volume) in ≤ 60 seconds, on a representative test of 3 unfamiliar users. Measured by wall-clock from "Step 3 first opens" to "submit clicked." Verifies SC-005-style discoverability of spec 009.
- **SC-002**: A render with the music selector set to "None" produces an MP4 whose audio track contains the voiceover ONLY — measured by inspecting the audio waveform: zero non-voice frequency content during voiceover-quiet moments. Confirms FR-002 and FR-005's "None" path.
- **SC-003**: A render with a specific bundled BGM track selected produces an MP4 in which that track is audible underneath the voiceover. Verified by spot-listening to 3 sampled renders.
- **SC-004**: A render with a custom uploaded MP3 produces an MP4 whose audio matches the uploaded track. Verified by spot-listening + checksum comparison of the BGM-only frequency band against the source track.
- **SC-005**: Volume slider produces measurable loudness changes — a 20 % vs. 60 % render of the same track has the BGM-frequency-band loudness measurably higher in the second. Tolerance: a clear audible difference; no precision-loudness target at v1.
- **SC-006**: The `bgm_file` field forward-compat test: a synthetic API request with `bgm_file: "brand-library/tenant_abc/music/intro_v3.mp3"` validates against the Pydantic model without rejection (the actual path needn't resolve). Confirms FR-009.
- **SC-007**: Renders that go through the legacy code path (no wizard, no music fields in the request body) MUST be byte-equivalent in their audio content to today's pipeline output. Confirms FR-010 zero-regression for non-VisualAI consumers.

## Assumptions

- **The existing MPT BGM pipeline at `app/services/video.py:545-557` is preserved as-is.** Changing the silent-fallback behavior or the auto-loop behavior would require editing `video.py`, which is upstream MoviePy assembly code that Principle II keeps rebase-clean. v1 inherits these behaviors and acknowledges them as v1 limitations (see Edge Cases). When the Step 3 mode registry rewrites the audio path, those behaviors can be re-evaluated.
- **The wizard does NOT preview audio in-browser at v1.** Audio preview requires an HTML5 `<audio>` element loading the uploaded file, which works but adds UX surface (loading states, browser-codec-compat issues, permission prompts on some browsers). v1 ships without preview; the creator hears the music for the first time in the rendered output. v2 may add a preview button.
- **The 10 MB upload cap is a soft limit, not a hard architectural one.** A 5-minute MP3 at 192 kbps is ~7 MB; 10 MB covers most realistic short-ad music. If creators routinely hit the cap, raise it before adding compression / bitrate-handling complexity.
- **Spec 009 (visual overlays) and this spec (music) are independent and parallel-deliverable.** They share the same upload-endpoint pattern but no files. Both can ship simultaneously; the order matters only for the operator's review queue.
- **Mode 2 is the only consumer at v1.** Modes 1, 3, 4, 5 inherit the same `bgm_*` fields when they ship via their own VisualAI feature branches. The wizard surface for music is per-mode.
- **No multi-tenant isolation at v1.** Audio uploads land in the same shared `storage/uploads/` dir as logo uploads. Tenant scoping arrives in Step 2 of the build plan via debt #2 burndown — at which point both audio and logo uploads scope per-tenant via the same path-rewrite.
- **A single music track per render at v1.** No layered music, no music+SFX combination, no per-section soundtrack changes. The audio mixing pipeline supports exactly one BGM track and one voiceover; that's enough for short-form ad content.
- **Default volume of 20 % preserves voice intelligibility on most listening environments.** This is the value MPT has shipped since upstream and matches studio mixing conventions for V/O over BGM. The 80 %-warning threshold is a creator-protection signal, not a hard cap.

## Dependencies

- This feature touches three fork-surface files (`app/controllers/v1/uploads.py` (extended OR a new sibling file), the wizard `page.tsx`, and `visualai-frontend/src/app/api/upload-audio/route.ts` (new)) — and ZERO other Layer 3 files. `app/services/video.py` is deliberately not touched (Principle II).
- This feature does NOT add new fields to `VideoParams`. It uses the existing `bgm_type`, `bgm_file`, `bgm_volume` fields ([app/models/schema.py:101-103](../../app/models/schema.py#L101-L103)).
- Spec 009's `POST /api/v1/uploads/logo` endpoint pattern is reused for `POST /api/v1/uploads/audio` — same controller, different file-type validation. The two upload endpoints SHOULD share a common multipart-validation helper to avoid drift between visual and audio upload behavior.

## Constitutional Impact

| Principle | Impact | Mitigation |
|---|---|---|
| **I. Layer 3 Scope** | None — exposing existing render-engine capability through Layer 1; no user / billing logic added. | n/a |
| **II. Surgical Fork Discipline** | The new audio upload endpoint lives in the fork-surface controllers directory (allowed). The existing audio mixing in `app/services/video.py` is **explicitly NOT modified** — silent-fallback behavior on mixing failure is inherited, even though it's the kind of behavior FR-013 of spec 009 forbids for visual overlays. The asymmetry is justified: video.py is upstream code that MUST stay rebase-clean. The audio side will get the same loud-fail treatment when Step 3's mode registry rewrites the audio path. | Documented in §Edge Cases; deferred to Step 3. |
| **III. Multi-Tenant Context Propagation** | Audio uploads at v1 land in shared `storage/uploads/` without tenant scoping — same shared infrastructure as spec 009's logo uploads. Continuation of debt #2. | Piggybacks on existing #2; no new debt. |
| **IV. External Asset Acceptance** | None — audio comes from user uploads (filesystem) or bundled `resource/songs/` (filesystem). No external API calls. | n/a |
| **V. Mode-Aware Rendering Contract** | Music UI is wired into Mode 2 directly via the wizard, not via the (yet-to-exist) `app/services/modes/` registry. Continuation of debt #4. | Piggybacks on existing #4; no new debt. |

**Net constitutional impact**: zero new debts. Two existing debts (#2, #4) gain one more burndown task each.

## Cross-references

- [Spec 009 — Brand Overlays](../009-brand-overlays/spec.md) — this feature's sibling. Both share the upload-endpoint pattern; spec 009's `Clarifications` section explicitly references this feature as the audio-side counterpart.
- [5-step build plan](/Users/amraeid/.claude/plans/can-you-confirm-that-dapper-emerson.md) — Step 5 anticipates "Brand library with visual memory (persisted product assets)"; this feature's `bgm_file` accepts the same Brand Library path shape.
- [Constitution v1.0.2](.specify/memory/constitution.md) — Principle II governs why `app/services/video.py` is not touched; §Constitutional Impact above documents the asymmetry vs. spec 009's loud-fail expectation.
- [STEP1_DEBT.md](../../STEP1_DEBT.md) — debts #2, #4 each gain one more burndown task via this feature.
- [app/services/video.py:545-557](../../app/services/video.py#L545-L557) — the existing BGM mixing implementation that this feature exposes through the wizard.
- [app/models/schema.py:101-103](../../app/models/schema.py#L101-L103) — the existing `bgm_type` / `bgm_file` / `bgm_volume` fields on `VideoParams`.
