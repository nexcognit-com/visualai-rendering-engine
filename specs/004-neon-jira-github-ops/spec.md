# Feature Specification: Neon Database, Jira Project, and GitHub Repository Operations Policy

**Feature Branch**: `004-neon-jira-github-ops`
**Created**: 2026-04-19
**Status**: Draft
**Input**: User description: "For all work related to Neon database, you will use your API and MCP to set the database. You will also create a Jira project under NextCognit and you will create a GitHub repo under NextCognit after you finish the first stage of the project."

## Overview

This specification sets governance rules and concrete deliverables for how VisualAI's engineering infrastructure is provisioned and maintained. It is an **operations policy + one-time setup plan**, not a product feature. It defines:

1. **Neon database governance** — every schema change, branch, role grant, migration, and read of production Neon resources MUST be performed through the Neon API or the Neon MCP server. Manual Neon console edits are disallowed outside of documented break-glass incidents.
2. **Jira project setup** — a single Jira project under the NexCognit Atlassian tenant is created to hold the VisualAI backlog across all five 5-step build-plan phases, with a consistent Epic → Story → Task hierarchy.
3. **GitHub repository creation** — after Step 1 of the 5-step build plan (tonight's MVP) ships and is demoed, the NexCognit GitHub organization is formally stood up with the necessary repositories and branch-protection rules so future work is traceable, reviewable, and continuity-safe.

The spec's audience is the internal engineering team (and agents acting on their behalf). The "user" throughout is an engineer or automation agent performing infrastructure or backlog operations.

**Note on organization name**: the original feature description says "NextCognit" in two places. The company name is **NexCognit** per the VisualAI Master Product Specification. This spec treats those two spellings as the same entity and standardizes on **NexCognit** going forward. Any existing Atlassian tenant or GitHub organization named "NextCognit" is assumed to be a typo artifact and should be reconciled to **NexCognit** at setup.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Engineer or agent modifies Neon schema through API/MCP only (Priority: P1)

A backend engineer (or a Claude-family agent working on their behalf) needs to add a column to the `credit_transactions` table, create a Neon branch for a risky migration, or inspect the production schema. They use the Neon MCP server (preferred for human-in-the-loop review) or the Neon REST API directly. They do NOT sign in to the Neon web console to make changes. The operation is logged, reversible via a Neon branch, and auditable.

**Why this priority**: The Neon DB is the single source of truth for credit balances, tenant data, and generation history. Ad-hoc console edits bypass review, lose audit history, and are the single biggest risk for data-integrity incidents. Enforcing API/MCP-only operations is a constitutional-level guarantee for data safety.

**Independent Test**: An engineer attempts to apply a schema change via the Neon console and is blocked by convention (documented in `OPERATIONS.md`). They repeat the change via the MCP or API; the change lands, produces an audit trail, and creates (or reuses) a Neon branch so rollback is a single command.

**Acceptance Scenarios**:

1. **Given** an engineer needs to create a new table, **When** they issue the change via Neon MCP or the Neon API from their dev machine or an agent session, **Then** a named migration (timestamped SQL file) is committed to the VisualAI repo BEFORE the change is applied, and the change is applied against a dedicated Neon branch first.
2. **Given** an engineer needs to read production-sensitive data for debugging, **When** they query via MCP or API using a read-only role, **Then** the operation is logged in an audit trail (Neon's own log + team-accessible query-history file) and no PII is extracted to a local file.
3. **Given** a destructive change (DROP COLUMN, DROP TABLE, TRUNCATE) is requested, **When** the change is issued, **Then** the tooling enforces a preview-diff (using `compare_database_schema`) and an explicit human confirmation before executing on the main branch.
4. **Given** a Neon branch reset or delete is requested, **When** the operation runs, **Then** the branch-lineage is preserved in documentation for 7 days and the destructive action is logged.
5. **Given** an emergency requires a direct Neon console edit (break-glass), **When** the edit is performed, **Then** an incident ticket is created in Jira within 24 hours describing the change, the reason, and a follow-up to automate the same change via API.

---

### User Story 2 - Team tracks all VisualAI work in one Jira project with consistent issue hierarchy (Priority: P1)

An engineer, PM, or founder opens Jira and sees a single VisualAI project under the NexCognit tenant. Every SpecKit feature (spec/plan/tasks) has a corresponding Jira Epic. Every Epic has Stories (one per user story in the spec) and Tasks (one per task in the SpecKit `tasks.md`). Every Task links to a specific SpecKit task ID and a GitHub PR.

**Why this priority**: Without a central backlog, work is scattered across chat threads, loose Google docs, and individual heads. A Jira-backed hierarchy aligned to SpecKit gives executive visibility, enables status reports, and survives team turnover.

**Independent Test**: Query the Jira project for all Epics; verify that every SpecKit feature (001–004 today, and every future numbered feature) has exactly one Epic. For Epic 002 (video-duration-variations), verify Stories US1, US2, US3 exist and each is linked to a GitHub PR when implementation ships.

**Acceptance Scenarios**:

1. **Given** the Jira project is created, **When** a team member visits the Jira project landing page, **Then** they see the project key, project lead, Epic-first backlog view, and a short README explaining the SpecKit → Jira mapping.
2. **Given** a new SpecKit feature `005-foo` is specified, **When** `/speckit-specify` completes, **Then** a Jira Epic with matching title is created (via the Atlassian MCP) and linked from the spec document's header.
3. **Given** a SpecKit plan and tasks exist for a feature, **When** `/speckit-tasks` completes, **Then** each task becomes a Jira Task under the feature's Epic with the SpecKit task ID (e.g., T007) as a custom field or label.
4. **Given** an engineer opens a PR implementing SpecKit task T007, **When** the PR references T007 in its title or description, **Then** the corresponding Jira Task auto-transitions to "In Review" and links the PR URL.
5. **Given** a PR merges, **When** the merge commit is detected, **Then** the Jira Task auto-transitions to "Done" and the Epic progress rolls up.

---

### User Story 3 - After Step 1 MVP demo, NexCognit GitHub repos exist with protection (Priority: P1)

Tonight (or whenever Step 1 of the 5-step build plan completes and is demo-reviewed), the team formally spins up the NexCognit GitHub organization (or verifies it exists) and creates the VisualAI repositories under it with main-branch protection, required PR reviews, and CI gating. From that point onward, `main` cannot be pushed directly; every change goes through a PR and at least one review.

**Why this priority**: Step 1's work currently lives on the user's laptop + a forked-from-upstream MPT repo + an ad-hoc sibling Next.js directory. Once the MVP is real, code must move into the company-owned, protected, auditable home so the founder, future hires, and investors see professional infrastructure.

**Independent Test**: After Step 1 demo, visit `github.com/nexcognit` (the org URL). Verify the repositories listed below exist with the correct branch-protection rules and initial commits from the local work.

**Acceptance Scenarios**:

1. **Given** Step 1 has shipped and been demo-approved, **When** the engineer runs the onboarding script or follows `OPERATIONS.md`, **Then** the `nexcognit` GitHub organization is confirmed (or created if absent) and the following repositories are created under it: `visualai-rendering-engine` (this repo, cut from the upstream MPT fork), `visualai-frontend` (the Next.js app built tonight), `visualai-orchestration` (empty placeholder for the Layer 2 API, seeded by a README + the orchestration spec when it lands).
2. **Given** a new repository is created under the NexCognit org, **When** the engineer pushes the initial commit, **Then** the repository has main-branch protection enabled with: require PR, require 1 approving review, require status checks to pass (for repos that have CI), disallow force pushes to `main`, disallow deletion of `main`.
3. **Given** the repositories exist, **When** a team member clones them, **Then** each repo contains a `README.md` explaining the layer, ownership, and link to the corresponding SpecKit features, and a `CLAUDE.md` capturing the per-repo agent guidance.
4. **Given** the repositories exist, **When** a pull request opens, **Then** CI runs (tests, linting, type-check) and PR merge is blocked until CI passes and reviews approve.
5. **Given** the `visualai-rendering-engine` repo is cut from the upstream MPT fork, **When** it is initialized on the NexCognit org, **Then** the upstream remote (`harry0703/MoneyPrinterTurbo`) is preserved as a fork parent so periodic rebases remain a git-native operation (constitution Principle II).

---

### User Story 4 - New engineer onboards to VisualAI in one session using these automations (Priority: P2)

A newly hired engineer joins and is given access to the NexCognit Atlassian tenant, the NexCognit GitHub org, and the Neon project. Following `OPERATIONS.md`, they clone the repos, see the Jira backlog, inspect the Neon schema via MCP, and make their first merged PR on a trivial Story within 4 hours.

**Why this priority**: Onboarding friction compounds with each hire. If US1–US3 are solid, onboarding flows naturally; if they aren't, every new hire re-solves environment setup themselves. P2 because the first hire is already aboard; this lands once hiring begins.

**Independent Test**: Run a dry-run onboarding with the founder as the "new hire." Time from "clone all three repos" to "first PR merged against a trivial backlog Story" is ≤ 4 hours.

**Acceptance Scenarios**:

1. **Given** the new hire has Atlassian, GitHub, and Neon invitations accepted, **When** they follow `OPERATIONS.md`, **Then** they have a local clone of all three repos, a running Layer 3 dev server, a running Next.js dev server, a Neon branch for their dev work, and a Jira view of the backlog — all within 60 minutes.
2. **Given** the backlog contains a trivial first-issue Story tagged `good-first-issue`, **When** the hire picks it up, **Then** the PR template, branch protection, and CI all work without intervention.

---

### Edge Cases

- **Neon operation fails mid-migration**: The migration MUST roll back automatically via its dedicated Neon branch; the failed migration SQL file is marked `-failed.sql` and a Jira ticket is created for analysis.
- **MCP server is temporarily unavailable**: Engineers fall back to the Neon REST API directly; the MCP outage is logged. No fallback to manual console edits.
- **Jira project name collides** with an existing project in the NexCognit tenant: setup script prompts for disambiguation rather than silently creating a second project.
- **GitHub org "NexCognit" is already claimed** by a different entity: an incident is raised; repos are temporarily created under a documented fallback org (e.g., founder's personal GitHub) with a migration plan to NexCognit once the name is secured.
- **NexCognit vs NextCognit spelling**: setup tooling checks both; if both exist, they are reconciled (one retained, the other archived with a redirect note).
- **Branch protection conflicts with solo-founder workflow**: during the Step 1 window (before team hires), "require 1 approving review" may be temporarily relaxed to "allow self-approval with admin override" — documented as a tracked Step 1 debt, flipped back to strict when the second engineer joins.
- **Agent lacks credentials**: if an agent tries to call Neon/Atlassian/GitHub MCP and credentials are unconfigured, the agent MUST surface a clear, actionable error rather than silently failing or guessing.
- **SpecKit feature created but Jira Epic sync fails**: the spec is still written to disk; the Jira sync is queued for retry; no feature is lost if Atlassian is briefly unreachable.
- **Code-only "fixes" bypass Jira**: small fixes (typo PRs, doc corrections, etc.) may merge without a Jira Task; the convention is Jira-required for work ≥ 30 min estimated. Conventional-commit subjects make Jira-less work discoverable.

## Requirements *(mandatory)*

### Functional Requirements

#### Neon Database Governance

- **FR-001**: All Neon schema changes (CREATE/ALTER/DROP, role grants, extension enables) MUST be performed via the Neon REST API or the Neon MCP server — never via the web console, except in documented break-glass incidents.
- **FR-002**: Every schema change MUST have a timestamped SQL migration file committed to the appropriate repository BEFORE the change is applied to the main Neon branch.
- **FR-003**: Destructive schema changes (DROP TABLE, DROP COLUMN, TRUNCATE, column-type narrowing) MUST be applied to a dedicated Neon branch first and verified with `compare_database_schema` before being promoted to main.
- **FR-004**: Production reads containing PII MUST use a read-only Neon role; exfiltrating PII to a local machine is prohibited by policy.
- **FR-005**: Break-glass console edits MUST trigger a Jira incident within 24 hours describing the change, the reason, and an automation follow-up.
- **FR-006**: Neon branch reset or delete actions MUST preserve a lineage record for at least 7 days in team-accessible documentation.
- **FR-007**: All Neon connection strings and credentials MUST live in environment variables or a secret manager, never in version control.

#### Jira Project Setup

- **FR-008**: A single Jira project named "VisualAI" (or "NexCognit VisualAI") MUST exist under the NexCognit Atlassian tenant, with an owner, lead, and project key.
- **FR-009**: The project MUST use a three-level hierarchy: Epic → Story → Task (plus Bug as a peer of Task).
- **FR-010**: Every SpecKit feature (numbered directory in `specs/`) MUST have exactly one Jira Epic, linked by title or a custom field containing the feature directory name.
- **FR-011**: Every user story in a feature's spec MUST have a corresponding Jira Story under the feature's Epic, labeled with the story's priority (P1/P2/P3).
- **FR-012**: Every SpecKit task (in `tasks.md`) MUST have a corresponding Jira Task under the feature's Epic, with the SpecKit task ID (e.g., T007) in a Jira label or custom field.
- **FR-013**: PRs referencing a SpecKit task ID in their title or description MUST auto-transition the corresponding Jira Task to "In Review," and merged PRs auto-transition to "Done."
- **FR-014**: Jira Epic progress MUST roll up from child Story/Task statuses.
- **FR-015**: Work smaller than 30 minutes (typo fixes, doc tweaks, config nudges) MAY skip Jira; larger work MUST have a Jira reference.

#### GitHub Organization & Repository Setup

- **FR-016**: The NexCognit GitHub organization MUST exist (or be created) before Step 1 completes, with the founder as owner.
- **FR-017**: At minimum the following repositories MUST exist under the organization after Step 1 demo: `visualai-rendering-engine`, `visualai-frontend`, `visualai-orchestration`.
- **FR-018**: The `visualai-rendering-engine` repository MUST preserve its upstream fork relationship with `harry0703/MoneyPrinterTurbo` to enable git-native upstream rebases (constitution Principle II).
- **FR-019**: Every repository MUST have `main`-branch protection with: require PR, require at least one approving review (relaxable to self-approval during solo-founder phase — tracked as Step 1 debt), require status checks to pass, disallow force push to `main`, disallow deletion of `main`.
- **FR-020**: Every repository MUST contain a `README.md` (layer, ownership, SpecKit link), a `CLAUDE.md` (agent guidance), and a `CODEOWNERS` file (even if everyone is a single user today).
- **FR-021**: Every repository MUST have CI configured to run tests / linting / type-checks on every PR, with merge blocked until CI passes.
- **FR-022**: The rendering-engine repo's first commit under NexCognit org MUST NOT discard the upstream history; the fork relationship stays intact so security patches from upstream are one `git pull upstream main` away.

#### Integration Tooling

- **FR-023**: The Neon MCP server MUST be registered with Claude Code so agent-driven schema operations route through it by default.
- **FR-024**: The Atlassian MCP server MUST be registered with Claude Code; the agent uses it for all Jira operations and for any Confluence documentation.
- **FR-025**: GitHub operations (repo creation, branch protection, PR opening) MUST use `gh` CLI or GitHub's REST/GraphQL API; manual clicking in the GitHub web UI is allowed but discouraged for bulk or repeatable operations.
- **FR-026**: Credentials for all three integrations MUST be rotated at least annually, and MUST NEVER be stored in plaintext in any repository.

#### Documentation

- **FR-027**: An `OPERATIONS.md` file MUST be maintained at the top of the `visualai-rendering-engine` repo (and cross-linked from others) documenting: onboarding steps, Neon-via-MCP workflow, Jira-via-Atlassian-MCP workflow, GitHub workflow, and break-glass procedures.
- **FR-028**: `OPERATIONS.md` MUST be updated whenever any of FR-001 through FR-026 changes; the update lands in the same PR as the change.

### Key Entities

- **Neon Project**: The persistent cloud database for VisualAI. Attributes: project ID, primary region, branch list, role list, connection-string mapping per environment (dev/staging/prod). Managed exclusively via Neon API or MCP.
- **Jira Project**: The backlog home for VisualAI under the NexCognit Atlassian tenant. Attributes: project key, project lead, default Epic-Story-Task hierarchy, integrations to GitHub.
- **Epic**: A Jira issue representing one SpecKit feature. Attributes: title, linked SpecKit feature directory, progress rollup, Stories list.
- **Story**: A Jira issue representing one user story from a SpecKit spec. Attributes: title, priority (P1/P2/P3), parent Epic, linked acceptance scenarios.
- **Task**: A Jira issue representing one row in a SpecKit `tasks.md`. Attributes: SpecKit task ID (e.g., T007), parent Story or Epic, linked PR, state.
- **GitHub Repository**: A repo under the `nexcognit` org. Attributes: name, visibility, branch-protection rules, CODEOWNERS, fork parent (for `visualai-rendering-engine`), CI configuration.
- **Break-Glass Incident**: An ad-hoc manual operation outside the normal API/MCP flow. Attributes: what/when/why/who, follow-up Jira ticket, automation-recovery PR.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100 % of Neon schema changes across a 90-day window are linked to a committed migration SQL file in-repo. Verified by weekly audit of Neon's change log against repo history.
- **SC-002**: 0 data-integrity incidents attributable to manual Neon console edits across the first 90 days, measured by post-incident reviews.
- **SC-003**: 100 % of SpecKit features created after this spec lands have a corresponding Jira Epic within 30 minutes of the feature spec being committed.
- **SC-004**: 90 % of SpecKit tasks committed to `tasks.md` are represented as Jira Tasks within 60 minutes of task list creation.
- **SC-005**: A new engineer onboarding onto VisualAI takes ≤ 4 hours from "invitations accepted" to "first PR merged," measured across the first 3 hires.
- **SC-006**: All three initial NexCognit GitHub repositories exist with main-branch protection within 24 hours of the Step 1 demo being signed off.
- **SC-007**: 0 accidental force-pushes to `main` across any NexCognit repository over the first 90 days, measured by audit-log review.
- **SC-008**: 100 % of break-glass Neon console edits produce a Jira follow-up ticket within 24 hours, verified by cross-reference between Neon audit log and Jira project.
- **SC-009**: `OPERATIONS.md` is updated in the same PR as any change to the process it documents, 100 % of the time, verified by a pre-merge CI check that fails when process-related files change without an `OPERATIONS.md` update.

## Assumptions

- **Organization name**: "NexCognit" is the canonical spelling per the VisualAI Master Specification. The user's "NextCognit" references in the feature description are treated as typos; this spec uses "NexCognit" consistently. Any existing Atlassian tenant or GitHub org under the "NextCognit" name is reconciled to "NexCognit" during setup.
- **Jira is Atlassian Cloud**: the NexCognit Atlassian tenant is an Atlassian Cloud instance. Self-hosted Jira Data Center is out of scope.
- **Atlassian MCP is authoritative**: the Atlassian MCP server (already configured in the user's Claude Code environment) is the authoritative tool for Jira operations. Engineers may use the Jira web UI for ad-hoc browsing; automated flows use the MCP.
- **Neon MCP is authoritative**: the Neon MCP server (already configured in the user's Claude Code environment) is the authoritative tool for schema operations. The Neon REST API is a valid fallback when MCP is unavailable.
- **"First stage" = Step 1 of the 5-step build plan**: the feature description's "after you finish the first stage of the project" is interpreted as Step 1 of the 5-step build plan maintained at `/Users/amraeid/.claude/plans/`. Creation of the GitHub org and repos happens after Step 1 demos successfully.
- **Solo-founder branch-protection relaxation**: the "require 1 approving review" branch-protection rule is relaxed to "allow self-approval with admin override" during the solo-founder phase. This is a tracked Step 1 debt, flipped back to strict when a second engineer joins. This prevents the constitution-level rule from blocking a one-person dev workflow tonight.
- **Three starting repositories**: `visualai-rendering-engine` (this repo, cut from the MPT fork), `visualai-frontend` (the Next.js app built in Step 1), and `visualai-orchestration` (empty placeholder seeded with README + orchestration spec link; real code lands in Step 2).
- **Upstream fork preservation**: `visualai-rendering-engine` is imported into NexCognit as a fork of `harry0703/MoneyPrinterTurbo`, keeping the fork-parent relationship for future rebases per constitution Principle II.
- **Conventional Commits enforced on every repo**: repeating the constitution's commit-subject rule for the two new NexCognit repos; CI validates the subject format.
- **OPERATIONS.md lives in the rendering-engine repo**: this repo is the "flagship" of the three; `OPERATIONS.md` here is the canonical source, with short stubs in the other repos pointing to it.
- **No production Stripe webhooks in Step 1**: the credit_transactions-related schema management is deferred to Step 4's Stripe integration; Step 1 only provisions the Neon project and a minimal schema (tenants/users) for the admin credit panel (spec 003) to function.
- **GitHub Actions as CI**: the default CI runner is GitHub Actions, pinned to pinned-SHA actions to meet Principle II's upstream-compatibility spirit (no vendor lock-in for the build-system).
- **Single-region Neon for Step 1**: multi-region replication is out of scope for this feature; Neon's primary region is whichever is closest to the founder's location.
- **This spec governs process, not product**: it is out of scope for constitution Principle I's "Layer 3 rendering only" rule because it does not add rendering logic to this repo; it adds meta-infrastructure shared across all three layers.
