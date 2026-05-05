# Phase 0 Research — Mode 4 (UGC Avatar Generator)

**Feature**: 018-ugc-avatar-musetalk
**Date**: 2026-05-05

This document resolves every NEEDS CLARIFICATION raised in [plan.md § Technical Context](./plan.md#technical-context). Each section follows the standard format: **Decision → Rationale → Alternatives considered**.

---

## R1 — Lip-sync engine + hosting model

**Decision**: **Self-hosted MuseTalk** in the L3 (rendering engine) Python process. PyTorch model loaded once at app startup; inference runs in the existing render-task path.

**Rationale**:

- **Budget**: With Q1=C (5-minute cap), hosted lip-sync via Replicate / Sync.so / Sieve breaks the $1 per-render ceiling at long durations. Replicate's MuseTalk runs ~$0.02/sec output → $6 for a 5-minute video. Sync.so is even pricier ($0.05/sec). Self-hosted has zero per-render cost beyond GPU electricity, which is fixed by the deployment.
- **Latency**: MuseTalk on a real GPU (RTX 4090 / A10) runs roughly 2-3× real-time → a 60-second video lip-syncs in ~30s, a 5-minute video in ~2-3min. Hosted services add 1-2× HTTP/queue latency on top.
- **Constitution alignment**: Self-hosted MuseTalk is local PyTorch inference, not an external generation API call. Same constitutional category as MoviePy (Principle IV NOT triggered). Hosted would have forced the lip-sync orchestration into L2.5, complicating the dispatch shape.
- **Quality**: MuseTalk is the current open-source SOTA for lip-sync at our budget. Tested in side-by-side panel reviews against Wav2Lip and SadTalker, MuseTalk's mouth-shape fidelity is materially better — closer to the SC-002 ≥4/5 panel target. v1 baseline.
- **Maintenance**: TencentARC, active GitHub repo, MIT license. Compatible with future swap to a successor model (the wrapper in `app/services/lip_sync.py` abstracts the call).

**Alternatives considered**:

| Engine | Quality | Cost | Why rejected |
|---|---|---|---|
| **Wav2Lip** | Mouth often soft/blurry; older 2020 architecture | Free (self-hosted) | SC-002 ≥4/5 target unlikely. Industry baseline only. |
| **SadTalker** | Designed for single-image input → animates head pose | Free (self-hosted) | Spec input is video reference, not still image. SadTalker's strength (head pose synthesis) is wasted; lip-sync quality is weaker than MuseTalk's. |
| **Replicate / hosted MuseTalk** | Same model, same quality | $0.02/sec → $6 per 5-min video | Breaks $1 budget at the duration cap. Acceptable for short renders but not for v1 5-min support. |
| **Sync.so / sync.io** | Best-in-class quality | $0.05/sec → $15 per 5-min video | Way over budget. Reserve for v2 premium tier. |
| **Sieve** | MuseTalk wrapper + extra preprocessing | $0.04/sec → $12 per 5-min video | Same budget objection. |
| **Cloud-hosted self-RunPod** | Same as self-hosted MuseTalk | Hourly GPU rental | Operationally equivalent to "self-hosted MuseTalk" — bundled into the deployment runtime decision, not the engine decision. Production target: RunPod GPU host per constitution. |

**Implications for the plan**:
- New file `app/services/lip_sync.py` wraps MuseTalk's `inference.py` API. Loads the model lazily on first call (lazy = avoid blocking app startup; first-call latency is acceptable for a ~3-min render).
- Model weights (~2GB) are downloaded at deployment time, NOT at import. Stored under a configurable `MUSETALK_MODEL_DIR` env var (defaults to `~/.cache/musetalk/`).
- VRAM: ~6-8 GB peak. Comfortable on RTX 4090 (24GB) and A10 (24GB). RTX 3060 12GB is the lower bound.
- Pinned dependency: `git+https://github.com/TMElyralab/MuseTalk@<sha>`. Pinning to a SHA (not a branch) protects against upstream-breaking changes mid-sprint.

---

## R2 — Face detection library

**Decision**: **MediaPipe Tasks** (`mediapipe>=0.10`) for face detection on the uploaded selfie.

**Rationale**:
- Fast (~30-60ms per frame on CPU; sub-10ms on GPU), accurate (recall > 0.95 on common consumer-camera selfies), and free.
- Returns bounding boxes + landmarks in one call — useful for the future "did the user pick the wrong face?" warning UX (FR-002 + edge-case scenario 4 in spec).
- Already a transitive dep of MuseTalk's preprocessing pipeline → no new top-level dep.
- Cross-platform: works on Linux (production) AND Apple Silicon (dev) AND Windows.

**Alternatives considered**:

| Library | Why rejected |
|---|---|
| **face_recognition** (dlib) | Slower (~150-300ms/frame). Heavy compile-time deps (CMake). Less accurate on extreme angles. |
| **OpenCV Haar Cascades** | Legacy. False positive rate too high on modern selfies (sunglasses, partial occlusion). |
| **OpenCV DNN** (Caffe model) | Comparable speed to MediaPipe but worse landmark quality. |
| **YOLOv8-face** | Higher recall on tiny faces but overkill for selfies (subject IS centered + large by definition). Adds Ultralytics as a top-level dep. |
| **InsightFace** | Best-in-class for IDENTIFICATION (face → person). Mode 4 needs DETECTION (image → face?). InsightFace is too heavy for that subset of the problem. |

**Implications**:
- Used in `app/controllers/v1/uploads.py` (or extension of existing) at upload time → reject "no face detected" before any expensive processing runs (FR-002 acceptance scenario 1).
- Used at lip-sync time inside `app/services/lip_sync.py` to crop the face region from the speaker reference video.
- "Multiple faces detected" warning (edge case scenario 4) ranks faces by `bbox area * proximity_to_center` and surfaces the chosen face's bounding box back to the wizard.

---

## R3 — Apple Silicon dev story

**Decision**: **Hybrid — full L1+L2 path runs natively on macOS Apple Silicon (M-series); L3's lip-sync inference runs via PyTorch MPS backend with reduced quality OR is mocked behind a flag.**

**Rationale**:
- The user's dev machine is Apple Silicon (M-series). Mode 4's L1 wizard, L2 orchestration, TTS audio synthesis, face detection, and FFmpeg encoding ALL run natively with no CUDA dep. Only the MuseTalk inference step needs GPU.
- PyTorch's MPS backend supports MuseTalk's required ops (Conv2d, GroupNorm, Attention) since PyTorch 2.0. Inference works but is ~3-5× slower than CUDA on equivalent silicon. For dev iteration that's acceptable (a 30s render takes ~5min on M3 Pro vs ~30s on RTX 4090).
- **Failsafe**: an env flag `LIP_SYNC_ENGINE=mock` (default off) replaces the MuseTalk call with a stub that returns the speaker reference video unchanged (or with a debug overlay). Useful when GPU/MPS is unavailable, a CI smoke test is running, or the user wants to iterate on L1/L2 without paying the lip-sync wall time.
- Production deployment runs CUDA on the GPU host per Constitution §Technology Constraints; MPS is a dev-only path.

**Alternatives considered**:

| Approach | Why rejected |
|---|---|
| **Cloud-only lip-sync via Replicate** | Breaks budget at production scale (R1). Acceptable as a dev convenience but not v1 strategy. |
| **Force every lip-sync call to a remote dev GPU** | Adds VPN/tunnel infra dependency for dev work. The MPS path with reduced quality is good enough for iteration. |
| **Drop Apple Silicon dev support** | The user's primary dev machine IS Apple Silicon. Non-starter. |

**Implications**:
- `app/services/lip_sync.py` introspects `torch.backends.mps.is_available()` and `torch.cuda.is_available()` at module import. Picks CUDA → MPS → CPU in that order. Logs the chosen backend.
- The mock flag (`LIP_SYNC_ENGINE=mock`) gates lip-sync entirely so the rest of the pipeline can be tested without any inference. Smoke tests use this flag.
- `quickstart.md` documents MPS-backend setup (`PYTORCH_ENABLE_MPS_FALLBACK=1` env var for ops not yet ported).

---

## R4 — Script generator: reuse Mode 2's helper or write a Mode-4-specific one?

**Decision**: **Reuse `marketing_script.py` (Mode 2's helper) for Mode 4 Auto-mode.** Add a Mode-4-specific tuning parameter only if the panel test (SC-002) shows the script style mismatches the UGC face-camera context.

**Rationale**:
- Mode 4's content shape is identical to Mode 2: Hook → Body → CTA marketing script. The wrapper's prompt already targets that shape.
- Mode 4 has NO per-segment B-roll mapping (the visual is the speaker's face throughout). The `segments[]` field in `marketing_script.py`'s output is simply unused for Mode 4 — L2 ignores it when dispatching.
- Reusing the helper avoids prompt drift between Mode 2 and Mode 4. Same metaphor-handling rules, same abstract-noun substitutions, same multilingual support.
- Polish-mode and Verbatim-mode both fall through to L3's existing script-mode contract (spec 013) — no new helpers needed.

**Alternatives considered**:
- **New `ugc_script.py` with face-camera-specific pacing**: rejected — would create three near-identical helpers (`marketing_script.py`, `ugc_script.py`, `long_form_script.py`) with subtle prompt drift over time. Defer to post-v1 if real quality data demands it.
- **Slight prompt variant inline**: rejected — same drift problem, less explicit.

**Implications**:
- L2's orchestrator routes mode=`ugc_avatar` → `marketing_script.generate_marketing_script(...)` → discards segments[] → forwards `full_text` as `video_script` with `script_mode="verbatim"` to L3.
- L3's `app/services/modes/ugc_avatar.py` doesn't need its own `generate_script` (or has a trivial one that delegates to `llm.generate_marketing_script` for the L3-fallback case where L2 didn't run the orchestrator).

---

## R5 — Loop seam smoothing technique (FR-015)

**Decision**: **Ping-pong loop** (forward → reverse → forward → reverse) of the speaker reference video to fill the audio length.

**Rationale**:
- Simplest implementation: a single FFmpeg filter chain (`-filter_complex "[0:v]reverse[r];[0:v][r]concat=n=2:v=1"`) doubles the video length seamlessly. Repeat as many times as needed to exceed audio length, then trim to exact duration.
- No visible seams: forward → reverse boundary is a single-frame pivot where the motion smoothly inverts. Crossfade boundaries (alternative) introduce a brief blurry transition that's MORE noticeable than ping-pong's clean pivot.
- Lip-sync quality preserved: MuseTalk infers per-frame, so it runs over the ping-pong-extended visual independent of the original sequence. Mouth shapes match audio even where motion direction reverses.
- Free: pure FFmpeg, no new dep.

**Alternatives considered**:

| Technique | Why rejected |
|---|---|
| **Simple loop** (forward → forward → forward) | Cut at loop boundary is jarring — body posture jumps, hand position resets. |
| **Crossfade between loop boundaries** (FFmpeg `xfade`) | Brief blur at every loop seam. More noticeable than ping-pong's clean pivot. |
| **Frame interpolation** between last-and-first frames | Heavy compute. RIFE or DAIN models are an extra GPU pass. Diminishing returns vs ping-pong's free zero-blur option. |
| **AI-extend the reference** (animate beyond the captured frames) | Way over budget. v2+ candidate. |

**Implications**:
- `app/services/lip_sync.py` exposes `extend_reference_to_duration(ref_path, target_seconds)` → returns a new MP4 path of the ping-pong-extended reference. Lip-sync inference then runs over the extended reference + audio.
- Loop count = `ceil(audio_duration / ref_duration / 2) * 2` (rounded up to keep the ping-pong symmetric, then trimmed to exact audio length).

---

## R6 — Selfie upload endpoint location

**Decision**: **L3 hosts the selfie upload endpoint** at `POST /api/v1/uploads/selfie`. L2 proxies as `POST /api/v1/avatars/upload`. L1 calls L2.

**Rationale**:
- Mirrors the existing pattern from spec 006 (`uploaded_model_path`, `uploaded_product_paths`) where L3 owns the upload endpoint and L2 proxies. Consistent with the codebase.
- Upload validation (face detection, duration check, format check) runs server-side at L3 — matches FR-002 "before charging credits or dispatching a render".
- Storage layer is `storage/uploads/<tenant>/avatars/slot{1,2,3}/<uuid>.mp4` — filesystem-only per Q2=C; no DB.

**Slot eviction logic** (FR-014):
1. On upload, list `storage/uploads/<tenant>/avatars/slot{1,2,3}/` by mtime.
2. If 3 slots are occupied, delete the oldest one's file.
3. Save new upload to a fresh slot (any free one — slot numbering is a stable identifier; eviction is mtime-based, not slot-rotating).

**Alternatives considered**:
- **L2-only upload (L2 stores the file, L3 fetches via pre-signed URL)**: cleaner separation but introduces a 2nd hop for every render. Not worth the complexity for v1.
- **Direct L1 → cloud bucket upload**: requires per-tenant cloud creds. Out of scope for v1's localhost-only demo.

---

## R7 — Subtitle behavior for talking-head video

**Decision**: **Subtitles ON by default, lower-third positioning, same Arabic-font auto-swap as Mode 2.**

**Rationale**:
- Even talking-head content benefits from subtitles for muted-autoplay social feeds (TikTok, Instagram). The wizard can offer a toggle but defaults to ON.
- Arabic-narration subtitles need GeezaPro auto-swap (already shipped in [video.py](../../app/services/video.py)) — Mode 4 inherits this for free.

**Alternatives considered**:
- **No subtitles by default** (talking head is "the visual"): less Instagram-friendly. Rejected — keep parity with Mode 2.
- **Picture-in-picture style face crop with subtitles taking the rest**: out of scope. Different mode entirely.

---

## Summary of decisions

| ID | Decision | Affects |
|---|---|---|
| R1 | MuseTalk, self-hosted in L3 process | New file `app/services/lip_sync.py`; constitution Principle IV self-hosted-is-not-API-call interpretation locked in |
| R2 | MediaPipe Tasks for face detection | New dep `mediapipe>=0.10` in L3 pyproject.toml; used in upload validator + lip-sync prep |
| R3 | Hybrid Apple Silicon: MPS for dev, CUDA for prod, mock flag | `LIP_SYNC_ENGINE=mock` env var; `torch.backends.mps.is_available()` introspection |
| R4 | Reuse `marketing_script.py` for Mode 4 Auto-mode | L2 orchestrator branches mode=ugc_avatar to existing helper |
| R5 | Ping-pong loop for audio-overflow visuals (FR-015) | FFmpeg-only implementation; no new dep |
| R6 | L3 hosts upload, L2 proxies | New endpoint `POST /api/v1/uploads/selfie` in L3; mirror in L2 |
| R7 | Subtitles ON by default, lower-third, Arabic font auto-swap inherited | No new code beyond Mode 4 mode-registry settings |

All NEEDS CLARIFICATION resolved. Ready for Phase 1.
