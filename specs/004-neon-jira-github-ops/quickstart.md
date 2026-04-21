# Quickstart: VisualAI Ops Setup from Scratch

**Feature**: 004-neon-jira-github-ops

End-to-end setup steps for a NexCognit admin spinning up (or auditing) the VisualAI operations stack: Neon DB, Jira project, GitHub organization + repos, and the canonical `OPERATIONS.md`. Execution target: within ~2 hours after the Step 1 Demo signs off.

---

## Prerequisites

1. Founder has accounts on:
   - Neon Cloud (or Neon project access via a team invite).
   - Atlassian Cloud with access to the NexCognit tenant.
   - GitHub with `admin:org` + `repo` scopes.
2. Claude Code is running in this repo with the Neon MCP, Atlassian MCP, and `gh` CLI available (verified via the session-start server list).
3. Step 1 demo sign-off has landed (founder or a designated reviewer has signed off on the Mode 2 end-to-end flow).

---

## 1. Neon project provisioning (≈ 15 min)

Follow [contracts/neon-operations.md](contracts/neon-operations.md) §"Allowed operations":

1. Via Claude Code, invoke `mcp__claude_ai_Neon__list_organizations` to confirm the target Neon org.
2. Invoke `mcp__claude_ai_Neon__create_project` with:
   - name: `visualai-prod`
   - region: `aws-us-east-1` (or closest to founder)
3. Record the project ID in `OPERATIONS.md` §"Neon Database".
4. Create a dedicated read-only role: commit a migration at `ops/neon/migrations/0001__create-roles.sql`:

   ```sql
   -- 0001__create-roles.sql
   -- Author: <you>  |  Date: 2026-04-19  |  Jira: VIS-###
   -- Reversal: DROP ROLE visualai_ro; DROP ROLE visualai_app;

   CREATE ROLE visualai_app NOLOGIN;
   CREATE ROLE visualai_ro NOLOGIN;
   GRANT CONNECT ON DATABASE neondb TO visualai_app, visualai_ro;
   GRANT USAGE ON SCHEMA public TO visualai_app, visualai_ro;
   GRANT SELECT ON ALL TABLES IN SCHEMA public TO visualai_ro;
   GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO visualai_app;
   ```
5. Apply via `mcp__claude_ai_Neon__prepare_database_migration` → `complete_database_migration` on `main`.
6. Capture two connection strings via `mcp__claude_ai_Neon__get_connection_string` (app role + read-only role). Store in GitHub Secrets and your local `.env.local`; NEVER in repo.

---

## 2. Jira project provisioning (≈ 15 min)

Follow [contracts/jira-sync.md](contracts/jira-sync.md):

1. Via Atlassian MCP, call `getAccessibleAtlassianResources`. Verify a site `nexcognit.atlassian.net` is listed; if not, see §"Reconciliation" in [research.md](research.md) §Q2.
2. Check whether project key `VIS` exists: `getVisibleJiraProjects`. If present, skip creation; otherwise create it via the Jira web UI (Atlassian MCP lacks a direct project-create tool) with:
   - Key: `VIS`
   - Name: `VisualAI`
   - Template: `Scrum` or `Kanban` (Scrum recommended)
   - Lead: founder
3. Add the custom field `spec_feature_dir` (Text - Short) to the Epic issue type; make it searchable.
4. For each existing SpecKit feature (001–004), run `/speckit-sync-jira` (or call the MCP tools by hand following the jira-sync contract) to create Epics and Stories with the correct custom-field value.
5. Append the resulting Jira Epic URL into each spec's header line:

   ```markdown
   **Jira Epic**: [VIS-### — Feature NNN — Title](https://nexcognit.atlassian.net/browse/VIS-###)
   ```

---

## 3. GitHub org + repo provisioning (≈ 45 min)

Follow [contracts/github-setup.md](contracts/github-setup.md) end-to-end. Key moments:

1. Confirm `nexcognit` org exists or create it (web UI if API is blocked on your plan).
2. Fork `harry0703/MoneyPrinterTurbo` into `nexcognit/visualai-rendering-engine` — preserving the fork parent is non-negotiable.
3. Create `nexcognit/visualai-frontend` and `nexcognit/visualai-orchestration` fresh.
4. Apply branch protection to each `main` using the helper in the github-setup contract.
5. Configure required status checks.
6. Commit initial `OPERATIONS.md` (canonical) in the rendering engine; commit stubs in the other two repos.
7. Run the smoke test (Step 9 of the github-setup contract): deliberately break a PR, verify `ops-guard` blocks it; fix, verify it passes.

---

## 4. Write `OPERATIONS.md` (canonical) (≈ 30 min)

1. Create `OPERATIONS.md` at the root of this repo with every section listed in [data-model.md](data-model.md) §"Artifact: `OPERATIONS.md`".
2. In each section, link to the corresponding contract in `specs/004-neon-jira-github-ops/contracts/`.
3. Add the stub `OPERATIONS.md` in `nexcognit/visualai-frontend` and `nexcognit/visualai-orchestration`, each one-line redirect.
4. Commit with:

   ```
   docs(ops): add canonical OPERATIONS.md (feature 004)  VIS-### #done
   ```

---

## 5. Install CI workflow (≈ 15 min)

1. Create `.github/workflows/ops-guard.yml` with the three checks from [research.md Q3](research.md):
   - Docs-update guard
   - Commit lint (Conventional Commits + VIS-### requirement unless `no-jira` label present)
   - `shellcheck` over `ops/**/*.sh`
2. Commit and push; open a test PR; confirm CI runs and the three checks show up.

---

## 6. New-engineer onboarding smoke test (≈ 4 hr, one-shot)

Once all 5 steps above land, run a self-simulated new-engineer onboarding:

1. On a fresh machine (or fresh user account), clone all three NexCognit repos.
2. Install Node 20, Python 3.11 + `uv`, FFmpeg, ImageMagick, Redis (Docker).
3. Authenticate `gh`, Atlassian MCP, Neon MCP.
4. Clone the `VIS` backlog; pick a `good-first-issue` Story.
5. Open a PR with `VIS-### #in-review` in the title.
6. Get the PR merged (with self-approval allowed).
7. Measure wall-clock time from step 1 to step 6. Target: ≤ 4 hours (SC-005).

---

## 7. Verify success criteria

Run through each success criterion in [spec.md §Success Criteria](spec.md):

| SC | Verification |
|---|---|
| SC-001 | Neon audit log of schema changes vs committed migration files: 100 % match |
| SC-002 | 0 data-integrity incidents attributable to manual console edits (90 days) |
| SC-003 | A `/speckit-specify` run creates a Jira Epic within 30 min of spec.md commit |
| SC-004 | A `/speckit-tasks` run creates Jira Tasks within 60 min |
| SC-005 | Onboarding time ≤ 4 hr (measured above) |
| SC-006 | Three repos with branch protection exist within 24 hr of Step 1 demo sign-off |
| SC-007 | No force-pushes to `main` across all repos (audit log) |
| SC-008 | 100 % of break-glass edits have Jira Incident within 24 hr |
| SC-009 | `ops-guard` blocks any PR that changes ops files without updating `OPERATIONS.md` |

---

## What to do if something fails mid-run

- **Neon MCP unreachable**: use Neon REST API directly; document the outage in `OPERATIONS.md` §"Break-glass" once resolved.
- **Atlassian MCP unreachable**: complete Jira setup via Atlassian web UI; create Epics/Stories by hand; do NOT block rendering-engine work on Jira availability.
- **`gh` rate-limited**: add 5-minute wait between batches of repo-setup calls; or run Steps 2–4 spread over a few hours.
- **Fork parent lost on `visualai-rendering-engine`**: recreate the repo as a fresh fork using the `gh repo fork` path in the github-setup contract; push your commits back on top of the upstream `main`.

Once all 7 steps above are green, the operations stack is live and ready for Step 2 of the 5-step build plan.
