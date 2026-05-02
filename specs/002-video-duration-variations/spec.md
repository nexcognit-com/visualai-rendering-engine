# Feature Specification: Video Duration Range, Variations, and Preview Gate for Long Videos

**Feature Branch**: `002-video-duration-variations`
**Created**: 2026-04-19
**Status**: Draft
**Input**: User description: "Videos duration needs to be from 5 seconds to 90 secs with click option to create variations , in case of long videos , a 5 sec preview will be created with human in the lopp to confirm before reduction"

## Overview

This feature establishes three coordinated capabilities for video generation in VisualAI:

1. **Duration control** — users pick any video length from 5 to 90 seconds, replacing the previous fixed per-mode duration bands.
2. **Variations on demand** — users click a "Create variations" button and receive multiple candidate renders from the same inputs, letting them pick the best one rather than re-submitting the whole prompt.
3. **Preview-before-commit gate for long videos** — when a user requests a "long" video (defined as duration > 30 seconds), the system first produces a cheap 5-second preview for each requested variation. Credits for the full-length render are only committed after the user approves one or more previews.

The three capabilities are interlinked: a single "Generate" click can produce N short full-length videos, or N long-video previews awaiting approval, depending on the selected duration.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Creator picks a precise video length (Priority: P1)

A marketing creator opens the Creation Wizard for a short marketing video, drags a duration slider to 22 seconds (or types 22 in the numeric input), and generates a video of exactly that length.

**Why this priority**: Fixed duration bands (e.g., "15, 30, 60") force creators to match the platform rather than the campaign brief. A continuous slider with a numeric fallback unblocks every downstream mode and replaces three disconnected UX rules ("short video is 15–60s", "long-form is 2–5 min") with one range.

**Independent Test**: A user selects durations of 5, 22, 45, 60, 75, 90 seconds across six separate generations. Each produced video's runtime MUST equal the selected value ± 1 second.

**Acceptance Scenarios**:

1. **Given** the Creation Wizard is open, **When** the user moves the duration slider, **Then** a numeric value between 5 and 90 is always displayed and the slider stops at those bounds.
2. **Given** the user types `93` into the numeric input, **When** the field blurs, **Then** the value is clamped to `90` and a toast explains the maximum.
3. **Given** the user types `3`, **When** the field blurs, **Then** the value is clamped to `5` and a toast explains the minimum.
4. **Given** the user confirms a duration and generates, **When** the final video is produced, **Then** the produced MP4's playable runtime equals the requested value ± 1 second (rounding to nearest frame).

---

### User Story 2 - Creator generates multiple variations with one click (Priority: P1)

A creator has set up a Short Marketing Video for a skincare product. Instead of generating, reviewing, tweaking, and re-submitting, they click "Create 3 variations." The system returns 3 distinct videos built from the same inputs so the creator can compare and pick the best.

**Why this priority**: AI output is probabilistic — one generation rarely nails the hook, pacing, or B-roll match. Variations-per-click is the highest-impact UX for creative quality and is standard across competing tools (Creatify, Pictory). Shipping without it feels like a beta.

**Independent Test**: A user clicks "Create 3 variations" on any duration ≤ 30 seconds. All 3 videos arrive in ≤ 3 minutes, each MUST be visibly distinct (different B-roll selection or different script phrasing), and all 3 count as independently playable deliverables.

**Acceptance Scenarios**:

1. **Given** the user is on the final wizard step, **When** they see the generate action, **Then** they can choose a variation count of 1, 2, or 3 (default: 3) via a small stepper next to the primary button.
2. **Given** the user clicks "Create 3 variations" with a 20-second duration, **When** the job starts, **Then** 3 parallel render tasks are enqueued and the progress UI shows 3 distinct progress tracks labeled "Variation 1, 2, 3."
3. **Given** all 3 variations complete, **When** the user opens the results screen, **Then** 3 playable video thumbnails are shown side-by-side, each with a "Keep" and "Discard" action.
4. **Given** the user discards 2 of 3 variations, **When** they confirm, **Then** only the kept variation remains in the Asset Library and credits for the discarded ones are NOT refunded (full pricing for all three).

---

### User Story 3 - Long-video preview gate prevents wasted credits (Priority: P1)

A creator sets duration = 60 seconds and clicks "Create 3 variations." Instead of immediately rendering three full 60-second videos, the system first produces three 5-second previews — one for each variation. The creator previews all three, approves two, and rejects one. Only the two approved previews continue to full 60-second render. Credits for the full-length version are debited only for the approved two.

**Why this priority**: Long videos are expensive to generate (compute cost and credit cost). A user who dislikes the preview style, voice, or pacing on a 60-second render has already paid for it. The preview gate is the single biggest cost-saving feature for creators working on longer content and protects against angry support tickets demanding credit refunds.

**Independent Test**: A user generates a 75-second video with 3 variations. The system produces three 5-second previews within 45 seconds total. The user approves 1 and rejects 2. Only 1 full 75-second video is produced and only 1 video's worth of credits is finally debited.

**Acceptance Scenarios**:

1. **Given** the user selects a duration > 30 seconds and clicks "Create N variations," **When** generation begins, **Then** the system first renders N × 5-second previews (each a representative sample of the full video: first 5 seconds of hook + script alignment) rather than full-length videos.
2. **Given** the previews finish, **When** the user arrives at the review screen, **Then** each preview is shown with a large video player, an "Approve" button, and a "Reject" button, and a banner explains "Approving commits the full X-second render and Y credits."
3. **Given** the user approves a subset of previews, **When** they confirm, **Then** only approved previews advance to full-length render; rejected ones stop and do NOT debit full credits (preview cost only).
4. **Given** a preview has been rendered and awaits user action, **When** the user leaves without deciding, **Then** the job remains in "Awaiting approval" state for at least 24 hours before auto-timeout.
5. **Given** the preview timeout expires without action, **When** cleanup runs, **Then** the job is marked expired, preview credits are retained (spent), and full-render credits are released back to the user's balance.
6. **Given** the user selects a duration ≤ 30 seconds, **When** they click generate, **Then** NO preview gate appears; full-length renders begin immediately.

---

### Edge Cases

- **Duration exactly 30 seconds**: No preview gate (gate triggers only at durations > 30s). This keeps the industry-standard 30-second ad free of friction.
- **User requests 1 variation of a long video**: A single 5-second preview is still produced and still requires approval. The gate is preview-vs-commit, not variation-count-based.
- **Preview and full render produce visibly different output**: Scripts generated for previews MUST be the first 5 seconds of the full script, not a separate "preview script." B-roll, voice, and pacing MUST match what the full render will produce. A ≥ 90% similarity between preview and full output is the acceptance bar.
- **Credit balance insufficient for full render after preview approval**: When the user clicks "Approve," the system re-checks the credit hold; if balance is insufficient, the full render is blocked and the user is shown a "Top up to continue" dialog. The preview is retained in the asset library at zero or preview-only cost.
- **Long-video preview fails to render**: The user is shown the failure and is NOT charged for the failed preview. They may retry with the same inputs at no cost.
- **Concurrent variation renders fail partially**: If 2 of 3 variations succeed and 1 fails, the user sees 2 playable results and 1 failure message. Credits are debited only for the 2 successes; the failed one is retried free up to 2 times.
- **User approves all N previews simultaneously**: All N full-length renders start in parallel; progress is shown per-variation.
- **A variation's preview is identical to another's**: When all N previews look the same (determinism collision), the system flags this and offers a "Regenerate with stronger diversity" button that re-submits with a different seed set at no additional preview cost.
- **Very short duration (5–10 seconds) combined with variations**: Full variations are produced immediately with no preview gate; this is the fastest path in the product.

## Requirements *(mandatory)*

### Functional Requirements

#### Duration Control

- **FR-001**: Users MUST be able to set any integer number of seconds from 5 to 90 (inclusive) as the desired video duration.
- **FR-002**: The Creation Wizard MUST present duration as a slider AND a numeric input bound to the same value; changing one updates the other.
- **FR-003**: Values outside the 5–90 range MUST be clamped to the nearest valid bound with an inline explanation.
- **FR-004**: The produced final video's playable runtime MUST equal the requested duration with a tolerance of ± 1 second (rounding to the nearest full frame at the video's frame rate).
- **FR-005**: The duration selection MUST be persisted as part of the job record so support can audit what the user requested.

#### Variations

- **FR-006**: Users MUST be able to select a variation count from {1, 2, 3} (default: 3) for any generation.
- **FR-007**: When N variations are requested, the system MUST produce N distinct renders from the same input set, varying at least one of: (a) LLM seed / script phrasing, (b) B-roll / footage selection, (c) music selection (if applicable).
- **FR-008**: All N variations MUST be visibly labeled "Variation 1, 2, 3" in the UI and in asset filenames or metadata for later reference.
- **FR-009**: Users MUST be able to keep or discard each variation individually on the results screen; keeping a variation adds it to the Asset Library, discarding does NOT refund credits.
- **FR-010**: Credit cost for N variations MUST equal N × single-video cost (no bulk discount, no surcharge).

#### Long-Video Preview Gate

- **FR-011**: When the requested duration is > 30 seconds, the system MUST render a 5-second preview for each requested variation BEFORE rendering the full-length video.
- **FR-012**: The preview MUST be a faithful representation of the first 5 seconds of the intended full video: same script opening, same voice, same B-roll selection for those 5 seconds, same pacing — NOT a separately-crafted teaser.
- **FR-013**: Preview rendering MUST charge a reduced preview-only credit cost that is a small fraction (not greater than 20 %) of the full-video cost for that variation.
- **FR-014**: After previews render, the user MUST be presented with an approval screen displaying each preview, a per-preview Approve / Reject action, and a visible statement of credits that will be debited on approval.
- **FR-015**: Only variations that the user explicitly approves MUST continue to full-length render; rejected previews MUST stop and release their full-render credit hold back to the user's balance.
- **FR-016**: A pending approval MUST remain actionable for at least 24 hours; after that the job MUST auto-expire, retaining only the preview cost as spent and releasing the full-render hold.
- **FR-017**: When the requested duration is ≤ 30 seconds, the preview gate MUST NOT engage; full-length renders start immediately on user submit.
- **FR-018**: The approval screen MUST show the preview's "first 5 seconds" clearly labeled, so the user understands they are judging a sample not a final product.

#### Credit & Billing Behavior

- **FR-019**: On submitting a variation job with duration > 30 s, the system MUST place a credit HOLD equal to N × full-video cost, then immediately debit only the N × preview cost; the remaining hold stays reserved pending approval.
- **FR-020**: On approval of K ≤ N previews, the system MUST debit the remaining (K × full-video cost) from the held amount and release any unused portion ((N − K) × full-video cost) back to available balance.
- **FR-021**: Rejected previews' full-render hold MUST be released to available balance within 10 seconds of rejection.
- **FR-022**: Auto-expired jobs MUST release full-render holds within 5 minutes of expiry.

### Key Entities

- **Video Job**: The user's request to generate video(s). Attributes include duration (5–90 s), variation count (1–3), mode, product reference, requested voice/music, preview_gate_required (derived from duration > 30 s), and state (draft → submitted → preview_rendering → awaiting_approval → full_rendering → complete → expired/failed).
- **Variation**: A single candidate render within a job. Attributes include variation index, seed set, preview asset URL, full asset URL, status (pending → preview_ready → approved/rejected/expired → full_ready → kept/discarded), preview_cost, full_cost.
- **Credit Hold**: A reservation against the user's balance tied to a job. Attributes include amount_reserved, amount_debited, amount_released, expires_at.
- **Preview Asset**: The 5-second sample rendered for approval. Attributes include duration (always 5 s), asset URL, derivation (always "first 5 s of the intended full render").

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100 % of generated videos fall within ± 1 second of the requested duration (measured by automated video-length inspection on every render).
- **SC-002**: Users who click "Create variations" with count ≥ 2 receive their full result set within ≤ 3 minutes for durations ≤ 30 s and ≤ 7 minutes for preview-gated durations including the approval step.
- **SC-003**: At least 70 % of users who set duration > 30 s and click generate review their previews within 1 hour; at least 85 % review within 24 hours (measured after 4 weeks in production).
- **SC-004**: Preview-gated jobs produce a measurable credit-savings outcome: at least 25 % of variations get rejected at preview, validating the gate's cost-protection purpose (measured after 4 weeks).
- **SC-005**: Preview-to-full visual similarity (first 5 s of full vs standalone preview) scores ≥ 90 % on an automated perceptual-similarity check for a random sample of 20 preview/full pairs per week.
- **SC-006**: Support ticket volume citing "my long video wasn't what I expected after paying full credits" drops by at least 80 % within 6 weeks of launch compared with the pre-launch baseline.
- **SC-007**: No user has been charged full credits for a rejected preview — verified by automated credit-ledger invariant: `debited ≤ preview_cost + (approved_count × full_cost)` for every job.

## Assumptions

- The 30-second threshold is the cutoff where the preview gate activates. Videos of exactly 30 s do NOT trigger the gate (threshold is strictly greater-than). This threshold is product-level policy and may be tuned post-launch; it is not a per-user setting.
- "Reduction" in the original feature description is interpreted as "credit deduction" / "full-render credit debit," matching the credit-based billing model in VisualAI Master Spec §6. The preview gate's purpose is to protect users from being debited for a full render they would reject.
- Variation count maximum of 3 is a reasonable industry default; expansion to 5 or 10 is a future enhancement not covered by this spec.
- Variation diversity is driven by seed variation on existing generation APIs (LLM / image / video / voice); adding entirely new routing logic is out of scope.
- The preview is the literal first 5 seconds of the intended full render, not a separately-crafted teaser. This keeps the user's judgment honest: "If you don't like this 5 s opening, the full 90 s won't fix it."
- Preview renders consume ≤ 20 % of the credits a full-length variation would cost. Exact pricing is set at launch per mode and is not frozen by this spec.
- Pre-existing fixed-duration rules in VisualAI Master Spec §3 (Mode 2 = 15–60 s, Mode 3 = 2–5 min) are superseded by this spec's 5–90 s range for modes in scope. Mode 3 (Long-Form, 2–5 minutes) is OUT OF SCOPE here and retains its own separate duration rules — it already has a different production pipeline.
- This spec governs frontend (Layer 1) and orchestration (Layer 2) behavior. The rendering engine (Layer 3, this repository, per constitution Principle I) MUST provide: (a) acceptance of an explicit duration parameter, (b) acceptance of a `render_mode: preview | full` flag, (c) generation of a 5-second preview that matches the first 5 s of the full render for identical inputs. No user management or credit logic lives in Layer 3.
- Credit-hold semantics (hold → debit / release) align with the existing credit ledger pattern described in VisualAI Master Spec §6.
- For modes in scope, "long video" means duration > 30 s within the 5–90 s range. The preview gate is a UX pattern independent of mode; adding it to Mode 3 Long-Form (2–5 min) may be desirable later but is not covered here.
