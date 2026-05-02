# Contract: Feature-Flag Behavior (`CREDIT_ADMIN_PANEL_MODE`)

**Feature**: 003-admin-credit-panel
**Consumer**: Layer 1 middleware, Layer 2 endpoint handlers, operator flipping the flag.
**Authority**: this document + [spec.md FR-025..FR-027 + US4](../spec.md) + [research.md Q2](../research.md).

This contract defines the exact behavior of each of the three permitted values of `CREDIT_ADMIN_PANEL_MODE` across Layer 1, Layer 2, and (for clarity) Layer 3.

---

## Permitted values

| Value | Intent |
|---|---|
| `full` | Testing phase. All reads and writes enabled. |
| `read_only` | Post-Stripe launch. Reads enabled; writes disabled; route remains visible for audit. |
| `disabled` | Post-retirement (optional). Route completely absent — 404 for everyone. |

Any other value (including empty, unset, mistyped) MUST cause Layer 2 to **fail to boot** with a clear error message. This prevents silently defaulting to an unintended mode.

---

## Layer 1 behavior

### Route visibility

| Mode | `/admin/credits` route |
|---|---|
| `full` | Serves (internal admins only; others get 403) |
| `read_only` | Serves (internal admins only); renders with `<ModeBanner mode="read_only" />` and write CTAs disabled |
| `disabled` | `middleware.ts` rewrites to the 404 page for EVERYONE including internal admins |

### How Layer 1 learns the mode

```
1. On page load, useQuery calls GET /api/v2/config/panel-mode.
2. TanStack Query caches for 60 seconds.
3. The `middleware.ts` function reads a small edge-cached version of the same endpoint for route-level enforcement.
```

### UX details per mode

| Element | `full` | `read_only` | `disabled` |
|---|---|---|---|
| Top-of-page banner | none | `ModeBanner` (yellow) | 404 |
| Grant button | enabled | visibly disabled with tooltip | n/a |
| Deduct button | enabled | visibly disabled with tooltip | n/a |
| Set-balance button | enabled | visibly disabled with tooltip | n/a |
| Release-hold button | enabled | visibly disabled with tooltip | n/a |
| Search box | enabled | enabled | n/a |
| Audit log table | enabled | enabled | n/a |
| User-detail page | enabled | enabled | n/a |

### Stale-cache safety

If Layer 1's cached mode is stale (e.g., flag flipped from `full` to `read_only` between cache refreshes), a user might see a Grant button enabled. When they click it, Layer 2 returns 403 `panel_is_read_only`. Layer 1 surfaces that error, invalidates the cached mode, and refreshes UI.

**Consequence**: Layer 2 is authoritative. Layer 1's UX is an optimistic mirror.

---

## Layer 2 behavior

### Startup

At process boot, Layer 2:

1. Reads `CREDIT_ADMIN_PANEL_MODE` env var.
2. If unset OR not in `{full, read_only, disabled}`, raises a fatal error and exits 1.
3. Logs `{"event":"panel_mode_boot","mode":"<value>"}` at INFO.
4. Binds a readonly module-level constant `PANEL_MODE` consumed by middleware + handlers.

Mode changes require a restart (or orchestrator-level config-change + rolling deploy). No hot-reload is supported; this is intentional per [research.md Q2](../research.md).

### Per-endpoint behavior

| Endpoint | `full` | `read_only` | `disabled` |
|---|---|---|---|
| `GET /api/v2/config/panel-mode` | 200 `{"mode":"full"}` | 200 `{"mode":"read_only"}` | 200 `{"mode":"disabled"}` |
| `GET /api/v2/admin/**` (reads) | 200 (auth) | 200 (auth) | 404 (route absent) |
| `POST /api/v2/admin/**` (writes) | 200 (auth) | 403 `panel_is_read_only` | 404 |
| `POST /api/v2/admin/.../role/grant` | 200 (auth) | 403 | 404 |
| `DELETE /api/v2/admin/.../role` | 204 (auth) | 403 | 404 |

### 404 implementation in `disabled` mode

When `PANEL_MODE = "disabled"`, the FastAPI router for `/api/v2/admin/*` is NOT registered at all. Routes don't exist; responses are the framework-default 404. This matches the FR-002 requirement that the route's existence not be discoverable.

The `/api/v2/config/panel-mode` endpoint MUST remain registered in all three modes so Layer 1 can render a graceful "admin panel unavailable" state if an internal admin tries to reach it via a stale bookmark.

### 403 response shape (read_only)

```json
{
  "error": "panel_is_read_only",
  "message": "The admin credit panel is currently in read-only mode. Credit adjustments are handled by Stripe billing.",
  "request_id": "req_..."
}
```

---

## Layer 3 behavior

Layer 3 is **not involved** in the panel. Principle I keeps credit logic entirely out of this repo. The flag does not reach Layer 3.

The only way this flag affects Layer 3 indirectly: Layer 2 (which this repo depends on for future orchestration) enforces the zero-start policy (FR-022) by rejecting generation submits with insufficient credits BEFORE calling Layer 3. Layer 3 sees only validated requests. No Layer 3 code change is required for any flag transition.

---

## Flag transition runbook

### `full` → `read_only` (Stripe launch day)

1. Announce in the team channel: "Admin credit panel going read-only in 5 min."
2. Update the Layer 2 deployment config: `CREDIT_ADMIN_PANEL_MODE=read_only`.
3. Trigger a rolling restart of Layer 2 instances.
4. Verify via `curl /api/v2/config/panel-mode` that the new mode is reported.
5. Verify in the browser that:
   - `/admin/credits` still loads.
   - `<ModeBanner />` displays the read-only message.
   - Grant / Deduct / Set buttons are visibly disabled.
6. Attempt a write through the UI; confirm Layer 2 returns 403 `panel_is_read_only`.
7. Elapsed wall time MUST be ≤ 5 minutes (SC-006).

### `read_only` → `disabled` (complete retirement)

1. Audit the read traffic on `/api/v2/admin/**` for the past 30 days. If reads are near zero and the audit log has been exported / archived, proceed.
2. Update config: `CREDIT_ADMIN_PANEL_MODE=disabled`.
3. Rolling restart.
4. Verify `/admin/credits` returns 404 (Next.js middleware rewrites).
5. Verify any `/api/v2/admin/*` returns 404.
6. Verify `/api/v2/config/panel-mode` returns `{"mode":"disabled"}`.

### Emergency reversal

If a Stripe webhook issue makes manual grants necessary post-launch, flip `read_only` → `full` for a short window. All grants during this window are audit-logged with `reason` beginning with "EMERGENCY:" by convention. After resolution, flip back.

This emergency reversal is an expected operational pattern — the flag is deliberately designed to support it.

---

## Validation tests (SC-005 verification)

Automated access test run on every Layer 2 deploy:

```
For each mode in {full, read_only, disabled}:
  Boot Layer 2 with CREDIT_ADMIN_PANEL_MODE=<mode>.
  As an internal admin user, hit GET /api/v2/admin/users/search?q=test
    Expect: 200 if full or read_only; 404 if disabled.
  As a non-internal-admin user, hit the same
    Expect: 403 if full or read_only; 404 if disabled.
  As an internal admin user, hit POST /api/v2/admin/users/u123/credits/adjust
    Expect: 200 if full; 403 if read_only; 404 if disabled.
  As an internal admin user, hit GET /api/v2/config/panel-mode
    Expect: 200 with correct mode value in all three cases.
```

A single CI job runs the suite three times with different boot configs. Failure blocks the deploy.
