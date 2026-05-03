# Research — Mode 3 Long-Form Video Generator

**Phase**: 0 (resolve all unknowns before designing data + contracts)
**Created**: 2026-05-03

## Decisions

### D-1 — Script generation strategy

**Decision**: Reuse the existing `app/services/llm.py` LLM-call pattern; add `generate_long_form_script(input_text, source_type, target_duration_seconds)` that emits a structured script with three sections (hook ≤ 15s, body 1.5–4 min split into 3–5 points, summary/CTA ≤ 20s). Word-budget = `target_duration_seconds * 2.5` (industry-standard 150 wpm for narration; conservative for non-native voices).

**Rationale**: Mode 2 already has `generate_marketing_script` — same pattern, longer output, sectioned scaffold. Keeps `llm.py` as the single LLM-prompt surface (Principle II compliance).

**Alternatives considered**:
- *Multi-LLM-call (one per section)*: simpler prompts but loses cross-section coherence; rejected.
- *Tool-use / structured-output API*: would add JSON-schema tool plumbing; defer to v2 if quality demands it.

### D-2 — Word-to-duration mapping

**Decision**: 150 wpm baseline → 2 min ≈ 300 words, 3 min ≈ 450, 4 min ≈ 600, 5 min ≈ 750. Validate after voice synthesis; if duration drift > ±15s, retry with adjusted word target (single retry).

**Rationale**: TTS voices average 140–160 wpm; 150 is a safe midpoint. Single retry handles outlier voices without runaway cost.

**Alternatives considered**:
- *Per-voice WPM table*: more accurate but creates a calibration burden; the post-synthesis check + retry handles drift cheaper.
- *Trimming/padding silence to hit target*: produces awkward pauses or abrupt endings; rejected.

### D-3 — Visual provider routing

**Decision**: Reuse Layer 2.5's existing routing policy from spec 015:
- `source_type == "url"` → AI image generation (Gemini Nano Banana, same provider Mode 1 ships) for product-specific frames.
- `source_type == "topic"` → Pixabay stock search per script segment (Pexels excluded per user's standing instruction).
- `source_type == "script"` → topic-extract from script + same as `topic`.

For each script segment (~12–25s of narration), Layer 2.5 returns 1–2 stills or a short looping video. Layer 3 stitches them with crossfades and the Ken-Burns zoom is **off** (we learned in spec 015 that zoompan triples render time and added little value).

**Rationale**: Mode 1 + Mode 2 already validate this routing. No new provider wiring. Cost stays in budget (~$0.05–0.20 per generation).

**Alternatives considered**:
- *Image-to-video (Kling/Veo)*: ~$3–4 per video — exceeds SC-005's $0.50 cap; deferred to follow-up alongside the Mode 1 Path-B work.
- *Stable Diffusion local generation*: would need a GPU service in Layer 2.5; out of scope for v1.

### D-4 — Subtitle positioning

**Decision**: Hard-code lower-third positioning at `y = 0.80 * frame_height` (i.e., 80% from top), white sans-serif text on a 60%-opacity black band. No per-mode subtitle styling layer in v1.

**Rationale**: Matches YouTube convention; FR-006 + SC-003 require this band; no user customization in v1's "Out of Scope" list. The mode registry entry encodes this so it can't drift.

**Alternatives considered**:
- *Configurable position*: deferred to v2 / spec 005 (settings menu) per the Out-of-Scope section.

### D-5 — Persistence + pre-signed URL handoff

**Decision**: Mirror spec 015's `product_shoot_store.py` exactly. JSON file at `storage/tasks/lf_<id>/record.json`; lazy disk-load on first call; pre-signed URLs re-minted on every read (15-min TTL); legacy bare-dir backfill if Layer 2 ever loses records.

**Rationale**: Spec 015 fully proved this pattern, including the empty/failed filter (≥20KB). Less surprises = faster delivery.

**Alternatives considered**:
- *Skip persistence; go straight to Neon*: blocked on spec 014 (auth + tenant) and Step 4; ~weeks away.
- *Redis*: introduces a runtime dependency; Constitution §Technology Constraints discourages Redis as source of truth.

### D-6 — Voice library + TTS provider

**Decision**: Reuse the Azure TTS + Edge TTS voices already wired for Mode 2. Long-form generations make on the order of 1 long synthesis call (full script) per generation, NOT one per segment — keeps cost low and the sentence boundaries / breath patterns natural across segment splits.

**Rationale**: One consistent voice across a 3-minute video reads better than spliced micro-clips; existing voice picker in the wizard already supports this.

**Alternatives considered**:
- *ElevenLabs*: significantly higher quality but ~10× cost — would breach SC-005; deferred to a premium tier in Step 5.
- *Per-segment synthesis with crossfades*: introduces audible seams; rejected.

### D-7 — Layer 3 endpoint shape

**Decision**: Reuse Layer 3's existing `POST /api/v1/videos` endpoint with:
- `params.mode = "long"` (new literal)
- `params.video_aspect = "16:9"` (already supported by upstream MPT)
- `params.video_clip_duration = <segment seconds>` and `params.video_count = <segment count>` already work upstream.
- `params.subtitle_position = "bottom"` already exists; the long-form mode registry sets the offset.

Layer 2 builds a `VideoParams` payload with these flags + tenant context (demo Step-3) + the pre-signed B-roll URL list, then awaits the assembled MP4.

**Rationale**: Zero net-new Layer 3 endpoints — surgical fork compliance. Modes 2 and 5 already follow this pattern.

**Alternatives considered**:
- *New Layer 3 endpoint `/api/v1/long-form`*: violates Principle II (sprawl); rejected.

### D-8 — URL scraping reuse

**Decision**: For `source_type == "url"`, Layer 2 calls Layer 1's existing `/api/scrape-url` endpoint (spec 012) and feeds the cleaned text into `generate_long_form_script`. No new scraper.

**Rationale**: Spec 012 already shipped robots.txt + rate limits + cache; reusing avoids duplicating that surface.

**Alternatives considered**:
- *Layer 2 owns scraping*: violates spec 012's architecture decision (scraping lives in Layer 1 to avoid cross-origin proxy complexity).

### D-9 — Concurrency + queueing

**Decision**: v1 ships sequential generation per user (no in-flight queue). Each Layer 2 request to the long-form route blocks until Layer 3 returns the MP4 (~3–5 minutes). The wizard polls a `GET /api/v1/long-form-videos/{id}` for status updates if needed.

**Rationale**: Single-user demo; concurrency is a Step-4 problem solved alongside multi-tenant. Avoiding background queues now keeps the v1 surface minimal.

**Alternatives considered**:
- *FastAPI BackgroundTasks*: adds complexity (status polling becomes load-bearing); deferred.

### D-10 — Failure surfaces

**Decision**: Three explicit failure codes returned by `POST /api/v1/long-form-videos`:
- `script_generation_failed` (LLM error or empty output)
- `voice_synthesis_failed` (TTS service error after 2 retries)
- `assembly_failed` (Layer 3 returned 4xx/5xx or timeout)

Plus inherited validation codes: `source_too_long`, `source_too_short`, `url_unreachable`, `invalid_bearer`.

**Rationale**: Lets the wizard render specific guidance (e.g., "your script is too short for 5 minutes — try 3 minutes or add more text") without dropping into a generic 500.

**Alternatives considered**:
- *Single generic `provider_error`*: matches Mode 1's surface but loses long-form-specific signal.

## Open questions resolved

All NEEDS CLARIFICATION items were resolved at spec time via reasonable defaults documented in `spec.md → Assumptions`. No outstanding research items.

## References

- VisualAI Master Spec §3 (5 modes), §4 (5-layer architecture), §5.1 (Layer 2.5 dynamic router).
- Constitution v1.1.0 — Principles II, III, IV, V are load-bearing here.
- Spec 015 (Modes 1 & 5 Registry) — record-persistence + pre-signed URL pattern transferred wholesale.
- Spec 012 (URL scraping) — reused for `source_type == "url"`.
- Spec 010 (music control), spec 009 (brand overlays) — inherited.
- 5-step build plan: Mode 3 lives in Step 4 of the master plan.
