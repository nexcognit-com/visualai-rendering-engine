# Contract: Frontend Components

**Feature**: 002-video-duration-variations
**Layer**: 1 — VisualAI Frontend (sibling repository at `../visualai-frontend/`)
**Design source**: [specs/001-nexcognit-ui-style/spec.md](../../001-nexcognit-ui-style/spec.md) provides the token and component foundation this feature composes against.

This file defines TypeScript prop shapes for the four components this feature introduces or extends. Implementation lives in the sibling frontend repo.

---

## Component: `DurationSlider`

**Purpose**: lets the user pick a video duration between 5 and 90 seconds.
**Implements**: FR-001, FR-002, FR-003; acceptance scenario US1.1 / US1.2 / US1.3.

```ts
export interface DurationSliderProps {
  /** Current duration in seconds. */
  value: number;
  /** Called when the user changes the value (slider drag or numeric input). */
  onChange: (seconds: number) => void;
  /** Minimum. Defaults to 5; override only for specialized modes. */
  min?: number;
  /** Maximum. Defaults to 90. */
  max?: number;
  /** Disabled while a generation is in flight. */
  disabled?: boolean;
  /** Visible label above the slider. */
  label?: string;   // default: "Duration"
  /** Optional helper text under the numeric input. */
  helperText?: string;
}
```

Behavior:
- Slider and numeric input are bound to the same `value`; editing one updates the other.
- Values outside `[min, max]` are clamped on blur; a toast fires with the clamped boundary explanation.
- Debounce `onChange` at 100 ms when dragging the slider.

---

## Component: `VariationStepper`

**Purpose**: lets the user pick how many variations to generate (1, 2, or 3).
**Implements**: FR-006.

```ts
export interface VariationStepperProps {
  /** Current count. */
  value: 1 | 2 | 3;
  /** Called when the user changes the count. */
  onChange: (count: 1 | 2 | 3) => void;
  /** Disabled while a generation is in flight. */
  disabled?: boolean;
  /** Optional label. */
  label?: string;   // default: "Variations"
}
```

Behavior:
- Rendered as a segmented 3-button group with the selected button in the active Dodger Blue state (per spec 001).
- Enter/Space and arrow keys move the selection for keyboard users (FR-014).

---

## Component: `PreviewApprovalGrid`

**Purpose**: shows the N previews for a preview-gated job with per-variation Approve / Reject actions.
**Implements**: US3 acceptance scenarios; FR-014, FR-015.

```ts
export interface PreviewApprovalGridProps {
  /** The previews to display, one per variation. */
  previews: PreviewEntry[];
  /** Cost the user sees per variation if they approve (credit count). */
  fullCostPerVariationCredits: number;
  /** Current credit balance; used to warn on insufficient credits. */
  currentCreditBalance: number;
  /** Called when user approves a variation. */
  onApprove: (variationIndex: number) => void;
  /** Called when user rejects a variation. */
  onReject: (variationIndex: number) => void;
  /** Called when the user clicks "Regenerate with stronger diversity." */
  onRegenerate: () => void;
}

export interface PreviewEntry {
  variationIndex: number;       // 0..N-1
  previewUrl: string;           // MP4 URL to render in an inline <video>
  durationSeconds: 5;           // always 5 for this feature
  state: "awaiting" | "approving" | "approved" | "rejecting" | "rejected";
  /** If all previews look identical, frontend sets this flag on all entries. */
  collapseDetected?: boolean;
}
```

Behavior:
- Each entry renders a large inline video player (auto-play muted on hover, with click-to-play controls).
- A banner above the grid reads: `Approving will commit the full <duration>s render and <fullCostPerVariationCredits> credits.`
- If `currentCreditBalance < fullCostPerVariationCredits × count(state === "awaiting")`, a warning banner invites top-up (FR-020 edge-case).
- If any `collapseDetected`, a secondary CTA appears: `Regenerate with stronger diversity` (no cost).
- Accessibility: every action button MUST have an `aria-label` including the variation index (e.g., `"Approve variation 2"`).

---

## Component: `GenerationProgress` (extended)

**Purpose**: existing component from spec 001's Step 1 build, extended to render per-variation tracks.

```ts
export interface GenerationProgressProps {
  /** One track per in-flight variation. */
  tracks: GenerationTrack[];
  /** Whether the overall job is in preview-gate awaiting_approval state. */
  awaitingApproval: boolean;
}

export interface GenerationTrack {
  variationIndex: number;
  label: string;              // e.g., "Variation 1"
  stage: "queued" | "script" | "voice" | "material" | "assembly" | "complete" | "failed";
  progress: number;           // 0..1
  renderMode: "preview" | "full";
  errorMessage?: string;
}
```

Behavior:
- Up to 3 tracks render in parallel as stacked horizontal progress bars.
- Each track shows its stage label next to the bar; completed tracks collapse to a single "Complete" pill.

---

## Hook: `useGenerationJob`

**Purpose**: Encapsulates the full lifecycle of a generation from submit through result retrieval, including polling, preview approval, and retry.

```ts
export interface UseGenerationJobOptions {
  mode: "product_shoot" | "short_marketing" | "ugc_avatar" | "faceless";
  inputs: GenerationInputs;       // shape defined by the wizard per mode
  totalDurationSeconds: number;
  variationCount: 1 | 2 | 3;
}

export interface UseGenerationJobResult {
  submit: () => Promise<void>;
  approve: (variationIndex: number) => Promise<void>;
  reject: (variationIndex: number) => Promise<void>;
  regenerate: () => Promise<void>;
  state: "idle" | "submitting" | "preview_rendering" | "awaiting_approval" | "full_rendering" | "complete" | "expired" | "failed";
  tracks: GenerationTrack[];
  previews: PreviewEntry[];
  finalAssets: FinalAssetEntry[];
  error?: string;
}

export interface FinalAssetEntry {
  variationIndex: number;
  assetUrl: string;
  durationSeconds: number;
  state: "kept" | "discarded";
}
```

Behavior:
- In Step 1 single-tenant mode, `submit()` posts directly to Layer 3 once per variation (`N` parallel calls). In Step 2+, `submit()` posts once to Layer 2 and Layer 2 handles fan-out.
- Polling: 1-second interval against `GET /api/v1/videos/{task_id}` in Step 1; replaced by SSE from Layer 2 in Step 2+.
- State transitions mirror the `VideoJob` state machine in [data-model.md](../data-model.md).

---

## Wizard integration

The Mode 2 Creation Wizard (per spec 001 UI patterns) gets two new steps wired to the above components:

1. **Step 3 — Inputs**: add `DurationSlider` and `VariationStepper` next to the existing script editor / voice selector / music selector.
2. **Step 4 — Generation**: if `totalDurationSeconds > 30`, show `PreviewApprovalGrid` after previews arrive; then show `GenerationProgress` for the full renders. Otherwise go straight to `GenerationProgress`.

The wizard's Generate CTA (Primary Button per spec 001) reads: `Create {variationCount} variation{s}` with dynamic pluralization.
