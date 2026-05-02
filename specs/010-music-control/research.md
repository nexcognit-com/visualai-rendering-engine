# Phase 0 Research: Music Track Control + Custom Uploads

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**: 2026-05-02

## R1 — Audio duration probe at upload time

**Decision**: Use `ffprobe -v quiet -show_entries format=duration -of csv="p=0" <file>` invoked via `subprocess` in the upload endpoint. ffprobe is a metadata-only call — it parses the container header without decoding audio, so it returns in single-digit milliseconds even for 10 MB files. Fall back to MoviePy's `AudioFileClip(path).duration` if ffprobe is missing for any reason (ffprobe is part of FFmpeg, which is a hard system requirement per the constitution; the fallback is defensive).

**Rationale**: the wizard's `duration_seconds` hint (FR-006, FR-012) needs to be available at upload time so the wizard can display "your track is 30 s — it will loop ~3× across a typical 90 s render" before the creator submits. ffprobe is fastest because it doesn't decode samples; MoviePy is acceptable as a fallback because it's already in the pipeline. Both produce the same float seconds output for valid containers.

**Alternatives considered**:
- **Pillow-equivalent for audio (`mutagen`)** — pure-Python tag library, would avoid the subprocess. Rejected: adds a new dependency; mutagen's coverage of containers is narrower than FFmpeg's; we already require FFmpeg as a hard system dep.
- **Skip duration display entirely** — simpler endpoint. Rejected: spec FR-012 explicitly requires the wizard to show duration so the creator knows whether the track will loop or be truncated.
- **Compute duration client-side via HTML5 `<audio>.duration`** — moves work out of the server. Rejected: requires loading the file into a `<audio>` element with metadata-only preload; cross-browser flaky (iOS Safari needs user-gesture for some `<audio>` events); creates a race with the upload flow.

## R2 — Audio MIME validation strategy

**Decision**: Two-layer validation. **Layer 1**: validate the `Content-Type` header sent by the browser against the allowed MIME set `{"audio/mpeg", "audio/wav", "audio/x-wav", "audio/ogg", "audio/mp4"}`. **Layer 2**: regardless of Content-Type, attempt the duration probe (R1) — a successful probe means FFmpeg recognizes the container, which is the authoritative truth. Reject with HTTP 415 `invalid_audio` if the probe fails.

**Why two layers**: browsers are inconsistent in setting Content-Type for audio (Chrome sends `audio/mpeg` for MP3, Firefox sometimes sends `audio/mp3`, Safari can send `audio/x-mpeg-3`). The MIME check filters obvious wrong types (e.g., a `.txt` upload claiming `text/plain`); the probe is the real validator.

**Allowed extensions** (mapped from validated MIME):

| MIME | Extension |
|---|---|
| `audio/mpeg` | `.mp3` |
| `audio/wav`, `audio/x-wav` | `.wav` |
| `audio/ogg` | `.ogg` |
| `audio/mp4` | `.m4a` |

**Rationale**: covers the four formats spec FR-003 lists. M4A → `audio/mp4` is the standard MIME (M4A files are MPEG-4 Part 14 containers with audio-only AAC payload). Following the convention establishes naming consistency with how MP3/WAV/OGG are handled.

**Alternatives considered**:
- **MIME-only validation** — fastest, but caught nothing when the browser sends the wrong Content-Type (which happens routinely). Rejected.
- **Probe-only validation** — sufficient for correctness but slower (subprocess on every request, even for clearly-wrong files). Two-layer keeps the cheap rejection path for obvious bad input.
- **Magic-byte sniffing in Python** (`python-magic`) — adds a dep; FFmpeg already does this internally during the probe. Reject as redundant.

## R3 — Volume mapping (UI 0–100% → backend 0.0–1.0)

**Decision**: Linear mapping. Wizard volume slider produces an integer 0–100; the API client divides by 100.0 to produce a float 0.0–1.0; backend stores in `params.bgm_volume`. Default UI slider position: 20 (matches MPT default 0.2). The 80%-warning threshold (FR-004) fires at slider position ≥ 80.

**Rationale**: simplest possible mapping. MPT's `MultiplyVolume(params.bgm_volume)` is a linear amplitude multiplier (not perceptual loudness), so a linear UI slider is honest about what the math does. A perceptual-loudness slider (e.g., dB-based with -inf to 0 dB range) would be more "audio-engineer-correct" but obscures the math from creators who just want "more or less music."

**Edge values**:
- Slider at 0 → `bgm_volume = 0.0` → no audible music. Equivalent to picking "None" but with a known track loaded (creator can drag back up later without re-uploading).
- Slider at 100 → `bgm_volume = 1.0` → music at full strength alongside voiceover. The wizard's ≥80 warning protects against this.
- Slider at default 20 → `bgm_volume = 0.2` → MPT's existing default. Renders without explicit music control land here too (FR-010 no-regression).

**Alternatives considered**:
- **dB-based slider** with -∞ to 0 dB range and a default at -14 dB (broadcast loudness target for V/O over BGM). Rejected: requires creators to understand dB; the mapping to MPT's linear `MultiplyVolume` would be confusing (`-14 dB ≈ 0.2 amplitude`).
- **Three-tier preset (low/medium/high)** — radically simpler UI but loses the granular control creators with branding goals want. Slider preserves more user agency for the same code complexity.

## R4 — No-regression strategy for legacy callers (FR-010, SC-007)

**Decision**: The wizard's `/api/generate` route conditionally includes `bgm_type` / `bgm_file` / `bgm_volume` in the request body **only when the music panel was actively configured by the creator**. If the creator never opens the music panel (or leaves it at the auto-default), no `bgm_*` fields are sent. MPT's `VideoParams` Pydantic model fills the defaults (`bgm_type="random"`, `bgm_file=""`, `bgm_volume=0.2`) — exactly today's behavior.

This means:
- Renders submitted without the new music UI → byte-identical audio output to today's pipeline.
- Direct API consumers (non-VisualAI) hitting `/api/v1/videos` directly → unchanged behavior.
- Renders submitted through the new music UI → new `bgm_*` values applied.

**Rationale**: zero-regression is a hard constraint (SC-007). The cleanest way to guarantee it is to not send fields when the creator hasn't expressed an opinion. Pydantic defaults preserve every existing field's semantics.

**Alternatives considered**:
- **Always send `bgm_*` fields with hardcoded defaults**: simpler client code but introduces regression risk if MPT's defaults ever change in an upstream rebase. The explicit "only-send-when-configured" rule keeps the contract independent of upstream defaults.
- **Toggle on the wizard's first paint** to "creator chose Random + 20%" by default and always send those values: visually identical from the creator's perspective, but fails the byte-equivalence test because the wizard now generates `bgm_volume=0.2` explicitly even when the creator never touched the slider — different from "field omitted, Pydantic defaults to 0.2." The two paths happen to produce the same render today but the contract isn't byte-equivalent. Rejected for testability.

## R5 — Endpoint-shape parity with spec 009's logo upload

**Decision**: `POST /api/v1/uploads/audio` mirrors `POST /api/v1/uploads/logo` in shape — multipart form with field name `file`, server-side UUID4 filename, MIME-derived extension, 201 response with `{path, size_bytes, mime_type}`. The audio variant adds one extra field: `duration_seconds: float`. The validation order is identical except step 5 ("open with Pillow to verify image") is replaced with step 5 ("probe with ffprobe to verify audio duration").

**Rationale**: keeping the two endpoints structurally identical reduces the cross-spec coordination cost (spec 009 owns the file; this spec extends it). The shared `_validate_upload(file, allowed_mimes, max_bytes)` helper documented in [plan.md §Cross-spec coordination](./plan.md) deduplicates the MIME + size validation for both endpoints.

**Alternatives considered**:
- **Separate file `app/controllers/v1/uploads_audio.py`** — would put the audio endpoint in its own module. Rejected: every uploaded asset is a file; one controller for "uploads of any kind" is more cohesive than splitting by media type.
- **Generic `POST /api/v1/uploads/{kind}`** with `kind` as a path param — too clever. Path params for type discrimination work well for resource hierarchies; here the validation rules differ enough (MIME tables, probe step, response shape) that separate endpoints are clearer.

## R6 — Bundled BGM track naming for the wizard dropdown

**Decision**: Read the file list from `resource/songs/` at server start, expose via a new `GET /api/v1/bgm/tracks` endpoint returning `[{name: "output042", path: "resource/songs/output042.mp3", duration_seconds: 138.4}, ...]`. The wizard fetches the list once on Step 3 mount and renders it in the Music selector dropdown. Track names show the filename minus `.mp3` (e.g., "output042") at v1; we don't hand-curate human-readable titles for 29 tracks today.

**Rationale**: the bundled tracks have generic filenames (`output000.mp3` through `output028.mp3`) — no metadata to pull human-readable titles from. Hand-curating is a one-time content task that's out of scope here. The endpoint reads the list at request time so a new track dropped into `resource/songs/` is immediately available without redeploying the API.

**Alternatives considered**:
- **Expose the full path string in the dropdown** (e.g., `resource/songs/output042.mp3`). Rejected: leaks server filesystem layout to the browser; ugly UX.
- **Hardcode the track list in the wizard's TS code**. Rejected: drift risk if the bundled set changes; one source of truth on the server is cleaner.
- **Return the track list inline in `/api/generate`'s response** so the client has it already. Rejected: bloats the request that doesn't need it; conflates "start render" with "list tracks."

## R7 — Smoke test layout

**Decision**: One pytest test file at `test/controllers/test_uploads_audio.py` covering 8 contract acceptance tests (mirrors spec 009's `test/controllers/test_uploads.py`):

| Test | Scenario |
|---|---|
| AU-1 | Valid 1 s sine-wave WAV ≤ 10 MB | 201 with `path` + `duration_seconds ≈ 1.0` |
| AU-2 | Valid 1 s sine-wave MP3 | 201 with `.mp3` extension and `duration_seconds ≈ 1.0` |
| AU-3 | Valid OGG | 201 with `.ogg` extension |
| AU-4 | Valid M4A | 201 with `.m4a` extension |
| AU-5 | Valid format but 12 MB body | 413 `file_too_large` |
| AU-6 | `.flac` upload (unsupported MIME) | 400 `unsupported_format` |
| AU-7 | Bytes claiming `audio/mpeg` MIME but actually plain text | 415 `invalid_audio` |
| AU-8 | Filename `../../etc/passwd.mp3` | 201 with stored filename = UUID4.mp3 (path-traversal NOT preserved) |

Synthetic test fixtures use NumPy + scipy.io.wavfile to generate 1-second 440 Hz sine waves at 16-bit 44.1 kHz — a few KB each, no committed binary fixtures, fast to compile in `tmp_path`. MP3/OGG/M4A variants are produced via a pytest fixture that converts the WAV via `subprocess.run(["ffmpeg", "-i", wav, "-y", "out.mp3"])` (ffmpeg is required as a system dep so this is safe in test env).

**Rationale**: covers every validation branch of the upload endpoint; matches the constitution's "smoke test exercising the rendering path with mocked Layer 2 inputs" requirement; uses synthetic fixtures so the test doesn't ship binary blobs.

**Alternatives considered**:
- **Visual diff testing of rendered audio** (compare BGM-frequency-band loudness in two renders) — too slow for unit smoke; that's quickstart manual verification territory (SC-005).
- **Use bundled `resource/songs/output000.mp3` as the test fixture**: would skip the synthetic-generation step. Rejected: tightly couples test reliability to the bundled library; safer to generate on demand.

## R8 — Open follow-ups (not blockers for v1)

These are deferred to v2 or later:

1. **In-browser audio preview before submission** — HTML5 `<audio>` element with metadata-only preload; cross-browser flaky on iOS. Add when there's a testable preview-validation flow.
2. **Per-section music** (intro / outro / main) — only meaningful for Mode 3 (long-form). Will be specced inside the Mode 3 feature when that lands.
3. **Sidechain compression** (auto-duck music when voiceover is active) — requires real audio analysis; significant scope. Research item for v2+.
4. **Loud-fail on BGM mixing failure** — requires editing `app/services/video.py`, which Principle II forbids. Step 3's mode registry will rewrite the audio path naturally; this gets fixed there.
5. **Curated bundled-track titles** (replace `output042` with "Uplifting Piano" etc.) — content task, one-time; not blocking the wizard surface.
6. **Loudness normalization** (target -14 LUFS broadcast loudness) — requires a `loudnorm` FFmpeg pass; out of scope at v1's "static linear-volume-multiplier" model.

## Summary

All NEEDS-CLARIFICATION items resolved. No new runtime dependency (ffprobe is part of FFmpeg, already a system requirement). The audio upload endpoint mirrors spec 009's logo upload structurally; the wizard music panel reuses the same patterns; the existing BGM mixing pipeline in `video.py` is left untouched per Principle II. v1 zero-regression is preserved by the conditional-field-send pattern in the wizard's API call.
