---
description: "Task list for Admin Credit Panel (feature 003)"
---

# Tasks: Admin Credit Panel (Testing-Phase Manual Credit Management)

**Input**: Design documents from [/specs/003-admin-credit-panel/](./)
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Test tasks are included because this feature touches the credit ledger — regression-proof invariants (non-negative balance, audit immutability, flag-mode access) are load-bearing (SC-003, SC-004, SC-005, SC-008). Contract tests are also included per every endpoint in the Layer 2 API contract.

**Organization**: Tasks are grouped by user story. Each US phase delivers an independently-testable increment.

**Repository targets**:
- `layer2` = `/Users/amraeid/Dropbox/Dev.lab/Cursor-Cluade/NexCognit-Content-generator/visualai-orchestration/` (sibling repo, created per spec 004 Step 1 demo)
- `frontend` = `/Users/amraeid/Dropbox/Dev.lab/Cursor-Cluade/NexCognit-Content-generator/visualai-frontend/` (sibling repo)
- `thisrepo` = `/Users/amraeid/Dropbox/Dev.lab/Cursor-Cluade/NexCognit-Content-generator/MoneyPrinterTurbo/` (Layer 3 — NOT modified except for `ops/neon/migrations/` per spec 004 governance)

**[P]** = parallel-eligible (different files, no dependency on incomplete tasks).
**[USk]** = user story k (from spec.md §User Scenarios).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: initialize the three working surfaces (Neon dev branch, Layer 2 repo, Layer 1 admin routes) before any credit logic lands.

- [ ] T001 Create a Neon dev branch named `dev-admin-credit-panel` via Neon MCP (per spec 004 [contracts/neon-operations.md](../004-neon-jira-github-ops/contracts/neon-operations.md)), capturing the branch connection string in a local `.env.local` for `layer2/` (never committed)
- [ ] T002 [P] In `layer2/`, scaffold FastAPI project with `uv init` and add dependencies: `fastapi`, `uvicorn`, `pydantic>=2`, `sqlalchemy[asyncio]>=2`, `asyncpg`, `python-jose[cryptography]`, `loguru`, `pytest`, `pytest-asyncio`, `httpx` — pinned in `pyproject.toml`
- [ ] T003 [P] In `frontend/`, install `@tanstack/react-table` for the audit log, confirm `@tanstack/react-query` and `zustand` already present from spec 001 scaffolding; add to `package.json`
- [ ] T004 [P] In `frontend/src/app/admin/credits/`, create directory plus empty `page.tsx` and `layout.tsx` placeholders that render a "Coming soon" card so the route renders without 404
- [ ] T005 In `layer2/app/`, create module skeleton: `api/v2/admin/`, `services/`, `models/`, `middleware/`, `main.py` with FastAPI app instance and a stub health endpoint at `/api/v2/config/panel-mode`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Neon schema, Pydantic models, and middleware that every US phase depends on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Database migrations (applied via Neon MCP per spec 004)

- [X] T006 [P] Write migration `thisrepo/ops/neon/migrations/0010__admin_users.sql` per [data-model.md §"New entity: admin_users"](data-model.md): table + indexes + CHECK constraints
- [X] T007 [P] Write migration `thisrepo/ops/neon/migrations/0011__credit_adjustments.sql` per [data-model.md §"New entity: credit_adjustments"](data-model.md): table + indexes + CHECK constraints
- [X] T008 Write migration `thisrepo/ops/neon/migrations/0012__audit_view_and_triggers.sql` creating the `audit_entries` VIEW, the `user_credit_balance()` function, the deferred non-negative-balance trigger, and the immutability trigger for both ledger tables
- [ ] T009 Apply migrations 0010–0012 via Neon MCP on the `dev-admin-credit-panel` branch (`prepare_database_migration` → review diff → `complete_database_migration`)
- [ ] T010 Seed the bootstrap internal admin by inserting one row into `admin_users` for the founder's existing user_id, via Neon MCP `run_sql` on the dev branch; capture the generated admin_user_id

### Pydantic + SQLAlchemy models

- [ ] T011 [P] Create `layer2/app/models/admin_user.py` with the SQLAlchemy ORM class + a Pydantic response schema; mark `__table_args__ = {"info": {"append_only": True}}` per [research.md Q3](research.md)
- [ ] T012 [P] Create `layer2/app/models/credit_adjustment.py` with SQLAlchemy + Pydantic, append-only marker, and the `action` enum `grant | deduct | set | release_hold`
- [ ] T013 [P] Create `layer2/app/models/audit_entry.py` as a read-only Pydantic model backed by the `audit_entries` VIEW (no ORM mapping; query via `asyncpg.fetch`)
- [ ] T014 [P] Create `layer2/app/models/credit_hold.py` importing from the future credit-ledger-core spec's shape; for Step-2 pre-launch, define locally and plan a consolidation in a later spec

### Middleware

- [ ] T015 Create `layer2/app/middleware/jwt.py` that validates the `Authorization: Bearer <jwt>` header, extracts `user_id` + `tenant_id`, attaches to the FastAPI request state, and returns 401 on invalid/expired
- [ ] T016 Create `layer2/app/middleware/admin_auth.py` that checks `admin_users.is_active = true` for the authenticated `user_id` and returns 403 when missing (or 404 when panel mode is `disabled`, handled by the flag middleware)
- [ ] T017 Create `layer2/app/middleware/admin_panel_flag.py` that reads `CREDIT_ADMIN_PANEL_MODE` at module load, fails boot on invalid values, and exposes `PANEL_MODE` as a module-level constant per [contracts/feature-flag-behavior.md](contracts/feature-flag-behavior.md)

### Shared endpoints

- [ ] T018 Implement `GET /api/v2/config/panel-mode` in `layer2/app/api/v2/config.py` returning `{"mode": "<value>"}` in all three flag states per the feature-flag contract
- [ ] T019 In `frontend/src/hooks/usePanelMode.ts`, create TanStack-Query hook that calls `GET /api/v2/config/panel-mode` with 60-s stale time
- [ ] T020 In `frontend/src/middleware.ts`, add an edge-level guard for `/admin/**` routes that reads the cached panel mode and rewrites to `/404` when mode is `disabled` per [contracts/frontend-components.md §"Middleware guard"](contracts/frontend-components.md)

**Checkpoint**: foundation ready. Neon schema + middleware + panel-mode plumbing in place; user-story phases can now proceed in parallel.

---

## Phase 3: User Story 1 — Internal admin grants credits to a test user (Priority: P1) 🎯 MVP

**Goal**: an internal admin can search a user, see their balance, and grant/deduct/set credits with a reason note. Resulting balance never goes negative. Self-grants and cross-tenant grants are flagged.

**Independent Test**: A new user is created with 0 credits. An admin grants 100 credits via the panel. The target user's next successful generation debits 10 credits, leaving a visible 90-credit balance. The panel's audit log shows the +100 grant by the admin, with timestamp, reason, and admin identity.

### Tests for User Story 1 ⚠️

> Write these tests FIRST, confirm they FAIL, then implement.

- [ ] T021 [P] [US1] Contract test for `GET /api/v2/admin/users/search` in `layer2/tests/api/admin/test_search.py`: verify 200 on valid query, 422 on missing `q`, 403 for non-admin, 404 when panel mode is `disabled`
- [ ] T022 [P] [US1] Contract test for `GET /api/v2/admin/users/{id}/credits` in `layer2/tests/api/admin/test_credits_read.py`: verify shape matches [contracts/layer2-admin-api.md](contracts/layer2-admin-api.md)
- [ ] T023 [P] [US1] Contract test for `POST /api/v2/admin/users/{id}/credits/adjust` in `layer2/tests/api/admin/test_adjust.py`: grant/deduct/set happy paths; validation failures on short reason, zero amount, deduct-below-zero; 409 confirmation-required for large grants
- [ ] T024 [P] [US1] Integration test `layer2/tests/services/test_non_negative_balance.py`: attempt to INSERT a deduct that would push balance negative → DB trigger raises, transaction aborts, no row written (SC-008 invariant)
- [ ] T025 [P] [US1] Integration test `layer2/tests/services/test_self_grant_flag.py`: when admin's user_id == target's user_id, the `is_self_grant` column is `true` and the row is audit-flagged
- [ ] T076 [P] [US1] Integration test `layer2/tests/services/test_concurrent_grants.py`: two parallel `POST .../credits/adjust` grants for the same user complete without lost updates; two `credit_adjustments` rows exist in commit order (spec edge case: concurrent admin actions)
- [ ] T026 [P] [US1] E2E Playwright test `frontend/tests/e2e/admin-grant.spec.ts`: sign in as admin, search user, grant 100 credits, verify updated balance appears within 5 seconds (US1 AS3)

### Layer 2 services + endpoints

- [ ] T027 [US1] Implement `layer2/app/services/admin_auth.py` with `assert_internal_admin(user_id)` used by every admin handler
- [ ] T028 [US1] Implement `layer2/app/services/user_search.py` with functions for exact-email, email-prefix (≥ 3 chars), and UUID lookups; returns `AdminUserSearchResult` shape
- [ ] T029 [US1] Implement `layer2/app/services/credit_adjustment.py` with `grant`, `deduct`, and `set_absolute` functions that INSERT into `credit_adjustments`, compute `resulting_balance`, and emit structured loguru lines per [contracts/layer2-admin-api.md §"Structured log events"](contracts/layer2-admin-api.md)
- [ ] T030 [US1] Implement `GET /api/v2/admin/users/search` endpoint in `layer2/app/api/v2/admin/users.py` wiring T028
- [ ] T031 [US1] Implement `GET /api/v2/admin/users/{user_id}/credits` endpoint in the same file (returns balance + holds)
- [ ] T032 [US1] Implement `POST /api/v2/admin/users/{user_id}/credits/adjust` endpoint in `layer2/app/api/v2/admin/credits.py` wiring T029, including the 100,000-threshold confirmation flow and the `read_only`/`disabled` mode gating

### Layer 1 components + hooks

- [ ] T033 [P] [US1] Build `frontend/src/components/admin/UserSearch.tsx` per [contracts/frontend-components.md §UserSearch](contracts/frontend-components.md) with 300 ms debounce, arrow-key navigation, OptionCard-based result rows
- [ ] T034 [P] [US1] Build `frontend/src/components/admin/BalancePanel.tsx` rendering balance + held + available + 3 CTAs inside a `<ContentCard>` from spec 001
- [ ] T035 [US1] Build `frontend/src/components/admin/CreditAdjustmentForm.tsx` with amount + reason (min 10 chars, live count) + live preview line; handles the 409-confirmation flow (second dialog); renders self-grant and cross-tenant warnings
- [ ] T036 [P] [US1] Build `frontend/src/hooks/useAdminUserSearch.ts` (TanStack Query, 2-min stale)
- [ ] T037 [P] [US1] Build `frontend/src/hooks/useAdminUserCredits.ts` (5-s stale)
- [ ] T038 [P] [US1] Build `frontend/src/hooks/useCreditAdjust.ts` (mutation; invalidates credits + audit queries on success)
- [ ] T039 [US1] Compose `frontend/src/app/admin/credits/page.tsx`: layout with `<UserSearch />` on left, when selected render `<BalancePanel />` and attach the `<CreditAdjustmentForm />` dialog wired to the three CTAs
- [ ] T040 [US1] Add `frontend/src/app/admin/credits/user/[id]/page.tsx` as a deep-link route that loads the selected user's panel without requiring a search

**Checkpoint**: US1 functional and testable independently. Admin can grant/deduct/set a user's balance end-to-end. MVP achieved.

---

## Phase 4: User Story 2 — Admin diagnoses history and releases stuck holds (Priority: P1)

**Goal**: admin can see the full audit log for any user (system + manual events interleaved) and can release stuck credit holds with a mandatory reason note.

**Independent Test**: Run a user through a scenario that creates 4 ledger events (grant, hold, partial debit, release). Open the panel. Verify all 4 events appear in chronological order with correct amounts, timestamps, reasons, and linked generation/job IDs. Release a stuck hold and verify balance increases by the hold amount.

### Tests for User Story 2 ⚠️

- [ ] T041 [P] [US2] Contract test for `GET /api/v2/admin/users/{id}/audit` in `layer2/tests/api/admin/test_audit.py`: pagination cursor round-trip; filter combinations (date range + actions + actor); 50-row default limit
- [ ] T042 [P] [US2] Contract test for `POST /api/v2/admin/users/{id}/holds/{hold_id}/release` in `layer2/tests/api/admin/test_release_hold.py`: happy path; 409 on already-settled; 422 on mismatched user/hold
- [ ] T043 [P] [US2] Integration test `layer2/tests/services/test_audit_view.py`: verify the `audit_entries` VIEW correctly unions `credit_transactions` and `credit_adjustments` in chronological order, sourced as `system` vs `admin`
- [ ] T044 [P] [US2] E2E Playwright test `frontend/tests/e2e/admin-release-hold.spec.ts`: create a stuck hold (via seed or mocked fixture), release it through the UI, verify row removal + balance increase

### Layer 2 services + endpoints

- [ ] T045 [US2] Implement `layer2/app/services/audit_query.py` with paginated, filterable SELECT against the `audit_entries` VIEW (cursor encoded as base64 of offset + filter hash)
- [ ] T046 [US2] Implement `layer2/app/services/hold_release.py` that compare-and-swaps the hold's state (reusing spec 002's state-machine pattern), INSERTs an offsetting `credit_adjustments` row with `action=release_hold`, and returns the new available balance
- [ ] T047 [US2] Implement `GET /api/v2/admin/users/{user_id}/audit` endpoint in `layer2/app/api/v2/admin/audit.py` wiring T045
- [ ] T048 [US2] Implement `POST /api/v2/admin/users/{user_id}/holds/{hold_id}/release` in `layer2/app/api/v2/admin/credits.py` wiring T046

### Layer 1 components + hooks

- [ ] T049 [P] [US2] Build `frontend/src/components/admin/AuditLogTable.tsx` using TanStack Table per [contracts/frontend-components.md §AuditLogTable](contracts/frontend-components.md): columns, filters, cursor pagination, flagged-row warning icons (self-grant, cross-tenant). **US2 AS2**: when a row includes a linked generation/job ID, render it as a link to the existing job-detail route in the frontend (path from spec 002 / orchestration; e.g. `/jobs/[id]` or equivalent) so admins reach preview/variation state — verify in E2E or component test
- [ ] T050 [P] [US2] Build `frontend/src/components/admin/HoldReleaseList.tsx` with active-holds table + release confirmation dialog (min 10-char reason)
- [ ] T051 [P] [US2] Build `frontend/src/hooks/useAdminUserAudit.ts` (60-s stale, cursor-aware)
- [ ] T052 [P] [US2] Build `frontend/src/hooks/useHoldRelease.ts` (mutation; invalidates credits + audit queries)
- [ ] T053 [US2] Extend `frontend/src/app/admin/credits/page.tsx` to render `<HoldReleaseList />` and `<AuditLogTable />` below the `<BalancePanel />` when a user is selected

**Checkpoint**: US2 functional. Admin can debug any user's credit history and recover stuck holds.

---

## Phase 5: User Story 3 — Zero-start invariant for new users (Priority: P2)

**Goal**: every new user signs up with 0 credits and cannot generate until an admin grants credits. The panel and the API both enforce this.

**Independent Test**: Create a new test user via the sign-up flow. Attempt to generate — the Generate CTA is disabled, and the API rejects the request with 402 (insufficient credits). Grant credits via the panel. Verify the user can now generate.

### Tests for User Story 3 ⚠️

- [ ] T054 [P] [US3] Integration test `layer2/tests/services/test_zero_start.py`: create a new `users` row; verify `user_credit_balance(id) == 0` AND `credit_adjustments` + `credit_transactions` have zero rows for that user
- [ ] T055 [P] [US3] Contract test `layer2/tests/api/test_generate_insufficient_credits.py`: as a new 0-balance user, hit the generation endpoint; expect 402 (or equivalent error code per the future orchestration spec); verify Layer 3 received no request
- [ ] T056 [P] [US3] E2E Playwright test `frontend/tests/e2e/new-user-zero-start.spec.ts`: sign up fresh user; see balance 0 displayed; attempt to click Generate; see the insufficient-credits dialog; after an admin grants credits in a separate session, user can generate

### Implementation

- [ ] T057 [US3] Add forward-dated regression guard in `layer2/tests/api/auth/test_signup_no_auto_grant.py`: creates a fresh user via the sign-up path, asserts `user_credit_balance(id) == 0`, asserts zero rows in both `credit_adjustments` and `credit_transactions` for that `user_id`. Decorate with `@pytest.mark.skipif(not _signup_endpoint_registered(), reason="auth/sign-up lands in a future orchestration spec")` where `_signup_endpoint_registered()` is a helper in `layer2/tests/conftest.py` that imports the FastAPI app and checks for a route matching `/api/v2/auth/signup`. The test auto-activates when the endpoint registers; no manual unmarking required.
- [ ] T058 [US3] Implement Layer 2 generation-request guard in `layer2/app/api/v2/jobs/` (or equivalent): before calling Layer 3, check `user_credit_balance(user_id) >= required_amount`; return 402 with a clear body if insufficient. If the codebase still exposes a **direct Layer 3** generation entrypoint, add a minimal HTTP 402 mapping there (no ledger logic); if all traffic is Layer-2-gated only, document in `README` or orchestration docs and skip Layer 3 edits
- [ ] T059 [US3] Build `frontend/src/components/InsufficientCreditsDialog.tsx` (shared component) that reads current mode from `usePanelMode`: in testing phase shows "Request credits from an admin"; in production shows "Top up via billing"
- [ ] T060 [US3] Wire the dialog into the Creation Wizard (from spec 002) so clicking Generate at 0-balance opens the dialog instead of submitting

**Checkpoint**: US3 enforced both at Layer 1 (UX) and Layer 2 (server-side). Zero-balance invariant is ironclad.

---

## Phase 6: User Story 4 — Feature-flag sunset mechanism (Priority: P2)

**Goal**: flipping `CREDIT_ADMIN_PANEL_MODE` between `full`, `read_only`, and `disabled` changes behavior correctly at every layer, with no deploy required beyond a config reload.

**Independent Test**: Deploy Layer 2 with `CREDIT_ADMIN_PANEL_MODE=read_only`. Visit the admin panel as an internal admin. Read views work; every write control is disabled with an explanation banner. Flip to `disabled`; the route returns 404 for everyone. Flip back to `full`; writes work again.

### Tests for User Story 4 ⚠️

- [ ] T061 [P] [US4] Contract test matrix `layer2/tests/api/test_flag_modes.py` per [contracts/feature-flag-behavior.md §"Validation tests"](contracts/feature-flag-behavior.md): 3 modes × (internal-admin vs non-admin) × (read endpoints, write endpoints, config endpoint) = 18 assertions
- [ ] T062 [P] [US4] Integration test `layer2/tests/test_boot_fatal_on_bad_mode.py`: setting `CREDIT_ADMIN_PANEL_MODE` to an invalid value (empty, `FULL`, `yes`, etc.) causes Layer 2 boot to exit with a fatal error
- [ ] T063 [P] [US4] E2E Playwright test `frontend/tests/e2e/admin-mode-transitions.spec.ts`: mock the panel-mode API to return each of the three modes; verify UI renders correctly in each; verify disabled-mode produces 404

### Implementation

- [ ] T064 [US4] Harden `layer2/app/middleware/admin_panel_flag.py` (from T017): explicit validation against `{full, read_only, disabled}`, structured log event `{"event":"panel_mode_boot","mode":"..."}`, raise `SystemExit(1)` on invalid
- [ ] T065 [US4] In `layer2/app/api/v2/admin/__init__.py`, conditionally register the router: if `PANEL_MODE == "disabled"`, do NOT include the `/api/v2/admin/*` routes (they return framework-default 404)
- [ ] T066 [US4] Ensure every write endpoint (T032, T048) checks `PANEL_MODE != "read_only"` at handler entry and returns 403 with body `{"error":"panel_is_read_only"}` when true
- [ ] T067 [P] [US4] Build `frontend/src/components/admin/ModeBanner.tsx` per [contracts/frontend-components.md §ModeBanner](contracts/frontend-components.md): yellow banner on `read_only`, red on `disabled` (defensive render), nothing on `full`
- [ ] T068 [US4] Wire `usePanelMode` into `<BalancePanel />`, `<CreditAdjustmentForm />`, `<HoldReleaseList />` so write controls disable themselves on `read_only` with a tooltip explanation
- [ ] T069 [US4] Extend `frontend/src/middleware.ts` (from T020) to rewrite to `/404` on `disabled` mode for every `/admin/**` path

**Checkpoint**: US4 validated. Feature flag works end-to-end across both layers. Sunset path proven.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T070 [P] Add loguru structured logging to every admin write in `layer2/app/api/v2/admin/*.py` per the log shape in [contracts/layer2-admin-api.md §"Structured log events"](contracts/layer2-admin-api.md); self-grants emit WARN level
- [ ] T071 [P] Add `X-Request-Id` middleware in `layer2/app/middleware/request_id.py` that generates a UUID per request and propagates through all logs + error responses
- [ ] T072 [P] Write migration `thisrepo/ops/neon/migrations/0013__audit_view_read_only_role.sql` granting `visualai_ro` role SELECT on the `audit_entries` VIEW for support-team read access
- [ ] T073 [P] Add `thisrepo/OPERATIONS.md` section "Admin Credit Panel" documenting: (1) bootstrap procedure for a new internal admin, (2) the `CREDIT_ADMIN_PANEL_MODE` flag's full/read_only/disabled semantics with pointers to the transition runbook, (3) the **pre-Stripe-launch checklist item** mandating the `full → read_only` flip before billing goes live (satisfies FR-026), (4) the weekly break-glass reconciliation query pattern per spec 004
- [ ] T074 Run the full [quickstart.md](quickstart.md) end-to-end against a clean dev Neon branch; document any deviations or fixes needed; update quickstart if commands drifted
- [ ] T075 Verify every success criterion SC-001 through SC-008 with a named test:
  - SC-001 ↔ T054 (zero-start)
  - SC-002 ↔ manual timing in quickstart §5
  - SC-003 ↔ T025 + T045 + T071 (audit completeness)
  - SC-004 ↔ T024 (non-negative balance)
  - Concurrent admin grants (spec edge case) ↔ T076 (ordering; complements ledger append guarantees)
  - SC-005 ↔ T061 (access matrix)
  - SC-006 ↔ manual timing in quickstart §7
  - SC-007 ↔ manual timing in quickstart §8
  - SC-008 ↔ T024

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: depends on Step 1 of the 5-step build plan (frontend scaffolded) + Step 2 starting (orchestration repo exists). Can begin as soon as both prerequisites are in place.
- **Phase 2 (Foundational)**: depends on Phase 1 completion. Blocks all user stories.
- **Phase 3 (US1)**: depends on Phase 2. First deliverable.
- **Phase 4 (US2)**: depends on Phase 2. Can run parallel to US1 if staffed for parallel work.
- **Phase 5 (US3)**: depends on Phase 2. Can run parallel to US1/US2.
- **Phase 6 (US4)**: depends on Phase 2 + at least T020 from Phase 1. Can run parallel to US1-US3 once Phase 2 complete.
- **Phase 7 (Polish)**: depends on Phases 3–6.

### User Story Dependencies

- **US1 (P1)**: no dependencies on other stories — fully self-contained MVP.
- **US2 (P1)**: depends on the `audit_entries` VIEW from T008 (Phase 2). Can run independently of US1.
- **US3 (P2)**: depends on Layer 2 generation endpoints existing; if the orchestration spec hasn't shipped generation endpoints yet, T058 is scoped to the guard only and full integration waits.
- **US4 (P2)**: depends on the middleware registered in T017 + T020 (Phase 2). Otherwise independent.

### Critical edges within a story

- **US1**: T027 → T029 → T032 (services before endpoints). T035 (CreditAdjustmentForm) depends on T038 (useCreditAdjust hook). Otherwise most work is parallel.
- **US2**: T045 → T047 (audit service before endpoint); T046 → T048 (release service before endpoint). T053 depends on T039 (US1's page scaffold) — small cross-story edge.
- **US4**: T064 → T065 → T066 must be sequential (mode constant → router conditional → handler check). Frontend tasks (T067–T069) parallelizable after the Layer 2 cascade.

### Parallel Opportunities

Per phase:

- **Phase 1**: T002 + T003 + T004 parallel; T005 after T002.
- **Phase 2**: T006 + T007 parallel; T008 after; T009 sequential. T011 + T012 + T013 + T014 parallel after T009. T015 + T016 + T017 parallel; T018 after T017; T019 + T020 parallel after T018.
- **Phase 3 (US1)**: all tests T021-T026 and T076 parallel. Services T027-T029 parallel. T030/T031/T032 after services. Components T033/T034/T036/T037/T038 parallel; T035 after T038; T039 after T033/T034/T035; T040 after T039.
- **Phase 4 (US2)**: T041-T044 parallel tests. T045/T046 parallel services. T047 after T045; T048 after T046. T049-T052 parallel components. T053 after T049/T050.
- **Phase 5 (US3)**: T054-T056 parallel; T057/T058 parallel implementation; T059/T060 parallel frontend.
- **Phase 6 (US4)**: T061-T063 parallel tests; T064 → T065 → T066 sequential; T067/T068/T069 parallel frontend.
- **Phase 7 (Polish)**: T070–T073 all parallel; T074/T075 after.

---

## Parallel Example: US1 kickoff

Once Phase 2 completes, kick off US1 tests in parallel:

```bash
# All tests for US1, launchable simultaneously:
Task: "T021 [P] [US1] Contract test for GET /api/v2/admin/users/search"
Task: "T022 [P] [US1] Contract test for GET /api/v2/admin/users/{id}/credits"
Task: "T023 [P] [US1] Contract test for POST /api/v2/admin/users/{id}/credits/adjust"
Task: "T024 [P] [US1] Integration test: non-negative balance invariant"
Task: "T025 [P] [US1] Integration test: self-grant flag"
Task: "T076 [P] [US1] Integration test: concurrent grants ordering"
Task: "T026 [P] [US1] E2E: admin search → grant → balance updates"
```

Then services in parallel:

```bash
Task: "T027 [US1] Implement admin_auth.py"           # can run concurrently — different file
Task: "T028 [US1] Implement user_search.py"          # different file
Task: "T029 [US1] Implement credit_adjustment.py"    # different file
```

Components in parallel:

```bash
Task: "T033 [P] [US1] Build <UserSearch /> component"
Task: "T034 [P] [US1] Build <BalancePanel /> component"
Task: "T036 [P] [US1] Build useAdminUserSearch hook"
Task: "T037 [P] [US1] Build useAdminUserCredits hook"
Task: "T038 [P] [US1] Build useCreditAdjust hook"
```

---

## Implementation Strategy

### MVP first (US1 only)

1. Phase 1 (Setup): ≈ 1 h
2. Phase 2 (Foundational): ≈ 4 h
3. Phase 3 (US1): ≈ 8 h
4. **STOP AND VALIDATE**: demo a grant end-to-end. Stop here if the goal was just the critical MVP.

**Total MVP**: ~13 hours of focused work. Suitable for a two-day sprint with one engineer.

### Incremental Delivery

1. Setup + Foundational + US1 → first ship (admin can grant credits).
2. Add US2 → second ship (admin can debug + release holds).
3. Add US3 → third ship (zero-start invariant enforced).
4. Add US4 → fourth ship (sunset mechanism validated).
5. Polish → fifth ship (CI-hardened, documented).

### Parallel Team Strategy

With two engineers after Phase 2:

- Engineer A: Phase 3 (US1 + frontend tasks).
- Engineer B: Phase 4 (US2 + audit-log table is meatier).
- Re-converge on Phase 5 and Phase 6 together; Phase 7 split by files.

---

## Notes

- Tasks marked [P] operate on different files with no incomplete-task dependencies; safe to assign in parallel.
- Tasks without [P] touch a shared file or depend on a predecessor in the same phase.
- Tests MUST be written and FAIL before implementation per the "write tests first" discipline in the Foundational phase.
- Every credit-affecting code path (T029, T046) MUST emit a structured loguru line per the contract.
- The Layer 3 rendering engine (this repo) is NOT modified by any of these tasks except for the migration SQL files under `ops/neon/migrations/` (per spec 004 Neon governance). All other changes land in `layer2/` and `frontend/`.
- Per [spec.md](./spec.md) Assumptions (FR-026, `OPERATIONS.md`, spec 004 runbook): the `OPERATIONS.md` "Admin Credit Panel" section in T073 MUST land in the same PR as any of the flag-behavior changes (pre-Stripe `full` → `read_only` checklist).
- A separate future spec `005-credit-ledger-core` owns the full `credit_transactions` + `credit_holds` schema and the hold/debit/release state machine shared with spec 002. This tasks file scopes only the admin-panel-specific tables (`admin_users`, `credit_adjustments`) and consumes the shared tables as read-only until that spec ships.
