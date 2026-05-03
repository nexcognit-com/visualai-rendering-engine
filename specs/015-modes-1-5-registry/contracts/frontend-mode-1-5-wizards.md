# Contract: Frontend Mode 1 + Mode 5 Wizards (Layer 1)

**Date**: 2026-05-03
**Owner**: Layer 1 (`../visualai-frontend/`)
**Touches**: `src/app/page.tsx`, `src/app/modes/faceless-channel/page.tsx` (NEW), `src/app/modes/product-shoot/page.tsx` (NEW), `src/app/api/product-shoot/route.ts` (NEW), `src/app/api/generate/route.ts` (extended), `src/lib/product-shoot.ts` (NEW)

This contract defines the user-facing surface for Modes 1 + 5: dashboard activation, two new wizard routes, and the proxy route shape Layer 1 uses to talk to Layer 2.

---

## 1. Dashboard activation (`src/app/page.tsx`)

**Pre-Step-3 state**: 5 mode cards. Mode 2 is clickable. Modes 1, 3, 4, 5 show a "Coming in Step N" badge and are non-clickable.

**Post-Step-3 state**:
- Mode 1 (Product Shoot) — clickable, navigates to `/modes/product-shoot`
- Mode 2 (Short Marketing Video) — unchanged, navigates to `/modes/short-video`
- Mode 3 (Long-Form 16:9) — non-clickable, badge: "Coming in Step 4"
- Mode 4 (UGC Avatar) — non-clickable, badge: "Coming in Step 4"
- Mode 5 (Faceless Channel) — clickable, navigates to `/modes/faceless-channel`

**Mode card metadata structure** (component: `ModeCard.tsx`):

```ts
type ModeCardConfig = {
  id: 'product-shoot' | 'short-video' | 'long-form' | 'avatar' | 'faceless-channel';
  title: string;             // "Product Shoot Generator"
  subtitle: string;          // "Studio-quality product photography from a single source"
  icon: LucideIcon;
  href: string | null;       // null when locked
  lockedBadge?: string;      // "Coming in Step 4" (omit when href present)
};
```

---

## 2. Mode 5 wizard (`src/app/modes/faceless-channel/page.tsx`)

**Wizard steps** (3 total, simpler than Mode 2's 4-step flow because there's no Visuals or Script editor):

| Step | UI | Output |
|---|---|---|
| 1 | Topic input (textarea, required, max 200 chars) + 6 preset chips: "Mediterranean diet", "Productivity tips", "Space facts", "Personal finance", "History oddities", "Tech minute" | `topic: string` |
| 2 | Voice selector (existing component — same as Mode 2, defaults to first English neural voice) + Music selector | `voice_name: string`, `bgm_path: string | null` |
| 3 | Generation progress — same component as Mode 2, polls `/api/status/[taskId]` | task status updates |

**Submit handler** (Step 3 → Generate):

```ts
async function handleGenerate(formState: FacelessFormState) {
  const res = await fetch('/api/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      mode: 'faceless',                        // signals Mode 5 to Layer 2 → Layer 3
      video_subject: formState.topic,          // existing field, repurposed
      voice_name: formState.voice_name,
      bgm_path: formState.bgm_path,
      // intentionally NOT setting visuals_mode — Mode 5 forces 'auto'
      script_mode: 'auto',                     // Mode 5 always auto-generates
    }),
  });
  if (!res.ok) throw new Error(await res.text());
  const { task_id } = await res.json();
  router.push(`/modes/faceless-channel/result?task_id=${task_id}`);
}
```

**Notes**:
- `/api/generate` is the existing proxy from Step 1; small extension: forward `mode` field if present (already does in Step 2)
- The result page is shared with Mode 2's progress/result UI — no new component needed
- No Visuals selector. Mode 5 forces auto-stock-footage; the user has no choice

---

## 3. Mode 1 wizard (`src/app/modes/product-shoot/page.tsx`)

**Wizard steps** (2 total — Mode 1 is faster than Mode 2):

| Step | UI | Output |
|---|---|---|
| 1 | Single image upload (drag-and-drop OR click-to-upload, accept `image/jpeg,image/png,image/webp`, max 10 MB) + optional description textarea (max 500 chars) | `source_image_file: File`, `description: string` |
| 2 | Generation progress (single-state — runs once, ~30s) → results gallery with 6 image thumbnails + download-all button | 6 image URLs displayed |

**Submit handler** (Step 1 → Generate):

```ts
async function handleGenerate(formState: ProductShootFormState) {
  const formData = new FormData();
  formData.append('image', formState.source_image_file);
  formData.append('description', formState.description);

  const res = await fetch('/api/product-shoot', {
    method: 'POST',
    body: formData,  // multipart — Layer 1 uploads to Layer 2 in one shot
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail ?? 'Generation failed');
  }
  const result: ProductShootResult = await res.json();
  setResult(result);  // re-render in Step 2 of wizard
}
```

**Result display**:
- 2×3 or 3×2 thumbnail grid of the 6 output images
- Each thumbnail clickable to open lightbox preview
- "Download all (.zip)" button — fetches each URL and bundles client-side (or links direct, since URLs are pre-signed)
- "Generate again" button → returns to Step 1
- "Save to My Assets" — Step 4 will persist; Step 3 placeholder

---

## 4. Frontend proxy: `src/app/api/product-shoot/route.ts` (NEW)

```ts
// src/app/api/product-shoot/route.ts
import { NextRequest, NextResponse } from 'next/server';

const LAYER2_BASE = process.env.LAYER2_BASE_URL ?? 'http://localhost:8088';
const DEMO_BEARER = process.env.LAYER2_DEMO_BEARER_TOKEN ?? '';

export async function POST(req: NextRequest) {
  // Step 3 demo: receives multipart from browser, uploads source image to Layer 2,
  // gets pre-signed URL back, then POSTs the JSON product-shoot request.
  const form = await req.formData();
  const file = form.get('image') as File | null;
  const description = (form.get('description') as string) ?? '';

  if (!file) {
    return NextResponse.json({ error: 'image required' }, { status: 400 });
  }

  // Step 1: upload to Layer 2's existing /api/v1/uploads endpoint (Step 2 contract)
  const uploadForm = new FormData();
  uploadForm.append('file', file);
  uploadForm.append('purpose', 'product_shoot_source');
  const uploadRes = await fetch(`${LAYER2_BASE}/api/v1/uploads`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${DEMO_BEARER}` },
    body: uploadForm,
  });
  if (!uploadRes.ok) return NextResponse.json(await uploadRes.json(), { status: uploadRes.status });
  const { pre_signed_url } = await uploadRes.json();

  // Step 2: trigger Mode 1 generation
  const genRes = await fetch(`${LAYER2_BASE}/api/v1/product-shoots`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${DEMO_BEARER}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      source_image_url: pre_signed_url,
      description,
    }),
  });
  if (!genRes.ok) return NextResponse.json(await genRes.json(), { status: genRes.status });
  return NextResponse.json(await genRes.json());
}
```

**Timeout**: Next.js default is 60s for serverless route handlers; configure `export const maxDuration = 120;` to accommodate Layer 2's 90s synchronous wait.

---

## 5. Frontend type definitions (`src/lib/product-shoot.ts`)

```ts
// src/lib/product-shoot.ts
export type ProductShootStatus = 'pending' | 'running' | 'complete' | 'failed';

export type ProductShootResult = {
  id: string;
  tenant_id: string;
  user_id: string;
  status: ProductShootStatus;
  source_image_url: string;
  description: string;
  output_image_urls: string[];          // length == 6 when status === 'complete'
  model_name: string;
  latency_ms: number | null;
  cost_estimate_usd: number | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
};

export type ProductShootFormState = {
  source_image_file: File | null;
  description: string;
};

export const MAX_DESCRIPTION_LENGTH = 500;
export const MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024;  // 10 MB
export const ACCEPTED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp'] as const;

export function validateProductShootForm(state: ProductShootFormState): string | null {
  if (!state.source_image_file) return 'Please upload a product image';
  if (state.source_image_file.size > MAX_IMAGE_SIZE_BYTES) return 'Image must be under 10 MB';
  if (!ACCEPTED_IMAGE_TYPES.includes(state.source_image_file.type as any)) {
    return 'Image must be JPEG, PNG, or WebP';
  }
  if (state.description.length > MAX_DESCRIPTION_LENGTH) {
    return `Description must be ≤ ${MAX_DESCRIPTION_LENGTH} characters`;
  }
  return null;
}
```

---

## 6. Test contract

### 6.1 `tests/product-shoot.test.ts` (Vitest)

Required cases:

| Test ID | Scenario | Expected |
|---|---|---|
| FE-PS-T1 | `validateProductShootForm({ source_image_file: null, description: '' })` | `"Please upload a product image"` |
| FE-PS-T2 | `validateProductShootForm` with valid 5MB JPEG + empty description | `null` |
| FE-PS-T3 | `validateProductShootForm` with 11MB image | `"Image must be under 10 MB"` |
| FE-PS-T4 | `validateProductShootForm` with `image/gif` | `"Image must be JPEG, PNG, or WebP"` |
| FE-PS-T5 | `validateProductShootForm` with description=501 chars | `"Description must be ≤ 500 characters"` |

### 6.2 Component tests (Playwright/Vitest UI — optional in Step 3)

| Test ID | Scenario | Expected |
|---|---|---|
| FE-WIZ-1 | Dashboard renders 5 mode cards | 3 clickable (Mode 1, 2, 5), 2 locked (Mode 3, 4) |
| FE-WIZ-2 | Click Mode 5 card | Navigate to `/modes/faceless-channel` |
| FE-WIZ-3 | Click Mode 1 card | Navigate to `/modes/product-shoot` |
| FE-WIZ-4 | Mode 5 wizard: topic empty + click Generate | Validation error |
| FE-WIZ-5 | Mode 1 wizard: no image + click Generate | Validation error |
| FE-WIZ-6 | Mode 1 wizard: mock 200 response | 6 thumbnails render in result step |

---

## 7. Environment variables (Layer 1)

| Var | Default | Purpose |
|---|---|---|
| `LAYER2_BASE_URL` | `http://localhost:8088` | Layer 2 base URL for proxy routes |
| `LAYER2_DEMO_BEARER_TOKEN` | (required) | Demo JWT for Step 3 single-user mode |
| `NEXT_PUBLIC_DASHBOARD_MODES` | `1,2,5` | Comma-separated active mode ids; future flag-flip mechanism |

---

## 8. Accessibility + branding

- All new UI uses NexCognit brand tokens (`nex-navy`, `nex-neon`, etc. — defined in spec 001 / spec 007 brand skill)
- Form fields use the existing shadcn `Input`, `Textarea`, `Button` components
- Lucide icons only — no emojis
- All buttons have `aria-label` or visible text; image upload uses `<input type="file" aria-describedby="...">` for screen-reader hint
- Result gallery thumbnails have `alt="Studio shot N"` (1-indexed)

---

## 9. Out of scope for Step 3 frontend

- "Save to My Assets" persistence — Step 4 (Neon)
- Mode 1 result regeneration with prompt edit ("try a different angle") — Step 4
- Mode 5 result re-render with different voice — Step 4
- Mode 1 ZIP bundling client-side — Step 3 may use simple per-image download links; ZIP is Step 4
- Mode 1 batch generation (multiple source images at once) — Step 5+
