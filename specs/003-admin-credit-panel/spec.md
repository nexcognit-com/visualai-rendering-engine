# Feature Specification: Admin Credit Panel (Testing-Phase Manual Credit Management)

**Feature Branch**: `003-admin-credit-panel`
**Created**: 2026-04-19
**Status**: Draft
**Input**: User description: "Add an admin panel to be able to set credits manually during testing, but there is no credits to be added in the beginning during testing. At the end, all credits and everything will be through APIs."

## Overview

During the testing phase of VisualAI (before Stripe-based top-ups ship in Step 4 of the 5-step build plan), the team needs a way to grant, deduct, or set credit balances for any user without touching the database by hand. This feature adds an internal-only admin panel for that purpose.

The panel is a **bridge capability**, not a permanent product surface. It exists to:
1. Let QA, product, and founder users hand out test credits so they can exercise generation flows.
2. Debug credit-ledger edge cases (e.g., a refund gone wrong during preview-gate testing) without direct SQL access.
3. Enforce a zero-balance starting state for every new test user, so nothing can be generated until credits are explicitly granted.

Once the Stripe webhook → `credit_transactions` pipeline ships (Step 4 milestone, per VisualAI Master Spec §9 Phase 2), the panel's write operations are disabled in production and the read-only audit view is retained as a break-glass tool. The design MUST make this retirement a one-line configuration change, not a code removal.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Internal admin grants credits to a test user (Priority: P1)

A NexCognit team member (founder, engineer, or QA lead) signs up a new test user to validate the end-to-end generation flow. They open the admin panel, look up that user by email, grant 100 credits, and add a note ("QA: short-marketing Mode 2 validation"). The test user refreshes and sees the new balance and can now generate.

**Why this priority**: Without this, every test generation requires a Stripe sandbox transaction or a raw DB edit. The whole testing phase is blocked or painful. This is the single highest-impact testing-phase productivity feature.

**Independent Test**: A new user is created with 0 credits. An admin grants 100 credits via the panel. The target user's next successful generation debits 10 credits, leaving a visible 90-credit balance. The panel's audit log shows the +100 grant by the admin, with timestamp, reason, and admin identity.

**Acceptance Scenarios**:

1. **Given** an admin is signed in with internal-admin role, **When** they open the admin panel and search for a user by email or user ID, **Then** the user's current credit balance and last 10 adjustments are visible within 2 seconds.
2. **Given** the admin has a user loaded, **When** they type `100` in the "Grant credits" field, add a required note, and confirm, **Then** the user's balance increases by exactly 100, an audit entry is written, and a success toast appears.
3. **Given** a successful grant has completed, **When** either the admin or the target user views the balance, **Then** the new value is consistent within 5 seconds of the grant.
4. **Given** the target user is logged in when a grant occurs, **When** they navigate to any page showing credits, **Then** the updated balance is visible without requiring a manual reload (live refresh or gentle toast).

---

### User Story 2 - Internal admin inspects credit history and diagnoses a balance anomaly (Priority: P1)

A support-style question comes in: "My test user only got one video for 100 credits, why don't I have 90 left?" An admin loads that user and sees the full credit-transaction history — holds, debits, releases, grants, deductions — in chronological order with amounts and reasons. They identify the cause (e.g., a held but unreleased amount from an expired preview job) and either release the stuck hold manually or deduct the appropriate amount.

**Why this priority**: Without an audit view, every support question becomes a DB forensics exercise. The audit view IS the panel's long-term value after write operations are retired.

**Independent Test**: Run a user through a test scenario that creates 4 ledger events (grant, hold, partial debit, release). Open the panel. Verify all 4 events are displayed in order with correct amounts, timestamps, reason text, and the linked generation/job ID when applicable.

**Acceptance Scenarios**:

1. **Given** a user has a ledger of ≥ 5 transactions, **When** the admin opens that user's history, **Then** the 50 most recent transactions are paginated and each shows: timestamp, type (grant / deduct / set / hold / debit / release), amount with sign, resulting balance, reason note, acting admin (for manual events) or linked job ID (for system events).
2. **Given** the admin is viewing history, **When** they click a linked generation/job ID, **Then** they navigate to the job's detail view showing preview/full assets, variation state, and any renders that failed.
3. **Given** a stuck hold is visible, **When** the admin clicks "Release hold" on a stuck row, **Then** the hold's outstanding amount is returned to the user's balance and the action is audit-logged.

---

### User Story 3 - New test users start with zero credits (Priority: P2)

A new test account is created (sign-up form submitted, or seeded by an admin). The account has 0 credits. Every generation attempt shows a clear "You need credits to generate — ask an admin or top up" message. Nothing consumes compute until credits are present.

**Why this priority**: Prevents accidental free runs, catches credit-ledger bugs early (any user who appears non-zero without a traceable grant is a bug), and mirrors the shape of the real Stripe-gated flow that replaces this panel.

**Independent Test**: Create a new test user via the sign-up flow. The user's initial balance is 0. Attempting to generate produces a clear insufficient-credits message and NO Layer 3 task is created. An admin grants credits; the user can now generate.

**Acceptance Scenarios**:

1. **Given** the sign-up flow is completed, **When** the new user's account is created, **Then** their credit balance is 0 and their ledger is empty (no automatic grants).
2. **Given** a user has 0 credits, **When** they attempt to start any generation, **Then** the Generate CTA is disabled with a tooltip, or clicking it yields an insufficient-credits dialog with a "Request credits" (testing phase) or "Top up" (post-launch) action.
3. **Given** a user with 0 credits attempts generation via the API directly, **When** the request is validated, **Then** the API rejects with a 402 Payment Required (or equivalent) and no rendering task is created in Layer 3.

---

### User Story 4 - Admin panel is gated behind a feature flag and hidden in production (Priority: P2)

The panel is visible only when an environment-level flag is on. In the production environment (after Stripe-based billing launches), the write operations are disabled and a banner explains that credits now flow through the billing system. The read-only audit view remains so support can investigate historical issues.

**Why this priority**: Mitigates the risk of the panel being exposed to paying customers, or of an admin accidentally granting credits after billing goes live. It is the "sunset" mechanism the feature description implies.

**Independent Test**: Deploy the app to a production-like environment with `CREDIT_ADMIN_PANEL_MODE=read_only`. Visit the admin panel route as an internal admin. The search and history views work; every "Grant," "Deduct," "Set balance," and "Release hold" control is either absent or disabled with an explanation.

**Acceptance Scenarios**:

1. **Given** `CREDIT_ADMIN_PANEL_MODE=full`, **When** an internal admin visits the panel, **Then** all read and write controls are enabled.
2. **Given** `CREDIT_ADMIN_PANEL_MODE=read_only`, **When** an internal admin visits the panel, **Then** read views work but write controls are absent or clearly disabled with an explanation banner.
3. **Given** `CREDIT_ADMIN_PANEL_MODE=disabled`, **When** any user (including an internal admin) visits the panel's route, **Then** the response is 404 (route not registered) — not 403 — so the route's existence isn't leaked.
4. **Given** the flag is `full` or `read_only`, **When** a non-internal-admin user (including a tenant admin) visits the route, **Then** the response is 403.

---

### Edge Cases

- **Negative balances**: The panel MUST prevent an admin from deducting more than the user's current balance, producing a clear error rather than allowing negative. Deducting exactly to zero is permitted.
- **Concurrent admin actions**: If two admins grant credits to the same user within the same second, both grants are applied and both audit entries are written in the correct order (optimistic concurrency via ledger append; no lost updates).
- **Admin is also a test user**: An admin MAY grant credits to themselves; this is explicitly logged and flagged in the audit view (visual marker on self-grants) to deter abuse.
- **Missing or unclear reason note**: Every write operation requires a minimum 10-character reason note. Submitting without the note shows a validation error.
- **Mid-flight generation**: Grants and deductions during an in-flight generation MUST be applied atomically with existing holds/debits; no race conditions that cause negative balances or double-debits.
- **User deleted while admin has panel open**: If the admin tries to act on a user who was deleted mid-session, they see a clear "User no longer exists" error; no orphaned ledger entries.
- **Very large grants (> 100,000 credits)**: Require a second admin confirmation step ("Are you sure you want to grant 500,000 credits?") to prevent fat-finger mistakes.
- **Target user across tenants**: An internal admin can search and act across any tenant (not constrained by tenant scoping) — this is a privileged superuser path and every cross-tenant action is flagged in the audit log.
- **Stripe-era conflict**: Post-launch, if an admin performs a grant while `CREDIT_ADMIN_PANEL_MODE=read_only`, the panel surface prevents the action; if someone bypasses the UI and hits the API directly, the API MUST also reject (server-side enforcement, not UI-only).
- **Audit log immutability**: Normative requirement is **FR-019** (no duplicate rules here).

## Requirements *(mandatory)*

### Functional Requirements

#### Access & Authorization

- **FR-001**: The admin panel MUST be accessible only to users with internal-admin role (distinct from tenant-level admin roles; internal admin is a NexCognit team role).
- **FR-002**: The panel's route MUST return 404 (not 403) when `CREDIT_ADMIN_PANEL_MODE=disabled` so the route's existence is not discoverable.
- **FR-003**: Every state-changing admin action MUST be authenticated AND authorized server-side; client-side gating is not sufficient.
- **FR-004**: When `CREDIT_ADMIN_PANEL_MODE=read_only`, write endpoints MUST reject with a clear error; the route MUST remain discoverable for audit.

#### User Search & Selection

- **FR-005**: Admin MUST be able to look up any user by exact email, exact user ID, or partial email prefix (≥ 3 characters).
- **FR-006**: Results MUST display user email, user ID, tenant name, current credit balance, account creation date, and role.
- **FR-007**: Selecting a user MUST load their credit history (most recent 50 entries, paginated) within 2 seconds.

#### Credit Operations

- **FR-008**: Admin MUST be able to **grant** credits (positive adjustment) in any integer amount from 1 to 1,000,000 per operation.
- **FR-009**: Admin MUST be able to **deduct** credits (negative adjustment) in any integer amount from 1 up to the user's current available balance.
- **FR-010**: Admin MUST be able to **set absolute balance** to any integer value from 0 upward; the operation is persisted as a single ledger entry describing the delta.
- **FR-011**: **(a)** Every credit-affecting write operation (grants, deducts, absolute-balance sets, hold releases) MUST require a reason note of at least 10 characters, enforced by a database CHECK constraint plus client-side validation on the corresponding form. **(b)** Elevation of a user to internal-admin status via an API or admin UI (insert/update into `admin_users` through that flow) MUST record a justification of at least 10 characters on the elevation action. **(c)** One-time bootstrap or migration-seed rows in `admin_users` MAY use an audited system tag defined in [data-model.md](data-model.md) (e.g. `bootstrap_initial_admin`) where free-text justification does not apply.
- **FR-012**: Operations that would result in negative balance MUST be blocked with a clear error.
- **FR-013**: Grants or set-balance operations whose resulting delta exceeds 100,000 credits MUST require a second confirmation step. Deducts are exempt regardless of size — the non-negative-balance invariant (FR-012) already caps their maximum magnitude at the user's current balance, and the resulting ledger entry is reversible via a compensating grant if needed.

#### Credit Hold & Release Operations (Diagnostic)

- **FR-014**: Admin MUST be able to view any user's currently-active credit holds, including the linked job ID, hold amount, and age.
- **FR-015**: Admin MUST be able to release a stuck or orphaned hold, returning the held amount to available balance; the release is audit-logged with the admin's identity and reason.

#### Audit & History

- **FR-016**: Every credit-affecting action — manual (grant, deduct, set, hold-release) and system (hold, debit, system release, expire) — MUST produce an immutable audit entry.
- **FR-017**: Audit entries MUST include: timestamp (UTC, millisecond precision), actor identity (admin user ID or "system"), action type, amount with sign, resulting balance, reason note or job reference, and tenant+user IDs.
- **FR-018**: The audit history view MUST support filtering by date range, action type, and actor (admin vs system).
- **FR-019**: Audit entries MUST never be deleted or edited; corrections are separate offsetting entries.
- **FR-020**: Self-grants (admin granting credits to their own account) MUST be visually flagged in every audit view.
- **FR-021**: Cross-tenant actions by internal admins MUST be visually flagged in every audit view.

#### Zero-Start State

- **FR-022**: Newly created user accounts MUST have a balance of 0 credits and an empty ledger, with no automatic signup grant.
- **FR-023**: Users with 0 credits attempting to generate MUST receive a clear insufficient-credits response at the API layer (server-side enforcement), regardless of UI state.
- **FR-024**: The frontend MUST surface the 0-balance state with a clear call-to-action appropriate to environment (request from admin during testing; top up post-launch).

#### Feature-Flag Retirement Path

- **FR-025**: The panel MUST read a single runtime flag `CREDIT_ADMIN_PANEL_MODE` with three values: `full` (all operations enabled), `read_only` (audit view only, write endpoints reject), `disabled` (route returns 404).
- **FR-026**: The default value in production deployments MUST be `disabled` once Stripe-based top-ups launch (Step 4 milestone).
- **FR-027**: Switching between modes MUST require only an environment-level configuration change (no code change, no redeploy beyond config reload).

### Key Entities

- **Admin User**: An internal NexCognit staff member with elevated panel access. Distinct from tenant admin. Attributes: user ID, email, granted_at, granted_by (the admin who elevated them, or "bootstrap" for the first admin).
- **Credit Adjustment**: A single manual credit-affecting action. Attributes: id, admin user ID, target user ID, tenant ID, action type (grant / deduct / set / release-hold), amount (signed), reason note, created timestamp, cross_tenant flag, self_grant flag.
- **Audit Entry**: The unified append-only log combining manual Credit Adjustments with system-produced ledger events (holds, debits, system releases, expirations) from the credit-ledger. Attributes per FR-017.
- **Credit-Panel Mode**: The runtime configuration that governs the panel's behavior. Values: full, read_only, disabled. Read on each request or on config reload.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of new user accounts start with 0-credit balance and an empty ledger, verified by an automated invariant check running on every sign-up.
- **SC-002**: An admin can find a target user, review their history, and apply a grant within 60 seconds of opening the panel (timed across 5 internal admins in a post-launch usability review).
- **SC-003**: 100% of credit-affecting actions — both manual and system — produce audit entries, verified by a ledger invariant: for any user, balance at time T equals the signed sum of their audit entries up to T.
- **SC-004**: 0 incidents of negative balance across all test users during the testing phase (6+ weeks), verified by continuous balance >= 0 assertions.
- **SC-005**: A non-internal-admin user visiting the panel's route when the mode is `full` or `read_only` receives a 403; when the mode is `disabled`, they receive a 404 — verified by automated access tests on every deploy.
- **SC-006**: After the Stripe-billing launch, switching `CREDIT_ADMIN_PANEL_MODE` from `full` to `read_only` takes < 5 minutes total (config change + verification), with no code deploy required.
- **SC-007**: Time from "new test user signs up" to "admin has granted credits, user generates first video" is under 3 minutes for an internal admin familiar with the panel.
- **SC-008**: 100% of write operations that would leave a non-zero negative balance are rejected with a clear error and do not write to the ledger (verified via automated edge-case tests).

## Assumptions

- "Internal admin" is a role distinct from tenant-level admin. It is granted out-of-band by the engineering team (initial bootstrap via DB seed; subsequent elevations by an existing internal admin). The spec for the full admin role management lifecycle is a separate future feature.
- The panel is a UI surface within the VisualAI frontend application (Layer 1), reached via a dedicated route (e.g., `/admin/credits`) that is not linked from the main navigation. Backend endpoints live in the Orchestration API (Layer 2). The rendering engine (Layer 3, this repository, per constitution Principle I) is NOT involved and performs no credit logic.
- The underlying credit-ledger (`credit_transactions` table per Master Spec §6) is the single source of truth. The admin panel is a management surface over that ledger, not a separate store.
- New users ALWAYS start at 0 credits during the testing phase. Any automatic free-tier grant policy (e.g., "20 credits on sign-up" from Master Spec §8) is a separate, post-launch feature that is NOT in scope here and does not apply while the feature flag is `full` or `read_only`.
- "Through APIs" (user's phrasing) is interpreted as: once the Stripe-integrated billing flow launches, all credit grants come from Stripe webhook → `credit_transactions` inserts. Manual admin writes are disabled at that point; the read-only audit path remains.
- Feature-flag values `full`, `read_only`, `disabled` are reasonable defaults that support the full retirement lifecycle. An alternative design of physically removing the panel post-launch is explicitly rejected because the audit view remains useful for historical debugging.
- FR-026 (default=disabled post-Stripe-launch) is an operational responsibility enforced by the pre-launch deployment runbook owned by spec 004. `OPERATIONS.md §"Admin Credit Panel"` (landed by task T073) MUST carry this pre-launch checklist item: "Before Stripe billing goes live, flip `CREDIT_ADMIN_PANEL_MODE` from `full` to `read_only` via the rolling config-change procedure in [contracts/feature-flag-behavior.md §'Flag transition runbook']."
- Every credit operation requires a reason note (10-char minimum). This is a reasonable default; reducing or removing the requirement is a UX choice that can be revisited, but the default protects against thoughtless actions.
- The 100,000-credit threshold for requiring a second confirmation is a reasonable default calibrated to be ~3× the largest paying-plan's monthly credit count (Pro = 3,000 per Master Spec §8, so grants > 100k should be rare and deliberate).
- Cross-tenant admin actions by NexCognit internal admins are a privileged superuser path. The panel does NOT scope searches by tenant; an internal admin sees all users across all tenants. Every cross-tenant write is flagged in the audit view. This is intentional for a testing-phase tool; post-launch the panel is read-only anyway.
- This spec does not cover the credit-ledger's own schema design (that's owned by a separate future feature for the Stripe billing integration). This spec consumes the ledger and writes to it.
