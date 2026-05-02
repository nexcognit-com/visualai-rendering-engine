# Implementation Plan: Admin Credit Panel (Testing-Phase Manual Credit Management)

**Branch**: `003-admin-credit-panel` | **Date**: 2026-04-19 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from [/specs/003-admin-credit-panel/spec.md](spec.md)

## Summary

An internal-only admin surface for granting, deducting, setting, and diagnosing credit balances on any user during the testing phase — with a hard-wired sunset mechanism: a single runtime flag flips the panel from `full` → `read_only` → `disabled` as the product matures past Stripe integration. The panel reads the same `credit_transactions` ledger that future Stripe webhooks will write to, so there is one source of truth across both paths.

Technical approach: land endpoints on the Layer 2 Orchestration API, backed by Neon PostgreSQL tables (created via the Neon MCP per spec 004's operations contract). Frontend surface is a dedicated route in the VisualAI Next.js app at `/admin/credits`, built from the design-system components established in spec 001 (ContentCard, Input, Select, Button, plus a new audit-log table). The rendering-engine repo (this repo, Layer 3, per constitution Principle I) does **not** implement admin or credit **application** logic; it may hold **only** reviewed Neon DDL under `ops/neon/migrations/` per constitution §Technology Constraints (Database) exception. New test users start at 0 credits (FR-022, SC-001) enforced at sign-up and by a server-side invariant check on every generation request.

## Technical Context

**Language/Version**:
- Layer 1 (frontend): TypeScript 5.x on Next.js 15 App Router.
- Layer 2 (orchestration API): Python 3.11 + FastAPI (matching the existing rendering-engine stack for team consistency; final choice confirmed in spec 002's orchestration contract).
- This repo (Layer 3): no new credit/admin business logic in `app/`; Neon DDL files only under `ops/neon/migrations/` when landed per tasks.

**Primary Dependencies**:
- Frontend: shadcn/ui + Radix primitives, Tailwind v4, TanStack Table for the audit log grid, TanStack Query for server state, Zustand for per-page UI state. All foundations installed during spec 001 implementation.
- Layer 2: FastAPI + Pydantic 2, SQLAlchemy 2 or asyncpg (decided in [research.md Q3](research.md)), python-jose for JWT validation, loguru for structured logs.
- Database: Neon PostgreSQL tables `users`, `tenants`, `credit_transactions`, `credit_holds`, `credit_adjustments`, `admin_users`. Schema owned by the future "credit-ledger core" spec; this feature consumes + extends it.

**Storage**:
- Neon PostgreSQL (single `visualai-prod` project with per-env branches per spec 004). New tables: `credit_adjustments` (manual write audit trail), `admin_users` (internal admin role registry). Existing tables referenced: `users`, `tenants`, `credit_transactions`, `credit_holds`.
- No client-side storage of credit data beyond TanStack Query cache (5-minute staleness for balance, 60-minute for audit rows).

**Testing**:
- Layer 1: Vitest for component unit tests; Playwright for E2E (admin-login → search → grant → verify balance path); axe-core per spec 001.
- Layer 2: pytest with `httpx` async client; integration tests against a test Neon branch (spec 004's Neon-branch-per-PR rule).
- Invariant tests: automated ledger-balance check (SC-003, SC-004); forbid-negative-balance check (SC-008); flag-mode access check (SC-005).

**Target Platform**:
- Evergreen browsers; no mobile requirement for the admin surface (desktop-first; tablet secondary; phone deferred).
- Layer 2 deployed to the NexCognit orchestration host (details owned by future orchestration spec).

**Project Type**: Web application — Layer 1 + Layer 2; Layer 3 limited to optional HTTP mapping (see Constraints) plus Neon DDL in `ops/neon/`.

**Performance Goals**:
- User search results within 2 s (FR-007).
- Credit-affecting write → UI reflects new balance within 5 s (US1 AS3).
- Audit log page (50 rows) first paint within 2 s.
- Balance invariant regression check runs on every generation request in < 10 ms (overhead on the generation critical path).

**Constraints**:
- Feature-flag-driven behavior (FR-025..027): three modes `full`, `read_only`, `disabled`; flag change is a single environment-variable flip with < 5-min propagation.
- 10-character minimum reason note on every write (FR-011).
- 100,000-credit grant threshold for second confirmation (FR-013).
- Negative-balance prevention enforced server-side (FR-012, SC-008) — the ledger invariant `debited + released ≤ reserved` AND resulting `balance ≥ 0` are both DB-level check constraints.
- Audit entries immutable (FR-019); enforced via DB-level lack of UPDATE/DELETE grants and a paranoid trigger that rejects row updates.
- **Generation / credits**: Layer 2 is authoritative — it MUST reject insufficient-credit generation before any Layer 3 call (primary path). Layer 3 in this repo is touched **only if** a direct-to-Layer-3 generation entrypoint still exists: then map that path to HTTP **402 Payment Required** without implementing ledger logic (constitution Principle I). If all traffic goes through Layer 2 only, document that and skip Layer 3 code changes.

**Scale/Scope**:
- Testing phase: ≤ 50 test users active, ≤ 5 internal admins, ≤ 200 adjustments/week. Post-launch: panel is `read_only`, so write scale is N/A; read scale follows general support-team inquiry volume (handful per week).
- Audit log: ~100,000 rows/year per typical SaaS usage — paginated, indexed, comfortable scale for Neon.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Evaluated against [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md) v1.0.2.

| Principle | Status | Notes |
|---|---|---|
| **I. Layer 3 Scope — Rendering Only** (NON-NEGOTIABLE) | ✅ PASS | Panel lives in Layer 1 (frontend) + Layer 2 (orchestration). This repo does not add credit/admin **application** code; Neon DDL under `ops/neon/migrations/` is the constitution §Technology Constraints (Database) exception. |
| **II. Surgical Fork Discipline** | ✅ PASS | No edits to this repo's five restricted fork-surface files. |
| **III. Multi-Tenant Context Propagation** | ✅ PASS (with note) | Every admin action carries the internal admin's `user_id` AND the target user's `user_id` + `tenant_id`. Layer 3's generation endpoints already require tenant context (per the constitution's Principle III Step 2 milestone); this feature doesn't introduce tenant-context gaps. |
| **IV. External Asset Acceptance Over Direct API Calls** | ✅ N/A | No rendering/asset logic. |
| **V. Mode-Aware Rendering Contract** | ✅ N/A | No mode-specific logic. |
| **§Technology Constraints — Database** | ✅ PASS | `ops/neon/migrations/*.sql` only; no ORM/schema in `app/` for tenant/credit/user. |

**Violations**: none.

**Complexity justification required**: no.

## Project Structure

### Documentation (this feature)

```text
specs/003-admin-credit-panel/
├── spec.md              # /speckit-specify output (done)
├── checklists/
│   └── requirements.md  # validation checklist (done)
├── plan.md              # this file
├── research.md          # Phase 0 output (this run)
├── data-model.md        # Phase 1 output (this run)
├── quickstart.md        # Phase 1 output (this run)
├── contracts/
│   ├── layer2-admin-api.md       # HTTP endpoints for admin operations
│   ├── frontend-components.md    # UI prop types for panel components
│   └── feature-flag-behavior.md  # full / read_only / disabled semantics
└── tasks.md             # /speckit-tasks output (next command)
```

### Source Code (across two repos + Neon DDL in this repo)

Application code for the panel lives in Layer 1 and Layer 2. This repo adds **only** `ops/neon/migrations/` SQL per tasks (and optional thin 402 mapping per Constraints). Remaining structure:

```text
# Layer 1 — ../visualai-frontend/
src/
├── app/
│   └── admin/
│       └── credits/
│           ├── page.tsx                      # Main panel view — search + balance + ops + audit
│           ├── user/[id]/page.tsx            # Deep dive on one user
│           └── layout.tsx                    # Admin-only layout with feature-flag guard
├── components/
│   └── admin/
│       ├── UserSearch.tsx                    # Email / user-id / prefix search
│       ├── BalancePanel.tsx                  # Current balance + quick-action CTAs
│       ├── CreditAdjustmentForm.tsx          # Grant / Deduct / Set inputs with reason + double-confirm
│       ├── HoldReleaseList.tsx               # Active holds with release action
│       ├── AuditLogTable.tsx                 # TanStack-Table-based filtered log
│       └── ModeBanner.tsx                    # Banner shown when flag is read_only
├── hooks/
│   ├── useAdminUser.ts                       # Load target user by id/email
│   ├── useCreditAdjustment.ts                # Submit grant / deduct / set mutations
│   └── useCreditAuditLog.ts                  # Paginated audit log query
├── lib/api/admin.ts                          # Layer 2 client wrapper
└── middleware.ts                             # Edge-level gate for /admin/** routes when flag=disabled

tests/
├── e2e/admin-credit-panel.spec.ts            # US1 + US2 end-to-end
└── components/admin/                         # Per-component Playwright tests

# Layer 2 — ../visualai-orchestration/
app/
├── api/v2/
│   └── admin/
│       ├── credits.py                        # HTTP endpoints: search, adjust, release-hold, audit
│       └── users.py                          # Admin bootstrap + role read
├── services/
│   ├── credit_ledger.py                      # Hold/debit/release state machine (shared with spec 002)
│   ├── credit_adjustment.py                  # Grant/deduct/set business logic
│   └── admin_auth.py                         # Internal-admin role check
├── models/
│   ├── admin_user.py                         # SQLAlchemy model
│   ├── credit_adjustment.py                  # SQLAlchemy model
│   └── credit_hold.py                        # Shared with spec 002
└── middleware/
    ├── jwt.py                                # JWT validation (shared)
    └── admin_panel_flag.py                   # Read CREDIT_ADMIN_PANEL_MODE, gate accordingly

# This repo (MoneyPrinterTurbo) — ops/neon/migrations/ per spec 004
├── 0010__admin_users.sql
├── 0011__credit_adjustments.sql
├── 0012__audit_view_and_triggers.sql          # VIEW, balance fn, triggers
└── 0013__audit_view_read_only_role.sql        # optional; Phase 7 / support read role

# Layer 2 — tests (../visualai-orchestration/)
tests/
├── api/admin/
│   ├── test_search.py
│   ├── test_adjust.py
│   ├── test_release_hold.py
│   ├── test_audit_log.py
│   └── test_flag_modes.py
└── services/
    ├── test_ledger_invariant.py              # SC-003, SC-004, SC-008
    └── test_new_user_zero_start.py           # SC-001
```

**Structure Decision**: Two-repo web application (frontend + orchestration API) plus Neon DDL committed in this repo under `ops/neon/migrations/` (constitution exception). The database migration SQL files follow spec 004's naming convention (`ops/neon/migrations/NNNN__description.sql`); the numbering continues from whatever the credit-ledger-core spec occupies. Numbers `0010`+ are reserved for this feature.

## Complexity Tracking

No violations. The feature uses the design-system components from spec 001, the ledger primitives from the future credit-ledger-core spec, and the operations policy from spec 004. No net new architectural concepts.

## Phase 0 — Research (resolved in [research.md](research.md))

Four open questions from the spec that shape the design:

1. How is "internal admin" identified and authorized vs tenant-level admin (who MUST NOT access this panel)?
2. What's the implementation shape of the feature-flag modes `full`/`read_only`/`disabled` — environment variable, database row, or config file — and how is the 404-vs-403 distinction enforced?
3. How do we guarantee audit-entry immutability at the DB level without adding operational burden on legitimate schema migrations?
4. What's the concurrency strategy when two admins write credit adjustments for the same user in the same second (FR edge case: concurrent admin actions)?

Phase 0 output: [research.md](research.md).

## Phase 1 — Design & Contracts

**Prerequisites**: Phase 0 complete.

Phase 1 output artifacts (produced in this run):

- [data-model.md](data-model.md) — entities: `AdminUser`, `CreditAdjustment`, `AuditEntry` (a VIEW over `credit_transactions` ∪ `credit_adjustments`), `CreditPanelMode`, plus the existing `CreditHold` and `CreditTransaction` this feature consumes.
- [contracts/layer2-admin-api.md](contracts/layer2-admin-api.md) — HTTP endpoints on Layer 2 for search, adjust (grant/deduct/set), release-hold, audit read, admin-role read.
- [contracts/frontend-components.md](contracts/frontend-components.md) — TypeScript prop shapes for `UserSearch`, `BalancePanel`, `CreditAdjustmentForm`, `HoldReleaseList`, `AuditLogTable`, `ModeBanner`.
- [contracts/feature-flag-behavior.md](contracts/feature-flag-behavior.md) — precise semantics for `full`/`read_only`/`disabled` across Layer 1 route existence, Layer 2 endpoint behavior, and Layer 3 (uninvolved but clarified).
- [quickstart.md](quickstart.md) — end-to-end local run of the admin panel after Step 2 ships Layer 2.

Agent context update: [`.specify/scripts/bash/update-agent-context.sh claude`](../../.specify/scripts/bash/update-agent-context.sh) runs after Phase 1 artifacts land.

**Post-design re-check**: Constitution Check re-evaluated against produced artifacts. Still ✅ PASS on all principles. No new complexity.
