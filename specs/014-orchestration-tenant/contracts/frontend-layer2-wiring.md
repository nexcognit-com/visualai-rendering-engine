# Contract: Frontend ↔ Layer 2 Wiring

**Feature**: 014-orchestration-tenant
**Layer**: Layer 1 (`visualai-frontend/`)

The wizard's existing `/api/*` proxy routes get retargeted from Layer 3 (`localhost:8090`) to Layer 2 (`localhost:8080`), and gain an `Authorization: Bearer ...` header on every upstream call.

---

## Env var changes

```diff
# visualai-frontend/.env.local (and .env.example)

- NEXT_PUBLIC_LAYER3_URL=http://localhost:8090
+ NEXT_PUBLIC_LAYER2_URL=http://localhost:8080
+ NEXT_PUBLIC_LAYER2_DEMO_BEARER=demo-bearer-replace-in-production
```

The old `NEXT_PUBLIC_LAYER3_URL` is removed. Wizard code that reads it is updated to read `NEXT_PUBLIC_LAYER2_URL`.

In Step 4 (NextAuth), `NEXT_PUBLIC_LAYER2_DEMO_BEARER` becomes obsolete — replaced by a server-side `getServerSession()` lookup that returns a Layer 2-issued JWT.

---

## Proxy route updates

Each `src/app/api/*/route.ts` proxy needs two changes:

### 1. URL base swap

```diff
- const MPT_BASE = process.env.NEXT_PUBLIC_LAYER3_URL ?? "http://localhost:8080";
+ const LAYER2_BASE = process.env.NEXT_PUBLIC_LAYER2_URL ?? "http://localhost:8080";
```

(Note: the default port becomes 8080 for Layer 2, while Layer 3 moves to 8090. This already matches the running setup we've been using.)

### 2. Authorization header

Every outgoing `fetch` call adds the bearer:

```diff
  const res = await fetch(`${LAYER2_BASE}/api/v1/videos`, {
    method: "POST",
-   headers: { "Content-Type": "application/json" },
+   headers: {
+     "Content-Type": "application/json",
+     "Authorization": `Bearer ${process.env.NEXT_PUBLIC_LAYER2_DEMO_BEARER ?? ""}`,
+   },
    body: JSON.stringify(mptBody),
  });
```

For multipart endpoints (upload-image, upload-audio): same pattern, but only the `Authorization` header is added explicitly — the multipart Content-Type comes from FormData.

---

## Files affected

| Proxy route | Backend endpoint | Change |
|---|---|---|
| [src/app/api/generate/route.ts](../../../visualai-frontend/src/app/api/generate/route.ts) | POST /api/v1/videos | URL base + bearer header |
| [src/app/api/status/[taskId]/route.ts](../../../visualai-frontend/src/app/api/status/[taskId]/route.ts) | GET /api/v1/tasks/{id} | URL base + bearer header |
| [src/app/api/upload-image/route.ts](../../../visualai-frontend/src/app/api/upload-image/route.ts) | POST /api/v1/uploads/image | URL base + bearer header (multipart) |
| [src/app/api/upload-audio/route.ts](../../../visualai-frontend/src/app/api/upload-audio/route.ts) | POST /api/v1/uploads/audio | URL base + bearer header (multipart) |
| [src/app/api/polish-preview/route.ts](../../../visualai-frontend/src/app/api/polish-preview/route.ts) | POST /api/v1/scripts/polish-preview | URL base + bearer header |
| [src/app/api/scrape-url/route.ts](../../../visualai-frontend/src/app/api/scrape-url/route.ts) | (Layer 1-only — Spec 012) | **No change** — never touched Layer 3 |
| [src/app/api/bgm-tracks/route.ts](../../../visualai-frontend/src/app/api/bgm-tracks/route.ts) | GET /api/v1/musics (legacy) | URL base + bearer header — gets routed through Layer 2 too |

The 5 proxies that hit MPT all need the same edit. ~10 lines total per file.

---

## Helper extraction (recommended)

To avoid 5x duplicated bearer-header code, introduce a single helper:

```typescript
// visualai-frontend/src/lib/layer2-client.ts
const LAYER2_BASE = process.env.NEXT_PUBLIC_LAYER2_URL ?? "http://localhost:8080";
const DEMO_BEARER = process.env.NEXT_PUBLIC_LAYER2_DEMO_BEARER ?? "";

export function layer2Url(path: string): string {
  return `${LAYER2_BASE}${path}`;
}

export function authHeaders(): Record<string, string> {
  return DEMO_BEARER ? { Authorization: `Bearer ${DEMO_BEARER}` } : {};
}

export async function layer2Fetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(layer2Url(path), {
    ...init,
    headers: {
      ...(init?.headers ?? {}),
      ...authHeaders(),
    },
  });
}
```

Each proxy then becomes:

```typescript
import { layer2Fetch } from "@/lib/layer2-client";

// POST /api/generate handler:
const res = await layer2Fetch("/api/v1/videos", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(mptBody),
});
```

---

## Error handling — Layer 2 unreachable (FR-016)

If `layer2Fetch` throws (network failure, DNS fail, refused), the proxy returns:

```typescript
return NextResponse.json(
  {
    error: "Orchestration service unavailable",
    error_code: "layer2_unavailable",
    detail: String(err),
  },
  { status: 503 },
);
```

The wizard's submit handler reads this and surfaces a clear "orchestration unavailable, please retry" toast. **Does NOT silently fall back to direct Layer 3 calls** (FR-016).

---

## Test coverage (planned)

| Test | Description |
|---|---|
| FE-1 | layer2Fetch attaches Authorization: Bearer header from env var. |
| FE-2 | layer2Fetch hits NEXT_PUBLIC_LAYER2_URL not LAYER3_URL. |
| FE-3 | When env var is empty, no Authorization header is sent (lets Layer 2 reject with missing_bearer). |
| FE-4 | /api/generate proxy passes bearer through; existing visuals_mode + script_mode pass-through unchanged. |
| FE-5 | /api/upload-image multipart proxy: bearer header set, FormData passes through, Content-Type managed by browser. |
| FE-6 | When Layer 2 unreachable, /api/generate returns 503 layer2_unavailable; the wizard's submit handler shows the orchestration-unavailable error. |
| FE-7 | Existing 81 frontend tests still pass after the URL base swap (mocks updated to point at Layer 2). |
