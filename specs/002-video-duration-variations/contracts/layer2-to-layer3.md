# Contract: Layer 2 Orchestration → Layer 3 Rendering Engine

**Feature**: 002-video-duration-variations
**Producer**: Layer 2 Orchestration API (future repo, Step 2 prerequisite)
**Consumer**: Layer 3 Rendering Engine (this repository)

This contract describes how Layer 2 issues rendering work to Layer 3 for a single `VideoJob` with `variation_count = N` and `total_duration_seconds > 30` (the full preview-gate path). Short-path variants (no gate) use the same shape with `render_mode=full` only.

---

## Step-by-step flow

### 1. Job submission

Layer 1 (frontend) → Layer 2: `POST /api/v2/jobs` with user inputs (not specified here; owned by a separate Layer 2 spec).

Layer 2 validates credit balance, places a hold of `N × full_cost`, generates `seed_base`, and returns a job ID to the frontend.

### 2. Preview dispatch (preview-gate path)

Layer 2 issues N parallel calls to Layer 3:

```http
POST http://layer3:8080/api/v1/videos
Content-Type: application/json

{
  "video_subject": "...",
  "video_script": "...",
  "voice_name": "...",
  "total_duration_seconds": 60,
  "variation_count": 1,
  "render_mode": "preview",
  "seed": 4217,
  "tenant_id": "t_...",          // Step 2 onward (Principle III compliance)
  "user_id": "u_...",            // Step 2 onward
  "generation_id": "g_..."       // Step 2 onward
}
```

Each call carries:
- `variation_count = 1` (Layer 3 produces one asset per call; variation orchestration is Layer 2's job).
- `seed = seed_base + variation_index` for variation `i`.
- `render_mode = "preview"`.

Layer 3 returns `202 Accepted` with a `task_id` per call.

### 3. Preview completion

Layer 3 publishes `mpt:task:{task_id}:preview_ready` on Redis with `{asset_url}`.

Layer 2 subscriber:
1. Records the preview asset in `preview_assets` table.
2. Debits `preview_cost` from the hold (ledger `debit` transaction).
3. Updates `Variation.state = preview_ready`.

When all N previews are in `preview_ready`, Layer 2 marks `VideoJob.state = awaiting_approval` and notifies the frontend via SSE/WebSocket.

### 4. User approval

Frontend → Layer 2: `POST /api/v2/jobs/{job_id}/variations/{index}/approve` or `/reject`.

Layer 2 on approve:
1. Transitions `Variation.state` to `approved`.
2. Issues full-render call to Layer 3:

```http
POST http://layer3:8080/api/v1/videos
Content-Type: application/json

{
  "video_subject": "...",        // Same inputs as the preview call
  "video_script": "...",
  "voice_name": "...",
  "total_duration_seconds": 60,
  "variation_count": 1,
  "render_mode": "full",
  "seed": 4217,                  // Same seed as the approved preview
  "tenant_id": "t_...",
  "user_id": "u_...",
  "generation_id": "g_..."
}
```

Layer 2 on reject:
1. Transitions `Variation.state` to `rejected`.
2. Issues a `release` transaction for `(full_cost - preview_cost)` credits.
3. Does NOT call Layer 3.

### 5. Full render completion

Layer 3 publishes `mpt:task:{task_id}:full_ready`.

Layer 2:
1. Records the full asset in `assets`.
2. Debits `(full_cost - preview_cost)` from the hold.
3. Transitions `Variation.state = full_ready`.
4. Notifies the frontend.

When all approved variations reach `full_ready` and no remaining variations are `preview_ready`, the job transitions to `complete`.

### 6. Timeout path

If `awaiting_approval` persists for 24 h, a Layer 2 background worker:
1. Transitions the job to `expired`.
2. Releases all remaining held credits.
3. Does NOT delete preview assets (user can still view them).
4. Never calls Layer 3.

---

## Error semantics

| Condition | Layer 2 action | Layer 3 action |
|---|---|---|
| Preview render fails | Retry up to 2× free; 3rd+ attempt consumes credits. Mark variation `failed` on give-up. | Emit `failed` event, cleanup task dir. |
| Full render fails after preview approved | Retry up to 2× free. Fixed credits already debited (preview cost). On give-up, refund `(full_cost - preview_cost)` as a `release`. | Same. |
| Layer 3 unreachable | Layer 2 queues the request, retries with exponential backoff up to 5 min. User sees "Renderer queue is busy" status. | N/A (service down). |
| Layer 3 returns 422 validation error | Layer 2 translates to user-facing error, refunds full hold. Indicates a Layer 2 bug (shouldn't happen in steady state). | N/A. |

---

## Cross-layer invariants enforced by Layer 2 only

- **Credit invariant** (SC-007): Layer 2 is the sole writer of `credit_transactions` rows. Layer 3 never writes to it.
- **Tenant isolation** (Principle III): Layer 2 MUST include `tenant_id` / `user_id` on every Layer 3 request after Step 2. Layer 3 rejects requests missing these fields once the feature flag `REQUIRE_TENANT_CONTEXT` is flipped on.
- **Approval gate**: Layer 2 MUST NOT issue `render_mode=full` until the corresponding variation has been user-approved. Layer 3 does not enforce this.

---

## Step-1 simplification

During Step 1 (tonight's MVP), no Layer 2 exists. The Next.js frontend calls Layer 3 directly at `http://localhost:8080/api/v1/videos`. Consequences:
- No preview gate in Step 1 for Mode 2 (preview gate first becomes usable in Step 2).
- No tenant context — `tenant_id` / `user_id` omitted; `REQUIRE_TENANT_CONTEXT=false`.
- No credit ledger — the "Credits: 1,250" counter in the sidebar is a mock.
- Variations in Step 1: for `duration ≤ 30`, the frontend issues N parallel `render_mode=full` calls with distinct seeds. For `duration > 30`, the frontend still shows the "Preview" approval UI but simulates it with a client-side 5-s truncation of a single full render (a Step-1-only workaround documented in `STEP1_DEBT.md`).

This simplification keeps tonight's MVP shippable while preserving the full contract for Step 2+ implementation.
