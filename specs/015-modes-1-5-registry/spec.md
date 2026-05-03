# Feature Specification: Modes 1 + 5 + Mode Registry + Layer 2.5 Image Routing (Step 3)

**Feature Branch**: `015-modes-1-5-registry`
**Created**: 2026-05-03
**Status**: Draft
**Input**: User description: "for Step 3"

## Overview

Step 3 of the 5-step VisualAI build plan turns the dashboard from "Mode 2 only" into "three modes live" by activating the two simplest non-Mode-2 cards — **Mode 5 (Faceless Channel Automation)** and **Mode 1 (Product Shoot Generator)** — and burning the three architectural debts (#3, #4, #5) blocking those modes.

The user-visible payoff: a creator clicking the **Faceless Channel** card on the dashboard now produces a topic-driven Pexels-stock video (the existing rendering pipeline, gated to its constitution-compliant home), and clicking the **Product Shoot Generator** card uploads one product image and receives 6 studio-quality photos generated via the NanoBanana Pro image-generation model. The other two cards (Modes 3 + 4) remain "Coming in Step 4" placeholders.

The architectural payoff:

- **`app/services/modes/` registry** lands as a real Python package: each mode has its own module exporting `script_prompt(...)`, `term_strategy(...)`, `material_strategy(...)`, and any mode-specific overrides. `task.py`'s call sites become single registry-dispatcher calls (`modes.pick(params.mode).generate_script(...)`). **Burns debts #4 + #5.**
- **`material.py` rewrite** accepts pre-signed asset URLs from Layer 2 instead of calling Pexels / Pixabay directly. The retained Pexels / Pixabay integration is gated behind `mode == "faceless"` (Mode 5) only, restoring the constitution's Principle IV. **Burns debt #3.**
- **Layer 2.5 Dynamic Model Router** materialises as a new package inside Layer 2 (the orchestration repo) that routes generation API calls — first delivery is image generation (NanoBanana Pro for Mode 1). Video generation (Veo / Kling / Luma) is scoped OUT of Step 3 and deferred to a follow-up; the architecture lands ready for it.
- **`VideoParams.mode` literal widens** from `{"faceless", "short"}` to `{"faceless", "short", "product_shoot"}`. Adding new modes after Step 3 is a constitution amendment (per Principle V) plus a registry module add.

After Step 3, `STEP1_DEBT.md` rows #3, #4, and #5 are struck through. Constitution Principles IV and V flip from DEBT to PASS. The only Step-1 carve-outs remaining at that point are content moderation (row #7, public-launch precondition) and the partial Layer-3 upload-storage row (#6's storage-location half, which retires alongside Step 4's signed-URL store).

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Generate a Faceless Channel video from a topic (Priority: P1)

A creator who runs a topic-driven YouTube Shorts channel about productivity tips opens the wizard, clicks the **Faceless Channel** card on the dashboard (now active, no longer a "Coming in Step 3" badge), enters a topic ("the science of waking up early"), picks a voice, and clicks Generate. Within ~90 seconds they get a vertical 9:16 video stitched from Pexels stock footage, AI-generated voiceover, burned-in subtitles, and background music. The video is clearly marked as Faceless mode in the asset library.

**Why this priority**: Faceless Channel is the smallest delivery in Step 3 — most of its pipeline already exists (it IS the pre-VisualAI MPT pipeline). The work is to gate the existing Pexels integration behind `mode == "faceless"` and surface it as a first-class wizard mode. Highest ROI per effort.

**Independent Test**: Click Faceless Channel on the dashboard, generate one video, confirm a 9:16 MP4 plays inline. Verify `script.json#params.mode == "faceless"` and `asset_audit.visuals_mode == "auto"` (the Pexels stock path). No regressions in Mode 2 rendering.

**Acceptance Scenarios**:

1. **Given** the dashboard is open, **When** the user clicks the Faceless Channel card, **Then** the Faceless wizard opens at `/modes/faceless-channel`.
2. **Given** the Faceless wizard, **When** the user types a topic + picks voice + clicks Generate, **Then** a render dispatches with `mode = "faceless"` and produces a 9:16 MP4 within 90s using Pexels-only stock footage.
3. **Given** a Mode 2 render submitted in parallel, **When** both renders complete, **Then** the Mode 5 render uses Pexels and the Mode 2 render uses whatever Mode 2's visuals_mode is set to. No cross-contamination.
4. **Given** a Mode 5 render's audit log, **When** inspected, **Then** `script.json#params.mode == "faceless"` and the rendered video uses ONLY Pexels-derived clips.

---

### User Story 2 — Generate Product Shoot photos from one image (Priority: P1)

A small-business owner has a single phone-quality photo of her ceramic coffee dripper. She opens the wizard, clicks the **Product Shoot Generator** card, uploads the photo, and clicks Generate. Within ~60 seconds she receives 6 professional studio-quality product photographs of the SAME dripper in different lighting / angles / staging — usable directly for her ecommerce listings and social ads. No video is produced; this is image-only output.

**Why this priority**: Product Shoot is the marquee non-video mode and the most-requested feature in creator interviews. It's also the natural complement to Mode 2 — creators who use Mode 1 to generate good product photos then upload those into Mode 2's `Use my own assets` to render a video.

**Independent Test**: Upload one product photo, click Generate, verify 6 distinct images appear in the wizard preview within 60s. Each image is studio-quality (visibly different from a phone photo). The user can download all 6 individually or as a ZIP.

**Acceptance Scenarios**:

1. **Given** the dashboard, **When** the user clicks the Product Shoot Generator card, **Then** the Product Shoot wizard opens at `/modes/product-shoot`.
2. **Given** the Product Shoot wizard, **When** the user uploads a JPEG / PNG / WebP product photo (≤ 10 MB) and clicks Generate, **Then** a generation dispatches with `mode = "product_shoot"` and within 60s the wizard displays 6 generated studio photos.
3. **Given** the user has 6 generated photos, **When** they click on one, **Then** they can download the full-resolution image. **When** they click "Download all", a ZIP is produced.
4. **Given** a Product Shoot generation, **When** inspected via the audit log, **Then** the per-task record shows the source image path + the 6 output image paths + the model that generated them (`nanobanana-pro` or equivalent).

---

### User Story 3 — Mode 2 keeps working without regression (Priority: P1)

A creator using Mode 2 (Short Marketing Video, the existing flow from Step 1) submits a render through the wizard. The video produces identically to before Step 3 — same script, same voice, same visuals composition. Step 3's internal refactor (modes registry + material.py rewrite) is invisible to Mode 2 users.

**Why this priority**: Mode 2 is the bulk of existing usage. Step 3's debt-burndown refactor MUST NOT break it. Zero-regression is non-negotiable.

**Independent Test**: Submit identical Mode 2 requests (same subject, voice, visuals settings) before and after Step 3 lands. Compare the resulting `script.json` payloads byte-for-byte (modulo timestamps + UUIDs). Visual playback should be indistinguishable.

**Acceptance Scenarios**:

1. **Given** Step 3 has merged, **When** a Mode 2 render is submitted with `visuals_mode = "auto"`, **Then** the resulting video uses Pexels + Pixabay stock (existing Mode 2 hybrid behavior unchanged) and `script.json#params.mode == "short"`.
2. **Given** a Mode 2 `user_uploaded` render, **When** submitted, **Then** the rendered video uses ONLY uploaded assets (existing behavior preserved).
3. **Given** a Mode 2 `hybrid` render, **When** submitted, **Then** the rendered video alternates uploads with stock context (existing FR-022 behavior preserved).

---

### User Story 4 — Add a fourth mode without touching pipeline code (Priority: P2)

A future agent (working on Step 4's Mode 3 — Long-Form Product Marketing Video) needs to add the fourth mode. They write `app/services/modes/long_form.py` exporting the same four functions every other mode module exports. They register it in `app/services/modes/__init__.py`. They widen the `VideoParams.mode` literal. They DO NOT touch `task.py`, `material.py`, or any pipeline-shared code.

**Why this priority**: This is the constitution Principle V payoff — adding modes is a clean, predictable, non-pipeline change. Validates the registry's design.

**Independent Test**: A simulated "add Mode 3" exercise: drop a stub `long_form.py` exporting trivial pass-through implementations of the registry interface. Submit a render with `mode = "long_form"`. Verify the dispatch reaches `long_form.py` without any `material.py` / `task.py` edits.

**Acceptance Scenarios**:

1. **Given** the modes registry, **When** a new mode module is added with the standard interface, **Then** `modes.pick("new_mode")` returns the new module and `task.generate_script(...)` routes to it without any pipeline edits.

---

### Edge Cases

- **Mode 5 + Pexels rate-limit / API down**: existing fallback to Pixabay applies (already in `material.py`). When both fail, the render fails with `error_code: "stock_apis_unavailable"` — no synthetic fallback (Mode 5 is by definition a stock-only flow).
- **Mode 1 + NanoBanana API down or rate-limited**: Layer 2.5's router returns HTTP 502 to Layer 1; the wizard surfaces a clear "image generation service unavailable" toast. No silent fallback to a different model in Step 3 (multi-model routing within Mode 1 is a Step 4 enhancement).
- **Mode 1 + NanoBanana returns < 6 images**: the contract is "6 images". If the model returns fewer, the wizard shows what it has and a soft warning ("only N of 6 generated; please retry or contact support").
- **Mode 1 + input image is unprocessable** (corrupt, NSFW, < 100 px on either dimension): Layer 2 (or Layer 3's existing upload pipeline) rejects at upload time with the same typed errors as spec 006.
- **Mode 2 hybrid still calls Pexels + Pixabay direct**: this is technically a continuation of debt #3 (limited to Mode 2's hybrid path now), but it's smaller in scope than before — the FRESH Mode 5 path is the constitution-compliant one. Mode 2 hybrid's stock fetch route through Layer 2.5 is deferred to a Step 3+ follow-up alongside AI video-generation routing.
- **Concurrent renders across modes**: each mode's pipeline must be thread-safe given `task_manager.add_task` runs renders in worker threads. The registry pattern's mode modules MUST NOT hold module-level mutable state.
- **`VideoParams.mode` set to a value not in the registry**: Pydantic `Literal` rejects at request validation time → HTTP 422 with `error_code: "unsupported_mode"`.
- **Asset library — Mode 1 outputs**: 6 generated images persist alongside Mode 2's video tasks under `storage/tasks/<task_id>/`. The My Assets page enumerates both kinds (images + videos).
- **Layer 2.5 vs Layer 3 boundary**: Layer 2.5 (the new image router inside Layer 2) handles ALL outbound calls to NanoBanana / OpenAI / etc. Layer 3 NEVER calls these directly — the constitution's Principle IV is enforced.
- **Pre-signed URLs from Layer 2**: when Mode 2 uploads + Mode 1 source images flow through Layer 2 → Layer 3, Layer 2 hands Layer 3 a pre-signed URL pointing at Layer 2's file store (or eventually Layer 4's signed-URL CDN). Layer 3 reads from that URL and never has direct access to user upload bytes. **Step 3 carve-out**: Layer 2's file store is just `storage/uploads/` for now (same as Step 2) — proper signed-URL infrastructure lands in Step 4.

## Requirements *(mandatory)*

### Functional Requirements

#### Mode 5 — Faceless Channel Automation

- **FR-001**: The Creation Dashboard MUST activate the **Faceless Channel** card so it routes to a working wizard. The "Coming in Step 3" badge MUST be removed.
- **FR-002**: The Faceless Channel wizard MUST accept a topic / keyword as its primary input plus voice + music (optional). It MUST NOT offer the Visuals selector (no upload mode for Mode 5; the entire point is automated stock).
- **FR-003**: When `mode == "faceless"`, Layer 3's pipeline MUST call Pexels + Pixabay directly via `material.py`. This is the ONE permitted direct external API call from Layer 3 per constitution Principle IV's Mode 5 exception.
- **FR-004**: When `mode != "faceless"` AND a request triggers `material.py` to call Pexels / Pixabay directly, `material.py` MUST raise / log an error and fall back to the pre-signed-URL path. This enforces Principle IV at runtime, not just by convention.
- **FR-005**: Mode 5 renders MUST produce 9:16 vertical video by default (consistent with the dashboard's TikTok-style preview). Aspect ratio is configurable per mode (Mode 3 will be 16:9 in Step 4).
- **FR-006**: Mode 5's audit log MUST set `params.mode == "faceless"` and `asset_audit.visuals_mode == "auto"`. The retry-tier shape from spec 006 is preserved (specific queries → general queries).

#### Mode 1 — Product Shoot Generator

- **FR-007**: The Creation Dashboard MUST activate the **Product Shoot Generator** card. The "Coming in Step 3" badge MUST be removed.
- **FR-008**: The Product Shoot wizard MUST accept exactly one product image (JPEG / PNG / WebP, ≤ 10 MB) as input. Optional: a brief text description of the product (≤ 200 characters) to bias the generation. No voice, no music — Mode 1 produces images only.
- **FR-009**: When the user clicks Generate, Layer 1 MUST POST to Layer 2's new `/api/v1/product-shoots` endpoint with the input image (multipart) + optional description.
- **FR-010**: Layer 2 MUST route the Mode 1 request to Layer 2.5's image-generation router, which calls **NanoBanana Pro** (or equivalent image-generation API; choice deferred to plan phase) with a "studio product photography, 6 variations" prompt enriched by the description.
- **FR-011**: Layer 2.5 MUST return 6 distinct studio-quality images per generation. The 6 images MUST be sliced from a 3×2 contact sheet (matching the master spec §3 design) OR returned as 6 individual images depending on the upstream API's shape; the contract MUST normalize to 6 individual image URLs in the response to Layer 1.
- **FR-012**: The wizard MUST display all 6 generated images in a grid view immediately upon completion. Each image MUST be downloadable individually.
- **FR-013**: A "Download all (ZIP)" button MUST package the 6 images into a single ZIP archive named `<product-name>-product-shoot-<timestamp>.zip`.
- **FR-014**: The 6 generated images MUST persist in the user's asset library indefinitely (subject to per-tenant retention policies in Step 4+) and appear in the My Assets page.
- **FR-015**: Mode 1 renders MUST NOT dispatch through Layer 3 (the rendering engine). Mode 1's whole pipeline lives in Layer 2 + Layer 2.5 + filesystem; Layer 3 has no role.

#### `app/services/modes/` registry

- **FR-016**: A new Python package MUST exist at `app/services/modes/` with one module per supported mode: `short.py` (Mode 2), `faceless.py` (Mode 5), `product_shoot.py` (Mode 1 — but exports stub registry hooks since Mode 1 doesn't use Layer 3 — keeps the registry symmetric).
- **FR-017**: Each mode module MUST export a stable Mode interface (e.g., a `Mode` class or set of named functions) covering: `generate_script(params)`, `generate_terms(params, video_script)`, `select_visuals_strategy(params)`, `default_aspect_ratio()`, plus mode-specific overrides as needed.
- **FR-018**: The registry MUST expose `modes.pick(name: str) -> Mode` returning the matching module, with `KeyError` (translated to HTTP 422) on unknown modes.
- **FR-019**: `app/services/task.py` MUST be refactored so `generate_script` and `generate_terms` become single-line calls to the registry: `mode_impl = modes.pick(params.mode); video_script = mode_impl.generate_script(params)`. The 3-branch dispatch (auto / verbatim / polish) from spec 013 is preserved as the first conditional layer; the mode-specific dispatch becomes the second.
- **FR-020**: After registry adoption, `app/services/llm.py`'s Mode 2 inline prompts (`generate_marketing_script`, mode == "short" branches in `generate_script` / `generate_terms`) MUST be MOVED into `short.py`'s implementation. The functions remain callable from `llm.py` for backward-compat (delegate to `short.py`) but ownership is now in the mode module.
- **FR-021**: STEP1_DEBT.md row #4 (Mode-Aware Rendering Contract) and row #5 (`task.py` outside fork-surface) MUST be struck through with `repaid in <commit sha>` annotations.

#### `material.py` rewrite — Asset URL acceptance

- **FR-022**: `app/services/material.py.download_videos` MUST accept pre-signed asset URLs from Layer 2 via the existing `visuals.json` sidecar pattern (spec 006). When the sidecar contains `pre_signed_clip_urls: [...]`, `material.py` downloads from those URLs instead of calling Pexels / Pixabay.
- **FR-023**: `material.py` MUST gate the retained `search_videos_pexels` + `search_videos_pixabay` direct-call paths behind a runtime check: only callable when `params.mode == "faceless"`. Any other mode hitting the direct-call path MUST raise `RuntimeError("principle_iv_violation")` to prevent silent regressions.
- **FR-024**: Mode 2's hybrid path (which currently calls Pexels + Pixabay direct via spec 006's hybrid logic) MUST be migrated to use pre-signed URLs from Layer 2 in a SUBSEQUENT release. **Step 3 carve-out**: this migration is OUT OF SCOPE for spec 015. Mode 2 hybrid continues to call Pexels + Pixabay direct (debt #3 partially repays — direct calls now permitted ONLY in Mode 5 and Mode 2's hybrid sub-path; the bulk-volume Auto / user_uploaded paths route through Layer 2). The remaining Mode 2 hybrid debt is scheduled for `Step 3.5` (a follow-up spec on this branch's lineage) or rolled into Step 4.
- **FR-025**: STEP1_DEBT.md row #3 (External Asset Acceptance) MUST be **partially struck through** — its Mode 2 Auto path retires (now routes through Layer 2's pre-signed URLs); its Mode 5 path is the permitted carve-out; its Mode 2 hybrid path remains as a smaller debt awaiting Step 3.5.

#### Layer 2.5 — Dynamic Model Router

- **FR-026**: Layer 2.5 MUST exist as a new package inside the Layer 2 service repo (`../visualai-orchestration/app/router/`) with at minimum: `image.py` (image-generation routing — first delivery), `__init__.py` exporting public dispatcher functions.
- **FR-027**: Layer 2.5's image router MUST expose a single function `generate_studio_photos(input_image_url, description, count=6) -> List[str]` that returns the URLs of generated images. The implementation calls NanoBanana Pro (or fallback) and saves outputs to Layer 2's local file store (same `storage/uploads/<tenant_id>/<uuid>.<ext>` pattern as Step 2).
- **FR-028**: Layer 2.5's API key for the image-generation provider MUST come from env var `LAYER25_NANOBANANA_API_KEY` (or equivalent per chosen provider). Production-safety guard refuses to start Layer 2 if the env is `production` and the key is missing/placeholder.
- **FR-029**: Layer 2.5 MUST log every outbound generation call with structured fields `tenant_id`, `user_id`, `model_name`, `cost_estimate_usd` (when known), `latency_ms`. Step 4's credit-ledger integration consumes these logs.
- **FR-030**: Video generation routing (Veo / Kling / Luma for hybrid context footage) is OUT OF SCOPE for Step 3. The architectural slot (`app/router/video.py`) is reserved but not implemented.

#### Constitution: amend Principle V to widen the Mode set

- **FR-031**: `.specify/memory/constitution.md` MUST be amended (MINOR version bump to v1.1.0) to add Mode 1 + Mode 5 to the accepted Agent Mode set's actively-implemented column. The constitution already lists all 5 modes by name; the amendment notes which are live as of Step 3.

### Key Entities

- **Mode (registry interface)**: One module per supported Agent Mode. Attributes: `name` (constant, matches `VideoParams.mode` literal), `default_aspect_ratio`, `script_prompt_template`, `term_strategy`, `material_strategy`, plus optional mode-specific hooks. No persistent state — module-level only.
- **Faceless Render Task**: Same shape as the existing Mode 2 render task, but with `params.mode == "faceless"`. Uses Pexels + Pixabay direct (the constitution's permitted Mode 5 exception).
- **Product Shoot Generation**: A new task type. Attributes: `id`, `tenant_id`, `user_id`, `source_image_url`, `description?`, `status` (`pending` / `running` / `complete` / `failed`), `output_image_urls: List[str]` (length 6 on success), `model_name`, `created_at`, `latency_ms`, `cost_estimate_usd?`. Persisted in Layer 2's task store (same `storage/tasks/<task_id>/` structure as Layer 3, mirrored in Layer 2).
- **Pre-signed Asset URL**: An HTTP URL pointing at a Layer 2 (Step 3) or Layer 4 (Step 4+) storage location. Attributes: `url`, `expires_at`, `content_type`, `byte_size`. In Step 3, the URL points at Layer 2's local `storage/uploads/<tenant_id>/<uuid>.<ext>` mounted at a per-task signed path.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of Mode 5 renders complete with `params.mode == "faceless"` AND use Pexels-derived clips ONLY. Verified by post-render audit invariant on every generation.
- **SC-002**: 100% of Mode 1 generations return exactly 6 image URLs within 60 seconds for the 95th percentile (covers NanoBanana's typical contact-sheet response time of ~30s plus round-trip overhead).
- **SC-003**: 0% of Mode 2 renders regress in output quality after Step 3 — A/B comparison of 10 identical Mode 2 inputs (subject + script + visuals_mode) before and after Step 3 produces visually-equivalent videos.
- **SC-004**: STEP1_DEBT.md rows #3 (partial), #4 (full), #5 (full) MUST be struck through with valid commit-sha annotations after Step 3's PRs merge.
- **SC-005**: Constitution Principle IV + V status flips from "DEBT" to "PASS" in the Step-3 PR description audits. Principle V's flip requires a constitution amendment to v1.1.0.
- **SC-006**: Adding a hypothetical Mode 6 (architectural-test exercise) requires editing **only** `app/services/modes/__init__.py` (registry export) + a new `app/services/modes/mode_6.py` + the `VideoParams.mode` literal. NO `task.py` / `material.py` / `llm.py` edits required. Verified by the US4 test exercise.
- **SC-007**: 0 incidents of Layer 3 calling NanoBanana / OpenAI image / video generation APIs directly. Verified by automated grep for prohibited imports / API URLs in Layer 3's source tree.
- **SC-008**: My Assets page lists Mode 1 (image-only) generations alongside Mode 2 + Mode 5 (video) generations within the same UI.

## Assumptions

- **Image-generation provider for Mode 1**: NanoBanana Pro is the primary choice per master spec §3. The plan phase MAY substitute an equivalent (e.g., FAL.ai's NanoBanana hosting, OpenAI's gpt-image-1, Google's Imagen 4) based on cost / latency / quality tradeoffs documented in `research.md`. The contract (input image + description → 6 studio photos) is provider-agnostic.
- **Layer 2's local file store** uses the same `storage/uploads/<tenant_id>/<uuid>.<ext>` shape that Step 2 introduced. Step 4's signed-URL CDN store is OUT OF SCOPE here; Step 3's "pre-signed URLs" are short-lived HTTP URLs minted by Layer 2 pointing at its local file mount.
- **Mode 2 hybrid Pexels / Pixabay calls** continue to live in Layer 3's `material.py` for Step 3. Migrating them to Layer 2.5's video-generation routing (Veo / Kling / Luma) is deferred to a follow-up spec — Step 3.5 or part of Step 4 — alongside the AI video-generation work.
- **Modes 3 + 4 placeholder UI** stays as "Coming in Step 4" badges. Spec 015 doesn't activate them.
- **Constitution v1.1.0 amendment** is part of this spec's PR. The amendment scope is narrow: note Mode 1 + 5 as actively-implemented, no principle changes. MINOR version bump because the active mode set expands (per the constitution's amendment rules).
- **`task_manager.add_task` thread safety**: registry modules MUST NOT hold mutable module-level state (since multiple renders run in parallel worker threads). Each mode's functions take params + return values; no class-level state.
- **NanoBanana Pro API contract**: assumed to accept a single source image + a text prompt and return either (a) a 3×2 contact sheet image that we slice to 6, or (b) 6 individual images directly. Plan phase confirms which.
- **Per-tenant cost tracking** for Mode 1's NanoBanana calls is logged but not enforced as a hard limit in Step 3. Hard limits + credit gating land in Step 4 alongside the data layer.
- **Mode 5's `error_code: "stock_apis_unavailable"`**: a new error code not previously defined. Documented in spec 015's contracts/.
- **Frontend dashboard cards**: today, Modes 1/3/4/5 are non-clickable with "Coming in Step N" badges. Spec 015 activates Modes 1 + 5 (clickable, route to wizards) and removes their badges; Modes 3 + 4 stay non-clickable.
- **My Assets page extension**: Mode 1 outputs are images, not videos — existing My Assets page logic that filters for `final-N.mp4` files needs extending to also enumerate image outputs from Mode 1 task directories. This is a Layer 1 frontend change inside spec 015's scope.
