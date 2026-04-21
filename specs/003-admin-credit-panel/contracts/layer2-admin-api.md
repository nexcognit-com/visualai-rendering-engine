# Contract: Layer 2 Admin Credit API

**Feature**: 003-admin-credit-panel
**Layer**: 2 — Orchestration API (sibling repo `../visualai-orchestration/`)
**Consumer**: Layer 1 admin panel at `/admin/credits`; never called from Layer 3.

All endpoints under the base path `/api/v2/admin/`. Every endpoint's behavior depends on the server's `CREDIT_ADMIN_PANEL_MODE` env var per [contracts/feature-flag-behavior.md](feature-flag-behavior.md).

---

## `GET /api/v2/admin/users/search`

Look up users by email (exact or prefix ≥ 3 chars) or user ID.

### Query params

| Name | Required | Notes |
|---|---|---|
| `q` | yes | Search term (email prefix OR exact email OR UUID) |
| `limit` | no | 1–50, default 20 |

### Response (200)

```json
{
  "results": [
    {
      "user_id": "u_01HZX...",
      "email": "qa1@nexcognit.com",
      "tenant_id": "t_...",
      "tenant_name": "Internal QA Tenant",
      "role": "Admin",
      "is_internal_admin": false,
      "created_at": "2026-04-18T00:00:00Z",
      "balance_credits": 0,
      "active_holds_count": 0
    }
  ],
  "returned": 1
}
```

### Errors

| Condition | Status |
|---|---|
| Missing `q` | 422 |
| Caller not internal admin | 403 |
| `CREDIT_ADMIN_PANEL_MODE = disabled` | 404 (route absent) |

---

## `GET /api/v2/admin/users/{user_id}/credits`

Full credit context for a single user.

### Response (200)

```json
{
  "user_id": "u_01HZX...",
  "email": "qa1@nexcognit.com",
  "tenant_id": "t_...",
  "balance_credits": 150,
  "held_credits": 30,
  "available_credits": 120,
  "active_holds": [
    {
      "hold_id": "h_...",
      "amount": 30,
      "related_job_id": "g_...",
      "created_at": "2026-04-19T00:00:00Z",
      "expires_at": "2026-04-20T00:00:00Z",
      "age_seconds": 600,
      "is_stuck": false
    }
  ]
}
```

**`is_stuck` semantics**: computed per the stuck-hold classification in
[data-model.md](../data-model.md). All active holds are returned for
admin visibility (FR-014); only `is_stuck: true` holds are eligible for
the release endpoint below (FR-015). The frontend renders every row but
gates the Release action on `is_stuck = true`.

---

## `GET /api/v2/admin/users/{user_id}/audit`

Paginated audit log for a user combining system events and admin adjustments.

### Query params

| Name | Required | Notes |
|---|---|---|
| `cursor` | no | Opaque pagination token |
| `limit` | no | 1–200, default 50 |
| `since` | no | ISO timestamp filter |
| `until` | no | ISO timestamp filter |
| `actions` | no | Comma-separated list to filter (e.g., `grant,hold,debit`) |
| `actor` | no | `admin`, `system`, or a specific admin_user_id |

### Response (200)

```json
{
  "entries": [
    {
      "source": "admin",
      "id": "ca_...",
      "action": "grant",
      "amount": 100,
      "resulting_balance": 150,
      "admin_user_id": "u_...",
      "admin_email": "founder@nexcognit.com",
      "reason": "QA: Mode 2 validation",
      "is_self_grant": false,
      "is_cross_tenant": false,
      "reference": null,
      "created_at": "2026-04-19T01:00:00Z"
    },
    {
      "source": "system",
      "id": "ct_...",
      "action": "hold",
      "amount": 30,
      "resulting_balance": 120,
      "admin_user_id": null,
      "reason": null,
      "is_self_grant": false,
      "is_cross_tenant": false,
      "reference": "g_...",
      "created_at": "2026-04-19T01:02:00Z"
    }
  ],
  "next_cursor": "eyJvZmZzZXQiOjUwfQ==",
  "has_more": true
}
```

---

## `POST /api/v2/admin/users/{user_id}/credits/adjust`

Manual credit adjustment: grant / deduct / set.

### Request body

```json
{
  "action": "grant" | "deduct" | "set",
  "amount": 100,           // for grant/deduct: positive integer; for set: absolute target balance (≥ 0)
  "reason": "QA validation of Mode 2 generation",
  "confirm_large_grant": false
}
```

### Validation

| Rule | Error (422) |
|---|---|
| `action` not in enum | "action must be grant / deduct / set" |
| `amount` < 1 (for grant/deduct) | "amount must be >= 1" |
| `amount` < 0 (for set) | "set amount must be >= 0" |
| `reason` length < 10 | "reason must be at least 10 characters" |
| deduct that would cause negative balance | "deduct amount exceeds available balance" |
| grant or set where resulting delta > 100_000 AND `confirm_large_grant != true` | 409 with body `{"error":"confirmation_required","delta":500000}` |

### Success response (200)

```json
{
  "adjustment_id": "ca_...",
  "new_balance": 250,
  "is_self_grant": false,
  "is_cross_tenant": false
}
```

### Errors

| Condition | Status |
|---|---|
| Caller not internal admin | 403 |
| `CREDIT_ADMIN_PANEL_MODE = read_only` | 403 with body `{"error": "panel_is_read_only"}` |
| `CREDIT_ADMIN_PANEL_MODE = disabled` | 404 |
| User not found | 404 |

---

## `POST /api/v2/admin/users/{user_id}/holds/{hold_id}/release`

Manually release a stuck credit hold.

### Request body

```json
{ "reason": "Stuck hold from expired preview job VIS-187" }
```

### Response (200)

```json
{
  "adjustment_id": "ca_...",
  "hold_id": "h_...",
  "released_amount": 30,
  "new_available_balance": 150
}
```

### Errors

| Condition | Status |
|---|---|
| Hold not in `active` state | 409 with body `{"error":"hold_already_settled"}` |
| Hold in `active` state but not classified as stuck | 409 with body `{"error":"hold_not_stuck"}` — server-side defense; prevents frontend-bypass attempts on healthy holds |
| Hold not belonging to the specified user | 422 |
| Panel read-only | 403 |
| Panel disabled | 404 |

---

## `GET /api/v2/admin/users/{user_id}/role`

Read a user's internal-admin status.

### Response (200)

```json
{
  "user_id": "u_...",
  "is_internal_admin": true,
  "granted_at": "2026-03-15T00:00:00Z",
  "granted_by_user_id": null,
  "grant_reason": "Bootstrap founder admin"
}
```

---

## `POST /api/v2/admin/users/{user_id}/role/grant`

Elevate a user to internal admin. Requires an existing internal admin.

### Request body

```json
{ "reason": "Hire: promoting VP Engineering to internal admin" }
```

### Response (200)

```json
{ "admin_user_id": "au_...", "granted_at": "..." }
```

### Errors

| Condition | Status |
|---|---|
| Caller not internal admin | 403 |
| Target already is internal admin | 409 |
| Caller trying to grant self (bootstrap case) | 403 |
| Panel not in `full` mode | 403 (role grants are a write op) |

---

## `DELETE /api/v2/admin/users/{user_id}/role`

De-activate a user's internal-admin status (does not delete the row; sets `is_active = false`).

### Response (204)

---

## `GET /api/v2/config/panel-mode`

Public endpoint (authenticated only; any signed-in user can read) used by Layer 1 to determine current mode.

### Response (200)

```json
{ "mode": "full" | "read_only" | "disabled" }
```

When `CREDIT_ADMIN_PANEL_MODE = disabled`, this endpoint still returns `{"mode": "disabled"}` (not 404) — the frontend needs this signal to render a graceful "admin panel unavailable" state.

---

## Headers

| Header | Value | Notes |
|---|---|---|
| `Authorization: Bearer <jwt>` | required on every endpoint except `/api/v2/config/panel-mode` which is permissive | JWT must include `user_id` |
| `X-Request-Id` | required | propagates through structured logs; surfaced in error responses for support |

---

## Structured log events

Every admin write emits a loguru structured log line:

```
{"ts": "...", "level": "INFO", "event": "admin_credit_adjustment",
 "admin_user_id": "u_...", "target_user_id": "u_...", "action": "grant",
 "amount": 100, "reason": "...", "new_balance": 150,
 "is_self_grant": false, "is_cross_tenant": false,
 "request_id": "...", "tenant_id": "..."}
```

`is_self_grant = true` also emits `level: WARN` so it surfaces in alerting.
