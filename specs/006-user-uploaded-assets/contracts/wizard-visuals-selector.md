# Contract: Wizard visuals selector (Layer 1)

**Feature**: 006-user-uploaded-assets
**Layer**: 1 (frontend, sibling repo `visualai-frontend/`)
**Files**:
- `src/lib/visuals-mode.ts` — type definitions + helper functions (NEW)
- `src/components/wizard/visuals-selector.tsx` — pill row + upload-slot grid (NEW)
- `src/app/modes/short-video/page.tsx` — wires the selector into the Script & Voice step (EXTEND)
- `src/app/api/upload-image/route.ts` — proxy to MPT `POST /api/v1/uploads/image` (NEW)
- `src/app/api/generate/route.ts` — pass through `visuals_mode` + `uploaded_*_paths` fields (EXTEND)

## Helper module: `src/lib/visuals-mode.ts`

```typescript
export type VisualsMode = "auto" | "user_uploaded";

export interface UploadedAsset {
  role: "model" | "product";
  filePath: string;          // server-returned cropped_path
  originalPath: string;      // server-returned original_path (for forward compat)
  filename: string;
  sizeBytes: number;
  contentHash: string;
  warning?: "low_resolution"; // surface from upload response
}

export interface WizardVisualsState {
  mode: VisualsMode;
  modelAsset: UploadedAsset | null;
  productAssets: UploadedAsset[];   // 0..3, ordered by user upload order
}

export type VisualsParams =
  | { visuals_mode: "auto" }
  | { visuals_mode: "user_uploaded";
      uploaded_model_path?: string;
      uploaded_product_paths: string[]; };  // 1..3

export const PRISTINE_VISUALS: WizardVisualsState = {
  mode: "auto",
  modelAsset: null,
  productAssets: []
};

export function isPristineVisuals(s: WizardVisualsState): boolean;
export function visualsStateToParams(s: WizardVisualsState): VisualsParams;
export function canSubmitVisuals(s: WizardVisualsState): boolean;
```

### Helper semantics

| Function | Input → Output | Behavior |
|---|---|---|
| `isPristineVisuals` | `WizardVisualsState` → `boolean` | `true` iff `mode === "auto" && modelAsset === null && productAssets.length === 0` |
| `visualsStateToParams` | `WizardVisualsState` → `VisualsParams` | When `mode === "auto"`: returns `{ visuals_mode: "auto" }` regardless of cached uploads (US3 acceptance: "switching from My assets to Auto, uploads retained in state but not used in render"). When `mode === "user_uploaded"`: emits `uploaded_model_path` only if `modelAsset !== null`; always emits `uploaded_product_paths` (which the caller validates is non-empty before submit). |
| `canSubmitVisuals` | `WizardVisualsState` → `boolean` | `true` for `mode === "auto"`. For `mode === "user_uploaded"`: `productAssets.length >= 1 && productAssets.length <= 3`. |

## UI component: `<VisualsSelector>`

Renders inside the Script & Voice wizard step, between the script-mode pills (spec 013) and the music selector (spec 010).

```tsx
<section className="visuals-selector">
  <h3>Visuals</h3>
  <PillRow
    options={[
      { value: "auto", label: "Auto (stock)", helper: "Pexels stock footage" },
      { value: "user_uploaded", label: "Use my own assets",
        helper: "Upload product photos" },
    ]}
    value={state.mode}
    onChange={(mode) => onChange({ ...state, mode })}
  />
  {state.mode === "user_uploaded" && (
    <UploadSlotGrid
      modelAsset={state.modelAsset}
      productAssets={state.productAssets}
      onChange={(modelAsset, productAssets) =>
        onChange({ ...state, modelAsset, productAssets })}
    />
  )}
</section>
```

`<PillRow>` is the existing component used by spec 013's script-mode selector — reuse without modification.

`<UploadSlotGrid>` is new and composed of:
- One **Model image** slot (square, 9:16 ratio aware), labeled "Model image (optional)".
- Three **Product image** slots (numbered 1, 2, 3), labeled "Product images (1 required)".

Each slot supports:
- Drag-and-drop file dropzone (HTML5 native — no lib).
- Click-to-select via hidden `<input type="file" accept="image/jpeg,image/png,image/webp">`.
- Progress bar during upload (XHR with `progress` event).
- Thumbnail preview from server-returned `filePath` after upload.
- Remove (×) button.
- Retry button on upload failure.

## Upload flow (single slot)

```
User drops file
  → client checks size > 30 MB → reject before upload (FR Edge Cases)
  → client checks MIME extension prefix → soft-reject obvious mismatches
  → POST /api/upload-image (Next.js route)
       → proxies to MPT POST /api/v1/uploads/image
  → on 200: state slot becomes UploadedAsset
  → on 4xx/5xx: state slot shows error + retry; no asset path stored
  → on warning: low_resolution toast appears (non-blocking)
```

## Frontend route: `POST /api/upload-image`

Thin proxy. Mirrors the existing `/api/generate` proxy pattern. Mostly forwards multipart untouched.

```typescript
// src/app/api/upload-image/route.ts
import { NextRequest, NextResponse } from "next/server";
const MPT_BASE = process.env.NEXT_PUBLIC_LAYER3_URL ?? "http://localhost:8080";

export async function POST(req: NextRequest) {
  const form = await req.formData();
  // FormData is forwarded as-is; fetch handles multipart boundaries.
  const mptRes = await fetch(`${MPT_BASE}/api/v1/uploads/image`, {
    method: "POST",
    body: form,
  });
  const text = await mptRes.text();
  let parsed: unknown;
  try { parsed = JSON.parse(text); } catch { parsed = { raw: text }; }
  return NextResponse.json(parsed, { status: mptRes.status });
}
```

## Frontend route extension: `POST /api/generate`

Extends the existing handler (spec 013 already added `script_mode` + `script_brief` pass-through). Adds:

```typescript
// Inside POST /api/generate handler, after script_mode handling:
if (body.visuals_mode === "user_uploaded") {
  mptBody.visuals_mode = "user_uploaded";
  if (typeof body.uploaded_model_path === "string") {
    mptBody.uploaded_model_path = body.uploaded_model_path;
  }
  if (Array.isArray(body.uploaded_product_paths)) {
    mptBody.uploaded_product_paths = body.uploaded_product_paths.filter(
      (p): p is string => typeof p === "string"
    );
  }
} else if (body.visuals_mode === "auto") {
  mptBody.visuals_mode = "auto";
}
// Otherwise: omit entirely → MPT applies None default → legacy.
```

## State preservation across mode switches (US3)

| Action | Effect on `WizardVisualsState` |
|---|---|
| Toggle `auto` → `user_uploaded` | `mode` flips; `modelAsset` and `productAssets` retained from prior session (if any) |
| Toggle `user_uploaded` → `auto` | `mode` flips; uploaded assets retained but `visualsStateToParams` emits only `{ mode: "auto" }` |
| Remove a product asset | `productAssets` shrinks by one; if zero remain, `canSubmitVisuals` returns `false` |
| Click "Make another" after a render | `WizardVisualsState` is preserved across renders within the session (US3 AS-1) |
| Reload the page | Wizard state resets to `PRISTINE_VISUALS` (Step 1 has no persistent draft state) |

## Test coverage (planned, Vitest)

- WV-1: `PRISTINE_VISUALS.mode === "auto"`, `modelAsset === null`, `productAssets.length === 0`
- WV-2: `isPristineVisuals(PRISTINE_VISUALS)` → `true`
- WV-3: `isPristineVisuals({ mode: "user_uploaded", ...PRISTINE_VISUALS })` → `false`
- WV-4: `visualsStateToParams({ mode: "auto", modelAsset: <some asset>, productAssets: [<one>] })` → `{ visuals_mode: "auto" }` (assets dropped on auto submit)
- WV-5: `visualsStateToParams({ mode: "user_uploaded", modelAsset: null, productAssets: [{ filePath: "p1" }] })` → `{ visuals_mode: "user_uploaded", uploaded_product_paths: ["p1"] }` (no `uploaded_model_path` key)
- WV-6: `visualsStateToParams({ mode: "user_uploaded", modelAsset: { filePath: "m" }, productAssets: [{ filePath: "p1" }, { filePath: "p2" }] })` → includes both `uploaded_model_path: "m"` and `uploaded_product_paths: ["p1", "p2"]`
- WV-7: `canSubmitVisuals({ mode: "auto", ... })` → `true`
- WV-8: `canSubmitVisuals({ mode: "user_uploaded", productAssets: [] })` → `false`
- WV-9: `canSubmitVisuals({ mode: "user_uploaded", productAssets: 4-items })` → `false` (cap at 3)
- WV-10: round-trip — auto → user_uploaded → upload assets → auto → user_uploaded retains assets in state.
