# Feature Specification: User-Uploaded Model & Product Assets

**Feature Branch**: `006-user-uploaded-assets`
**Created**: 2026-04-22
**Status**: Draft
**Input**: User description: "there should be an option instead of letting the app pull image , user can add an image of a model and up to 3 images of the product he wants to generate video for"

## Overview

Today every Mode 2 (Short Marketing Video) generation pulls B-roll from Pexels stock. For a specific product — a ring, a pair of sneakers, a skincare bottle — stock footage will never match the actual item; it shows *a* generic diamond ring, not *this* diamond ring. The output looks disjointed because the clips are unrelated to one another and unrelated to the real product.

This feature adds an explicit **"Use my own assets"** option to the Creation Wizard. When selected, the user uploads:

- **One model image** (optional) — a portrait or styled shot of the person representing the brand/product context.
- **One to three product images** (required when the option is selected) — close-up or context shots of the specific product being advertised.

These images become the video's B-roll, replacing the Pexels fetch entirely. The system produces motion from the still images (zoom/pan for Step 1; true image-to-video via Layer 2.5's Dynamic Model Router in Step 3+). The voiceover, subtitles, and music pipeline remain unchanged.

## Clarifications

### Session 2026-05-02

- Q: Implementation phasing — Step 1 ship-now or wait for Step 2/3? → A: Ship in Step 1 now, mirroring specs 009 (logo overlays) and 010 (music control). Storage at `storage/uploads/<uuid>.<ext>`; no Layer 2; permissive moderation heuristic in Step 1 with mandatory cloud-moderation upgrade before public release; single-user. STEP1_DEBT.md gains row(s) for any rules relaxed. The spec's "Layer 2" framing in §Assumptions is treated as forward-compatibility wording: scope-per-tenant when debt #2 repays in Step 2.
- Q: Wizard placement — where does the asset-source selector live? → A: Inside the existing **Script & Voice** step (the step that already hosts spec 013's script-mode pills and spec 010's music selector). The selector sits as a parallel pill row labelled **Visuals** with two options: `Auto (stock)` and `Use my own assets`. Step 1 stays strictly about input (URL / image / script). FR-001 is updated accordingly.
- Q: Where does the auto-vs-uploaded video pipeline branch live? → A: Inside `app/services/material.py.download_videos`. The function checks `params.visuals_mode == "user_uploaded"` and either calls Pexels (auto path, current behavior) or converts uploaded image paths into clips with Ken Burns motion (new code path). This is the early shape of debt #3's eventual repayment ("rewrite `material.py` to accept pre-signed URLs from Layer 2"). No new `task.py` edit; debt #5 line count stays unchanged. The Ken Burns motion implementation may live in a private helper inside `material.py` or be delegated to a new function inside an existing fork-surface file — final placement decided in `/speckit-plan`.
- Q: Motion-from-stills depth in Step 1? → A: Slow zoom (in or out, alternated per image, 4–8% over the segment duration) + optional 3% pan in a random direction + crossfade. Implemented via MoviePy `ImageClip` + `.resize(lambda t: ...)` and `.set_position(lambda t: ...)`. ~10 lines of helper code; satisfies FR-013's "zoom/pan (Ken Burns)" wording. Saliency-aware Ken Burns is deferred to a future milestone alongside FR-011's drag-to-reframe override.
- Q: Content moderation in Step 1? → A: Local heuristic only (content-type + dimension validation + basic visual-signal check), logged in audit but non-blocking. A `MODERATION_REQUIRED` config flag defaults to `False` in Step 1; flipping it to `True` activates a real cloud moderation API in a later milestone. STEP1_DEBT.md gains a row marking SC-006 as unmet in Step 1 and naming the public-launch precondition. FR-010 wording is updated to reflect this Step-1 carve-out.

### Session 2026-05-03

Post-implementation pivot: the original `auto` ⇄ `user_uploaded` binary turned out to produce slideshow-quality renders for SaaS/product-marketing content. Real product videos cut between *contextual setting* (people, environment) and *product reveal* (UI/screenshot). This session adds a third mode — **hybrid** — and tightens `generate_terms` so Pexels queries return setting/use-case footage rather than literal product-feature search terms.

- Q: Hybrid-mode interleave pattern? → A: Strict alternation `[stock, user, stock, user, …]`, always opening on stock. Deterministic, simple to test, gives the hook 2–3 s of real-world context before the product reveal. The model bookend rule from FR-015 (when present) takes precedence at the absolute opening + closing positions; alternation operates between them.
- Q: `generate_terms` prompt scope for hybrid mode (and Auto mode by extension)? → A: Two-pass. First pass: LLM extracts a single industry/setting tag from the script (one of `manufacturing`, `healthcare`, `retail`, `office`, `logistics`, `hospitality`, `education`, `fitness`, `construction`, `agriculture`, or `general`). Second pass: a separate prompt expands that tag into 5 Pexels-friendly setting queries (e.g., `manufacturing` → `["worker on factory floor", "automated assembly line", "quality control inspection", "warehouse forklift operations", "industrial robot arm"]`). Product-feature search terms are never queried. The setting tag is persisted in `script.json#asset_audit.setting_tag` for verifiability and future analytics.
- Q: Stock-empty fallback for hybrid mode? → A: Two-tier retry. Stage 1: try the 5 specific setting queries; if any returns clips, use them. Stage 2: if Stage 1 returns zero, retry with the `general` tag's 5 queries (common B-roll like `["people walking through office", "business meeting handshake", "city street time-lapse", "person typing on laptop", "team collaboration whiteboard"]`). Stage 3: if Stage 2 ALSO returns zero, fall back to all-user-images and record `pexels_empty_fallback: true` in `script.json#asset_audit` so the wizard can surface a soft warning. No hard error.
- Q: Stock source(s) for hybrid mode? → A: **Pexels + Pixabay** as parallel sources; both are already integrated in upstream MPT's `material.py` (`search_videos_pexels` + `search_videos_pixabay`). The hybrid renderer queries both for each setting term, dedupes by URL, and picks first N matches; if a single search term returns clips from one source but not the other, the result is still usable. Roughly doubles inventory at zero new cost or new dependency. The architectural seam for AI-generated context footage (Veo / Kling / Luma routed through Layer 2.5 per Principle IV) is left open for Step 3+; spec 006 does NOT call any generation API directly. Adding paid stock sources (Storyblocks, Adobe Stock) is deferred — likely won't be worth the cost once Layer 2.5 routes to AI generation.
- Q: Where does the model image sit in hybrid mode (FR-015 bookend rule conflicts with Q1's "open on stock")? → A: **Model image fills the first user-image slot (position 2)**. Pattern with 1 model + 3 products in hybrid mode: `[stock, model, stock, product_1, stock, product_2, stock, product_3, stock_closing]`. Opens on stock for setting context (per Q1), reveals brand within 2–3 s via model in slot 2, alternates remaining product clips with stock context. The pure `user_uploaded` mode keeps the original FR-015 bookend rule unchanged (model opens + closes); only hybrid mode applies this revised placement.

This feature **does not** remove the existing "auto (stock footage)" path. The user picks one of two modes at wizard Step 1:

1. **Auto** — current Pexels-based flow (fast, generic, best for topic-driven content like Mode 5 Faceless Channel).
2. **My assets** — user uploads 1 model + 1–3 product images (slower to prepare, dramatically more on-brand for product marketing).

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Creator generates a Mode 2 video using their own product photos (Priority: P1)

A small-business owner wants a 20-second ad for her new line of ceramic coffee drippers. She has three product photos her photographer took last week: a top-down shot on a wooden table, a close-up of the spiral pour pattern, and a lifestyle shot of the dripper beside a steaming cup. She opens the Creation Wizard, picks **"Use my own assets"**, uploads those three images, writes or accepts a script about the product, and hits Generate. The resulting video features ONLY her three photos (animated with zoom/pan and cross-fades), a voiceover describing the product, and burned-in subtitles. Not a single frame of Pexels stock.

**Why this priority**: Product marketing is the core VisualAI use case. Without this, every Mode 2 render is generic and looks nothing like the user's actual product. Fixing this is the single largest step-change in output quality between "toy demo" and "usable product."

**Independent Test**: Upload 3 product images, generate a video, and verify every frame of the output originates from one of the uploaded images (no Pexels clips). Confirm via `ffprobe` that video runtime equals audio runtime ± 1 s, and via visual inspection that each uploaded image gets at least 2 seconds of screen time.

**Acceptance Scenarios**:

1. **Given** the Creation Wizard is open, **When** the user reaches the **Script & Voice** step, **Then** they see a **Visuals** pill row with two options: `Auto (stock)` and `Use my own assets` — defaulting to `Auto`.
2. **Given** the user picks `Use my own assets`, **When** the Visuals selector toggles, **Then** an upload area appears beneath the pill row showing slots for one Model image (optional) and three Product image slots (at least one required), inline within the same step.
3. **Given** the user drags a product photo (JPEG, 2 MB) into the first product slot, **When** the upload completes, **Then** a thumbnail preview appears within 2 seconds and the slot shows a green checkmark + filename.
4. **Given** the user has uploaded 3 product photos and no model image, **When** they click Generate, **Then** the generation starts with no errors, and the resulting video uses only those 3 images as visual source.
5. **Given** the user tries to click Generate with zero product images uploaded, **When** they attempt submit, **Then** the button is disabled with a tooltip: "Upload at least one product image to continue."
6. **Given** the render completes, **When** the user plays the result, **Then** every visible frame traces back to one of the user's uploaded images (confirmed by a final-asset audit log).

---

### User Story 2 — Creator includes a model image to anchor the video's opening (Priority: P1)

A skincare brand founder wants her face associated with her serum. She uploads one hero portrait of herself (the "model image") plus three product photos. The resulting 30-second video opens on her portrait (with a subtle zoom-in), transitions to the three product photos in sequence, and returns briefly to her portrait at the end. The model image anchors the brand; the product images carry the demonstration.

**Why this priority**: Brand-led content needs a consistent visual anchor. A single product photo × 4 repetitions is monotonous; mixing in a human face creates warmth and trust. This is the second-most-requested feature in creator interviews (behind #1 which is "my own product shots").

**Independent Test**: Upload 1 model image + 3 product images, generate, and verify the model image appears in at least 2 non-consecutive segments of the video (e.g., opening + closing), and the product images appear in order between them.

**Acceptance Scenarios**:

1. **Given** the model image slot is filled plus 3 product slots, **When** the video renders, **Then** the model image is used for the opening shot (first 3–5 seconds) AND for the closing shot (last 2–4 seconds) by default.
2. **Given** the user wants different placement, **When** they expand an advanced "Image placement" control, **Then** they can set each slot's usage to `Opening`, `Middle`, `Closing`, or `Auto (default)`.
3. **Given** the model image is uploaded but no product images, **When** the user attempts Generate, **Then** the system warns: "A product image is required. The model image alone cannot tell your product story."

---

### User Story 3 — Creator switches between "Auto" and "My assets" mid-session (Priority: P2)

A user starts in `Auto` mode for a brainstorming generation, doesn't like the stock results, and wants to retry with their own assets. They toggle back to Step 1, switch to `Use my own assets`, upload images, and regenerate — without having to close and reopen the wizard or lose the script/voice they already configured.

**Why this priority**: First-attempt generations rarely satisfy; creators iterate. Forcing them to restart the whole wizard is friction that costs conversion.

**Independent Test**: Run an `Auto` generation, then without leaving the wizard, toggle to `Use my own assets`, upload 2 product photos, and regenerate. The script/voice settings from the first attempt carry over. The second generation uses only uploaded assets.

**Acceptance Scenarios**:

1. **Given** a generation has completed in `Auto` mode, **When** the user clicks "Make another" and toggles to `Use my own assets`, **Then** the wizard reappears with the previous script and voice preserved, but the upload area is empty.
2. **Given** the user toggles from `My assets` to `Auto`, **When** they advance, **Then** uploaded images are retained in the session (one click to restore) but are not used in the upcoming render unless toggled back.
3. **Given** the user uploaded 3 images in `My assets` mode, **When** they switch to `Auto` and regenerate, **Then** none of the uploaded images appear in the `Auto` result — the two modes are strictly separate.

---

### Edge Cases

- **Unsupported file type**: user drops a `.tiff` or `.heic` file. Reject client-side with "JPEG, PNG, or WebP only." Server re-validates.
- **Image too large**: files > 10 MB rejected with "Max 10 MB per image." Files > 30 MB rejected before the upload starts (client-side size check before network transfer).
- **Image too small / low resolution**: anything under 720 px on the longest side gets a soft warning ("This will look soft; prefer images ≥ 1080 px") but is allowed.
- **Source aspect doesn't match output**: uploads are auto-cropped to 9:16 (Mode 2 default) centered on the most salient region; user can override with a drag-to-reframe tool in a follow-up milestone.
- **User uploads a video file by mistake**: the uploader displays the MIME-type error; the wizard doesn't crash.
- **User removes an image mid-upload**: stale upload is cancelled; slot returns to empty state.
- **Malicious content / NSFW image**: flagged by an automated moderation pass (e.g., cloud moderation API) before the image joins the render pipeline; user sees a clear rejection without the image being processed.
- **Model image contains multiple faces**: current behavior is to treat the whole frame as the hero image without face-crop. A future milestone may add face-centric reframing.
- **Uploaded image has a transparent background (PNG)**: background is composited onto a neutral fill (brand color or black) before animation.
- **User uploads the same file twice**: accepted; treated as two separate slots. No deduplication (user may intentionally repeat an image for emphasis).
- **Partial upload failure (network drop)**: the failed slot shows a red retry icon; other completed slots are unaffected.
- **Generation starts before all uploads finish**: Generate CTA is disabled until every slot with a file shows a completed state.
- **Asset retention**: uploaded images are retained with the generation record for a documented period (default: as long as the generation exists; user can delete on demand).

## Requirements *(mandatory)*

### Functional Requirements

#### Wizard Option & Entry

- **FR-001**: The Creation Wizard's **Script & Voice** step MUST expose a **Visuals** selector with three mutually-exclusive modes: `Auto (stock footage)`, `Hybrid (your assets + relevant stock)`, and `Use my own assets`. `Auto` is the default. The selector renders as a pill row consistent with the existing script-mode and music selectors in the same step. **Hybrid** (per Clarifications 2026-05-03) interleaves user uploads with Pexels + Pixabay stock context clips queried via a two-pass setting-tag prompt; behavior detailed in FR-022..FR-025.
- **FR-002**: Switching modes within an open wizard session MUST preserve script, voice, and other downstream choices; only the asset-source context changes.

#### Upload Area & Slots

- **FR-003**: When `Use my own assets` is selected, the UI MUST present one Model image slot (optional) and three Product image slots (numbered 1, 2, 3). At least one Product slot MUST be filled before Generate enables.
- **FR-004**: Each slot MUST support drag-and-drop, click-to-select from file picker, and clear/replace actions.
- **FR-005**: Completed uploads MUST display: thumbnail preview, filename, file size, and a remove (×) control.
- **FR-006**: In-progress uploads MUST display a progress indicator. Failed uploads MUST display a retry control.

#### Accepted Files & Validation

- **FR-007**: The system MUST accept `image/jpeg`, `image/png`, and `image/webp` content types. Other types MUST be rejected with a clear error at the point of upload.
- **FR-008**: Maximum file size MUST be 10 MB per image, enforced both client-side (pre-upload) and server-side (post-upload).
- **FR-009**: Images smaller than 720 px on the longest side MUST trigger a soft-warning toast but MUST still be accepted.
- **FR-010**: Uploaded images MUST pass an automated content-safety check before joining the render pipeline. Rejected images MUST NOT appear in any output. **Step 1 carve-out (per Clarifications 2026-05-02)**: when `MODERATION_REQUIRED=False` (Step 1 default), the safety check is a local lightweight heuristic that logs but does NOT block; SC-006 is explicitly unmet in Step 1. Flipping `MODERATION_REQUIRED=True` activates a real cloud moderation API and is a precondition for any public launch.
- **FR-011**: The system MUST auto-crop every uploaded image to the target video aspect ratio (9:16 for Mode 2). The crop MUST be centered on the image's most salient region using a server-side saliency heuristic; users MUST be able to override the crop in a later milestone (not required for feature parity).

#### Video Construction from Uploaded Images

- **FR-012**: When `Use my own assets` is selected, the video MUST be constructed EXCLUSIVELY from the user's uploaded images. ZERO Pexels or Pixabay clips MUST appear in the output. This MUST be verifiable via a per-render asset audit log. (Hybrid mode has its own composition contract — see FR-022..FR-025.)
- **FR-013**: The system MUST convert each still image into motion via a zoom/pan (Ken Burns) effect, cross-faded between segments. Cross-fade duration MUST be 0.3–0.5 s.
- **FR-014**: Each uploaded image MUST receive at least 2 s of screen time in the final video, unless doing so would make the total runtime exceed the voiceover runtime; in that case, all images MUST receive equal screen time covering the voiceover duration.
- **FR-015**: In `user_uploaded` mode, when a model image is present, it MUST appear in the opening segment (first 3–5 s) AND closing segment (last 2–4 s) by default, bookending the product images. Product images MUST play sequentially between the model bookends in the order uploaded. (In `hybrid` mode the model bookend rule is replaced by FR-022's slot-2 placement; opening + closing positions are reserved for stock context per Q1.)
- **FR-016**: Cross-fades between image segments MUST respect a minimum segment length (≥ 2 s); the system MUST NOT produce flicker-fast cuts.

#### Storage & Retention

- **FR-017**: Uploaded images MUST be stored per-user in a way that a second user in the same tenant cannot see them.
- **FR-018**: Uploaded images MUST persist with the generation record for as long as the generation record exists. If the user deletes the generation, the images deleted together.
- **FR-019**: Users MUST be able to delete an uploaded image at any time from their asset library; doing so MUST NOT retroactively alter past generations that consumed the image.

#### Auditability

- **FR-020**: Every generation using `Use my own assets` MUST produce a per-render audit log listing the exact filenames, content hashes, and order of uploaded images that contributed to the final video.
- **FR-021**: The audit log MUST record the mode toggle state (`Auto` vs `Hybrid` vs `Use my own assets`) for every generation, regardless of which mode was used.

#### Hybrid Mode (added per Clarifications 2026-05-03)

- **FR-022**: When `visuals_mode == "hybrid"`, the renderer MUST interleave user uploads with stock context clips in strict alternation, opening on stock: `[stock, user, stock, user, …, stock_closing]`. The model image (when present) MUST occupy the first user-image slot (position 2 of the sequence); product images fill the remaining user-image slots in upload order.
- **FR-023**: Stock clips for hybrid mode (and Auto mode by extension) MUST be selected via a two-pass LLM-driven query: pass 1 extracts a single industry/setting tag from the script (one of `manufacturing`, `healthcare`, `retail`, `office`, `logistics`, `hospitality`, `education`, `fitness`, `construction`, `agriculture`, `general`); pass 2 expands that tag into 5 Pexels-friendly setting queries. Product-feature search terms MUST NOT be queried.
- **FR-024**: Hybrid-mode stock fetching MUST query Pexels AND Pixabay in parallel for each setting query, dedupe by URL, and select clips by first-match order. Two-tier retry MUST run if a tier returns zero clips: tier 1 = the 5 specific setting queries; tier 2 = the 5 `general` tag queries; tier 3 = fall back to all-user-images and record `pexels_empty_fallback: true` in the audit log.
- **FR-025**: The audit log under `script.json#asset_audit` MUST include `setting_tag` (the resolved industry tag), `stock_queries` (the 5 setting queries used), and per-stock-clip entries with `provider` (`pexels` or `pixabay`) and `query` (the term that matched). When fallback to user-only fires, `pexels_empty_fallback: true` MUST appear at the top level.

### Key Entities

- **Uploaded Asset**: A single image the user has provided. Attributes: id, owner_user_id, tenant_id, role (`model` or `product`), original_filename, content_hash, stored_path, mime_type, byte_size, source_width_px, source_height_px, cropped_path (9:16), uploaded_at, safety_check_result.
- **Asset Bundle**: The grouping of one optional Model Asset + 1–3 Product Assets submitted for a specific generation. Attributes: id, generation_id, model_asset_id (nullable), product_asset_ids (ordered list), created_at.
- **Generation Asset Audit**: Per-render log of which exact assets contributed. Attributes: generation_id, bundle_id, asset_ids_in_order, mode (`auto` or `user_uploaded`), created_at.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of `Use my own assets` renders contain ZERO Pexels/Pixabay frames, verified by the audit log invariant on every generation.
- **SC-002**: A user with 3 pre-saved product photos can complete a full generation (upload → script → voice → render → playback) in under 4 minutes.
- **SC-003**: ≥ 70% of users who try a `Use my own assets` render in their first session rate the resulting video "usable" or better (internal 5-point scale), versus a baseline measurement of the `Auto` stock mode.
- **SC-004**: File uploads complete within 10 seconds for 95% of images on a typical home-broadband connection (target size: 5 MB file on a 20 Mbps connection).
- **SC-005**: 0 incidents of one user seeing another user's uploaded images across all tenants, verified by automated authorization tests on every deploy.
- **SC-006**: Automated content-safety check rejects 100% of a standard adversarial image test set before any such image reaches the render pipeline.
- **SC-007**: For a render with one model + three product images, each image receives at least 2 seconds of screen time in ≥ 95% of outputs (the remaining 5% are very short videos where equal-time apportionment dominates).
- **SC-008**: The mode toggle in the wizard preserves script + voice state across ≥ 99% of switches (measured via instrumentation across the first 500 switches post-launch).

## Assumptions

- Uploads are a first-class part of Mode 2 (Short Marketing Video) and MAY extend to Mode 3 (Long-Form Video) later. Mode 5 (Faceless Channel) continues to be topic-driven and does NOT offer uploads — faceless content is the stock-footage use case.
- "Model image" in this spec means a still product-marketing portrait or styled shot, NOT a lip-synced talking-head avatar. Avatars that speak belong to Mode 4 (UGC Avatar Ad) per VisualAI Master Spec §3. If a user wants their model to speak, they select Mode 4 instead.
- Uploads become the B-roll **only when the user opts in**. Existing `Auto` flow (Pexels) is preserved as the default and remains fully functional.
- Motion from stills uses zoom/pan (Ken Burns) for Step 1 / Step 2 delivery. Step 3+ routes the user's uploaded images through Layer 2.5's image-to-video model (e.g., Veo, Kling, or Luma) to generate true motion from stills — dramatically more realistic. The feature's visible contract (user uploads → video uses those images) is identical across both implementations.
- Aspect-ratio reframing is automatic center-crop for v1. A drag-to-reframe tool is a follow-up milestone.
- Content-safety scanning uses a cloud moderation API (choice deferred to plan phase). A Step-1 simplification may use a permissive local heuristic with explicit upgrade to the cloud service before any public release.
- This spec governs Layer 1 (frontend — upload UI) and Layer 2 (orchestration — validation, moderation, storage) behavior. The rendering engine (Layer 3, this repository, per constitution Principle I) receives pre-signed URLs to the cropped assets and composes them into the final video — it does NOT host the raw upload store. **Step 1 carve-out (per Clarifications 2026-05-02)**: until Layer 2 exists, the upload endpoint and local storage live in this Layer 3 repo at `storage/uploads/<uuid>.<ext>` mirroring specs 009/010; this is recorded as a debt row alongside debts #1–#5 in `STEP1_DEBT.md`.
- Storage retention follows the generation's lifecycle. Standalone asset libraries (where users save reusable product photos independent of a specific generation) are a future Brand Library feature per VisualAI Master Spec §9 Phase 2 and are OUT OF SCOPE here.
- Tenant admins and users within the same tenant do NOT share asset pools by default. Tenant-level shared asset libraries are a future capability.
- `config.toml` / Settings (spec 005) is NOT involved — this feature's data is per-render user data, not configuration.
- Interaction with the active Step 1 Mode 2 MVP: this feature ships **inside Step 1** per Clarifications 2026-05-02 (revising the original Step 2/3 target). The wizard's mode selector exposes `Use my own assets` as soon as the backing endpoint and renderer branch land; no feature flag is required because the toggle defaults to `Auto` (current behavior) and uploads only activate when the user opts in.
