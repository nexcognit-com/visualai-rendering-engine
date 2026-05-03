# Feature Specification: Mode 3 — Long-Form Video Generator (16:9 YouTube, 2-5 min)

**Feature Branch**: `016-long-form-video`
**Created**: 2026-05-03
**Status**: Draft
**Input**: User description: "Mode 3"

## Context

Mode 3 is the third of five generation modes in VisualAI's Master Spec, alongside Mode 1 (Product Shoot), Mode 2 (Short Marketing Video, 9:16, 30–60s), Mode 4 (UGC Avatar), and Mode 5 (Faceless Channel). Mode 3 produces YouTube-style explainers in a landscape 16:9 frame, 2 to 5 minutes long, with narration, B-roll visuals, lower-third subtitles, and optional background music — the format a creator would upload to a YouTube channel rather than reels/shorts.

Mode 3 is a Step-4 deliverable in the 5-step build plan. Mode 4 (UGC Avatar) ships in a separate spec.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Solo creator turns a topic into a 3-minute explainer (Priority: P1)

A solo content creator opens the dashboard and clicks the Long-Form Video card. They type a topic (e.g., "How AI is changing logistics in 2026") or paste a source URL, pick a target duration (default 3 minutes) and a voice, and click Generate. Within ~3 minutes, a 16:9 MP4 plays inline. They click Download and post it to YouTube.

**Why this priority**: This is the primary use case — turning an idea into a publishable YouTube explainer without manual editing. Without this flow, Mode 3 has no value.

**Independent Test**: From a clean dashboard, the creator can complete an end-to-end run with a topic prompt and a default voice, ending with a downloadable 16:9 MP4 of approximately the chosen duration. Tested in isolation by mocking external generation services and asserting the produced file's duration, aspect ratio, and that subtitles fall in the lower-third region.

**Acceptance Scenarios**:

1. **Given** the user is on the dashboard and Mode 3 is active, **When** they click the Long-Form Video card, **Then** the wizard opens at Step 1 (Input).
2. **Given** the user pastes a topic prompt and selects target duration "3 minutes" and a voice, **When** they click Generate, **Then** progress UI animates through stages (script → voice → visuals → assembly) and within 5 minutes a 16:9 MP4 plays inline.
3. **Given** the generation completes, **When** the user clicks Download, **Then** an MP4 file with `.mp4` extension downloads with a filename including the topic + timestamp.
4. **Given** the generated video, **When** played, **Then** subtitles appear in the lower-third region (between 75% and 90% of frame height) for the entire video.
5. **Given** the user requested a 3-minute target, **When** the video is produced, **Then** its actual duration is between 2:45 and 3:15 (±15s tolerance).

---

### User Story 2 — Marketer turns a product URL into a long-form explainer (Priority: P2)

A marketer pastes a product page URL into the wizard and asks for a 4-minute walkthrough. The system scrapes the URL (using the same scraping path Mode 2 uses), drafts a longer narrated explainer covering the product's features, benefits, and use cases, and produces a 16:9 video.

**Why this priority**: Reuses Mode 2's URL-scraping pipeline, broadens Mode 3's input options, and addresses a high-value B2B use case. Lower than P1 because it depends on URL-scraping working correctly (already shipped via spec 012) and is a wider but less foundational entry point.

**Independent Test**: Tested by mocking the URL scrape to return a known product description and asserting the generated script references that description's key facts.

**Acceptance Scenarios**:

1. **Given** the user pastes a product URL, **When** they click Generate, **Then** the system scrapes the URL and generates a script grounded in the scraped content.
2. **Given** the URL is unreachable, **When** the user clicks Generate, **Then** the system surfaces a clear error and offers a fallback to topic-only input.

---

### User Story 3 — Generated long-form video appears in My Assets (Priority: P2)

After a successful generation, the new video appears in the My Assets grid alongside videos from Modes 2/5 and product shoots from Mode 1. The thumbnail is a landscape (16:9) frame; clicking opens an inline preview that plays the video.

**Why this priority**: Required for parity with the other modes' My Assets surfacing. Without it, users can't find a generation after closing the wizard. Slightly lower than P1 because the wizard's inline preview at completion is a partial fallback.

**Independent Test**: Run a generation, navigate to My Assets, assert the new video card is present, displays a 16:9 thumbnail, and plays when previewed.

**Acceptance Scenarios**:

1. **Given** a Mode 3 generation completes, **When** the user opens My Assets, **Then** the new video appears at the top of the grid (newest-first) with a landscape thumbnail.
2. **Given** the user clicks the card, **When** the preview opens, **Then** the video plays inline and a Download action is available.

---

### User Story 4 — Pre-written script (Priority: P3)

A power user already has a polished script (e.g., copied from a doc) and wants the system to produce visuals + voice + assembly without rewriting the script. They paste the script into the input box, select a duration that matches the script length, and generate.

**Why this priority**: Adds flexibility for users with their own writing process. Lower than P1/P2 because it's a power-user shortcut around the script-generation step.

**Independent Test**: Run a generation with a 400-word pre-written script and assert the produced video's narration matches the script verbatim (or with only minor punctuation edits).

**Acceptance Scenarios**:

1. **Given** the user pastes a 400-word script and selects "3 minutes", **When** they click Generate, **Then** the system uses the script as-is for narration (no LLM rewrite) and produces the video.
2. **Given** the script length is grossly mismatched with the target duration (e.g., 50-word script targeting 5 minutes), **When** the user clicks Generate, **Then** the system warns and either pads with related content or rejects with a clear message.

---

### Edge Cases

- **Topic too vague to generate from**: System surfaces a "topic too thin" warning and asks the user to add detail before generating.
- **Target duration unachievable from script**: If a pasted script would produce a video much shorter (or longer) than the target, the system warns once and lets the user proceed or adjust.
- **All B-roll requests fail**: If the visuals provider returns nothing for any segment, the system surfaces a clear error rather than producing a black-frame video.
- **Voice synthesis fails mid-generation**: System retries up to 2× per segment, then fails the generation with a clear `voice_synthesis_failed` error.
- **Final assembled video exceeds reasonable file size (e.g., >500 MB)**: System logs a warning but ships the file (no truncation).
- **User abandons the wizard mid-generation**: System completes the generation in the background; user finds it in My Assets when they return.
- **Two long-form generations in flight at once for the same user**: System queues sequentially in v1 (single-user demo); spec 014's tenant plumbing will revisit concurrency rules.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Users MUST be able to start a Mode 3 generation from the dashboard via a "Long-Form Video" card.
- **FR-002**: The Mode 3 wizard MUST accept input from any one of: a topic prompt, a source URL, or a pre-written script.
- **FR-003**: Users MUST be able to choose a target duration from the set {2, 3, 4, 5} minutes; default 3 minutes.
- **FR-004**: Users MUST be able to choose a narration voice from the same voice library Mode 2 uses.
- **FR-005**: System MUST produce a 16:9 landscape video at 1920×1080 resolution (1080p).
- **FR-006**: System MUST overlay generated subtitles in the lower-third region of the frame (between 75% and 90% of frame height).
- **FR-007**: System MUST include synthesized narration covering the entire script.
- **FR-008**: System MUST include B-roll visuals timed to script segments (each visual occupies a continuous segment of the video, no static single-frame outputs).
- **FR-009**: System MUST optionally include background music; users MUST be able to disable music.
- **FR-010**: System MUST report progress through at least four stages: "Generating script", "Synthesizing voice", "Fetching visuals", "Assembling video".
- **FR-011**: System MUST surface the completed video as a playable inline preview AND a downloadable MP4 file.
- **FR-012**: Generated videos MUST appear in My Assets, newest-first, with a landscape thumbnail.
- **FR-013**: System MUST persist each generation as a record with id, tenant id, user id, status, source type, source text, output video URL, target duration, actual duration, voice id, music selection, error code, error message, latency ms, cost estimate, created at, completed at.
- **FR-014**: System MUST cap topic prompts at 500 characters and pre-written scripts at 1500 words to prevent abuse.
- **FR-015**: System MUST require a valid bearer token on all Mode 3 endpoints (consistent with Modes 1/2/5 in the demo-tenant Step-3 layer).
- **FR-016**: When the source is a URL and scraping fails, the system MUST surface a clear error AND offer the user a fallback to "convert to topic prompt".
- **FR-017**: Generated video duration MUST be within ±15 seconds of the user's selected target.
- **FR-018**: System MUST log a cost estimate (USD) per generation and expose it on the record.
- **FR-019**: System MUST mark a generation as `failed` (not `running`) within 10 minutes if no progress, and surface a `timeout` error.

### Key Entities *(include if feature involves data)*

- **LongFormGeneration**: A single user-initiated long-form video generation. Has identifier, tenant id, user id, status (running | complete | failed), source type (topic | url | script), source text, target duration in seconds, actual duration in seconds, voice identifier, music identifier (or "none"), output video URL (pre-signed), subtitle positions, error code, error message, latency in ms, cost estimate in USD, created timestamp, completed timestamp.
- **ScriptSegment** (internal): A single contiguous chunk of the produced narration with its own visual + timing window. Has start time, end time, text, visual reference (URL or generation id). Internal to the generation record; not exposed via API in v1.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From clicking the Long-Form Video card to receiving a playable MP4, users complete a generation in under 5 minutes for the 3-minute target (median wall-clock).
- **SC-002**: 90% of generations land within ±15 seconds of the user's selected target duration.
- **SC-003**: 100% of subtitles render in the lower-third region (frame height 75%–90%); no center or upper-third placements.
- **SC-004**: The new video appears in My Assets within 2 seconds of completion.
- **SC-005**: Cost per generation stays at or below $0.50 USD (median across the 4 duration options).
- **SC-006**: 95% of users who reach Step 1 of the wizard reach a completed video without retry.
- **SC-007**: Subtitle accuracy (matched against the source narration text) ≥ 95% per video.
- **SC-008**: Visuals match script-segment topic intent for ≥ 80% of segments (qualitative review).

## Assumptions

- **Target user**: A solo creator or small marketing team producing YouTube explainers. The demo single-user mode applies until spec 014 closes Step 2's tenant work.
- **Subtitle styling**: White sans-serif text on a subtle dark band, positioned 80% from the top of the frame. Customization is out of scope for v1.
- **Script structure (default)**: Hook (10–15s) + body with 3–5 points + summary/CTA (15–20s). The system uses this scaffold for `topic` and `url` source types; a pre-written script overrides it.
- **Voice**: Reuses the Azure/Edge TTS voices already wired for Mode 2 (no new voice procurement). The voice library is shared across modes.
- **Visuals**: Reuses the same hybrid policy Mode 2 ships today — URL-typed inputs route through AI image/video generation; topic-typed inputs source B-roll from Pixabay; per the user's standing instruction Pexels is excluded.
- **Background music**: Reuses Mode 2's bundled BGM library (29 tracks). Custom uploads via spec 010's path-rewrite are inherited.
- **Persistence**: JSON-file store at `storage/tasks/lf_<id>/record.json` as a Step-3 stand-in for the Step-4 Neon `long_form_generations` table — same shape, just files instead of rows.
- **Auth**: Demo bearer token for v1; tenant plumbing arrives with spec 014.
- **Scraping**: Reuses the Layer 1 URL scraping endpoint shipped in spec 012 for the URL source type.
- **Brand overlays + audio uploads**: Spec 009 (brand overlays) and spec 010 (music control) apply to Mode 3 outputs identically to Mode 2 outputs once the route is registered.
- **Failed-shot filtering**: Mode 3 inherits Mode 1's pattern of filtering empty/corrupt outputs from My Assets.

## Out of Scope (v1)

- Chapter markers + YouTube description timestamp export (Step 5 candidate).
- Multi-language voiceover or auto-translate (Step 5).
- Custom subtitle styling (font, color, position) — v1 ships fixed lower-third white-on-dark.
- Channel branding intro/outro stings (covered by spec 009 brand overlays already).
- 4K output — 1080p is the v1 ceiling.
- Episodic / series production (>5 min, multi-part).
- Chapter authoring UI (multi-section script editor).
- Direct YouTube upload integration (Step 5).
- Live preview during generation — v1 ships final video only.

## Dependencies

- **Spec 012** (URL scraping) — required for User Story 2 (URL source type).
- **Spec 010** (music control) — inherited for music selection.
- **Spec 009** (brand overlays) — inherited for logo overlay if user has brand assets.
- **Spec 014** (orchestration tenant plumbing, Step 2) — eventually wraps Mode 3's auth + tenant_id, but Mode 3 ships against the demo-tenant Step-3 layer first; spec 014 lifts it later.
- **Spec 015** (modes registry) — Mode 3 plugs into the registry skeleton shipped in PR-A.
- **NEX-462** (Mode 1 / spec 015 Step 3 epic) — pattern to follow for record persistence and pre-signed URL handoff.
