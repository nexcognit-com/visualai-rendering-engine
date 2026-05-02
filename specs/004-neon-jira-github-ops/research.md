# Research: Neon / Jira / GitHub Operations Policy

**Phase**: 0 — Research
**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

Four design decisions that shape Phase 1. Decision / Rationale / Alternatives.

---

## Q1. Canonical SpecKit → Jira sync structure

**Decision**: Each SpecKit feature directory (e.g., `specs/002-video-duration-variations/`) maps 1:1 to a Jira **Epic**. Each P1/P2/P3 user story in the feature's `spec.md` maps to a Jira **Story** under that Epic. Each row in the feature's `tasks.md` maps to a Jira **Task** under the Story it implements (or directly under the Epic if the task is setup/foundational/polish). The linkage is stored in two places:

1. A Jira **custom field** `spec_feature_dir` on Epics (indexed, searchable).
2. A Jira **label** `spec-task:T007` on Tasks (preserves the SpecKit Task ID for PR title matching).

PR-to-Jira state transitions use **Smart Commits** syntax — the PR title contains `VIS-123 #in-review` on open and Jira's built-in commit listener transitions the issue. On merge the commit message contains `VIS-123 #done` and Jira closes the issue.

**Rationale**:
- Custom field on Epic is the fastest query path ("show me all work on feature 002"); label on Task is the cheapest PR-side identifier that doesn't require a full issue lookup.
- Smart Commits is a built-in Atlassian feature — no custom webhook to maintain. Works identically for GitHub and the Atlassian MCP.
- The Jira project key `VIS` (for VisualAI) becomes the stable prefix across all issue keys. Short keys are easier to type into PR titles than full URLs.
- The Epic → Story → Task three-level hierarchy matches Jira Cloud's built-in issue-type scheme; no customization burden.

**Alternatives considered**:
- *Put the SpecKit feature directory in the Epic summary*: rejected. Summaries are user-facing text that often gets edited; a custom field is stable.
- *One Jira issue per SpecKit task only (no Epic/Story)*: rejected. Flat lists don't support progress rollup and executive reporting.
- *Build a custom GitHub Actions workflow that calls Jira API on PR events*: rejected for v1. Smart Commits is zero-maintenance; a custom workflow is deferred to the future if Smart Commits proves insufficient (e.g., if we want auto-release-notes).

---

## Q2. Naming and reconciliation of NexCognit org across three vendors

**Decision**: Canonical brand spelling is **NexCognit** (one lowercase `x`, one capital `C`). Three vendor identifiers derived:

| Vendor | Identifier | Value | Why |
|---|---|---|---|
| GitHub | organization slug | `nexcognit` | all lowercase per GitHub convention |
| Atlassian | site URL | `nexcognit.atlassian.net` | if different today, migrate |
| Atlassian | Jira project key | `VIS` | VisualAI product; short, typeable |
| Neon | project name | `visualai-prod` (and `visualai-staging`, `visualai-dev`) | product-level, environment-scoped |

Reconciliation process when setup starts:

1. Run `gh api orgs/nexcognit` — if 200, org exists and we confirm the founder is Owner. If 404, create: `gh api orgs --method POST -f login=nexcognit`.
2. Run `gh api orgs/nextcognit` (legacy typo check) — if 200, raise an incident ticket and plan a rename (`gh api orgs/nextcognit --method PATCH -f new_login=nexcognit`).
3. Via Atlassian MCP `getAccessibleAtlassianResources`, enumerate the sites visible to the authenticated user. If any includes "NextCognit" or "Nex Cognit" variations, flag them in the onboarding doc and pick the canonical one. No automated rename for Atlassian (Cloud doesn't support silent site-URL rename); manual consolidation via Atlassian support if necessary.
4. Neon project names are free-text; create fresh with the canonical spelling.

**Rationale**:
- Consistency across three vendors is the single biggest risk of "I thought we were on X but the URL says Y" confusion. Pinning the spelling + the slug formula removes ambiguity.
- GitHub org rename is supported (the `gh api PATCH` call) and automatic — taking the fast path when available.
- Atlassian site rename is NOT supported on Cloud; the manual-consolidation note sets realistic expectations.

**Alternatives considered**:
- *Use "VisualAI" as the org name*: rejected. The company is NexCognit; VisualAI is a product. Keeps future multi-product flexibility.
- *Use the original "NextCognit" misspelling if it's already taken by the user*: rejected. Typos calcify into permanent confusion; correct once, early.
- *One Neon project with many branches vs per-environment projects*: hybrid — one Neon project, per-environment branches. Simpler billing and one connection-string schema with per-env credentials.

---

## Q3. Minimum-noise CI workflow for SC-009 ("OPERATIONS.md updates with process changes")

**Decision**: A single workflow `.github/workflows/ops-guard.yml` triggered on PR open/sync. It does three things, each cheap:

1. **Docs-update guard**: if `git diff --name-only origin/main...HEAD` includes any of `ops/**`, `.github/workflows/**`, `.specify/memory/constitution.md`, `.specify/templates/**`, or this feature's `spec.md` / `plan.md`, then `OPERATIONS.md` MUST also appear in the diff. Otherwise the check fails with a message pointing at SC-009 and this file.
2. **Commit lint**: run `commitlint` with the Conventional Commits config against each commit in the PR. Fail the PR if any subject violates.
3. **Shellcheck**: run `shellcheck` on every `*.sh` under `ops/`.

Exceptions: docs-update guard is bypassed if the PR label `ops-docs-exempt` is present — used for genuine cases like "reformat whitespace across all ops files."

**Rationale**:
- Cheap to run (≤ 30 s total). Fast feedback.
- Three checks cover the three failure modes we care about: docs drift, commit hygiene, and broken ops scripts.
- Label-based exception is one line of workflow YAML and requires a human decision (adding a label) before merge — auditable.
- Not a "big DevOps pipeline" — just a governance tripwire. Full CI (tests, type-check, build) lives per-repo, not here.

**Alternatives considered**:
- *Enforce via commit hook on developer machines*: rejected. Hooks are opt-in and bypassable. CI is authoritative.
- *Require an `OPERATIONS.md` "last-updated" timestamp comment*: rejected. Brittle; breaks on unrelated edits.
- *No CI check — trust reviewers*: rejected. SC-009 is a measurable success criterion; humans forget.

---

## Q4. Break-glass procedure for manual Neon console edits

**Decision**: Define a Jira issue type "Incident" in the `VIS` project with a required template `ops/neon/break-glass-incident-template.md`. When an engineer performs a direct Neon console edit, they MUST within 24 hours (FR-005, SC-008):

1. File an Incident ticket in Jira using the Atlassian MCP with the template pre-populated.
2. Include: exact change made, reason, user affected (if any), time applied, Neon branch name if one was cut, and a follow-up task linking to the automated-replacement PR.
3. Create a follow-up Task linked as a child: "Automate the `<operation>` via Neon MCP/API" so the break-glass can't happen twice for the same operation.

Auditing: a scheduled Jira JQL query runs weekly: `project = VIS AND issuetype = Incident AND created > -7d AND cf[spec_feature_dir] = "004-neon-jira-github-ops"`. Count vs Neon's audit log (via `describe_project` or Neon's own UI) — any mismatch is a missing Jira ticket and triggers a reminder.

**Rationale**:
- Zero-enforcement policies don't survive contact with a weekend production fire. Making the break-glass path a 2-minute template reduces friction to compliance.
- The scheduled reconciliation query catches the cases where an engineer forgot — the feedback loop closes within 7 days.
- Follow-up Task as a child means the same break-glass can't happen twice; each one automates itself out of existence over time.

**Alternatives considered**:
- *Block the Neon console via an SSO policy restricting role permissions*: rejected for v1. Too heavy-handed; the console has legitimate read-only uses (dashboards). Revisit if compliance demands (SOC-2).
- *No break-glass tracking — just trust*: rejected. FR-005 + SC-008 are explicit spec commitments.
- *File the Incident via GitHub Issue instead of Jira*: rejected. Jira is the canonical backlog per this spec; splitting governance across two trackers defeats US2.

---

## Summary

All four Phase-0 questions resolved. No unresolved NEEDS CLARIFICATION items remain. Key design choices carried into Phase 1 contracts:

- **Jira project key is `VIS`**; custom field `spec_feature_dir` on Epics; label `spec-task:T###` on Tasks; Smart Commits for state transitions.
- **Org spelling is `nexcognit`**; reconcile any "NextCognit" variant aggressively; GitHub org rename automated; Atlassian site rename manual.
- **CI tripwire workflow `ops-guard.yml`**: docs-update guard + commitlint + shellcheck; label-based exception; not a full CI.
- **Break-glass = Jira Incident + follow-up Task + weekly reconciliation query**.
