# Data Model: Video Duration Range, Variations, and Preview Gate

**Phase**: 1 — Design & Contracts
**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

This feature spans three layers. Persistent entities (`VideoJob`, `Variation`, `CreditHold`, `PreviewAsset`) live in Layer 4 (Neon PostgreSQL), managed by Layer 2. Layer 3 (this repo) operates on ephemeral copies of these records passed in with each API call and does not own any table.

---

## Entity: `VideoJob`

Owned by Layer 2. Persisted in Neon PostgreSQL `generations` table (per Master Spec §6), extended by this feature.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `user_id` | UUID | FK → `users.id`, NOT NULL | |
| `tenant_id` | UUID | FK → `tenants.id`, NOT NULL | |
| `mode` | enum | `product_shoot | short_marketing | long_form | ugc_avatar | faceless`, NOT NULL | `long_form` is out of scope for this feature but the enum value exists. |
| `product_id` | UUID | FK → `products.id`, NULLABLE | Null for Mode 5 (Faceless Channel). |
| `total_duration_seconds` | int | `BETWEEN 5 AND 90`, NOT NULL | Requested final length. |
| `variation_count` | int | `BETWEEN 1 AND 3`, NOT NULL, default 3 | |
| `preview_gate_required` | bool | NOT NULL, derived: `total_duration_seconds > 30` | Stored for audit simplicity. |
| `state` | enum | see state machine below, NOT NULL | |
| `seed_base` | int | NOT NULL | Root seed for variation derivation. |
| `created_at` | timestamptz | NOT NULL, default `NOW()` | |
| `updated_at` | timestamptz | NOT NULL | |
| `expires_at` | timestamptz | NULLABLE | Set to `created_at + 24h` when entering `awaiting_approval`. |

**State machine** (`VideoJob.state`):

```
draft
  │  submit
  ▼
submitted
  │  if preview_gate_required: dispatch N previews
  │  else: dispatch N full renders
  ▼
preview_rendering ──────────► full_rendering (if gate not required)
  │                                │
  │  all N previews complete       │  all N full renders complete
  ▼                                ▼
awaiting_approval                complete
  │  user decides per-variation
  │  (approvals → full_rendering per-variation;
  │   rejections → variation → rejected)
  │  any approved → full_rendering; all rejected → complete (all rejected)
  │  24h elapsed without decision → expired
  ▼
full_rendering ─────────────► complete / failed
```

Terminal states: `complete`, `expired`, `failed`.

---

## Entity: `Variation`

Owned by Layer 2. Persisted in Neon PostgreSQL `generations_variations` (new table added by the credit-ledger / orchestration spec, not this spec).

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `job_id` | UUID | FK → `VideoJob.id`, NOT NULL | |
| `variation_index` | int | `BETWEEN 0 AND variation_count - 1`, UNIQUE per job | |
| `seed` | int | NOT NULL | `= job.seed_base + variation_index` for first attempt; `+ 100 + i` after "regenerate with stronger diversity." |
| `state` | enum | see below, NOT NULL | |
| `preview_asset_id` | UUID | FK → `PreviewAsset.id`, NULLABLE | Null until preview renders. |
| `full_asset_id` | UUID | FK → `assets.id` (Layer 4), NULLABLE | Null until full render. |
| `preview_cost_credits` | int | NOT NULL when preview exists | Small fraction of full cost. |
| `full_cost_credits` | int | NOT NULL | |
| `rejected_reason` | text | NULLABLE | Optional user note on reject. |
| `created_at` | timestamptz | NOT NULL | |
| `updated_at` | timestamptz | NOT NULL | |

**State machine** (`Variation.state`):

```
pending
  │  preview render starts (if gate) OR full render starts (if no gate)
  ▼
preview_rendering ─────────► full_rendering (if no gate)
  │                              │
  │  preview done                │
  ▼                              ▼
preview_ready                 full_ready
  │  user acts                   │  user marks kept/discarded
  ▼                              ▼
approved / rejected / expired  kept / discarded
  │  if approved
  ▼
full_rendering ─────────────► full_ready → kept / discarded
```

Terminal states: `kept`, `discarded`, `rejected`, `expired`, `failed`.

---

## Entity: `CreditHold`

Owned by Layer 2. Persisted in Neon PostgreSQL `credit_transactions` table (Master Spec §6), with aggregation via a `credit_holds` table.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `job_id` | UUID | FK → `VideoJob.id`, NOT NULL | |
| `user_id` | UUID | FK → `users.id`, NOT NULL | |
| `amount_reserved` | int | NOT NULL | Total credits initially held. |
| `amount_debited` | int | NOT NULL, default 0 | Sum of all debits applied to this hold. |
| `amount_released` | int | NOT NULL, default 0 | Sum of all releases applied to this hold. |
| `state` | enum | `active | settled | expired`, NOT NULL | Settled when `amount_debited + amount_released == amount_reserved`. |
| `expires_at` | timestamptz | NOT NULL | |
| `created_at` | timestamptz | NOT NULL | |

**Invariant** (enforced by DB check constraint and asserted in SC-007):

```
amount_debited + amount_released <= amount_reserved
```

**Ledger events written to `credit_transactions`**:

- `hold`: amount = `N × full_cost_credits` (on job submit).
- `debit` (preview): amount = `preview_cost_credits`, one per variation, referenced by `variation_id`.
- `debit` (full): amount = `full_cost_credits - preview_cost_credits`, one per approved variation.
- `release`: amount = `full_cost_credits - preview_cost_credits` per rejected variation; remaining balance on job expire.

---

## Entity: `PreviewAsset`

Owned by Layer 2; URL stored in Neon, binary in Cloudflare R2.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `variation_id` | UUID | FK → `Variation.id`, NOT NULL, UNIQUE | One preview per variation. |
| `duration_seconds` | int | NOT NULL, default 5 | Always 5 for this feature. |
| `url` | text | NOT NULL | R2 pre-signed URL. |
| `derivation` | enum | NOT NULL, default `first_5s_of_full` | Reserved for future teaser-style previews. |
| `byte_size` | int | NOT NULL | |
| `content_hash` | text | NOT NULL | For preview-to-full equivalence regression test (SC-005). |
| `rendered_at` | timestamptz | NOT NULL | |

---

## Layer 3 — Request-only shapes

Layer 3 does not persist these as entities. It receives them per request in `VideoParams` (extended) and emits task-state records to Redis.

### `VideoParams` extensions (this repo, [app/models/schema.py](../../app/models/schema.py))

New fields on the existing Pydantic model:

| Field | Type | Default | Notes |
|---|---|---|---|
| `total_duration_seconds` | `int` (5 ≤ x ≤ 90) | no default — required going forward; during Step 1 may retain an implicit "use LLM-derived length" fallback guarded by a feature flag | Validates with Pydantic `Field(ge=5, le=90)`. |
| `variation_count` | `Optional[int]` (1 ≤ x ≤ 3) | 1 | Preserves existing `video_count` semantics at default 1. May deprecate `video_count` in a follow-up. |
| `render_mode` | `Literal["preview", "full"]` | `"full"` | `"preview"` truncates final assembly at t=5s and skips post-processing passes that don't affect the first 5 s. |
| `seed` | `Optional[int]` | None (`None` → randomize and log) | Used across LLM, voice-selection, material selection, music selection. |

### Redis task-state keys (extended)

| Key pattern | Value | Lifetime |
|---|---|---|
| `task:{task_id}:state` | JSON `{stage, progress, variation_index, render_mode}` | Job lifetime + 1 h TTL after terminal state |
| `task:{task_id}:event:preview_ready:{variation_index}` | `"1"` | Pub-sub only (not retained) |
| `task:{task_id}:event:full_ready:{variation_index}` | `"1"` | Pub-sub only |
| `task:{task_id}:event:failed:{variation_index}` | error string | Pub-sub only |

---

## Relationships

```
VideoJob 1 ── N Variation
VideoJob 1 ── 1 CreditHold
Variation 1 ── 0..1 PreviewAsset (exists iff preview_gate_required)
Variation 1 ── 0..1 Asset (full render; exists after full_rendering completes)
CreditHold 1 ── N credit_transactions (hold, debit × multiple, release × multiple)
```

---

## Validation rules

- **Duration**: `5 ≤ total_duration_seconds ≤ 90`. Enforced at Layer 1 (slider/input clamp), Layer 2 (API validation), Layer 3 (Pydantic). All three must enforce — defense in depth.
- **Variation count**: `1 ≤ variation_count ≤ 3`. Same defense in depth.
- **Preview gate derivation**: `preview_gate_required := total_duration_seconds > 30`. Computed at Layer 2 on job submit; immutable thereafter.
- **Seed propagation**: `Variation.seed = VideoJob.seed_base + Variation.variation_index` (or `+ 100 + i` on regeneration).
- **Credit invariant**: `CreditHold.amount_debited + CreditHold.amount_released ≤ CreditHold.amount_reserved` at all times; enforced by DB check constraint.
- **Preview equivalence**: `PreviewAsset.content_hash` for variation V should match the content hash of the first 5 s of V's full asset when re-rendered with identical inputs + seed (regression test, not runtime invariant).
