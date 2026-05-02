# Quickstart: Admin Credit Panel

**Feature**: 003-admin-credit-panel

End-to-end local run of the panel once Step 2 of the 5-step build plan has shipped Layer 2. Target duration: **≈ 45 minutes** from clean checkouts to a working panel with a grant flow demonstrated.

---

## Prerequisites

- All spec 001 work (design tokens + component catalog) has landed in `../visualai-frontend/`.
- All spec 004 work has landed: Neon project exists, Jira project exists, GitHub repos exist.
- Layer 2 orchestration repo exists at `../visualai-orchestration/` with the credit-ledger core endpoints (hold/debit/release) functional.
- Neon branches: one `main` (production-equivalent), one dev branch per engineer.
- Local environment variables set:
  - `DATABASE_URL=postgresql://...` (dev branch connection string)
  - `JWT_SECRET=...` (shared with Layer 1)
  - `CREDIT_ADMIN_PANEL_MODE=full`

---

## 1. Apply Neon migrations (≈ 5 min)

From `../visualai-orchestration/`:

```sh
# Create per-engineer dev branch on Neon (via MCP per spec 004)
# Claude: mcp__claude_ai_Neon__create_branch with name "dev-<handle>"

# Apply migrations 0010–0012 via Neon MCP (0013 optional — support read role; see tasks T072)
# 0010__admin_users.sql
# 0011__credit_adjustments.sql
# 0012__audit_view_and_triggers.sql
```

Migrations follow spec 004's naming (`ops/neon/migrations/NNNN__*.sql`). After applying:

```sh
psql $DATABASE_URL -c "\d admin_users"
psql $DATABASE_URL -c "\d credit_adjustments"
psql $DATABASE_URL -c "\d+ audit_entries"     # the VIEW
```

---

## 2. Seed bootstrap internal admin (≈ 2 min)

```sh
psql $DATABASE_URL <<'SQL'
INSERT INTO users (id, email, role, tenant_id)
VALUES (gen_random_uuid(), 'founder@nexcognit.com', 'Admin', '<tenant_id>')
RETURNING id;
-- note the returned id as $FOUNDER_USER_ID

INSERT INTO admin_users (user_id, is_active, granted_by, grant_reason)
VALUES ('$FOUNDER_USER_ID', true, NULL, 'Bootstrap founder admin');
SQL
```

---

## 3. Start Layer 2 (≈ 5 min)

```sh
cd ../visualai-orchestration
export CREDIT_ADMIN_PANEL_MODE=full
uv run uvicorn app.main:app --reload --port 9090
```

Verify:

```sh
curl -s http://localhost:9090/api/v2/config/panel-mode | jq
# Expected: {"mode": "full"}
```

---

## 4. Start Layer 1 frontend (≈ 5 min)

```sh
cd ../visualai-frontend
pnpm dev
```

Open http://localhost:3000 and sign in as the bootstrap founder email.

---

## 5. Walk the admin panel (≈ 10 min)

1. Navigate to http://localhost:3000/admin/credits — the panel loads (you're an internal admin).
2. Search for a test user by email or ID in `<UserSearch />`.
3. If no test users exist, sign up one via the regular VisualAI sign-up flow. Verify it has **0 credits** on arrival (SC-001).
4. Select the test user from the search results.
5. `<BalancePanel />` shows balance 0, no active holds.
6. Click **Grant**, enter `100` credits with reason "QA quickstart validation."
7. Click **Apply**. Verify:
   - Success toast.
   - Balance now 150.
   - `<AuditLogTable />` shows a new row: source=admin, action=grant, amount=+100, actor=you.

---

## 6. Exercise edge cases (≈ 10 min)

### Self-grant

1. Navigate to `/admin/credits/user/<your-own-user-id>`.
2. Attempt to grant yourself 50 credits.
3. Verify the form shows a red self-grant warning before submit.
4. Submit.
5. Verify the resulting audit row has the `self_grant` flag set and renders with a warning icon.

### Cross-tenant

1. If a test user exists in a different tenant, select them.
2. Grant credits.
3. Verify the form shows an orange cross-tenant notice.
4. Verify the audit row has `is_cross_tenant = true` and the warning icon.

### Large grant requires second confirmation

1. Attempt to grant 500,000 credits.
2. First submit returns a "second confirmation" dialog.
3. Check the "I understand" checkbox; submit.
4. Verify success; balance changes by 500,000.

### Insufficient-credits invariant

1. Attempt to deduct an amount larger than the target user's balance.
2. Verify the form rejects with "Deduct exceeds available balance."
3. Verify no row was written to `credit_adjustments` (query directly via MCP or `psql`).

### Release stuck hold

1. Use Layer 3 (or mocks) to create a generation job that produces a hold (e.g., via spec 002's preview-gate flow).
2. Expire the job manually (or wait 24 h with a shortened `TEST_EXPIRY_OVERRIDE_MINUTES`).
3. Visit the admin panel; the stuck hold appears in `<HoldReleaseList />`.
4. Click **Release**; enter reason.
5. Verify hold disappears and available balance increases by the held amount.

---

## 7. Test feature-flag transitions (≈ 5 min)

### Flip to `read_only`

```sh
# Stop Layer 2
# Restart with:
export CREDIT_ADMIN_PANEL_MODE=read_only
uv run uvicorn app.main:app --reload --port 9090
```

In the browser:

1. Refresh `/admin/credits`.
2. Wait for the mode cache to refresh (up to 60 s) OR do a hard refresh.
3. Verify `<ModeBanner mode="read_only" />` appears at the top.
4. Verify Grant / Deduct / Set / Release buttons are disabled with tooltips.
5. Verify `<AuditLogTable />` still works.

### Flip to `disabled`

```sh
export CREDIT_ADMIN_PANEL_MODE=disabled
uv run uvicorn app.main:app --reload --port 9090
```

1. Refresh `/admin/credits`.
2. Verify 404 (via Next.js middleware rewrite).
3. Directly hit `curl -s http://localhost:9090/api/v2/admin/users/search?q=test` — returns 404.
4. Hit `curl -s http://localhost:9090/api/v2/config/panel-mode` — returns 200 with `{"mode":"disabled"}`.

---

## 8. Verify Success Criteria (≈ 10 min)

| SC | Validation |
|---|---|
| SC-001 | Sign up a new test user; verify 0 balance, empty ledger |
| SC-002 | Time yourself: search → grant. Target: ≤ 60 s (after familiarity) |
| SC-003 | Run `pytest tests/services/test_ledger_invariant.py` — passes |
| SC-004 | Run the balance-invariant SQL: every user's `user_credit_balance(id) >= 0` |
| SC-005 | Automated access test from [contracts/feature-flag-behavior.md](contracts/feature-flag-behavior.md) §"Validation tests" — all 3 modes behave correctly |
| SC-006 | Time the `full → read_only` flip: target ≤ 5 min |
| SC-007 | Run onboarding end-to-end; target ≤ 3 min from new-user sign-up to first generation |
| SC-008 | Negative-balance test: attempt deduct that would go negative; DB trigger rejects; verify no row written |

---

## 9. Failure modes and debugging

| Symptom | Likely cause | Fix |
|---|---|---|
| 403 on every `/admin/*` call | Caller's user not in `admin_users` | Verify seed ran; check `is_active = true` |
| `/admin/credits` renders blank | Frontend can't reach Layer 2 at :9090 | Check CORS + Layer 2 health |
| Grant succeeds but balance doesn't change in UI | TanStack Query cache stale | Click refresh or wait 5 s |
| DB rejects every adjustment with "non-negative balance violation" | The trigger is enforcing; check the target's current balance | Review the attempted amount; fix the input |
| Boot error "invalid CREDIT_ADMIN_PANEL_MODE" | Env var unset or mistyped | Set to `full`, `read_only`, or `disabled` |
| 404 on `/admin/credits` even in `full` mode | Middleware cached `disabled` from a prior session | Clear browser cache; hard reload |

---

## Sunset validation (simulated Step 4 completion)

Once Stripe webhooks ship (Step 4 of the 5-step build plan):

1. Flip `full` → `read_only` via the runbook above.
2. Verify historical audit entries remain fully viewable.
3. Stripe-driven credit grants appear in the `credit_transactions` ledger; the `<AuditLogTable />` shows them with `source=system` alongside historical admin entries.
4. Confirm that no internal admin still has a business need to write manually. If they do, the flag is reversible (flip back to `full` for the duration of the emergency).
5. Six months later, optionally flip to `disabled` if the panel is no longer needed. Until then, `read_only` remains the steady state.
