# Contract: Layer 2 Public API (frontend ↔ Layer 2)

**Feature**: 014-orchestration-tenant
**Layer**: Frontend (Layer 1) ↔ Orchestration (Layer 2)
**Repo**: new sibling `../visualai-orchestration/`

Layer 2 exposes the same wire shape that Layer 3 currently exposes — the wizard's existing proxy routes are largely unchanged. The differences are: (a) the URL points at Layer 2 instead of Layer 3, (b) every request includes an `Authorization: Bearer <demo>` header, (c) the demo tenant context is added by Layer 2, not the wizard.

---

## Authentication

Every Layer 2 endpoint requires:

```http
Authorization: Bearer <LAYER2_DEMO_BEARER>
```

The demo bearer is configured in Layer 1's `.env`:
```
NEXT_PUBLIC_LAYER2_DEMO_BEARER=demo-bearer-replace-in-production
```

Layer 2 validates the bearer string-equals-comparison (constant-time) against its `LAYER2_DEMO_BEARER` env var. Mismatch → HTTP 401:

```json
{ "error_code": "invalid_bearer", "detail": "Bearer token rejected." }
```

Missing header → HTTP 401:

```json
{ "error_code": "missing_bearer", "detail": "Authorization: Bearer header required." }
```

---

## Endpoints

### `POST /api/v1/videos`

Forwards to Layer 3's `POST /api/v1/videos` after JWT minting.

**Request body**: identical to Layer 3's existing contract (any `VideoParams` shape — `visuals_mode`, `script_mode`, etc.). Layer 2 does NOT validate the body shape; that's Layer 3's job.

**Response**: verbatim from Layer 3.

**Layer 2 errors** (before forwarding):
- 401 `missing_bearer` / `invalid_bearer` — auth.
- 503 `render_engine_unavailable` — `LAYER3_BASE_URL` unreachable.

---

### `GET /api/v1/tasks/{task_id}`

Forwards to Layer 3's `GET /api/v1/tasks/{task_id}`.

Same auth header required. Layer 2 forwards the path param verbatim.

---

### `POST /api/v1/uploads/image`

Multipart proxy to Layer 3's `POST /api/v1/uploads/image`.

**Request**: multipart with fields `file` (binary) + `role` (`"model"` or `"product"`) — same as Layer 3.

Layer 2 forwards via `httpx.AsyncClient(...).post(url, files=..., data=..., headers=...)`. The body is streamed through, not buffered (matters for the 10 MB upload limit).

**Response**: verbatim from Layer 3.

---

### `POST /api/v1/uploads/audio`

Multipart proxy to Layer 3's `POST /api/v1/uploads/audio`.

Same shape as the image variant.

---

### `POST /api/v1/scripts/polish-preview`

JSON proxy to Layer 3's `POST /api/v1/scripts/polish-preview`.

**Request body**: same as Layer 3 (`{ brief, video_subject?, duration_seconds?, language? }`).

**Response**: verbatim from Layer 3.

---

## Health endpoints

```http
GET /healthz
GET /readyz
```

`/healthz` returns `200 {"status": "ok"}` if Layer 2 is up.

`/readyz` checks Layer 3 reachability via `GET {LAYER3_BASE_URL}/api/v1/tasks/healthz` (or whatever Layer 3 health endpoint we wire up); returns `200 {"layer3": "ok"}` if healthy, `503` otherwise. No auth required for either health endpoint.

---

## CORS policy

Layer 2 MUST send permissive CORS in dev (`Access-Control-Allow-Origin: http://localhost:3001`, allow methods + headers including `Authorization`). Production CORS is locked to the configured `LAYER1_BASE_URL` env var.

---

## Test coverage (planned)

| Test | Description |
|---|---|
| LA-1 | Missing Authorization header → 401 missing_bearer. |
| LA-2 | Wrong bearer value → 401 invalid_bearer. |
| LA-3 | Valid bearer + valid POST /videos body → forwards to Layer 3 mock; returns 200 + same body. |
| LA-4 | Valid bearer + GET /tasks/{id} → forwards path param + query string. |
| LA-5 | Multipart upload-image: bytes pass through unchanged; `role` field forwarded. |
| LA-6 | polish-preview JSON forwarded; 400 errors from Layer 3 propagate. |
| LA-7 | Layer 3 unreachable → 503 render_engine_unavailable. |
| LA-8 | /healthz and /readyz return without auth. |
| LA-9 | CORS preflight OPTIONS includes Authorization in Access-Control-Allow-Headers. |
| LA-10 | Production-guard: setting `LAYER2_ENV=production` with default bearer fails startup. |
