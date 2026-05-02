# Feature Specification: Orchestration Layer + Tenant Plumbing (Step 2)

**Feature Branch**: `014-orchestration-tenant`
**Created**: 2026-05-03
**Status**: Draft
**Input**: User description: "step 2"

## Overview

Step 1 shipped Mode 2 end-to-end on the existing rendering engine, but did so by relaxing two non-negotiable architecture principles:

- **Layer 3 Scope** (Principle I): the frontend calls the rendering engine directly, bypassing what should be the orchestration tier.
- **Multi-Tenant Context Propagation** (Principle III): every render runs single-user with no `tenant_id` / `user_id` / JWT — the rendering engine accepts whoever calls it.

This is exactly what `STEP1_DEBT.md` rows #1 + #2 promise to retire in Step 2. Step 2's job is to introduce **Layer 2 — the Orchestration API** as a real network tier that sits between Layer 1 (Next.js wizard) and Layer 3 (rendering engine). Layer 2 is where authentication issuance, tenant context, and forward-routing live.

After Step 2:

- The frontend talks ONLY to Layer 2.
- Layer 2 forwards to Layer 3 with a signed JWT carrying tenant context.
- Layer 3 rejects any request that doesn't bear a valid JWT issued by Layer 2.
- Tenant context appears in Layer 3's structured logs and audit log entries.
- The single-user demo path continues to work — but as a "demo tenant" with a real ID, not as the absence of identity.

This is the contract-real, behavior-still-single-user version of the architecture. Multi-tenant data isolation, real authentication issuance (NextAuth), and credit gating land later in Step 4 — Step 2 is the plumbing, not the storefront.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Render a Mode 2 video through the orchestration tier (Priority: P1)

A solo founder running the local demo opens the wizard at `localhost:3001/modes/short-video`, fills the brief + assets, and clicks Generate. The request goes to Layer 2 (`localhost:8080`), which authenticates the call against a static demo credential, attaches a JWT carrying the demo tenant's `tenant_id` + `user_id`, and forwards to Layer 3 (`localhost:8090`). Layer 3 verifies the JWT, accepts the render, runs the existing pipeline, and returns the same MP4 the user got in Step 1 — but now every audit line carries the tenant context.

**Why this priority**: This is the entire point of Step 2. Without it, Layer 3 stays unprotected and the architecture stays half-implemented.

**Independent Test**: Run the local stack (`pnpm dev`, `python main.py` for Layer 3, the new `python main.py` for Layer 2). Submit a render via the wizard. Verify (a) the request never hits `localhost:8090` directly from the browser, only via the proxy through Layer 2, (b) the resulting `script.json` audit log contains a non-null `tenant_id` + `user_id`, (c) the rendered MP4 is identical-quality to a Step 1 render.

**Acceptance Scenarios**:

1. **Given** Layer 2 is running and the wizard is configured to use it, **When** the user submits a render, **Then** the resulting task's `script.json` records the demo tenant's `tenant_id` and `user_id` and the Mode 2 MP4 is produced.
2. **Given** the wizard hits Layer 3 directly (e.g., via a stale env override), **When** the request lands without a JWT, **Then** Layer 3 returns HTTP 401 with `error_code: "missing_jwt"` and no task is created.
3. **Given** Layer 2 forwards a request with a JWT signed by an unknown key, **When** Layer 3 verifies, **Then** the request is rejected with HTTP 401 `error_code: "invalid_jwt"`.

---

### User Story 2 — Tenant context appears in every log line and filename (Priority: P1)

A future agency operator (Step 5 reader) needs to debug why a render failed. They open Layer 3's structured logs, filter by `tenant_id`, and see only the renders that belong to that tenant. The render task directory under `storage/tasks/<task_id>/` includes the `tenant_id` in the `script.json#params` block and any media files emit metadata tags identifying the owning tenant.

**Why this priority**: Multi-tenant isolation begins with traceability. Without it, agency-mode (Step 5) is a data leak waiting to happen.

**Independent Test**: Run two renders with two different demo tenant IDs. Confirm the `storage/tasks/` directories are tagged correctly (filesystem layout doesn't need to be tenant-scoped yet — that's Step 4 — but the audit data must include tenant_id everywhere it's relevant).

**Acceptance Scenarios**:

1. **Given** a render submitted with `tenant_id: T1`, **When** the task completes, **Then** `script.json#params.tenant_id == "T1"` and Layer 3's `loguru` log lines for that task all include `tenant_id="T1"`.
2. **Given** two simultaneous renders from different tenants T1 and T2, **When** logs are filtered by tenant, **Then** the filter returns only that tenant's lines (no cross-contamination from race conditions or shared global state).

---

### User Story 3 — Backward compatibility for the upstream MoneyPrinterTurbo client (Priority: P2)

Someone running the upstream MPT WebUI (`webui/Main.py`) at `localhost:8090` directly continues to work — the upstream WebUI doesn't know anything about Layer 2 or JWTs. The constitution says Layer 3 must be defensible, but it also says we don't break upstream so rebases stay clean.

**Why this priority**: Rebase friction with upstream MPT is a strategic cost the constitution explicitly minimizes (Principle II Rationale).

**Independent Test**: Hit `localhost:8090` from `webui/Main.py` (or `curl` with no Authorization header) using the legacy upstream payload shape. Confirm the request either succeeds (if Layer 3 has a "trust local upstream" mode flag enabled) or fails cleanly with a clear error message identifying it as an "upstream-direct call rejected" rather than a generic 401.

**Acceptance Scenarios**:

1. **Given** `LAYER3_TRUST_LOCAL_UPSTREAM=true` in the environment, **When** a request arrives at Layer 3 without a JWT but from `127.0.0.1` on a non-public bind, **Then** the request is accepted and a synthetic "upstream-demo" tenant context is attached for the render.
2. **Given** the same flag is `false` (production default), **When** the same request arrives, **Then** it's rejected with HTTP 401 `error_code: "missing_jwt"` and a log line explaining that the upstream-trust flag is off.

---

### Edge Cases

- **JWT expiry mid-render**: a long render's task continues even if the JWT used to submit it expires before the render completes. The JWT is verified at submit-time only; downstream pipeline doesn't re-check. Token-bound long-running operations are a Step 4 concern (when credit holds are time-bounded).
- **Layer 2 unreachable**: the wizard surfaces a clear "orchestration service unavailable, please retry" error. Doesn't fall back to direct Layer 3 calls (would defeat the security boundary).
- **Layer 3 unreachable from Layer 2**: Layer 2 returns HTTP 503 with `error_code: "render_engine_unavailable"`; the wizard polls for retry.
- **Demo credentials in production**: the static demo bearer / signing key MUST NOT be the production secret. A startup check fails Layer 2 if `LAYER2_ENV=production` and the demo secret is detected.
- **Asset upload routing**: `POST /api/v1/uploads/image` and `/audio` MUST route through Layer 2 too. Layer 3 keeps the endpoints (since Layer 4 isn't here yet to host signed-URL storage), but only via Layer 2 with valid JWT.
- **Polish-preview**: `POST /api/v1/scripts/polish-preview` (added in Step 1 follow-up) MUST also require a JWT in Step 2.
- **Webhooks / callbacks**: Step 2 doesn't introduce any webhook endpoints. Layer 3's render completion is observed via the existing `GET /api/v1/tasks/{id}` polling — no Layer 3 → Layer 2 callback yet (deferred to Step 4 when generation events drive credit settlement).
- **Existing Step 1 demo path**: when `LAYER3_TRUST_LOCAL_UPSTREAM=true` and Layer 2 isn't running, the demo path continues to work for local-only smoke tests. This is documented as a transitional dev-mode aid, not a production option.

## Requirements *(mandatory)*

### Functional Requirements

#### Layer 2 Service

- **FR-001**: A new FastAPI service named `visualai-orchestration` MUST exist as a separate repository (`../visualai-orchestration/`) and MUST run on `localhost:8080` by default in dev environments.
- **FR-002**: Layer 2 MUST expose the following public endpoints, each forwarding to a corresponding Layer 3 endpoint after attaching JWT-signed tenant context:
  - `POST /api/v1/videos` → `POST /api/v1/videos`
  - `GET /api/v1/tasks/{task_id}` → same
  - `POST /api/v1/uploads/image` → same
  - `POST /api/v1/uploads/audio` → same
  - `POST /api/v1/scripts/polish-preview` → same
- **FR-003**: Layer 2 MUST authenticate incoming requests via a static demo bearer token (configured via env var `LAYER2_DEMO_BEARER`) before forwarding. This is the Step 2 single-user authentication; real authentication via NextAuth + Wix CRM lands in Step 4.
- **FR-004**: Layer 2 MUST mint a short-lived (15-minute) JWT for every forwarded request, signed with `LAYER2_JWT_SIGNING_KEY` (HMAC-SHA256). The JWT carries: `tenant_id`, `user_id`, `iss: "visualai-orchestration"`, `aud: "visualai-rendering-engine"`, `exp`, `iat`, `jti`.
- **FR-005**: For Step 2's single-user demo, Layer 2 MUST attach a constant demo tenant context: `tenant_id: "demo-tenant-001"`, `user_id: "demo-user-001"`. The values are configurable via env vars but default to these constants.
- **FR-006**: Layer 2 MUST forward the original request body unchanged plus the new `Authorization: Bearer <JWT>` header. Layer 3-specific fields (e.g., `tenant_id` inside the body) are also injected so Layer 3's existing `VideoParams` Pydantic model can pick them up.
- **FR-007**: Layer 2 MUST return Layer 3's response body and status code verbatim, with one exception: if Layer 3 is unreachable Layer 2 returns HTTP 503 `error_code: "render_engine_unavailable"`.

#### Layer 3 (this repo) JWT verification

- **FR-008**: Layer 3 MUST add JWT middleware to the video controllers (`/api/v1/videos`, `/api/v1/tasks/*`, `/api/v1/uploads/*`, `/api/v1/scripts/*`). The middleware verifies the `Authorization: Bearer <JWT>` header signature using the same `LAYER2_JWT_SIGNING_KEY`, the issuer/audience claims, and the expiration.
- **FR-009**: When the JWT is missing, Layer 3 MUST return HTTP 401 with body `{"error_code": "missing_jwt", "detail": "..."}`. When the JWT is invalid or expired, return HTTP 401 with `error_code: "invalid_jwt"` or `"expired_jwt"`.
- **FR-010**: When the JWT is valid, Layer 3 MUST extract `tenant_id` + `user_id` from the JWT claims and (a) make them available to the request handler via `request.state` (or equivalent), (b) merge them into the request body before Pydantic parsing so `VideoParams.tenant_id` / `user_id` populate correctly when the body is forwarded by Layer 2.
- **FR-011**: `VideoParams` MUST gain required `tenant_id: str` and `user_id: str` fields. The model_validator MUST raise on empty/missing values when `LAYER3_REQUIRE_TENANT_CONTEXT=true` (production default after Step 2 lands; defaults to `false` for the Step 1 transition window).
- **FR-012**: Layer 3 MUST embed `tenant_id` + `user_id` in every `loguru` log line for the duration of a request, via a context-var-bound logger or Loguru's `bind()` API. This applies to logs in the request handler thread AND to logs in the render worker thread that processes the task.
- **FR-013**: Layer 3 MUST persist `tenant_id` + `user_id` into `storage/tasks/<task_id>/script.json#params` so post-render forensics can attribute each render to its owning tenant.

#### Frontend (Layer 1)

- **FR-014**: The Next.js wizard at `visualai-frontend/` MUST update its `NEXT_PUBLIC_LAYER3_URL` env var (or rename to `NEXT_PUBLIC_LAYER2_URL`) to point at Layer 2's `localhost:8080`. All `/api/generate`, `/api/status`, `/api/upload-image`, `/api/upload-audio`, `/api/polish-preview` proxies MUST forward to Layer 2 instead of Layer 3.
- **FR-015**: The wizard MUST send a static demo bearer token (`process.env.NEXT_PUBLIC_LAYER2_DEMO_BEARER`) in the `Authorization: Bearer ...` header on every Layer 2 request. This is the wizard's auth credential for the Step 2 demo; replaced by NextAuth-issued tokens in Step 4.
- **FR-016**: When Layer 2 is unreachable, the wizard MUST surface an explicit "orchestration service unavailable" error to the user, NOT silently fall back to direct Layer 3 calls.

#### Transitional dev-mode aid

- **FR-017**: Layer 3 MUST honor the env flag `LAYER3_TRUST_LOCAL_UPSTREAM` (default `false`). When `true` AND the request originates from `127.0.0.1` (`request.client.host`) AND no JWT is present, Layer 3 MUST attach a synthetic "upstream-demo" tenant context (`tenant_id: "upstream-demo"`, `user_id: "upstream-demo-user"`) and process the request normally. This is a dev-mode-only transition aid for the upstream MoneyPrinterTurbo WebUI; the flag MUST be `false` in production environments.
- **FR-018**: If `LAYER2_ENV=production` AND any of (`LAYER2_DEMO_BEARER` is the default placeholder, `LAYER2_JWT_SIGNING_KEY` matches the default placeholder, `LAYER3_TRUST_LOCAL_UPSTREAM=true`), Layer 2 (and/or Layer 3) MUST refuse to start and exit with a clear error message identifying which insecure setting tripped the check.

#### Debt burndown

- **FR-019**: After Step 2 ships, `STEP1_DEBT.md` row #1 (Layer 3 Scope) and row #2 (Multi-Tenant Context) MUST be struck through with a `repaid in <commit sha>` annotation. Row #6 (spec 006 upload endpoint Layer-3 carve-out) becomes partially repaid: uploads now route through Layer 2 (Principle I burned), but storage location stays in `storage/uploads/` until Layer 4's signed-URL store lands in Step 3+.
- **FR-020**: After Step 2 ships, the `storage/uploads/<uuid>.<ext>` path MUST gain a tenant prefix: `storage/uploads/<tenant_id>/<uuid>.<ext>`. The path-traversal guard in `app/models/schema.py:_require_under_uploads` MUST validate against the tenant-scoped subdirectory.

### Key Entities

- **Layer 2 Forwarding Request**: An incoming HTTP request to Layer 2 with a demo bearer token. Attributes: `endpoint_path`, `request_body`, `bearer_token`, `client_ip`, `received_at`. Transient — not persisted.
- **JWT Claims**: The set of claims attached to every Layer 2 → Layer 3 forwarded request. Attributes: `tenant_id`, `user_id`, `iss`, `aud`, `exp`, `iat`, `jti`.
- **Tenant Context (in Layer 3)**: The Layer-3-internal binding between a request and its owning tenant for the duration of the render. Attributes: `tenant_id`, `user_id`, `request_id`, `task_id` (when render dispatches). Stored in request state; embedded in logs + audit entries; persisted in `script.json#params`.
- **Demo Tenant**: The single static tenant context used during Step 2's single-user demo. Attributes: `id: "demo-tenant-001"`, `display_name: "Demo Tenant"`, `created_at`. Hardcoded; not stored in any DB.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After Step 2 lands, **0% of Mode 2 renders** complete without a `tenant_id` populated in the audit log. Verified by automated post-render audit invariant on every generation.
- **SC-002**: Direct calls to Layer 3's `localhost:8090/api/v1/videos` from outside `127.0.0.1` (or with the trust flag off) MUST receive HTTP 401 in 100% of cases. Verified by an automated `curl` test in CI.
- **SC-003**: A Mode 2 render submitted via the wizard → Layer 2 → Layer 3 chain completes in **≤ 2 seconds longer** than the equivalent Step 1 direct call (Layer 2's overhead). Verified by timing 10 renders in each path.
- **SC-004**: STEP1_DEBT.md row #1 (Layer 3 Scope) and row #2 (Multi-Tenant Context) MUST both be struck through with valid commit-sha annotations after Step 2's PR merges.
- **SC-005**: 100% of Layer 3 `loguru` log lines emitted during a request lifecycle MUST contain `tenant_id="..."` and `user_id="..."` fields. Verified by grep on a sample render.
- **SC-006**: The wizard's `pnpm dev` developer experience MUST remain ≤ 1 step harder to set up than Step 1. Specifically: `cp .env.example .env` + `pnpm dev` continues to work end-to-end with the demo bearer pre-populated. Adding Layer 2 to the local stack adds at most one terminal pane.
- **SC-007**: The upstream MoneyPrinterTurbo WebUI (`webui/Main.py`) continues to function locally when `LAYER3_TRUST_LOCAL_UPSTREAM=true`, **regardless** of Layer 2 running or not. Verified by hitting `localhost:8090` directly with the legacy payload.
- **SC-008**: Constitution Principle I + III status flips from "DEBT" to "PASS" in the spec 006 + spec 014 PR description audits.

## Assumptions

- Layer 2 lives in a **separate git repository** (`../visualai-orchestration/`), not as a subdirectory of this repo. This isolation matches the eventual deployment shape (different services, different scaling profiles, different team ownership).
- Layer 2 is a **FastAPI service** in Python — same runtime as Layer 3 — for development consistency. Future migration to a different runtime (e.g., Cloudflare Workers / Edge Functions) is not in scope for Step 2.
- Authentication in Step 2 is a **static demo bearer token**, NOT a real auth flow. NextAuth + Wix CRM integration land in Step 4 alongside the data layer. The Step 2 architecture is forward-compatible: NextAuth-issued tokens slot into the same `Authorization: Bearer ...` header without API-shape changes.
- The JWT signing scheme is **symmetric HMAC-SHA256** for Step 2. Asymmetric (RS256) keys belong to Step 4 when third-party services need to verify Layer 2's tokens.
- Step 2 does NOT introduce a database. The "demo tenant" is a hardcoded constant; multi-tenant data isolation (Neon, agency sub-tenants) lands in Step 4.
- Step 2 does NOT implement Layer 2.5's Dynamic Model Router for image/video/voice generation APIs — that's Step 3 alongside Modes 1 + 5 and the `material.py` rewrite.
- The frontend's bearer token (`NEXT_PUBLIC_LAYER2_DEMO_BEARER`) is exposed to the browser since Next.js `NEXT_PUBLIC_*` vars are public. This is acceptable for the Step-2 demo because the bearer is not secret in the security sense — it's just the demo token. Production requires server-side credential issuance, which lands with NextAuth in Step 4.
- Layer 2's deployment target for production is RunPod or equivalent — same shape as Layer 3 — but Step 2 only requires local development to work; production deployment of Layer 2 lands incrementally in later steps.
- Spec 008 (NexCognit credit gating) remains paused — credit gating routes through Layer 1's wrapper around `/api/generate`, NOT through Layer 2's forwarding tier. Layer 2 doesn't know about credits in Step 2; that's a Layer 1 + Step 4 concern.
- The upstream `webui/Main.py` is not actively used by NexCognit's product but stays in the repo for upstream-rebase compatibility. Step 2's `LAYER3_TRUST_LOCAL_UPSTREAM` flag preserves it for local dev.
- File paths under `storage/uploads/` migrate to `storage/uploads/<tenant_id>/<uuid>.<ext>` per FR-020. Existing `storage/uploads/<uuid>.<ext>` files from Step 1 either get migrated to `storage/uploads/demo-tenant-001/` in a one-time backfill OR are left orphaned (acceptable for the demo).
- The Layer 2 ↔ Layer 3 hop is HTTP over loopback in dev (`localhost:8080` → `localhost:8090`); production deployment specifics (TLS termination, internal mesh, etc.) are deferred.
