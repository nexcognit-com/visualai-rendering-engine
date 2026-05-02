# Feature Specification: NexCognit Credit Gating Integration

**Feature Branch**: `008-nexcognit-credit-gating`
**Created**: 2026-05-02
**Status**: Draft (paused — see §Resume conditions)
**Input**: User description: "NexCognit credit gating integration"

## Overview

Wire VisualAI into the NexCognit credit-management middleware (deployed at `https://middleware.nexcognit.com`) so that every video generation request is gated against a verified customer's credit balance before any LLM / rendering work runs, and is metered after success against a per-app pricing table. This is how VisualAI converts free demo traffic into paying-customer-only traffic without each agent mode building its own paywall.

The integration target is **Layer 1** (`visualai-frontend/`) at v1, not Layer 3 (this MoneyPrinterTurbo fork). This honors Constitutional Principle I (Layer 3 is rendering-only). When Layer 2 (Orchestration API) is built in Step 2 of the build plan, the integration MAY migrate from Layer 1 → Layer 2 for finer-grained per-LLM-call metering, but v1 lives in the frontend's API proxy routes.

This spec was started during a 2026-05-02 session that paused at the smoke-test step because the middleware's `users` table has no live records yet — VisualAI is pre-customer, so there is nothing to gate. All architectural decisions are locked in below. Implementation resumes when the first paying customer signs up via the Wix CRM webhook flow OR a synthetic test user is inserted via psql for smoke testing.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Verified customer can generate a video; unverified visitor cannot (Priority: P1)

A user signed in to VisualAI submits the Mode 2 wizard. Before any rendering work starts, the frontend looks up that user's NexCognit `crm_member_id`, calls the gate endpoint with the user's id and the VisualAI Mode 2 agent UUID, and proceeds only when the gate returns `ok: true`. If the user is not a paying customer (no record in the `users` table) OR is out of tokens OR is account-suspended, the gate fails closed and the wizard surfaces a typed error ("not a customer / out of tokens / account suspended") with the appropriate next-action message — not a generic "something went wrong."

**Why this priority**: this is the entire point of the integration. Without P1, anyone can generate unlimited videos for free. Every other story is downstream of this one.

**Independent Test**: With the integration deployed, submit Mode 2 wizard requests as (a) a real paying customer with positive balance — render proceeds and a final MP4 is produced; (b) the same customer with zero balance — gate refuses with `out_of_tokens`, no render happens; (c) an unknown email not in the `users` table — gate refuses with `customer_not_found`, no render happens. All three cases visible to the developer running the test in well under one minute each.

**Acceptance Scenarios**:

1. **Given** a Wix CRM customer with positive balance, **When** they submit the Mode 2 wizard, **Then** the frontend's `/api/generate` route resolves their email to a `crm_member_id`, the gate returns `ok: true`, and the MPT render starts within 2 seconds of the gate response.
2. **Given** the same customer with zero balance, **When** they submit the wizard, **Then** the gate returns `ok: false, error: "out_of_tokens", next_action: "top_up"`, the wizard shows a "top up to continue" UX, and no MPT render is initiated.
3. **Given** an email not in the `users` table, **When** they submit the wizard, **Then** the gate returns `customer_not_found`, the wizard shows a "sign up via Wix" UX, and no MPT render is initiated.
4. **Given** a customer whose status is `suspended`, **When** they submit the wizard, **Then** the gate returns `account_suspended, next_action: "contact_support"` and the wizard shows the appropriate copy.

---

### User Story 2 — Successful renders meter consumption back to the customer's wallet (Priority: P1)

When a Mode 2 render completes successfully on the MPT backend, the frontend reports the consumption to NexCognit via `/v1/events/consumption` so the customer's Lago wallet drains by the right number of tokens. The metering uses the units defined in `pricing-registry/apps.json`'s `visualai` entry (decided in this session): `video_seconds` for the rendered duration, `voiceover_seconds` for the audio, and `image_generation` for any generated stills. The kit converts those native units to tokens automatically using the per-app rate table.

**Why this priority**: a gate without metering means customers either never drain their wallet (they get free renders forever) or get charged on intent rather than success (they get charged for failed renders). Both break the credit ledger contract.

**Independent Test**: Run a real Mode 2 render against a paying customer with a known wallet balance. After the render completes successfully, verify in the Lago UI (operator-only) that the wallet drained by exactly the expected delta computed from the video duration × `video_seconds: 200` rate.

**Acceptance Scenarios**:

1. **Given** a successful Mode 2 render that produced a 30-second video with 30 seconds of voiceover, **When** the render completes, **Then** the frontend reports `{unit: "video_seconds", count: 30}` and `{unit: "voiceover_seconds", count: 30}` to `/v1/events/consumption`, the response includes a `lago_event_id`, and the wallet drains by 30 × 200 + 30 × 50 = 7,500 tokens.
2. **Given** a Mode 2 render that fails inside MPT (e.g., Pexels error, FFmpeg crash), **When** the failure is detected, **Then** NO consumption report is sent and the wallet does not drain.
3. **Given** the same `execution_id` is reported twice (race condition or retry), **When** the second report arrives at `/v1/events/consumption`, **Then** Lago dedups idempotently and the wallet drains exactly once.

---

### User Story 3 — Operator can observe and reconcile credit activity (Priority: P3)

The operator (founder) can verify, for any individual customer, that the wallet drains match the renders they actually got. This is enabled by the existing `lago_event_id` returned on each successful consumption call plus the existing My Assets tab showing render history; the operator simply joins them via the `execution_id`.

**Why this priority**: low day-one value (no real customers yet) but essential as soon as billing complaints exist. Putting it as P3 means we satisfy it via the existing My Assets surface without inventing new admin UIs.

**Independent Test**: Inspect the My Assets tab for a known customer and the operator's view of their Lago wallet history. The two MUST line up by `execution_id` / generation timestamp / token count.

**Acceptance Scenarios**:

1. **Given** a customer with N successful Mode 2 renders this billing cycle, **When** the operator opens that customer's Lago wallet history, **Then** there are N consumption events whose `execution_id`s match the N MPT task ids visible in the customer's My Assets.
2. **Given** a customer disputes a charge, **When** the operator looks up their history, **Then** they can produce, per render, the `execution_id`, the final video URL (already stored under MPT's `storage/tasks/<id>/`), and the wallet event's `lago_event_id`.

---

### Edge Cases

- **First-render cold start**: the middleware's first call from a fresh Next.js process can take ~8 s due to cross-region latency (us-east-2 Neon ↔ wherever Vercel/local runs). The frontend's `client.timeoutMs` MUST be ≥ 30 s, not the kit's default 10 s.
- **Render starts before gate response (race)**: the MPT call MUST NOT be issued until gate.invoke returns `ok: true`. No "fire and check later" patterns.
- **Render fails mid-pipeline after the gate succeeded**: no consumption report is sent. The operator absorbs the cost. Acceptable trade-off because failed renders cost the operator real money on Pexels / OpenAI but charging the customer for our backend bug is worse.
- **Customer's `status` flips to `suspended` during a long render**: the render finishes (the gate already approved it). No mid-flight cancellation. Acceptable trade-off; render economics are bounded by Mode 2's ~90s ceiling.
- **NexCognit middleware unreachable** (DNS, 502, timeout > 30 s): the frontend MUST fail closed (refuse the render) with a "service temporarily unavailable, please retry" message — never fail open by silently letting the render proceed.
- **Bearer rotated on the middleware VPS without redeploying the frontend**: every gate call returns 401. The frontend's error UX MUST distinguish "configuration / operator problem" (401) from "your account is suspended" (403) so the operator can react fast.
- **The operator account itself is not yet in `users`**: this is the 2026-05-02 paused state. The integration is wired but cannot smoke-test until at least one customer record exists.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The integration MUST live in **Layer 1** (`visualai-frontend/`) at v1. The implementation MUST NOT touch this MoneyPrinterTurbo (Layer 3) repo's source tree (`app/`, `app/services/`, controllers, render pipeline). This honors Constitutional Principle I (Layer 3 is rendering-only).
- **FR-002**: The integration MUST be packaged as the NexCognit kit's TypeScript client (from `nexcognit-com/nexcognit-integration-kit/clients/typescript/`) installed under `visualai-frontend/src/lib/nexcognit/`, NOT a hand-rolled re-implementation. v1 reuses what the kit ships.
- **FR-003**: The integration MUST gate **every** call to MPT's `/api/v1/videos` (the render-initiation boundary in `visualai-frontend/src/app/api/generate/route.ts`). There MUST be no code path that reaches MPT without a successful gate.invoke.
- **FR-004**: The gate sequence MUST be: `client.identity.resolveOrCreate({email})` → `client.gate.invoke({crm_member_id, agent_id, payload})` → MPT call → `client.events.report({unit, count, execution_id, crm_member_id, plan_code})`. Each step MUST complete before the next starts; no parallelism between identity-then-gate or gate-then-MPT.
- **FR-005**: Consumption metering MUST report Mode 2 renders against the `visualai` slug's units (decided in the 2026-05-02 session): `video_seconds: 200, image_generation: 1000, voiceover_seconds: 50, avatar_seconds: 500`. The `visualai` entry MUST be PR'd into `nexcognit-com/nexcognit-integration-kit/pricing-registry/apps.json` before any production deployment.
- **FR-006**: Each VisualAI Agent Mode MUST have its own `agent_configs` row with a distinct `agent_type` string, so per-mode usage analytics remain separable. v1 ships only `agent_type: "visualai_short_marketing_video"` (Mode 2). Modes 1, 3, 4, 5 add their own rows when they ship in Step 3 / Step 4 of the build plan.
- **FR-007**: The integration MUST fail closed: any unexpected error from the middleware (timeout, 5xx, malformed response) MUST refuse the render with a "service unavailable" message. Never silently let an ungated render through.
- **FR-008**: Customer-facing errors MUST surface NexCognit's typed `error` codes (`out_of_tokens`, `customer_not_found`, `account_suspended`, `account_inactive`, `agent_halted`) and the recommended `next_action` (`top_up`, `contact_support`, `none`, `retry_later`) — not generic "something went wrong" copy.
- **FR-009**: The bearer token MUST live only in `visualai-frontend/.env.local` (gitignored). It MUST NOT appear in `.env.example`, committed source, error messages surfaced to the user, or browser-visible state. The bearer is server-only — the frontend must call the middleware from server-side route handlers, not client components.
- **FR-010**: The client `timeoutMs` MUST be set to 30 s, not the kit's default 10 s, to accommodate the middleware's ~8 s cross-region cold-start observed in the 2026-05-02 session.
- **FR-011**: A consumption report MUST be sent ONLY after MPT confirms the render succeeded (a `final-N.mp4` exists in `storage/tasks/<task_id>/`). Renders that fail mid-pipeline MUST NOT report consumption. The operator absorbs the cost of failed renders.
- **FR-012**: The integration MUST surface the `lago_event_id` from every successful consumption report into the My Assets row for that render, enabling the audit pattern in User Story 3 without a separate admin UI.
- **FR-013**: When Mode 1, 3, 4, or 5 ships, that mode's first render MUST be preceded by a `POST /v1/agents` call to create a fresh `agent_configs` row for the new `agent_type`. The returned `id` becomes that mode's constant `AGENT_UUID` (analogous to Mode 2's `NEXCOGNIT_AGENT_ID_MODE2` env var).

### Key Entities

- **NexCognit Service Bearer**: a long-lived hex string stored in `visualai-frontend/.env.local` as `NEXCOGNIT_SERVICE_BEARER`. Authoritative copy lives on the middleware VPS as `N8N_SERVICE_BEARER` (legacy name from the n8n-era of the middleware; nothing in VisualAI itself uses n8n). Rotated rarely; rotation requires redeploying the frontend.
- **CRM Member**: a customer in NexCognit's `users` table, identified by an opaque `crm_member_id` (e.g., `wix_member_abc123`) and a verified email. v1 is resolve-only; users are provisioned by the Wix CRM webhook flow, not by VisualAI.
- **Agent Config**: a row in NexCognit's `agent_configs` table representing one (user_id, agent_type) pair. v1 ships one row for the operator + `visualai_short_marketing_video`; the row's `id` UUID is the Mode 2 `AGENT_UUID`.
- **Pricing Registry Entry**: the `visualai` row in `nexcognit-com/nexcognit-integration-kit/pricing-registry/apps.json`. Maps unit names to per-unit token costs. Adding a new mode's units to the entry forces a kit PR.
- **Gate Result**: the response from `POST /v1/agent/invoke`. Either `ok: true` (with `request_id` to use as `execution_id` later) or `ok: false` with a typed `error` and `next_action`.
- **Consumption Event**: the body of `POST /v1/events/consumption`. Contains `execution_id` (= the gate's `request_id`), `crm_member_id`, `plan_code`, `tokens_consumed`. The kit converts native units to `tokens_consumed` using the registry rates.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of Mode 2 render requests submitted by an unverified visitor (no record in `users`) MUST be refused at the gate. Zero such requests reach MPT. Measured by inspecting MPT's `storage/tasks/` directory after a 24-hour test window with mixed real-customer + visitor traffic — no task folders MUST correspond to unverified emails.
- **SC-002**: The Lago wallet for a known test customer MUST drain by exactly `(video_seconds × 200) + (voiceover_seconds × 50)` tokens per successful Mode 2 render. Verified per-render in the operator's Lago UI; tolerance is zero (the kit's `events.report` ensures integer math, never float drift).
- **SC-003**: Failed renders (any non-200 from MPT, or any task that doesn't produce a `final-N.mp4`) MUST drain zero tokens from the customer's wallet. Verified by inducing a failure (e.g., revoke Pexels key during a test render) and confirming the wallet balance is unchanged after the failure.
- **SC-004**: Customer-facing error UX MUST distinguish all five typed errors (`out_of_tokens`, `customer_not_found`, `account_suspended`, `account_inactive`, `agent_halted`) with distinct copy and a correct CTA matching the `next_action`. Verified by manually inducing each error and inspecting the wizard's UX.
- **SC-005**: Median end-to-end gate latency (frontend → middleware → frontend) MUST be ≤ 1.5 s after the cold-start warm-up; cold-start MUST be ≤ 30 s on the first call after a Vercel cold boot or local dev restart. Measured by logging server-side timestamps around each `client.gate.invoke`.
- **SC-006**: Bearer leakage check: a string match for the bearer's first 8 hex chars MUST return zero hits across (a) any browser-network response body, (b) any committed file in `visualai-frontend/`, (c) any user-facing error message rendered in the UI.

## Assumptions

- **The middleware exists and is healthy.** v1 of this spec doesn't deploy or maintain `https://middleware.nexcognit.com`; that's a separate operational concern. Outage handling is FR-007 (fail closed).
- **The Wix CRM is the sole source of truth for customer provisioning at v1.** VisualAI does not auto-create customers. A user must complete a Wix purchase flow before they can resolve to a `crm_member_id`. This is the same constraint that paused the 2026-05-02 implementation session.
- **Lago is the wallet/billing system behind NexCognit.** Token drains are visible in Lago UI; that's where the operator reconciles. VisualAI doesn't speak Lago directly — only the middleware does.
- **Mode 2 metering is per-render, post-completion.** v1 charges based on actual rendered video duration when the render finishes, not an upfront estimate. This means a customer with 5,000 tokens can attempt a 35-second render even though it would have cost 6,500 tokens, and the wallet will go briefly negative. Acceptable because (a) Lago supports overdraft + `next_action: top_up`, (b) Mode 2 renders are bounded at ~90 s so worst-case overdraft is ~18,000 tokens, and (c) the kit's gate does a soft balance check before allowing the render to start.
- **The integration is bounded to Mode 2 at v1.** Modes 1/3/4/5 reuse the same client wiring but each adds its own `agent_configs` row + `agent_type` + units (FR-013). This spec defines only Mode 2; the others are out of scope and ship inside their own VisualAI feature branches.
- **The frontend's existing `/api/generate` route is the only render-initiation surface.** New surfaces (e.g., a "regenerate" button on My Assets, a future API for Pro customers) MUST go through the same gate + meter wrap. This spec doesn't fork to handle those.
- **The bearer is a shared platform secret, not per-tenant.** Every VisualAI deployment authenticates to the middleware with the same `NEXCOGNIT_SERVICE_BEARER`. Per-tenant authentication is a future concern (Step 4+) when Layer 2 introduces JWT middleware.

## Resume conditions

The 2026-05-02 implementation session paused at the smoke-test step (Step 7 of `INTEGRATE.md`) because `POST /v1/identity/resolve-or-create` returned `customer_not_found` for the operator's own email — the `users` table is empty.

Implementation resumes when at least ONE of the following is true:

- **A real VisualAI customer signs up via the Wix CRM webhook flow.** The webhook fires, creates a `users` row, and a `crm_member_id` is now resolvable.
- **The operator inserts a synthetic test user via psql** (operator owns Neon; `INSERT INTO users (crm_member_id, email, status) VALUES ('test_visualai_smoke_001', 'amr.ae@cortex41.ai', 'active')`). Bypasses the CRM contract; only safe in non-production / smoke-test contexts.
- **VisualAI ships a Wix CRM purchase landing page first** as a precursor feature, so its first real customer can complete the loop end-to-end. This may slot earlier in the build plan than Step 4.

Once any resume condition is met, the next concrete steps are documented in [memory/project_nexcognit_integration.md](file:///Users/amraeid/.claude/projects/-Users-amraeid-Dropbox-Dev-lab-Cursor-Cluade-NexCognit-Content-generator-MoneyPrinterTurbo/memory/project_nexcognit_integration.md):

1. Get a real `crm_member_id`.
2. `POST /v1/agents` to create the Mode 2 agent_configs row; capture the returned `id` into `.env.local` as `NEXCOGNIT_AGENT_ID_MODE2`.
3. Copy the kit's TypeScript client into `visualai-frontend/src/lib/nexcognit/`.
4. Add `nexcognit.config.json` with the `visualai` pricing units.
5. Wrap `visualai-frontend/src/app/api/generate/route.ts` with identity → gate → MPT → consumption.
6. Smoke-test per `INTEGRATE.md` Step 7; expect `lago_event_id` in the response.

## Cross-references

- [5-step build plan](/Users/amraeid/.claude/plans/can-you-confirm-that-dapper-emerson.md) — this feature naturally lands inside Step 4 ("Modes 3 & 4 + Data Layer + Auth"), but the gate is so cheap to wire that it could ship earlier as a Step 1.5 increment if real customers arrive sooner.
- [Constitution v1.0.2](.specify/memory/constitution.md) — Principle I scopes Layer 3 to rendering only; this spec consciously places the integration in Layer 1 to comply.
- [STEP1_DEBT.md](../../STEP1_DEBT.md) — Step 1 deliberately ships without credit gating. This spec is the planned repayment.
- NexCognit integration kit: `https://github.com/nexcognit-com/nexcognit-integration-kit` — the source of `INTEGRATE.md`, the TypeScript client, the pricing registry, and the kit-side smoke test.
- NexCognit middleware: `https://github.com/nexcognit-com/nexcognit-middleware` — operator-only; defines the actual `/v1/agents`, `/v1/identity/resolve-or-create`, `/v1/agent/invoke`, `/v1/events/consumption` routes the client calls.
- [memory/project_nexcognit_integration.md](file:///Users/amraeid/.claude/projects/-Users-amraeid-Dropbox-Dev-lab-Cursor-Cluade-NexCognit-Content-generator-MoneyPrinterTurbo/memory/project_nexcognit_integration.md) — session-level memory of the 2026-05-02 paused state.
