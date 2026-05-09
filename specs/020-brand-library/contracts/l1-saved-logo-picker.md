# Contract: L1 Saved-Logo Picker (wizard integration)

**Owner**: Layer 1 (`visualai-frontend/src/components/brand-library/saved-logo-picker.tsx` — new) + the wizard surfaces in `src/app/modes/<mode>/...` that already include a per-render logo upload step.
**Caller**: every Mode wizard that has an overlay-logo step. Today only Mode 2 has this (per spec 009); Modes 1/3/4/5 add their own pickers as they get overlay support.
**Spec links**: spec.md FR-008, FR-009 · spec 009 (per-render overlays — the underlying surface this picker augments).

## Component shape

`<SavedLogoPicker>` is a React component that:

1. Fetches `GET /api/brand/logos` on mount (proxied to L2 by the new L1 route).
2. Renders the response as a row of clickable thumbnails with labels.
3. Emits `onPick(logoId, logoMeta)` when the creator clicks a saved logo.
4. Renders nothing (or a small "no saved logos yet — go to /brand" CTA) when the list is empty.
5. Renders a "this asset was deleted" warning if a previously-picked id is no longer in the response (handles in-progress wizards across delete actions).

```tsx
type SavedLogoMeta = {
  id: string;
  label: string;
  thumbnail_url: string;
  has_alpha: boolean;
  width_px: number;
  height_px: number;
};

type Props = {
  onPick: (logoId: string, meta: SavedLogoMeta) => void;
  selectedLogoId?: string | null;
};

export function SavedLogoPicker(props: Props): JSX.Element;
```

## Render dispatch contract

When the wizard dispatches the render (Mode 2's `/api/generate` route per spec 009), the body carries either:

- An inline upload (existing path): `{ overlay: { kind: "logo", upload_path: "..." } }`
- OR a saved-logo reference (new path): `{ overlay: { kind: "logo", saved_logo_id: "<uuid>" } }`

L1's `/api/generate` proxy detects which form was sent and forwards through to L2. L2 runs `resolve_saved_logo` (from `contracts/l2-brand-library-api.md`) to translate `saved_logo_id` into a concrete `upload_path` before forwarding to L3. Failure modes:

- `saved_logo_id` references a soft-deleted or cross-tenant id → L2 returns 400 `saved_logo_not_found`. L1 surfaces this to the wizard with a "your previously-saved logo was deleted; pick another" message.
- Both `upload_path` AND `saved_logo_id` present → L2 picks `saved_logo_id` (precedence rule documented; L1 SHOULD never send both, but the rule is explicit so the behavior is deterministic).

## Empty state (no saved logos)

When `GET /api/brand/logos` returns `{ logos: [] }`, the picker renders:

```
┌─────────────────────────────────────────────┐
│  No saved logos yet.                         │
│  [ Upload one for this render ]              │
│  Or go to your /brand library to save one    │
│  for reuse across all renders.               │
└─────────────────────────────────────────────┘
```

The "Upload one for this render" button falls back to the existing per-render upload UI (spec 009). The "/brand library" link opens a new tab so the wizard state is preserved.

## Deleted-mid-wizard state

If the wizard previously had `selectedLogoId = X` and a refetch reveals X is no longer in the live list:

1. The picker visually unselects.
2. A small banner appears above the picker: "Your previously-selected logo was deleted. Pick another or upload a new one."
3. The wizard's "next" / "submit" button is disabled until either a new logo is selected or the upload-new path is taken.

This matches FR-005 / Acceptance Scenario 4 in spec.md.

## Performance budget

- The `GET /api/brand/logos` fetch should complete in ≤ 200ms on a local stack with ≤ 10 saved logos. SC-003 derives from this.
- Thumbnail images use the L3 `thumbnail_url` directly (no L1 image proxy); browsers can cache them.

## Interaction with future Modes

Modes 1, 3, 4, and 5 do not have overlay-logo wizard steps yet (spec 009 is Mode 2 only at v1). When those modes add overlay support, they import this same picker component. No additional contract changes.

For Mode 4 (UGC Avatar) specifically: overlays are out of scope per spec 018 (the avatar IS the brand surface). This picker would only land in Mode 4 if a future spec adds a "brand chip in the corner" feature — not committed at v1.
