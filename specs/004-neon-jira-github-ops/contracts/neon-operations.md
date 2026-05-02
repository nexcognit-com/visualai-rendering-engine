# Contract: Neon Operations (via MCP or REST)

**Feature**: 004-neon-jira-github-ops
**Consumer**: Engineers and Claude Code agents performing any Neon-database work.
**Authority**: this document + [spec.md FR-001..007](../spec.md) + `OPERATIONS.md` at repo root.

This contract enumerates what Neon operations are ALLOWED, the preferred tool for each, and what is DISALLOWED outside of a break-glass incident.

---

## Preferred tool ranking (top to bottom, per operation)

1. **Neon MCP server** — for interactive engineer+agent flows. Human-in-the-loop via Claude Code surface.
2. **Neon REST API** (`https://console.neon.tech/api/v2/…`) — for automated scripts (CI, scheduled jobs). Preferred when the operation runs unattended.
3. **Neon web console** — **DISALLOWED** for all operations except documented break-glass incidents.

---

## Allowed operations

| Operation | Preferred MCP tool | Notes |
|---|---|---|
| List projects | `mcp__claude_ai_Neon__list_projects` | Read-only. |
| Describe project | `mcp__claude_ai_Neon__describe_project` | Read-only. |
| List branches | `mcp__claude_ai_Neon__describe_branch` (on default) or `list_projects` then inspect | Read-only. |
| Create branch | `mcp__claude_ai_Neon__create_branch` | MUST be followed by a commit of a named SQL migration file if branch will receive schema changes. |
| Reset branch from parent | `mcp__claude_ai_Neon__reset_from_parent` | Destructive — lineage preserved for 7 days per FR-006. |
| Delete branch | `mcp__claude_ai_Neon__delete_branch` | Destructive — lineage preserved for 7 days. |
| Run SQL (read) | `mcp__claude_ai_Neon__run_sql` against read-only role | Preferred for debugging. |
| Run SQL (write) against DEV branch | `mcp__claude_ai_Neon__run_sql` | Allowed against `dev-*` / `pr-*` branches. |
| Run SQL (write) against MAIN | `mcp__claude_ai_Neon__prepare_database_migration` → apply-then-`complete_database_migration` | Two-step flow with diff preview mandatory. |
| Compare schemas | `mcp__claude_ai_Neon__compare_database_schema` | Required before any DESTRUCTIVE migration is promoted to `main`. |
| Explain SQL plan | `mcp__claude_ai_Neon__explain_sql_statement` | Performance tuning. |
| List slow queries | `mcp__claude_ai_Neon__list_slow_queries` | Observability. |
| Query tuning | `mcp__claude_ai_Neon__prepare_query_tuning` → `complete_query_tuning` | Interactive tuning flow. |
| Get connection string | `mcp__claude_ai_Neon__get_connection_string` | Output NEVER logged; secret. |
| Describe table schema | `mcp__claude_ai_Neon__describe_table_schema` | Read-only. |
| List database tables | `mcp__claude_ai_Neon__get_database_tables` | Read-only. |

---

## Disallowed operations (outside break-glass)

| Operation | Rationale |
|---|---|
| Any SQL run via the Neon web console | Bypasses migration file requirement (FR-002) and audit trail. |
| DROP / TRUNCATE run directly on `main` branch | Must first run on a dedicated branch and pass `compare_database_schema` (FR-003). |
| `set role` to a superuser mid-session | Defeats the read-only role separation (FR-004). |
| Creating a role or granting permissions via any path other than a committed migration file | Committed migrations are the sole source of truth for schema + permissions. |
| Storing a Neon connection string in a committed file | FR-007. Secrets live in env vars and GitHub Secrets only. |

---

## Required migration file convention

Every schema-changing migration MUST:

1. Live in `ops/neon/migrations/NNNN__description.sql` (sequential integer prefix, 4 digits, zero-padded).
2. Include a top-of-file comment block with: author, date, related Jira issue key (e.g., `VIS-42`), reversal statement.
3. Be committed to the repo BEFORE the migration is applied to any branch.
4. Be idempotent where reasonable (`CREATE TABLE IF NOT EXISTS`, `DROP ... IF EXISTS` in reverse scripts).

Example file naming:

```
ops/neon/migrations/
  0001__create-tenants-and-users.sql
  0002__add-credit_transactions.sql
  0003__add-generations-and-variations.sql
  0004__add-admin-credit-adjustments.sql
```

---

## Destructive-change flow (mandatory for DROP / TRUNCATE / column-type narrowing)

1. Write the migration SQL file; commit to branch via PR.
2. Open Neon MCP and run:
   - `create_branch` with name `migration-<migration-number>-<short-slug>`.
   - `prepare_database_migration` against that branch with the migration SQL.
3. Run `compare_database_schema` between the new branch and `main`; review output.
4. Get explicit human confirmation (not agent self-approval) before proceeding.
5. `complete_database_migration` to apply to `main`.
6. Log the Jira key + migration number in the PR's merge-commit message so Smart Commits transitions the ticket to `#done`.
7. Keep the migration branch for 7 days minimum before `delete_branch` (rollback window).

---

## Break-glass procedure

When a production incident requires an immediate change that can't wait for the MCP flow:

1. Perform the console edit.
2. Within 24 hours, file a Jira `Incident` ticket in the `VIS` project using the template at [`ops/neon/break-glass-incident-template.md`](../../../ops/neon/break-glass-incident-template.md) (file to be created by this feature's implementation).
3. Create a child Jira `Task` titled `Automate the <operation> via Neon MCP/API` so the same break-glass cannot happen twice.
4. Reference both issue keys in the next PR that implements the automation.

The weekly reconciliation query (see [research.md Q4](../research.md)) will flag any Neon audit-log console edit lacking a matching `Incident` ticket within 7 days — addressable by the founder or on-call.

---

## Agent-specific rules

When Claude Code (or another agent) performs Neon operations on behalf of an engineer:

- The agent MUST announce which MCP tool it is about to call before calling it.
- The agent MUST surface the connection-string path used (env var name, not the string itself) for debugging clarity.
- The agent MUST NOT infer or fabricate project IDs; always verify via `list_projects` first.
- The agent MUST present `compare_database_schema` output to the human before applying a destructive migration.
- The agent MUST refuse to run any operation disallowed above, with a link to this document.
