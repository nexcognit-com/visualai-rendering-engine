# Feature Specification: Mode 3 long-form 10-minute cap + URL-expiry resilience + WebM selfie uploads

**Feature Branch**: `019-longform-10min-fix`
**Created**: 2026-05-09
**Status**: Draft
**Input**: User description: "Extend Mode 3 (long-form) duration cap from 5 minutes to 10 minutes, with URL-expiry fallback for longer renders. Includes the selfie-upload MIME/WebM-codec fix that surfaced during testing."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Pick a 10-minute target on Mode 3 long-form (Priority: P1)

A creator opens Mode 3 (Long-Form Video) to make a YouTube-format piece. The duration picker now offers 8-minute and 10-minute targets in addition to the 2/3/4/5-minute ones that existed before. They pick 10 minutes, write their subject, and dispatch. The render returns a single ~10-minute MP4 with the spec's 12–15s/shot pacing — meaning roughly 30–40 distinct visual segments, far more variety than the old 5-minute cap allowed.

**Why this priority**: This is the headline reach extension — without it, Mode 3 is capped below YouTube long-form territory and creators have no way to produce a 10-minute piece in one click. Delivering this alone unlocks an entire content surface (YouTube monetization-eligible long-form ads earn at higher CPM than ≤5-min spots).

**Independent Test**: Open the wizard, pick Mode 3, choose 10-minute duration, enter any valid subject, dispatch. Within the wall-clock budget for 10-min renders, verify (a) the resulting MP4 plays end-to-end at ~600 seconds ±5s, (b) subtitles align across the full duration, (c) the segment count lands in the 30–40 range, (d) no single segment exceeds the 12–15s pacing target.

**Acceptance Scenarios**:

1. **Given** the wizard's Mode 3 picker is open, **When** the creator views the duration choices, **Then** 8-minute (480s) and 10-minute (600s) options are visible alongside the existing 2/3/4/5-minute options.
2. **Given** the creator selects the 10-minute duration, **When** they dispatch a render with a typical subject, **Then** the orchestration layer accepts the request without rejecting it as "duration out of range".
3. **Given** a 10-minute render completes, **When** the creator plays the result, **Then** the visual variety is materially higher than a 5-minute render of the same subject — segment count is in the 30–40 range, not capped at 25.
4. **Given** a 10-minute render is dispatched, **When** the wizard polls for completion, **Then** the wizard's poll timeout is long enough to outlast the render (does not time out before the render finishes).

---

### User Story 2 — A long render survives a paused/throttled fetch step (Priority: P2)

A creator dispatches a long Mode 3 render (5–10 minutes target) from a laptop that subsequently sleeps, hibernates, or otherwise stalls between the orchestration step that mints pre-signed clip URLs and the rendering step that fetches them. By the time the fetch step runs, some or all of those URLs have expired (HTTP 403 / 410 from the signing layer). The render does not die. Instead, each individual unfetchable segment is silently replaced by a same-duration black-frame placeholder, audio and subtitles stay aligned to the timeline, and the creator gets back a near-complete render with at most a few brief black gaps that they can re-roll selectively rather than re-running the full render from scratch.

**Why this priority**: This is the reliability backstop that makes the 10-minute cap usable in real conditions. Without it, the longer the render, the higher the probability that *some* URL expires before fetch — and the old behavior killed the entire render on the first such URL, wasting compute time and the creator's wait. P2 because P1 (the cap raise) is the visible feature; P2 is the non-negotiable supporting fix without which P1 would be unreliable on long renders.

**Independent Test**: Force the fetch step to encounter at least one 403 or 410 response on a pre-signed URL (e.g. by using an already-expired test fixture URL). Verify the render still produces a final MP4 of the correct total duration, with audio and subtitles aligned, and a black-frame placeholder of the segment's intended length where the failed URL was.

**Acceptance Scenarios**:

1. **Given** a render whose pre-signed URLs are valid except for one which returns 403 expired, **When** the fetch step runs, **Then** the failed segment is replaced by a black-frame placeholder of its target duration and the render completes normally.
2. **Given** a render in which two non-adjacent segments fail to fetch (both 410), **When** the render completes, **Then** total output duration matches the audio length within ±0.2s and subtitle cues stay aligned to the original timeline.
3. **Given** the fetch step encounters a transient 5xx error (not an expiry), **When** the second retry succeeds, **Then** no placeholder is written for that segment — the real clip is used.
4. **Given** every single URL in a render has expired, **When** the fetch step runs, **Then** the render still produces an output (an entirely-black-but-correct-duration video with valid audio and subtitles) rather than failing — the creator can re-dispatch with fresh URLs from there.

---

### User Story 3 — Record-in-browser selfie upload (Mode 4) accepts WebM (Priority: P2)

A creator uses Mode 4's in-wizard "Record selfie" affordance, which captures via the browser's MediaRecorder API. Modern browsers emit `Content-Type: video/webm;codecs=vp8` (or `;codecs=vp9`) — a codec parameter the upload validator did not previously recognize, which made every recorded selfie fail with a generic "Unsupported MIME" error before validation could even run. Recorded selfies now upload successfully on the first try, are stored as MP4 in the speaker-reference slot, and are immediately reusable in the Mode 4 wizard.

**Why this priority**: Same severity as Story 2 — a P1-blocking defect for the most common Mode 4 capture path (record-in-browser). Without it, every browser-recorded selfie fails and the creator has to fall back to recording elsewhere and uploading the file. P2 because Mode 4's record-in-browser flow is itself an additive UX over the upload-a-file flow; the upload flow worked before this fix.

**Independent Test**: Open Mode 4 in a Chromium-based browser, click "Record selfie", record 5–15 seconds, click upload. Verify the upload returns success (not "Unsupported MIME"), the file is persisted as MP4, and the creator can immediately use it as the speaker reference for a render.

**Acceptance Scenarios**:

1. **Given** a browser MediaRecorder emits `Content-Type: video/webm;codecs=vp8`, **When** the upload validator inspects the MIME, **Then** it strips the codec parameter, recognizes `video/webm`, and proceeds to validation.
2. **Given** the upload payload is a valid WebM (VP8 or VP9), **When** the file is persisted, **Then** it is stored as MP4 (re-encoded to H.264) so downstream lip-sync engines that expect H.264 input read it without a transcoding step at render time.
3. **Given** an uploaded WebM contains an audio track, **When** the file is persisted as MP4, **Then** the audio track is dropped (Mode 4 narration is synthesized from the script — the selfie's audio is not used).
4. **Given** the uploaded MIME really is unrecognized (e.g. `image/png`), **When** validation runs, **Then** the error message reports the original full content-type string so the creator can see what they actually sent.

---

### Edge Cases

- **A 10-minute render's wizard poll timeout is too short.** The wizard must allow enough polling headroom for ~50–70 minutes of render wall-clock on M-series silicon (no NVIDIA assumed); a poll timeout shorter than that would falsely report timeout on a successful render.
- **Black-frame fallback also fails** (disk full, ffmpeg missing, write permission denied). The render genuinely cannot recover and surfaces an explicit `material.fetch_failed` error — the placeholder is a backstop, not a catch-all.
- **Every URL expires AND the network itself is also down.** The render still produces a fully black output — the creator sees that all segments are placeholders and can decide to re-dispatch with fresh URLs.
- **Audio shorter than total intended visual duration** (rare, but possible if TTS truncates) — alignment math uses the audio length as the source of truth; placeholders are sized to match the original visual segment durations, not stretched to fill any gap.
- **Recorded-in-browser selfie has a MIME the codec-strip path turns into something the validator still doesn't recognize** (e.g. `audio/webm`). Validator rejects with the original full content-type string so the creator can read what their browser sent.
- **MKV file uploaded from desktop** — same re-encode path as WebM (cannot stream-copy non-H.264 into MP4); transcodes to H.264, drops audio, succeeds.
- **Creator picks 8 minutes** instead of 10 — same code path; segment count target sits between the 5-minute and 10-minute envelopes; no special-case logic.
- **A single segment's target duration is unknown to the fetch step** when it has to write the placeholder — placeholder defaults to a safe fixed duration (5s) and the timeline-alignment step downstream stretches/clips audio to the actual visual length.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Mode 3 (Long-Form Video) MUST accept duration targets of 120, 180, 240, 300, 480, and 600 seconds. The previous 300-second cap is lifted to 600 seconds. Selecting 600 seconds at the wizard MUST flow through to the orchestration layer and the rendering layer without rejection at any boundary.
- **FR-002**: Mode 3's segment-count envelope MUST scale with the new cap — the 10-minute target requires up to 40 distinct visual segments at the spec's 12–15s/shot pacing. The previous 25-segment ceiling MUST be raised to 40.
- **FR-003**: When the rendering layer fetches a pre-signed clip URL and receives HTTP 403 or 410, the layer MUST treat that URL as expired and stop retrying. Retry budget is reserved for transient 5xx, not for a dead signature.
- **FR-004**: When a pre-signed clip URL cannot be fetched (expired per FR-003, or otherwise after the retry budget is exhausted), the rendering layer MUST write a black-frame MP4 placeholder of the failed segment's target duration in place of the missing clip and continue the render. The placeholder MUST be readable by the downstream assembly step — operationally: a single-stream MP4 with codec H.264, pixel format yuv420p, no audio track, and duration matching the failed segment's target ± 0.05 seconds.
- **FR-005**: Each placeholder substitution MUST emit one structured log line at WARNING level (loguru `logger.warning`) — not silently swallowed, not raised as a fatal error. The line MUST include the clip index, the URL truncated to 80 characters, and the underlying fetch error string, so operators can grep per-render placeholder ratios.
- **FR-006**: When placeholder substitution itself fails (e.g. ffmpeg invocation errors, disk full), the rendering layer MUST fail the render with a clear `material.fetch_failed` error rather than producing a malformed asset. The placeholder is a backstop, not a guaranteed-success path.
- **FR-007**: After all per-segment fetches finish (whether real or placeholder), audio and subtitle cues MUST remain aligned to the original timeline — placeholder segments occupy exactly the same time slots they would have if the fetch had succeeded.
- **FR-008**: The selfie-upload validator (Mode 4 speaker reference) MUST strip codec parameters from the request's `Content-Type` header before looking up the MIME in its allow-list. A request with `Content-Type: video/webm;codecs=vp8` MUST resolve to the same accepted entry as `Content-Type: video/webm`.
- **FR-009**: When the uploaded selfie is WebM or MKV, the system MUST re-encode the video to H.264 (yuv420p) before persisting as the canonical MP4 speaker reference. The audio track MUST be dropped during this step. Stream-copy is not acceptable for these formats because VP8/VP9 cannot live in an MP4 container.
- **FR-010**: If the upload validator rejects a request as MIME-unsupported, the error message MUST report the original (un-stripped) content-type string so the creator can debug what their client actually sent.

### Key Entities

- **Pre-signed clip URL**: a single-use download URL minted by the orchestration layer with an embedded expiry. Carries the segment's intended target duration as out-of-band metadata so the rendering layer knows what placeholder length to write if the URL is dead. State transitions: `valid → expired (403/410)`. Once expired, regeneration requires re-running the orchestration step that minted it.
- **Black-frame placeholder clip**: a same-duration MP4 written in place of an unfetchable real clip. Single black 1280×720 30fps frame stretched to the segment's target duration via a constant-color filter; no audio. Indistinguishable from a real clip downstream.
- **Speaker Reference (Mode 4, upload variant)**: the multi-format selfie a creator records or uploads, persisted into the Speaker Reference slot defined in spec 018 (FR-014). Acceptable input formats: MP4, MOV, WebM (VP8/VP9), MKV. Canonical persisted form: H.264 MP4 with no audio track. Provenance: tenant + user + slot index per the Mode 4 hybrid persistence model.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Creators can dispatch Mode 3 renders at 10-minute target duration end-to-end through the wizard. The 8/10-minute options appear in the duration picker, the orchestration layer accepts the request, the rendering layer produces a single MP4 of the requested duration ±5 seconds, and the wizard reports completion without timing out.
- **SC-002**: For Mode 3 renders at 10-minute target, segment count lands in the 30–40 range — meaningfully higher visual variety than the prior 25-segment ceiling, measured by counting distinct visual cuts in the output.
- **SC-003**: A 10-minute Mode 3 render whose fetch step encounters 1–2 expired pre-signed URLs (out of ~30–40 segments) MUST still produce a usable final MP4. "Usable" = correct total duration ±0.2s, audio and subtitle alignment intact, ≤5% of total wall-clock time spent in black-frame segments.
- **SC-004**: When every pre-signed URL in a render has expired, the render still produces a syntactically valid MP4 of correct duration with intact audio and subtitles — entirely black visually, but recoverable by re-dispatching from the orchestration layer rather than restarting the full render. (This is an upper-bound resilience guarantee; the typical case is 0–2 expirations.)
- **SC-005**: 100% of valid in-browser-recorded selfies (WebM with VP8 or VP9 codec, 5–60 seconds, single visible face) upload successfully on first attempt. The previous 100% failure rate on browser-recorded WebM is fixed.
- **SC-006**: When a creator uploads a genuinely unsupported file type (e.g. PNG, GIF, plain text), the rejection error message includes the original full `Content-Type` string the client sent — measured by inspecting the error payload returned to the wizard for at least 3 distinct unsupported types.

## Assumptions

- **Reference hardware**: render-time math (10-min target → ~50–70 min wall-clock) is calibrated for M-series silicon without NVIDIA acceleration. On NVIDIA GPUs the wall-clock will be lower; the wizard's poll timeout (75 min) is sized for the slower path, so the GPU path is comfortably under it.
- **Twelve Labs cost envelope**: per-render Twelve Labs cost stays under the existing $1 budget at the 10-minute target (~$0.50–0.65 typical), so the cap raise does not require a billing or rate-limit review.
- **Pre-signed URL TTL**: a paired orchestration-layer change extends the URL TTL during long renders, making 403/410 expirations rare in practice. The black-frame fallback in this spec is the safety net for the residual cases (laptop sleep, network throttle, abnormally slow render); it is NOT a substitute for the TTL bump.
- **Black-frame placeholder dimensions**: 1280×720 at 30fps is sufficient because the assembly step downstream re-scales to the output's target aspect ratio; the placeholder's intrinsic size does not need to match the real clips.
- **Mode 4 selfie audio is irrelevant**: dropping the audio track during WebM→MP4 re-encode is acceptable because the lip-sync pipeline synthesizes narration from the script (per spec 018); the selfie's original audio was never used.
- **Browser MediaRecorder behavior**: modern Chromium-based browsers emit `video/webm;codecs=vp8` by default; Firefox and Safari emit similar codec-suffixed MIMEs. The codec-stripping fix is browser-agnostic — any client that conforms to RFC 7231 §3.1.1.1 (MIME parameters separated by `;`) is handled.
- **No per-tenant rate-limit changes**: the duration-cap raise does not, by itself, change render concurrency or per-tenant rate limits; capacity planning at the orchestration and rendering layers is unchanged.
- **Existing alignment math reused**: the rendering layer's audio-length-driven timeline math is the same that already aligns Mode 2 and previous Mode 3 outputs. Black-frame placeholders consume their nominal segment duration; no new alignment logic is introduced.
- **L1 wizard poll timeout** (out of L3 scope): the `visualai-frontend` wizard polls the render task with a timeout sized to outlast a 10-min render on M-series hardware (75 minutes — was 40, paired-bumped with this branch's L3 work). Enforced at L1; verified end-to-end by Journey A in `quickstart.md`, not by an L3 unit test. Tracked in the `visualai-frontend` repo.
