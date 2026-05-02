# Data Model: Admin Credit Panel

**Phase**: 1 — Design & Contracts
**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

Entities defined across the Neon PostgreSQL schema (Layer 4), consumed by Layer 2 service code, and rendered by Layer 1 components. This feature **introduces** two new tables (`admin_users`, `credit_adjustments`) and **consumes** three existing tables from the credit-ledger core (`users`, `credit_transactions`, `credit_holds`).

---

## New entity: `admin_users`

Purpose: registry of internal NexCognit staff authorized to operate the Admin Credit Panel.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK, default `gen_random_uuid()` | |
| `user_id` | UUID | FK → `users.id`, UNIQUE, NOT NULL | One admin row per user max |
| `is_active` | boolean | NOT NULL, default `true` | Flipping to `false` de-activates without deletion |
| `granted_by` | UUID | FK → `users.id`, NULLABLE | Null for bootstrap admin; otherwise the admin who granted |
| `granted_at` | timestamptz | NOT NULL, default `NOW()` | |
| `grant_reason` | text | NOT NULL, CHECK (length(grant_reason) ≥ 10) | Min 10 chars, matches FR-011 |

**Indexes**:
- PK on `id`.
- UNIQUE on `user_id`.
- Partial index on `user_id WHERE is_active = true` for fast auth checks.

**Validation rules**:
- Cannot grant to a user that doesn't exist.
- Cannot insert a row where `granted_by = user_id` (no self-grant via DB; bootstrap uses `granted_by = NULL`).

---

## New entity: `credit_adjustments`

Purpose: append-only audit trail for every manual credit-affecting action performed by an internal admin.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `admin_user_id` | UUID | FK → `admin_users.id`, NOT NULL | Acting admin |
| `target_user_id` | UUID | FK → `users.id`, NOT NULL | Whose balance is changing |
| `target_tenant_id` | UUID | FK → `tenants.id`, NOT NULL | Denormalized for cross-tenant audit queries |
| `action` | enum | NOT NULL | `grant`, `deduct`, `set`, `release_hold` |
| `amount` | int | NOT NULL, CHECK (amount != 0) | Signed: positive for grant/release; negative for deduct; final-balance-minus-previous for set |
| `reason` | text | NOT NULL, CHECK (length(reason) ≥ 10) | FR-011 |
| `related_hold_id` | UUID | FK → `credit_holds.id`, NULLABLE | Non-null only for `release_hold` |
| `is_self_grant` | boolean | NOT NULL, default `false` | True when `admin_users.user_id = target_user_id` (FR-020) |
| `is_cross_tenant` | boolean | NOT NULL, default `false` | True when admin's tenant_id ≠ target_tenant_id (FR-021) |
| `resulting_balance` | int | NOT NULL, CHECK (resulting_balance ≥ 0) | Pre-computed at write time; never negative |
| `created_at` | timestamptz | NOT NULL, default `NOW()` | |

**Immutability** (per [research.md Q3](research.md)):
- No UPDATE or DELETE grants on this table for the `visualai_app` role.
- BEFORE UPDATE/DELETE trigger raises an exception:
  ```sql
  CREATE TRIGGER credit_adjustments_immutable
  BEFORE UPDATE OR DELETE ON credit_adjustments
  FOR EACH ROW EXECUTE FUNCTION raise_immutable_violation();
  ```

**Indexes**:
- PK on `id`.
- `(target_user_id, created_at DESC)` for per-user history queries.
- `(admin_user_id, created_at DESC)` for per-admin activity audits.
- Partial index `(created_at DESC) WHERE is_self_grant = true OR is_cross_tenant = true` for flagged-action queries.

---

## Consumed entity: `credit_transactions` (owned by credit-ledger core spec)

Existing ledger table of system-originated credit events (holds, debits, releases, expires — no manual grants). This feature reads but does not write here.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | |
| `user_id` | UUID | |
| `tenant_id` | UUID | |
| `event_type` | enum | `hold`, `debit`, `release`, `expire` |
| `amount` | int | Signed |
| `related_job_id` | UUID | FK to `generations` for job-related events |
| `related_hold_id` | UUID | |
| `created_at` | timestamptz | |

---

## Consumed entity: `credit_holds` (shared with spec 002)

Existing table; this feature uses it to list active holds per user (US2) and to release stuck holds (FR-015). See spec 002's data-model.md.

### Stuck-hold classification

A hold is classified as "stuck" when ANY of:

- The linked job is in state `expired` or `failed`.
- The hold has been in `active` state for more than 24 hours without
  transitioning to `settled`.
- The hold's `related_job_id` no longer exists in `generations` (orphan).

The `GET /api/v2/admin/users/{id}/credits` endpoint returns ALL active
holds per FR-014 (the admin needs full visibility into a user's hold
state), each annotated with an `is_stuck: boolean` field computed from
the predicate above. The `<HoldReleaseList />` frontend component
renders every row but exposes the "Release" action ONLY on rows where
`is_stuck = true`. Healthy (`is_stuck = false`) holds are displayed
read-only — releasing them manually would corrupt invariants the job
state machine relies on (e.g., an in-flight render job losing its
reserved credit mid-render).

---

## Virtual entity: `AuditEntry` (VIEW)

Purpose: unified chronological audit trail per user, combining manual adjustments and system events.

```sql
CREATE VIEW audit_entries AS
SELECT
  'system' AS source,
  ct.id, ct.user_id, ct.tenant_id,
  ct.event_type AS action,
  ct.amount,
  NULL AS admin_user_id,
  ct.related_job_id AS reference,
  NULL AS reason,
  false AS is_self_grant,
  false AS is_cross_tenant,
  ct.created_at
FROM credit_transactions ct
UNION ALL
SELECT
  'admin' AS source,
  ca.id, ca.target_user_id AS user_id, ca.target_tenant_id AS tenant_id,
  ca.action::text,
  ca.amount,
  ca.admin_user_id,
  ca.related_hold_id AS reference,
  ca.reason,
  ca.is_self_grant,
  ca.is_cross_tenant,
  ca.created_at
FROM credit_adjustments ca;
```

The Layer 2 audit endpoint queries this view, paginated and filtered. The view is read-only by construction.

---

## Virtual entity: Feature-Flag Mode

Not persisted in the DB. Read at Layer 2 startup from the environment variable `CREDIT_ADMIN_PANEL_MODE`. Valid values: `full`, `read_only`, `disabled`. Any other value is a fatal boot error.

Layer 1 reads the current mode via `GET /api/v2/config/panel-mode` (returned as `{"mode": "full" | "read_only" | "disabled"}`). TanStack Query caches for 60 s.

---

## Balance derivation

User balance is computed, not stored:

```sql
CREATE FUNCTION user_credit_balance(p_user_id UUID) RETURNS int AS $$
  SELECT
    COALESCE((SELECT SUM(amount) FROM credit_transactions WHERE user_id = p_user_id), 0)
    +
    COALESCE((SELECT SUM(amount) FROM credit_adjustments   WHERE target_user_id = p_user_id), 0)
$$ LANGUAGE SQL STABLE;
```

Server-side invariant (via a trigger on both ledger tables): no INSERT may leave the resulting balance negative.

```sql
CREATE OR REPLACE FUNCTION enforce_non_negative_balance() RETURNS TRIGGER AS $$
DECLARE
  target UUID;
BEGIN
  target := COALESCE(NEW.user_id, NEW.target_user_id);
  IF user_credit_balance(target) < 0 THEN
    RAISE EXCEPTION 'non-negative balance violation for user %', target;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE CONSTRAINT TRIGGER non_negative_balance_ct
  AFTER INSERT ON credit_transactions
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION enforce_non_negative_balance();

CREATE CONSTRAINT TRIGGER non_negative_balance_ca
  AFTER INSERT ON credit_adjustments
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION enforce_non_negative_balance();
```

SC-008 verification: every deduct / hold / debit operation, regardless of origin, passes through one of these two insert paths. Violation = transaction abort.

---

## State transitions (`CreditAdjustment.action` per target user)

A single target user's effective balance moves through states by virtue of accumulated events. There is no per-user state machine persisted; the balance is always the signed sum. Shown here for mental model:

```
balance starts at 0 (from new-user sign-up; no auto-grant in testing phase, FR-022)
 │  grant(+N)
 ▼
balance = N
 │  hold(N_hold) ─── (from a generation job)
 ▼
balance = N, held = N_hold, available = N - N_hold
 │  debit(-N_hold) on success / release(+N_hold) on reject/expire
 ▼
final balance depends on debit vs release
 │  admin may grant / deduct / set at any time (subject to non-negative invariant)
```

---

## Relationships

```
admin_users            credit_adjustments             credit_transactions
  │                      │                              │
  │ admin_user_id ───────┤                              │
  │                      │ target_user_id ───────►  users
  │                      │ target_tenant_id ──────► tenants
  │                      │ related_hold_id ───────► credit_holds
  │                                                     │
  │                                                     │ user_id ──► users
  │                                                     │ related_job_id ─► generations
  │                                                     │
  └─► user_id ──► users                                 │
                                                         │
                           audit_entries (VIEW) ◄───────┘◄──── credit_adjustments
```

---

## Validation rules (authoritative list)

1. **admin_users**: `user_id` unique; `grant_reason ≥ 10 chars`; `granted_by != user_id` for non-bootstrap rows.
2. **credit_adjustments**: `amount != 0`; `reason ≥ 10 chars`; `resulting_balance ≥ 0`; `related_hold_id` non-null only for `action = release_hold`.
3. **audit trail**: UPDATE / DELETE on `credit_adjustments` and `credit_transactions` blocked by trigger.
4. **balance**: user balance (sum across both ledger tables) must be ≥ 0 at all times; enforced by deferred constraint triggers.
5. **flag mode**: `CREDIT_ADMIN_PANEL_MODE` env var ∈ {`full`, `read_only`, `disabled`}; any other value is fatal at Layer 2 boot.
6. **zero-start**: new `users` inserts trigger NO automatic `credit_adjustment` during the testing phase — FR-022 verified by a Layer 2 integration test.
7. **Self-grant flag**: trigger auto-populates `is_self_grant = true` when the adjusting admin's `user_id = target_user_id`.
8. **Cross-tenant flag**: trigger auto-populates `is_cross_tenant = true` when admin's tenant != target's tenant.
