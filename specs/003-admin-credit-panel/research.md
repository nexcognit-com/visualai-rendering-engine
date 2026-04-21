# Research: Admin Credit Panel

**Phase**: 0 — Research
**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

Four Phase-0 design decisions. Decision / Rationale / Alternatives.

---

## Q1. Internal-admin identification & authorization vs tenant-level admin

**Decision**: Internal admin is a **separate role**, stored in a dedicated table `admin_users` that is ORTHOGONAL to the `users.role` column (which holds tenant-level roles: Admin / Editor / Viewer per VisualAI Master Spec §6). A user being `users.role = Admin` for their tenant grants zero access to the credit panel. Access requires an entry in `admin_users` with `is_active = true`.

**Authorization check** (on every Layer 2 admin endpoint):

```
1. Validate JWT signature & expiry.
2. Extract user_id from claims.
3. SELECT 1 FROM admin_users WHERE user_id = $user_id AND is_active = true;
4. If 0 rows → 403 (or 404 when panel mode = "disabled").
5. If 1 row → proceed.
```

**Bootstrap**: the first `admin_users` row is seeded by SQL migration (founder's user_id). Subsequent additions are performed by an existing internal admin via a dedicated `POST /api/v2/admin/users/grant` endpoint that requires an existing internal admin and accepts `user_id` + `reason`.

**Rationale**:
- Two-table separation is unambiguous: nothing a tenant admin does can accidentally elevate them to internal admin. No role hierarchy confusion.
- Separate table also lets us audit admin-role grants independently (who was granted internal admin, when, by whom) with zero impact on the `users` table's shape.
- Bootstrap via seed migration is fine because spec 004's Neon governance requires every migration to be committed; the seed of admin user #0 is as auditable as any other schema change.

**Alternatives considered**:
- *Add `is_internal_admin` boolean to `users`*: rejected. Conflates role dimensions; a bug that updates `role` could accidentally touch internal-admin privileges. Two-table separation is the safer data model.
- *Enum on `users.role` with an "InternalAdmin" value*: rejected. Semantic overload of a field already used for tenant roles.
- *External auth service (Auth0 roles, Clerk organizations)*: rejected for v1. We already have Neon + a simple JWT issuer; adding an external identity service is disproportionate complexity for a ≤ 5-admin testing phase.

---

## Q2. Feature-flag implementation: env var, DB row, or config file?

**Decision**: Single **environment variable** `CREDIT_ADMIN_PANEL_MODE` on the Layer 2 service, with three permitted values: `full`, `read_only`, `disabled`. Layer 1 reads this via a minimal `/api/v2/config/panel-mode` endpoint on Layer 2 and caches the result for 60 seconds in TanStack Query.

**Behavior matrix** (also in [contracts/feature-flag-behavior.md](contracts/feature-flag-behavior.md)):

| Mode | Layer 1 `/admin/credits` route | Layer 2 read endpoints | Layer 2 write endpoints | Unauthorized user response |
|---|---|---|---|---|
| `full` | serves (or 403 for non-admin) | 200 | 200 | 403 |
| `read_only` | serves with a locked-write banner | 200 | 403 "Mode is read-only" | 403 |
| `disabled` | Next.js `middleware.ts` returns 404 (not found, not forbidden) | 404 | 404 | 404 |

**404 vs 403 distinction** for the `disabled` mode is the critical privacy property (FR-002, SC-005): a 403 leaks the route's existence; a 404 suggests no admin panel was ever deployed.

**Rationale**:
- Env var is immutable during a process's lifetime, so there's no surprise mid-request flag flip. Switching modes is a restart (or a modern orchestrator's rolling config-change) and is < 5 min wall clock (SC-006).
- Env var is in ONE place (Layer 2 service configuration) — Layer 1 only learns about it via a read-only endpoint, so there's no deploy-time coupling between the two repos.
- 60-second cache on Layer 1 is safe because mode flips are a deliberate operational action, not a per-request concern. Worst case: an admin sees stale UI for a minute before the banner appears.
- Reading from a DB row would invite the question "what happens if the DB is down?"; env var avoids that failure mode entirely.

**Alternatives considered**:
- *DB row in `app_config` table*: rejected. Adds a dependency on the DB for a trivial setting and introduces a race-between-read-and-write window at flag-flip time.
- *Config file committed to repo*: rejected. Mode flip would require a deploy, breaking SC-006's "< 5 minutes" target.
- *Feature-flag service (LaunchDarkly, Flagsmith)*: rejected for v1. Overkill for a 3-value flag that flips twice in the product lifetime.

---

## Q3. Audit-entry immutability at the DB level

**Decision**: Enforce immutability via three complementary mechanisms, none of which compromise legitimate migrations:

1. **DB-level privilege separation**: the `visualai_app` role has `INSERT` on `credit_transactions` and `credit_adjustments` but NO `UPDATE` or `DELETE` grant. Only the DB owner role (used only during migrations) has those privileges.
2. **Trigger-based row-write enforcement**: a `BEFORE UPDATE OR DELETE` trigger on both audit tables raises an exception. Belt-and-suspenders for the case where a future migration forgets to re-revoke a grant.
3. **Append-only pattern in the service layer**: SQLAlchemy models for `CreditAdjustment` and `CreditTransaction` are declared with `__table_args__ = {"info": {"append_only": True}}` and a service-layer guard raises on any attempted session.delete() or session.merge() of those models.

Legitimate corrections to incorrect historical data: done by INSERT of an offsetting entry with `reason` noting "correction for adjustment X" — never by UPDATE.

**Rationale**:
- Belt-and-suspenders: if an agent (or engineer) accidentally writes code that would mutate an audit row, three layers independently block it. Only one layer has to succeed to protect the ledger.
- Privilege separation is standard PostgreSQL defense in depth. Trigger is the defense if someone grants UPDATE during a future migration and forgets to revoke.
- Offsetting-entry corrections are how real financial ledgers work (double-entry bookkeeping in spirit if not in form). Matches industry expectations.
- Migrations themselves aren't blocked — they run as the DB owner, not `visualai_app`. Spec 004's Neon governance already ensures migrations are committed, diffed, and applied through the MCP flow, so "migration touches ledger" is a visible event.

**Alternatives considered**:
- *Blockchain / cryptographic hash chain*: rejected. Massive overkill for a testing-phase tool; the audit trail is not adversarial.
- *Trigger only, no privilege separation*: rejected. Triggers can be dropped by a superuser; privilege separation is the stronger foundation.
- *No enforcement, trust code review*: rejected. FR-019 + SC-003 make immutability load-bearing; humans slip.

---

## Q4. Concurrent admin writes to the same user

**Decision**: Use **optimistic append-only semantics**: every credit-affecting write is a single INSERT into `credit_adjustments` (for manual ops) or `credit_transactions` (for system ops). No row-level locking, no SELECT-FOR-UPDATE on the `users` row. Balance is computed as the running sum of all ledger events (not cached on the user row).

Two admins granting 100 credits each to the same user in the same second produce two INSERTs in whatever order the DB accepts them; both are visible, both audit-logged, and the user's balance is `old + 100 + 100 = +200` regardless of interleaving.

**Exception**: credit HOLDS and DEBITS against an existing hold use `UPDATE credit_holds SET state=... WHERE id=? AND state=?` — single-row compare-and-swap, which gives exactly-once semantics without distributed locks. See spec 002's credit state machine for the pattern.

**User balance invariant** enforced as a deferred DB check constraint:

```sql
CHECK (
  (SELECT COALESCE(SUM(amount), 0) FROM credit_transactions ct WHERE ct.user_id = users.id)
  +
  (SELECT COALESCE(SUM(amount), 0) FROM credit_adjustments ca WHERE ca.target_user_id = users.id)
  >= 0
)
```

(Expressed as a trigger-based assertion rather than a raw CHECK because PostgreSQL CHECK constraints can't directly reference other tables. Same practical effect.)

**Rationale**:
- Append-only ledgers with computed balances are the canonical accounting pattern — no lost updates, natural concurrency, complete audit trail.
- Deriving balance at read time is slightly more expensive than reading a cached column, but at the scale of this feature (≤ 50 test users) the cost is negligible. At post-launch scale, balance can be materialized via a trigger-maintained summary table without changing the ledger semantics.
- Preventing negative balance via a trigger check gives server-side safety (FR-012, SC-008) that is impossible to bypass from the client.
- Avoids the distributed-lock anti-pattern entirely.

**Alternatives considered**:
- *Cache balance in `users.credit_balance` + row-level lock on write*: rejected. Invites cache-incoherence bugs and makes the ledger harder to reason about.
- *Serializable transaction isolation on every write*: rejected. Tanks throughput at scale; appends are naturally isolated.
- *Single-threaded admin writer*: rejected. Artificial bottleneck.

---

## Summary

All four Phase-0 questions resolved. No unresolved NEEDS CLARIFICATION items remain. Key design choices carried into Phase 1 contracts:

- **`admin_users` is its own table**, orthogonal to `users.role`. Internal admin ≠ tenant admin.
- **Env-var flag `CREDIT_ADMIN_PANEL_MODE`** on Layer 2; cached 60 s on Layer 1. `disabled` returns 404 (not 403).
- **Immutability = privilege separation + triggers + append-only service models** (three layers of defense).
- **Balance computed from append-only ledger**; no locks; a trigger-based non-negative-balance assertion prevents server-side bypass.
