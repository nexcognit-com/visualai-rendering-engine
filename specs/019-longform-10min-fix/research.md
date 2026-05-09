# Phase 0 Research: Mode 3 long-form 10-minute cap + URL-expiry resilience + WebM selfie uploads

**Feature**: `019-longform-10min-fix` | **Date**: 2026-05-09

This feature has no `[NEEDS CLARIFICATION]` markers in the spec. The decisions below are the ones the implementer made before shipping commits `c124ebb` and `e817809`; they are documented here so future readers (and `/speckit-analyze`) can see what was rejected and why.

## Decision 1 — Black-frame placeholder format

**Decision**: 1280×720 @ 30fps, libx264 veryfast preset, yuv420p, no audio track. Generated via FFmpeg `lavfi color` filter (`color=c=black:s=1280x720:r=30:d={duration}`).

**Rationale**:
- 1280×720 is large enough that the assembly step's downscale path (which always re-scales to the output's target aspect) does not visibly upsample. Smaller (e.g. 320×180) would cost nothing to encode but risks measurable quality loss if downstream code ever switches to upsampling.
- 30fps matches the project's standard render fps; using 24/25/60 would force a frame-rate conversion at concat time.
- `lavfi` synthesizes the frame in-process — no input file, no temp PNG, no extra dependency on Pillow/ImageMagick.
- `veryfast` preset because the placeholder's visual quality is irrelevant; faster encode is the only thing that matters.

**Alternatives considered**:
- **Match the failed segment's exact resolution** — rejected. Assembly always re-scales to the output target; matching adds complexity with no visible benefit.
- **Include a silent audio track** — rejected. The downstream concat step pulls audio from the master narration track, not from individual clips. Embedding silent audio risks demuxer confusion ("two audio streams at concat point") for no upside.
- **Use a 1×1 px clip then upscale** — rejected. The lavfi color filter generates the requested size directly; "tiny then upscale" adds a filter chain stage with no benefit.

## Decision 2 — HTTP 403 vs 410 handling

**Decision**: Treat both as terminal (no retry). Break out of the retry loop and fall through to the placeholder substitution path.

**Rationale**:
- 403 is the canonical S3-style "pre-signed URL signature expired" response (AWS S3, Cloudflare R2, Google GCS in S3-compatible mode all emit 403 with `<Code>AccessDenied</Code>` for expired signatures).
- 410 is the canonical "gone" response. Some providers emit 410 instead of 403 when the underlying object has been deleted while the URL is still nominally valid.
- Neither has any chance of succeeding on retry — the URL signature itself is dead, and L3 has no path to mint a fresh one.
- Spending the retry budget on these statuses delays the placeholder substitution (and therefore overall render time) for no benefit.

**Alternatives considered**:
- **Retry once on 403** — rejected. Wasted ~30 seconds (request timeout) per dead URL with no chance of recovery.
- **Distinguish 403 from 410 in the placeholder log** — minimal benefit; the warning log already captures the status code in the original `RuntimeError` text. Not worth a code-path branch.
- **Re-fetch the URL through L2 to get a fresh signature** — rejected per Constitution §IV. L3 must not call out to L2 for asset-generation purposes; L2 is the producer of pre-signed URLs and L3 is the consumer. A fresh-URL path would invert that contract.

## Decision 3 — WebM → MP4 conversion strategy

**Decision**: Re-encode video to H.264 (yuv420p), drop audio. Specifically:

```
ffmpeg -i <upload> -c:v libx264 -pix_fmt yuv420p -an <out.mp4>
```

**Rationale**:
- VP8 and VP9 (the codecs WebM ships with from MediaRecorder) cannot be stream-copied into an MP4 container — the MP4 muxer accepts only a small set of codecs (H.264, H.265, MPEG-4 Part 2, ProRes, etc.). Stream-copy fails with "could not find tag for codec vp8" / "vp9".
- Downstream lip-sync (MuseTalk per spec 018) reads H.264 MP4. A persisted speaker-reference that was not transcoded would force the lip-sync stage to invoke FFmpeg again at render time — duplicating work.
- yuv420p (rather than yuv444p or yuv420p10) is what consumer devices and browsers expect for MP4 playback. Matches the format MuseTalk's reference pipeline assumes.

**Alternatives considered**:
- **Stream-copy (`-c copy`)** — rejected. Was the original code path; silently failed on every browser-recorded WebM. The bug this commit fixes.
- **Keep the audio track** — rejected. MuseTalk synthesises narration from the script, so the selfie's audio is unused. Carrying it forward risks: (a) operator confusion when the speaker-reference plays back with the user's actual voice, (b) downstream demuxer issues if any future stage assumes mute speaker references.
- **Re-encode to H.265** — rejected. Larger compatibility surface to test, no measurable quality benefit at this resolution / duration, and MuseTalk's reference path is calibrated against H.264.

## Decision 4 — Segment count upper bound at the 10-minute cap

**Decision**: Raise `segment_count_range` upper bound from 25 to 40.

**Rationale**:
- Mode 3's pacing target is 12–15 seconds per shot. At 600s output and the 12s lower bound, you get 50 segments; at 15s upper, 40 segments. Picking 40 as the upper bound lands near the middle of that envelope.
- The 25 cap, inherited from the 5-minute era (300s / 12-15s = 20–25 segments), would force the assembly step to extend individual shots beyond 15s at the 10-min target — visually flatter than what the spec promises.

**Alternatives considered**:
- **50 (max of the pacing envelope)** — rejected. Pushes Twelve Labs visual-relevance cost toward the upper edge of the $1 budget envelope and creates more rapid-cut "stock footage soup" feel.
- **Leave 25 unchanged** — rejected. Forces the assembly to repeat segments or stretch them past the pacing target at 10-min duration, producing visibly slower long-form output than spec.
- **Per-duration scaling table** (e.g. 25 for 5min, 32 for 8min, 40 for 10min) — rejected. Adds configuration complexity without meaningfully improving the result; the 8-minute target lands within 8/40 = 12s/shot lower-bound to 8/30 = 16s upper, which is acceptably close to the 12–15s target without per-duration tuning.

## Decision 5 — Wizard poll timeout 40 → 75 minutes

**Decision** (paired L1 commit, recorded here for completeness): bump the wizard's render-poll timeout from 40 minutes to 75 minutes.

**Rationale**:
- 10-min Mode 3 wall-clock on M-series hardware is 50–70 minutes (linear scale from 5-min target's 25–35 min). A 40-min poll timeout falsely reports "render timed out" on every successful 10-min render.
- 75 min gives ~7% headroom over the calibration upper bound. Keeps the wizard from giving up while a render is genuinely still running.

**Alternatives considered**:
- **120 min (double the upper bound)** — rejected. Excessive headroom encourages the wizard to keep polling on genuinely stuck renders rather than surfacing the failure to the creator.
- **Per-duration timeout** (40 min for ≤5 min target, 75 for ≥8 min) — rejected. Extra configuration plumbing without a concrete failure mode it solves; the 75-min flat ceiling is acceptable on shorter renders too (poll just stops earlier when complete).

## Decision 6 — Spec 008 credit-refund deferral on render failure

**Decision** (carried from spec 018 FR-011, restated here): credit-refund obligation on a render that ends in a black-only output is deferred to spec 008. This feature does not introduce a refund path.

**Rationale**: Constitution §I prohibits credit business logic in this layer. The orchestration layer (Layer 2) and the credit ledger (Layer 4) are the right places for refund decisions, and spec 008 is the active workstream for that. Logging the placeholder-substitution event is sufficient for L2 to consume when 008 lands.

**Alternatives considered**:
- **Pre-emptively emit a "render-degraded" event from L3** — rejected. Adds a new event surface that L2 cannot yet consume; would be dead code until spec 008.
- **Reject placeholder-heavy renders outright** (e.g. fail if >25% of segments fell back) — rejected. Defeats the whole point of resilience; better to ship the salvaged render and let the creator decide whether to re-roll.
