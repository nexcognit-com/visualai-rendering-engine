# Feature Specification: Mode 4 — UGC Avatar Generator (MuseTalk lip-sync)

**Feature Branch**: `018-ugc-avatar-musetalk`
**Created**: 2026-05-05
**Status**: Draft
**Input**: User description: "Mode 4 — UGC Avatar Generator. The user records or uploads a short selfie video (face talking to camera, ~5-15 seconds is enough as a 'speaker reference'). The system generates a video where that person's face appears to speak any script the wizard provides — driven by MuseTalk lip-sync over a TTS-synthesized narration. Output is a vertical 9:16 MP4 the same shape Mode 2 produces today. The selfie is the speaker; the script is freshly generated (auto / verbatim / polish — same script_mode contract as Mode 2). Voice catalog from spec-i18n applies — Arabic voice + English selfie should still produce a believable Arabic-speaking version of that face."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — One-shot UGC ad from selfie + product brief (Priority: P1)

A creator wants to make an ad in their own voice and face without filming a full take for every variation. They open the wizard, pick "UGC Avatar", drop a 5-15 second selfie of themselves talking to camera (any topic — content doesn't matter, MuseTalk only needs the face reference), then describe the product they're advertising in the brief box. They pick a voice (English American, Arabic Egyptian, Spanish — whichever matches the audience they're posting to). Within ~90-180 seconds they get back a vertical 9:16 MP4 where their face appears to speak a freshly written hook → body → CTA marketing script in the chosen language. They can post that MP4 to TikTok / Instagram / YouTube Shorts unchanged.

**Why this priority**: This is the MVP — the single transaction that proves Mode 4 works. Without this, no other story matters. Delivering this alone gives a creator the ability to produce in-language ads at near-zero marginal cost per variation.

**Independent Test**: Submit one selfie + one product subject through the wizard. Wait for completion. Open the resulting MP4 in a video player. Verify (a) the face is the same person from the selfie, (b) the mouth movements match the words being spoken, (c) the voice matches the chosen voice, (d) the script is on-topic for the product brief, (e) the output is 9:16 vertical and playable.

**Acceptance Scenarios**:

1. **Given** the wizard's "UGC Avatar" mode is open and no selfie is uploaded, **When** the creator clicks Generate, **Then** the system blocks dispatch with a clear "selfie reference required" message.
2. **Given** the creator has uploaded a 12-second selfie video and entered "Caffeine-free organic energy drink for working parents" as subject, **When** they pick voice "en-US-AvaMultilingualNeural" and click Generate, **Then** within 90-180 seconds a 9:16 MP4 is available where the selfie's face mouths an English hook→body→CTA script about the energy drink.
3. **Given** the same selfie + product, **When** the creator picks voice "ar-EG-SalmaNeural" instead, **Then** the resulting MP4 has the same person's face speaking a Modern-Arabic-script ad — the face does not change, only the language and the mouth movements adapt.
4. **Given** the creator's selfie has multiple faces visible (background photobomb), **When** they upload it, **Then** the system identifies the largest/most-centered face as the speaker reference and warns the creator at upload time which face was chosen.

---

### User Story 2 — Verbatim-mode (creator pastes their own script) (Priority: P2)

The creator already has a script written (or wants exact word-for-word control). They open Mode 4, drop their selfie, paste the script into the script field, pick voice + flip script_mode to Verbatim, click Generate. Output is the same shape as P1 but using the creator's exact words, no LLM-generated alternatives.

**Why this priority**: This is the highest-trust output for marketing professionals and regulated industries (legal disclaimers, medical claims, financial advice). It's a small additive change once P1 ships — the script_mode contract already exists in Mode 2 and just needs to be wired through.

**Independent Test**: Upload a selfie + paste a known script ("Trust us, we're licensed in 47 states. Visit example.com today."). Generate. Open the MP4. Verify the audio is exactly that script in the chosen voice, and the lip-sync matches.

**Acceptance Scenarios**:

1. **Given** the wizard, **When** the creator pastes a 50-word script and picks Verbatim mode, **Then** the LLM is not invoked for script generation and the audio is exactly the pasted text.
2. **Given** Verbatim mode is selected and the script field is empty, **When** the creator clicks Generate, **Then** dispatch is blocked with a "Verbatim mode requires a non-empty script" message.

---

### User Story 3 — Polish-mode (creator gives a brief, LLM cleans it up) (Priority: P3)

The creator has rough notes / bullet points but doesn't want the LLM to invent the message from scratch. They paste those notes into the script field, flip script_mode to Polish. The LLM rewrites it as a tight hook→body→CTA in the chosen voice's language, but stays grounded in the creator's facts.

**Why this priority**: Bridges P1 (full LLM creativity) and P2 (zero LLM intervention). Useful for creators who know exactly what they want said but don't want to be the copywriter. Polish-mode already exists in Mode 2 — Mode 4 just inherits it.

**Independent Test**: Upload selfie + paste 3 rough bullet points + pick Polish mode. Verify the output narration covers all 3 points but in polished marketing prose.

**Acceptance Scenarios**:

1. **Given** the creator pastes "morning coffee, single origin, $12 per bag, 30-day money back guarantee", **When** they flip to Polish mode and generate, **Then** the resulting narration weaves all four facts into a fluid 20-second pitch.

---

### Edge Cases

- **No clear face in the selfie** — the upload contains landscapes, objects, or shots where the face is too small or angled away. System rejects upload at validation time with a face-not-detected error before any expensive processing runs.
- **Multiple faces in the selfie** — group selfie or background bystanders. System picks the largest, most-centered face and surfaces a warning so the creator can re-upload if the wrong face was selected.
- **Selfie shorter than 5s** — too short to extract a stable face reference. System rejects with a "minimum 5-second video required" message.
- **Selfie longer than 15s** — accepted, but only the first 15 seconds are used as the reference (the rest is discarded for performance).
- **Wildly different selfie aspect ratio** (4:3 horizontal, 16:9 landscape) — accepted; the face crop pipeline center-crops the face region regardless of source aspect ratio.
- **Selfie face wearing sunglasses or heavy partial occlusion** — accepted but flagged at upload time as "face partially obscured — lip-sync quality may degrade".
- **Voice and selfie mouth shape mismatch** — e.g. tight-lipped neutral selfie vs an emphatic Italian voice. Lip-sync will still work but may look uncanny. Out of scope to detect — creator's call.
- **Script too long for the chosen output duration** (Auto/Polish mode) — LLM is instructed to target the creator's chosen duration; clamping at the 300s cap when applicable.
- **Verbatim script that would exceed 300s of audio** — rejected at validation time before render dispatch (FR-013).
- **Generated audio longer than the speaker reference video** — the speaker reference is seamlessly looped (FR-015). For example, a 12-second selfie reading a 47-second script loops ~4× through the lip-sync; loop seams are smoothed.
- **Wizard closed mid-render** — ongoing render continues server-side; creator can return and find it under "My Assets" / history.
- **Selfie file is corrupted or has no audio track** — accepted (audio not needed; only video is read for face reference). System treats it as silent.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept an uploaded video file (between 5 and 60 seconds, common consumer formats — MP4 / QuickTime / WebM) as the speaker reference for the avatar. **Only the first 15 seconds are used as the actual reference**; the remainder is discarded for performance and storage. Uploads shorter than 5 seconds or longer than 60 seconds are rejected at validation time with a clear duration-out-of-range error.
- **FR-002**: System MUST detect a face in the speaker reference and reject uploads where no face is detected with a user-readable error before charging credits or dispatching a render.
- **FR-003**: System MUST support the same three script-generation modes as Mode 2: Auto (LLM writes hook→body→CTA from a subject brief), Verbatim (creator's pasted script is used as-is), and Polish (LLM cleans up creator's rough notes while preserving facts).
- **FR-004**: System MUST honor the multilingual voice catalog from the i18n feature — the creator can pick any of the available voices (Arabic dialects, English variants, Spanish, French, German, Italian, Portuguese, Hindi, Mandarin, Japanese, Korean, Russian, Turkish, etc.).
- **FR-005**: When the creator picks a voice whose locale differs from the language of any pasted script, the system MUST generate the script in the voice's language (Auto/Polish) or warn the creator about the language mismatch (Verbatim). Same locale-inference behavior already shipped with i18n applies.
- **FR-006**: System MUST generate a vertical 9:16 MP4 output where the speaker reference's face appears to speak the generated narration, with the mouth movements synchronized to the audio per FR-007 (±0.2s tolerance).
- **FR-007**: Generated output duration MUST match the audio length within ±0.2 seconds.
- **FR-008**: Generated output MUST embed subtitles aligned to the audio in the same language as the narration, using the same Arabic-capable font auto-swap behavior already shipped (Arabic narration → Arabic-glyph font).
- **FR-009**: System MUST tag the output asset with the creator's tenant + user identity so it appears in their "My Assets" history alongside other modes' renders.
- **FR-010**: While a render is in progress, the wizard MUST display progress feedback (stage labels: face-extraction → audio-synthesis → lip-sync → final-encode) and a cancel option.
- **FR-011**: System MUST gracefully handle lip-sync runtime failures (model load timeout, GPU-out-of-memory, malformed reference) by surfacing a typed error to the wizard. **Credit-refund obligation deferred** until spec 008 (NexCognit credit-gating, currently paused per NEX-461) lands; once spec 008 is active, FR-011 must also reverse any pre-render credit hold for failed renders. v1 surfaces the typed error only.
- **FR-012**: Output MP4 MUST be playable in standard browsers and downloadable directly from the wizard's result panel.
- **FR-013**: Maximum allowed creator-target output duration is **5 minutes (300 seconds)** — the same cap as Mode 3 long-form. Verbatim-mode inputs whose narration would exceed 300s of audio MUST be rejected at validation time with a "script too long for v1 cap" error. Auto/Polish-mode generation MUST instruct the LLM to target ≤ 300s and clamp the request if the creator picks an unsupported duration.
- **FR-014**: Speaker reference selfies follow a **hybrid persistence model**: each tenant's last 3 most recently uploaded references are retained on disk and automatically surfaced in the wizard's "recent selfies" picker for one-tap reuse. The 4th upload evicts the oldest. No explicit avatar-management UI is built in v1; the picker is the entire surface area. References older than the most-recent-3 are deleted from disk during eviction. Tenants can force-delete via the My Assets surface.
- **FR-015**: When the generated audio's duration exceeds the visual reference's length (selfie was 12s, audio is 47s), the system MUST **seamlessly loop the speaker reference video** so the lip-sync output equals the audio length within ±0.2s. Loop boundaries MUST be smoothed (frame interpolation or short crossfade) to avoid a visible "jump" at each loop point. Audio is never truncated.

### Key Entities

- **Speaker Reference**: An uploaded short video clip (5-15s) whose face becomes the avatar. Carries tenant + user provenance, upload timestamp, detected-face bounding-box metadata, and a slot index (1, 2, or 3 — the most-recent-3 hybrid persistence model from FR-014). When a 4th upload arrives, the oldest slot is evicted from disk.
- **Avatar Render**: A single Mode-4 generation request. Links a Speaker Reference + a Voice + a Script (text or generation-input) + tenant context. Tracks state through the pipeline (queued → face-prep → tts → lip-sync → encoding → complete | failed).
- **Avatar Asset**: The final 9:16 MP4 + accompanying subtitle file + metadata (duration, voice locale, script text, source speaker reference id). Stored alongside the creator's existing Mode 2/3/5 renders.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 90% of Mode 4 renders at the **30-second target duration** complete in under 180 seconds end-to-end (selfie upload → final MP4 ready for download), measured at the wizard layer. Renders at the 300-second (5-minute) maximum complete in under 8 minutes for the same percentile — render time scales near-linearly with output duration on the chosen runtime.
- **SC-002**: For 95% of completed renders, an external viewer who is not the creator cannot tell that the lip movements were synthesized — measured by a panel test where reviewers rate "did this person actually say these words?" on a 5-point scale, with target average score ≥ 4.0.
- **SC-003**: Voice-locale switching works without face-region degradation — creators can flip the same selfie between English, Arabic, and Spanish voices and the resulting face quality is visually indistinguishable across languages (no warping, no mouth-region artifacts that vary by language).
- **SC-004**: Auto-mode script generation matches the chosen voice's locale 100% of the time — Arabic voice produces Arabic script, never English.
- **SC-005**: Failed renders surface a typed error message that maps directly to a recovery action the creator can take (re-upload selfie, choose different voice, retry, contact support) within 95% of failure cases.
- **SC-006**: Mode 4 occupies the same wizard surface area as Mode 2 — a creator who has used Mode 2 can complete a Mode 4 render without reading help docs, measured by usability test.
- **SC-007**: First-time creators complete their first Mode 4 render within 5 minutes of opening the wizard (excluding render time).

## Assumptions

- **Selfie format**: video file (mp4, mov, webm) is required for v1. Single-image avatar generation is a v2 candidate but not in scope here — quality from a single still is materially worse than from short video reference.
- **Render synchrony**: dispatch is synchronous from the wizard's perspective (POST returns a task id, wizard polls), matching Mode 2's existing pattern.
- **Compute**: Mode 4 runs on whatever compute the existing render layer has access to. GPU vs CPU choice is a planning-phase decision; the spec is runtime-agnostic.
- **Multi-tenant isolation**: speaker references and rendered assets are tenant-scoped; no cross-tenant sharing in v1.
- **Existing infrastructure reused**: voice catalog (spec-i18n), script-mode contract (spec 013), language inference from voice locale, Arabic-capable subtitle font auto-swap, asset history surfacing, wizard progress/cancel UX. None of these are rebuilt — Mode 4 is a new mode that consumes existing primitives.
- **Output format**: 9:16 vertical MP4 only for v1. 16:9 horizontal (long-form-style) is a v2 candidate but explicitly out of scope here so the talking-head crop remains tight.
- **Background**: the avatar's background is the selfie's original background — face is the focus; the system does NOT insert stock B-roll behind the avatar in v1 (that's a different mode entirely).
- **Liveness verification**: not in scope for v1 — any uploaded selfie is accepted on trust. Detection of impersonation, deepfake-of-a-deepfake, or non-consenting subjects is a separate compliance feature.
- **Persistence**: speaker references and outputs follow the same retention policy as Mode 2/3/5 outputs. Tenant-controlled deletion via the My Assets surface.

## Resolved Clarifications

The three NEEDS-CLARIFICATION items raised during spec authoring (2026-05-05) were resolved as follows:

- **Q1 — Output duration cap → 5 minutes (Mode 3 long-form parity).** FR-013 sets 300 seconds as the v1 ceiling. Implication: planning phase must size the runtime budget for 5-minute renders (likely GPU territory on the longer end).
- **Q2 — Selfie persistence → hybrid last-3 (no explicit management UI).** FR-014 codifies the most-recent-3 retention model. No new database schema beyond filesystem-on-disk; no management surface in the wizard beyond the picker.
- **Q3 — Audio-overflow handling → loop visuals.** FR-015 codifies seamless looping of the speaker reference to match audio length. Audio is never truncated.
