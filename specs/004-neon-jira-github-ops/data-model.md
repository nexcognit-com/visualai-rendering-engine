# Data Model: Neon / Jira / GitHub Operations Policy

**Phase**: 1 — Design & Contracts
**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

"Data model" for this feature is an inventory of **artifacts across vendor systems** plus the in-repo documents that describe them. No relational DB schema is introduced here (Neon schema itself is owned by future feature specs — e.g., the credit-ledger core spec).

---

## Artifact: Neon Project

**Owner**: NexCognit team via Neon Cloud.
**Managed via**: Neon MCP (`mcp__claude_ai_Neon__*`) or Neon REST API.

| Field | Value / Rule | Source of truth |
|---|---|---|
| Project ID | Auto-generated on create; recorded in `OPERATIONS.md` | Neon |
| Project name | `visualai-prod` (single project; environments = branches) | This spec |
| Primary region | Closest to founder's location at setup (e.g., `aws-us-east-1`) | Operator decision at setup |
| Branches | `main` (production-equivalent), `staging`, `dev-<handle>` per engineer, `pr-<number>` per open PR (auto-created, auto-deleted) | Neon |
| Roles | `visualai_app` (read/write), `visualai_ro` (read-only for debugging) | Migration SQL files |
| Connection strings | Per-environment, stored in per-repo GitHub Actions secrets and in each engineer's `.env.local` (NEVER in repo) | GitHub Secrets + local files |

---

## Artifact: Jira Project

**Owner**: NexCognit team via Atlassian Cloud.
**Managed via**: Atlassian MCP (`mcp__claude_ai_Atlassian__*`).

| Field | Value / Rule |
|---|---|
| Site URL | `nexcognit.atlassian.net` |
| Project key | `VIS` |
| Project name | `VisualAI` |
| Project lead | Founder (initial); reassigned when PM joins |
| Default assignee | Project lead |
| Issue types | Epic, Story, Task, Bug, Incident |
| Workflows | default Jira Cloud "Software" workflow: `To Do → In Progress → In Review → Done`; Incident adds `Open → Investigating → Resolved → Closed` |
| Custom fields | `spec_feature_dir` (text, searchable) — attached to Epics only; used to link Jira Epic ↔ SpecKit feature directory |

### Issue hierarchy & field conventions

| Issue type | Parent | Summary format | Labels | Custom fields |
|---|---|---|---|---|
| Epic | — | `Feature NNN — <Feature title>` | `speckit`, `feature-NNN` | `spec_feature_dir=NNN-<short-name>` |
| Story | Epic | `US<k> — <User story title>` | `priority-P<k>`, `feature-NNN` | — |
| Task | Story OR Epic | One-liner summarizing the SpecKit task | `spec-task:T###`, `feature-NNN` | — |
| Bug | Epic OR Story | `Bug: <short summary>` | `bug`, `feature-NNN` | — |
| Incident | Epic (`OPS`) | `Break-glass: <system>/<operation>` | `incident`, `break-glass` | — |

### State transitions via Smart Commits

| PR action | Commit/PR text pattern | Jira transition |
|---|---|---|
| Open PR linked to issue | Title contains `VIS-123 #in-review` | Task → In Review |
| Merge PR | Merge-commit subject contains `VIS-123 #done` | Task → Done |
| Comment on issue from PR | `VIS-123 #comment <text>` | Comment appended |

---

## Artifact: GitHub Organization

**Owner**: NexCognit team via GitHub Cloud.
**Managed via**: `gh` CLI + GitHub REST/GraphQL.

| Field | Value / Rule |
|---|---|
| Organization slug | `nexcognit` (all lowercase) |
| Display name | `NexCognit` |
| Owner | Founder |
| Initial members | Founder; expanded when hire #2 joins |
| Default repo visibility | `private` |
| 2FA requirement | Enforced for all members |
| Base permission | Read (members get write via team membership, not org-level) |

---

## Artifact: GitHub Repository (three instances)

| Field | `visualai-rendering-engine` | `visualai-frontend` | `visualai-orchestration` |
|---|---|---|---|
| Slug | `visualai-rendering-engine` | `visualai-frontend` | `visualai-orchestration` |
| Visibility | `private` | `private` | `private` |
| Fork parent | `harry0703/MoneyPrinterTurbo` | none | none |
| Default branch | `main` | `main` | `main` |
| Branch protection (`main`) | see below | see below | see below |
| Required status checks | this repo's existing test suite + `ops-guard` | `lint`, `typecheck`, `unit`, `e2e-smoke` (landed in Step 1) | (none until Step 2 delivers an orchestration codebase) |
| CODEOWNERS | `* @founder` initially; expanded per-area when team grows | same | same |
| `README.md` | "Layer 3 rendering engine" + SpecKit link | "Layer 1 VisualAI frontend" + SpecKit link | "Layer 2 orchestration API (empty scaffold, see spec YYY-orchestration)" |
| `CLAUDE.md` | per-repo agent guidance | per-repo agent guidance | per-repo agent guidance |
| `OPERATIONS.md` | CANONICAL (full content) | STUB (one line redirecting to canonical) | STUB |

### Branch-protection rule (applied identically to each repo's `main`)

| Rule | Value |
|---|---|
| Require pull request | yes |
| Required approving reviews | 1 — relaxed to "allow self-approval with admin override" during solo-founder phase |
| Dismiss stale reviews on push | yes |
| Require status checks to pass | yes |
| Require branches to be up to date before merging | yes |
| Require linear history | yes |
| Require conversation resolution before merging | yes |
| Allow force pushes | no |
| Allow deletions | no |
| Restrict pushes (CODEOWNERS) | yes |

---

## Artifact: `OPERATIONS.md` (canonical, at repo root)

**Owner**: this repo (`visualai-rendering-engine`).
**Purpose**: single source of truth for all ops policy.

### Required section schema

| Section | Content |
|---|---|
| `# OPERATIONS — VisualAI` | Title + short purpose statement |
| `## Audience` | Internal NexCognit engineering + agents acting on their behalf |
| `## Neon Database` | How to create/modify schema via MCP/API, break-glass rules, migration conventions |
| `## Jira (VIS project)` | Epic/Story/Task mapping to SpecKit, Smart Commits syntax, project URL |
| `## GitHub (nexcognit/ org)` | Repo list + links, branch-protection rules, CODEOWNERS convention |
| `## Onboarding` | Step-by-step for a new engineer; links to `ops/onboarding/new-engineer-checklist.md` |
| `## Break-glass incident procedure` | When allowed, template link, follow-up requirements |
| `## Credentials` | Where each vendor's secrets live; never in repo |
| `## Change control for this document` | SC-009 rule: update this file in the same PR as any process change |

---

## Artifact: Break-Glass Incident Record

**Owner**: Jira `VIS` project, issue type `Incident`.
**Template**: [`ops/neon/break-glass-incident-template.md`](../../ops/neon/break-glass-incident-template.md) (file created by this feature).

### Required fields

| Field | Notes |
|---|---|
| Title | `Break-glass: neon-console/<operation>` |
| Reporter | the engineer who performed the action |
| Reported at | ISO 8601 timestamp, manual edit OK |
| What was changed | Free text describing the exact change |
| Why | Why automation was insufficient |
| Branch created? | Yes / No / N/A |
| Users affected | Count of affected users; zero if a non-production edit |
| Automation follow-up | Linked child Task in Jira (required) |

---

## Artifact: SpecKit ↔ Jira Sync Records (virtual)

No new in-repo file stores these; they are embedded in SpecKit documents as optional header lines.

### Header convention added to every `spec.md` after this feature ships

```markdown
**Feature Branch**: `NNN-short-name`
**Created**: YYYY-MM-DD
**Jira Epic**: [VIS-### — Feature NNN — Title](https://nexcognit.atlassian.net/browse/VIS-###)
**Status**: Draft | In Review | Accepted
```

When the Jira Epic doesn't exist yet, the line reads `**Jira Epic**: (not yet synced)`.

---

## Relationships diagram

```
SpecKit feature dir (specs/NNN-short-name/)
│
├── spec.md ──────► Jira Epic (VIS-###, custom field spec_feature_dir=NNN-short-name)
│    └── User Story K ──► Jira Story (child of Epic, labels: priority-PK, feature-NNN)
│
├── tasks.md ─────► Jira Task (child of Story or Epic, label: spec-task:T###)
│
└── GitHub PR ────► commit msg has "VIS-### #done" ──► Jira auto-transition

Neon Project (visualai-prod)
├── main branch
├── staging branch
└── dev-<handle> / pr-<number> branches

GitHub Org (nexcognit)
├── visualai-rendering-engine   (fork of harry0703/MoneyPrinterTurbo)
├── visualai-frontend           (Next.js)
└── visualai-orchestration      (empty until Step 2)

OPERATIONS.md (canonical in rendering-engine) ←─── stubs redirect here from the other two repos
```

---

## Validation rules

- **Single-source spelling**: `nexcognit` / `NexCognit` is the only accepted spelling across all artifacts. Any "NextCognit" occurrence is a setup-time bug to reconcile.
- **Connection-string secrecy**: Neon connection strings appear in exactly two places — GitHub Actions environment secrets and each engineer's local `.env.local`. They MUST NOT appear in any committed file.
- **Smart Commits authority**: the only way a Jira Task auto-transitions is via a PR commit/title containing the `VIS-### #in-review` or `VIS-### #done` pattern. Manual transitions are allowed but the audit trail loses the PR link.
- **Break-glass incident invariant**: for every row in Neon's audit log that corresponds to a console-originated edit in the last 7 days, there MUST be a Jira `Incident` ticket in the `VIS` project with a creation time within 24 hours of the edit. Verified by the weekly reconciliation query.
- **Branch-protection uniformity**: the three repos apply identical branch-protection rules. A PR that modifies branch-protection config on any repo MUST also modify the other two in the same PR to keep them in sync.
