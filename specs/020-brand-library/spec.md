# Feature Specification: Brand Library — tenant-scoped persistent brand assets

**Feature Branch**: `020-brand-library`
**Created**: 2026-05-10
**Status**: Draft
**Input**: User description: "Brand Library — a tenant-scoped persistent repository where creators save and reuse brand assets across every render. v1 covers brand logos (transparent PNGs uploaded once, available to any Mode wizard), brand colors (hex tokens reusable in overlays plus future style application), and brand voice (free-text tagline or mission statement used as context for script generation). Visible in Layer 1 as a /brand page in the existing sidebar nav. Styled to match analytics.nexcognit.com — dark theme, clean cards, tenant-isolated."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Save a logo once, reuse across all Modes (Priority: P1)

A creator opens the VisualAI app, navigates to the Brand Library tab in the sidebar, and uploads a transparent PNG of their company logo. They give it a label ("Primary logo") and save. Later, when they open Mode 2 (Short Marketing Video) and reach the overlays step, the saved logo appears as a one-click pick alongside an "Upload new" option. They click it, finish the wizard, and the rendered MP4 carries that logo without ever uploading the file again. The same one-click selector appears in Modes 1, 3, 4, and 5 wherever an overlay slot exists.

**Why this priority**: This is the entire reason the feature exists — without P1, every render is a fresh upload, every wizard re-asks for the same brand assets, and there is no continuity across the 5 Modes. P1 turns "VisualAI knows your brand" from a marketing claim into a product behavior.

**Independent Test**: As a single test user, upload one logo through the Brand Library page, dispatch one render in Mode 2 picking that logo from the library (no re-upload), play the result, confirm the logo appears. Then dispatch a Mode 5 render with the same logo (still no re-upload), confirm the same logo appears. P1 passes when both renders carry the logo and the file was uploaded exactly once.

**Acceptance Scenarios**:

1. **Given** the Brand Library page is open with no saved assets, **When** the creator uploads a transparent PNG and labels it "Primary logo", **Then** the logo appears in a card-grid view with the label and an upload timestamp, plus a delete affordance.
2. **Given** at least one saved logo exists, **When** the creator opens Mode 2 (or any other Mode with overlay support) and reaches the overlay step, **Then** the saved logos appear as one-click thumbnails in addition to the existing "upload new" affordance, with the saved labels visible.
3. **Given** the creator picks a saved logo in the wizard, **When** they dispatch the render, **Then** the rendered MP4 has the logo composited per the existing per-render overlay rules (spec 009) and the asset file was NOT re-uploaded — only its identifier was passed to Layer 2.
4. **Given** the creator deletes a saved logo, **When** any in-progress wizard that referenced that logo is reopened, **Then** the wizard surfaces a "this asset was deleted, pick another" warning rather than failing silently at render time.

---

### User Story 2 — Save a brand color and use it as an overlay accent (Priority: P2)

The creator wants their brand-accent hex color (e.g., `#FF6B35`) to appear consistently across every render that uses a colored rectangle overlay or a tinted lower-third. They open Brand Library, click "Add color", paste or pick the hex value, label it ("Brand orange"), save. Later in any Mode that supports rectangle overlays, the saved color appears in the wizard color picker as a one-click choice. They never have to re-paste the hex anywhere.

**Why this priority**: P2 because it adds a second asset type beyond logos and is materially less load-bearing than P1 (a creator can ship without saved colors by re-pasting per render). But it is cheap on the data model side once the persistence backend exists, and it sets up the future Style Pack expansion (multiple coordinated colors per brand).

**Independent Test**: Save one hex color in the Brand Library, open a Mode 2 wizard overlay step, confirm the color appears in the picker as a labeled chip. Pick it, dispatch render, confirm the rectangle overlay in the output uses that exact hex value.

**Acceptance Scenarios**:

1. **Given** the Brand Library page is open, **When** the creator pastes a 6-character hex value (with or without leading `#`) and labels it, **Then** the color is saved and appears as a labeled chip in the page.
2. **Given** at least one saved color exists, **When** the creator reaches a wizard step that picks an overlay color, **Then** the saved colors appear as one-click chips with the labels visible alongside the freeform color input.
3. **Given** the creator saves an invalid hex value (e.g., `#XYZ123`), **When** they attempt to save, **Then** the page rejects the value with an inline error before persisting.

---

### User Story 3 — Save a brand voice tagline used as script-generation context (Priority: P3)

The creator has a consistent brand tagline / mission statement they want every auto-generated script to be aware of (e.g., "We build calm, judgment-free fitness tools for people over 50"). They paste it into the Brand Library Brand Voice field, save, and from that point onward every Auto-mode or Polish-mode script generated in any Mode includes the tagline as part of the LLM system context — meaning the resulting copy stays on-brand without per-render re-prompting.

**Why this priority**: P3 because it touches the LLM dispatch path (Layer 3), not just the L1/L2 surface, and the value is harder to verify (subjective). It is included in the spec rather than deferred so the data model accommodates it from day one — adding it later would require a schema migration. But it ships only after P1 and P2 are stable.

**Independent Test**: Save a brand voice tagline. Generate a Mode 2 Auto-mode script. Inspect the script (visible in the wizard preview) for evidence the LLM was aware of the tagline (e.g., the phrase "judgment-free" appears in the output, or the tone shifts measurably toward the brand). Repeat with the tagline cleared and confirm the output reverts to the un-flavored baseline.

**Acceptance Scenarios**:

1. **Given** the creator saves a brand voice tagline of up to 280 characters, **When** they later generate an Auto-mode or Polish-mode script in any Mode, **Then** the LLM dispatch carries the tagline as context (verified by inspecting the request payload at the L3 boundary in dev mode).
2. **Given** no brand voice is saved, **When** the same Auto-mode script is generated, **Then** the LLM dispatch does NOT include any brand-voice context — the existing behavior is byte-identical to today.

---

### Edge Cases

- **Empty library at first wizard open** — when no logos / colors / voice exist, the wizard overlay step shows a "no saved assets yet — upload one or skip" affordance with a link to the Brand Library page. Never an empty silent picker.
- **Large logo upload** — the existing image-upload backend caps payload size; if the creator uploads a logo above the cap, the page surfaces the same typed `file_too_large` error as the existing image-upload path, no special new error.
- **Logo with no transparency** — accepted, surfaced with a one-line warning ("logo has no alpha — will be a solid rectangle over the video"). Does not block save.
- **Creator deletes a logo while a render referencing it is in flight** — the in-flight render completes with the logo (Layer 3 already has the local copy). Future renders cannot select the deleted logo. The wizard reflects the deletion immediately.
- **Tenant boundary leak attempt** — a creator from tenant A cannot view, select, or delete tenant B brand assets. Every L2 endpoint enforces tenant isolation via the existing JWT middleware (constitution §III). v1 has no asset-sharing model.
- **Hex color in a non-RGB notation** (HSL, named colors, rgba) — rejected at save time with a one-line "hex notation only at v1" error. Future expansion allowed but explicitly out of v1 scope.
- **Brand voice longer than the 280-char cap** — rejected at save time. Cap is chosen so the tagline fits cleanly inside any LLM system-prompt budget without crowding the existing per-mode prompts.
- **Two creators in the same tenant edit the same library concurrently** — last-write-wins at v1 (no locking, no merge UX). Acceptable for v1 single-creator-per-tenant pattern; revisit when team-sharing arrives.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The Brand Library page MUST be accessible from the existing Layer 1 sidebar at `/brand` and MUST be tenant-isolated — a session for tenant A only sees tenant A assets.
- **FR-002**: The Brand Library MUST support saving a brand logo as a transparent PNG (or PNG with no alpha; see Edge Cases). The asset is stored via the existing Layer 3 `/api/v1/uploads/image` endpoint under the tenant already-tenant-scoped uploads path. No new image-storage surface is introduced at v1.
- **FR-003**: The Brand Library MUST support saving a brand color as a 6-character RGB hex value (with or without a leading `#`), labeled by the creator. Persistence is via a new Layer 2 endpoint described in `contracts/`.
- **FR-004**: The Brand Library MUST support saving a brand voice — a single free-text string, max 280 characters — labeled by implication (one brand voice per tenant at v1). Persistence is via the same Layer 2 endpoint as colors.
- **FR-005**: For any saved logo, the L1 page MUST display a thumbnail of the image, the creator-supplied label, the upload timestamp, and a delete affordance. Delete is soft-delete at the Layer 2 / Layer 4 metadata layer, with the underlying image file retained on Layer 3 storage until explicit eviction (matching the spec 018 hybrid persistence pattern).
- **FR-006**: For any saved color, the L1 page MUST display the swatch and the label. Delete is hard at the metadata layer (no soft-delete needed — colors are tiny and re-creatable).
- **FR-007**: For the saved brand voice, the L1 page MUST display the text in an editable textarea. Edit replaces the value; clearing the textarea plus save deletes the brand voice.
- **FR-008**: Every wizard surface across all 5 Modes that already has an overlay-logo step (currently spec 009 covers this for Mode 2) MUST include a "saved logos" picker as a one-click selector option, alongside the existing per-render upload control. Picking a saved logo MUST result in the render referencing the saved asset by identifier — no new copy of the file.
- **FR-009**: When the wizard dispatches a render with a saved logo selected, the request body to Layer 2 MUST carry the saved-logo identifier. Layer 2 MUST resolve it to the actual asset path before forwarding to Layer 3, so Layer 3 sees a path it can fetch (matching today per-render upload flow).
- **FR-010**: The brand voice tagline MUST be included as system-prompt context in every Auto-mode or Polish-mode script generation in any Mode. When no brand voice is saved, dispatch behavior MUST be byte-identical to today behavior.
- **FR-011**: The Brand Library page MUST visually match the look-and-feel of `analytics.nexcognit.com` — dark theme, card-based layout, NexCognit accent token treatment. The exact token palette comes from spec 001 (UI Style); v1 adopts the tokens spec 001 already documents and does not introduce new ones. **As-built tokens** (extracted from the reference site because spec 001 is still Draft) are documented in `research.md` §"Decision 7" — a future spec 001 release reconciles by mapping these to formal token names.

### Key Entities

- **Brand Logo**: a tenant-scoped saved logo. Carries: tenant_id, creator user_id, label, image asset path (under L3 uploads), upload timestamp, soft-delete flag. Multiple logos per tenant allowed at v1; future spec may cap or rank.
- **Brand Color**: a tenant-scoped saved color. Carries: tenant_id, creator user_id, label, 6-character hex value (uppercase, no leading `#` in storage). Multiple colors per tenant allowed.
- **Brand Voice**: tenant-scoped tagline / mission statement. Singleton per tenant at v1. Carries: tenant_id, last-edited user_id, text (≤ 280 chars), updated timestamp.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After a creator saves at least one logo, every subsequent wizard open in any Mode that supports overlays surfaces the saved logo as a one-click pick — measured by walking each Mode wizard once after a single logo save and confirming the picker appears in 100% of overlay-supporting Modes.
- **SC-002**: A render dispatched with a saved logo MUST land the logo on-screen identically to a render dispatched with a fresh per-render upload of the same file — verified by frame-diff on a stable test fixture.
- **SC-003**: The Brand Library page renders in under 1 second on a typical local dev stack with 0–10 saved logos, 0–10 saved colors, and a saved brand voice — measured at the wizard `Time to interactive` metric.
- **SC-004**: A creator with no saved assets opens the Brand Library page and reaches a "save your first logo" state within 30 seconds of first navigation — measured by usability test.
- **SC-005**: Tenant isolation is enforced at every L2 endpoint — verified by sending requests for tenant A assets with tenant B JWT and asserting 403 / 404 (whichever the existing JWT middleware returns) for 100% of test cases.
- **SC-006**: When a saved brand voice is present, the script-generation LLM dispatch payload visibly contains the voice text — verified by logging the system-prompt block in dev mode and confirming the tagline string appears for every Auto-mode or Polish-mode call **in every Mode that generates scripts via the L3 LLM path** (Modes 2, 3, 4, 5 at v1; Mode 1's product-shoot pipeline lives entirely in L2 per Constitution §I and is out of scope for this SC).

## Assumptions

- **Tenant model unchanged** — v1 reuses the existing tenant-id-from-JWT pattern (constitution §III). Brand assets are tenant-scoped; no team-sharing, no cross-tenant linking. Multi-creator-per-tenant access is implicit ("everyone in tenant A sees tenant A library") and not explicitly tested at v1.
- **Storage backend reuses the existing L3 image-upload path** — `app/controllers/v1/uploads.py` already accepts and tenant-scopes images. Brand logos are persisted there with no new storage surface. The mapping table that ties saved-logo IDs to file paths lives in L2 (or L4 once that lands).
- **Spec 009 (per-render overlays) lands first** OR ships in parallel — the wizard logo selector is the primary integration point for saved logos, and that selector is owned by spec 009. If spec 009 is not yet shipped when this spec implements, the saved-logo picker still renders on the Brand Library page and is exercised end-to-end via Mode 2 once spec 009 catches up.
- **Brand voice is system-prompt context, not a hard constraint** — when saved, the LLM is told about the tagline but is not forced to include it verbatim. v1 does not enforce that the tagline appears in the output; that is a future ML-eval concern.
- **Visual design tokens come from spec 001** — this spec does not define new tokens, fonts, or component shapes. It consumes whatever spec 001 already documents. If spec 001 is itself in Draft, the implementation extracts the as-built tokens from `analytics.nexcognit.com` (the documented reference site) and notes the divergence in plan.md so future spec 001 changes can reconcile.
- **Existing L1/L2 auth model holds** — there is no new authentication step for the Brand Library; access is gated by the same demo-bearer / JWT pattern that gates the rest of the L1 API routes.
- **No backwards compatibility burden** — the Brand Library is a net-new page; nothing today depends on its absence. No feature flag is required for the page itself, only for the wizard-side logo picker (so wizards without saved logos continue to render the existing per-render upload path unchanged).
- **No billing dimension at v1** — saving brand assets is free; there is no per-asset cost, no quota, no usage-based pricing. Storage cost is absorbed under existing L3 disk budgets.
