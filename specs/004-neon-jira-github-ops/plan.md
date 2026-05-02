# Implementation Plan: Neon Database, Jira Project, and GitHub Repository Operations Policy

**Branch**: `004-neon-jira-github-ops` | **Date**: 2026-04-19 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from [/specs/004-neon-jira-github-ops/spec.md](spec.md)

## Summary

This feature is an **operations-policy + one-time-setup deliverable**, not a user-facing product feature. It establishes:

1. How Neon database work is done (via Neon API or MCP; migrations in-repo; destructive changes on branches).
2. The structure of the VisualAI Jira project under NexCognit (Epic → Story → Task hierarchy tied to SpecKit features).
3. The creation of three GitHub repositories under the NexCognit org after the Step 1 demo signs off.
4. A canonical `OPERATIONS.md` that documents all of the above for present and future team members.

Technical approach: ship four concrete artifacts in this repo — `OPERATIONS.md`, `.github/workflows/ops-guard.yml` (CI check for SC-009), an `ops/` directory holding Neon migration scaffolding and runbooks for the three vendor integrations, and an `ops/onboarding/` sub-tree. External-system state (the NexCognit Atlassian project key, the NexCognit GitHub org existence, the Neon project ID) is provisioned via scripted calls using the already-configured Neon MCP, Atlassian MCP, and `gh` CLI. No rendering-engine code is touched (Layer 3 stays pure per constitution Principle I).

## Technical Context

**Language/Version**: This feature adds no runtime code. Automation uses:
- Shell (bash) for orchestration scripts under `ops/`.
- Claude Code slash-commands + MCP invocations for the Atlassian/Neon interactive flow.
- YAML for GitHub Actions workflows.
- Markdown for `OPERATIONS.md`, `README.md` stubs, and migration SQL files.

**Primary Dependencies**:
- **Neon MCP server** (pre-configured per session start) and Neon REST API as fallback.
- **Atlassian MCP server** (pre-configured) for all Jira + Confluence operations.
- **`gh` CLI** (GitHub-official) for repo creation, branch-protection rule setup, and PR checks.
- **GitHub Actions** as the CI runner.
- **Conventional Commits** validation via a lightweight commit-lint check in the `ops-guard` workflow.

**Storage**:
- Source-controlled: migration SQL files under `ops/neon/migrations/`, `OPERATIONS.md`, CI workflows under `.github/workflows/`.
- External state:
  - Neon: one project, named branches (main, staging, per-PR).
  - Atlassian: one Jira project under the NexCognit tenant, plus corresponding Confluence space (if enabled).
  - GitHub: one organization (`nexcognit`), three repositories.

**Testing**:
- A lightweight CI check in `ops-guard.yml`: lints `OPERATIONS.md` for required sections, verifies that any touched file under `.specify/`, `ops/`, `.github/workflows/`, or this spec's paths is accompanied by an `OPERATIONS.md` update (enforces SC-009), and runs `shellcheck` over ops scripts.
- Manual acceptance: the four user-story tests in spec.md are exercised post-setup by the founder running through the scripts.
- No unit-test suite produced for this feature — the deliverables are documents, workflows, and vendor-system state, not functions to test.

**Target Platform**:
- Developer machines (macOS / Linux) for running ops scripts and MCP invocations.
- GitHub Actions ubuntu-latest runners for CI.
- Neon Cloud, Atlassian Cloud, GitHub Cloud — all managed services.

**Project Type**: Meta-infrastructure / DevOps policy. Single-repo artifact set plus stubs in two future sibling repos.

**Performance Goals**:
- New-engineer onboarding from invitations-accepted → first PR merged: ≤ 4 hours (SC-005).
- SpecKit feature → Jira Epic auto-creation latency: ≤ 30 minutes (SC-003).
- SpecKit task → Jira Task auto-creation latency: ≤ 60 minutes (SC-004).
- Neon MCP operation round-trip: ≤ 10 s for a simple schema query; ≤ 60 s for a branch-create + migration apply; interactive.

**Constraints**:
- Zero manual Neon console edits during normal operations (FR-001).
- All three secret sets (Neon, Atlassian, GitHub) kept out of the repository (FR-007, FR-026).
- Branch protection on `main` is strict (FR-019), with the solo-founder self-approval relaxation being the only tolerated deviation while the team is 1 person.
- `OPERATIONS.md` updates land in the same PR as any process-affecting change (FR-028, SC-009).

**Scale/Scope**:
- 1 NexCognit Atlassian tenant, 1 Jira project, 1 GitHub organization, 3 initial repositories, 1 Neon project with ≤ 20 branches at any time (one per active PR + main + staging + a small pool of named dev branches).
- Onboarding target: supports first 3 hires without rework.
- SpecKit-to-Jira sync: supports at least 5 features created per week without manual intervention.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Evaluated against [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md) v1.0.0.

| Principle | Status | Notes |
|---|---|---|
| **I. Layer 3 Scope — Rendering Only** (NON-NEGOTIABLE) | ✅ PASS | This feature adds `OPERATIONS.md`, `.github/workflows/ops-guard.yml`, and `ops/` — none are rendering logic, user-facing business logic, or Layer 3 product code. Principle I governs rendering code, not meta-infrastructure. |
| **II. Surgical Fork Discipline** | ✅ PASS | No edits to any of the five restricted fork-surface files (`material.py`, `llm.py`, `voice.py`, `schema.py`, `app/controllers/`). The only new top-level directory is `ops/`; this is intentional for a governance document set, and it is listed in `OPERATIONS.md` as a NexCognit-owned addition kept isolated from upstream MPT. Future rebases onto `harry0703/MoneyPrinterTurbo` will ignore it. |
| **III. Multi-Tenant Context Propagation** | ✅ N/A | No rendering job data flows through this feature. Principle III's tenant/user requirements do not apply to operations policy. |
| **IV. External Asset Acceptance Over Direct API Calls** | ✅ N/A | This feature does not render video; Principle IV governs asset-sourcing, not ops tooling. The feature's USE of the Neon/Atlassian/`gh` APIs is a governance mandate, not a rendering code path. |
| **V. Mode-Aware Rendering Contract** | ✅ N/A | No rendering involved. |

**Violations**: none.

**Complexity justification required**: no.

**Spirit check**: Principle II warns against "sprawling forks." Adding `ops/`, `.github/`, and `OPERATIONS.md` to a surgically-forked repo is a measured addition common to every open-source fork that becomes a product. The fork parent (`harry0703/MoneyPrinterTurbo`) remains intact; upstream rebases treat these additions as NexCognit-only and merge cleanly because they occupy paths upstream does not use.

## Project Structure

### Documentation (this feature)

```text
specs/004-neon-jira-github-ops/
├── spec.md              # /speckit-specify output (done)
├── checklists/
│   └── requirements.md  # validation checklist (done)
├── plan.md              # this file
├── research.md          # Phase 0 output (this run)
├── data-model.md        # Phase 1 output (this run)
├── quickstart.md        # Phase 1 output (this run)
├── contracts/
│   ├── neon-operations.md        # What can be done via Neon MCP/API and how
│   ├── jira-sync.md              # SpecKit ↔ Jira sync contract
│   └── github-setup.md           # NexCognit GitHub org provisioning contract
└── tasks.md             # /speckit-tasks output (next command — NOT produced here)
```

### Repository artifacts added by this feature

```text
# In the visualai-rendering-engine repo (this repo)
OPERATIONS.md                             # NEW: canonical ops doc (FR-027)
.github/
└── workflows/
    └── ops-guard.yml                    # NEW: CI check for SC-009 + shellcheck + commit-lint
ops/
├── README.md                            # NEW: points at OPERATIONS.md
├── onboarding/
│   └── new-engineer-checklist.md        # NEW: US4 happy-path steps
├── neon/
│   ├── migrations/
│   │   └── .gitkeep                     # migrations land here when Step 2+ begins
│   ├── provision.md                     # NEW: how to create the Neon project via MCP
│   └── break-glass-incident-template.md # NEW: used for FR-005 Jira tickets
├── jira/
│   ├── sync-speckit-to-jira.md          # NEW: SpecKit → Jira sync runbook (contract)
│   └── pr-transition-hook.md            # NEW: how PR titles transition Jira Task state
└── github/
    └── setup-org-and-repos.md           # NEW: NexCognit GitHub org runbook (contract)

# In the NexCognit/visualai-frontend repo (created after Step 1 demo)
OPERATIONS.md                             # NEW: stub redirecting to rendering-engine canonical doc

# In the NexCognit/visualai-orchestration repo (created after Step 1 demo, empty until Step 2)
OPERATIONS.md                             # NEW: stub redirecting to rendering-engine canonical doc
README.md                                 # NEW: "Orchestration API - empty scaffold, owned by spec XXX"
```

**Structure Decision**: Introduce one new top-level directory `ops/` alongside the existing `app/`, `webui/`, `test/`. The `ops/` directory is process governance — it is NEVER imported from Python, never deployed, and is explicitly scoped outside constitution Principle II's five fork-surface restrictions because it is an org-level addition (documentation + runbooks + CI), not an edit to the forked codebase's runtime surfaces. Upstream MPT has no `ops/` path; merge conflicts with future upstream rebases are therefore structurally impossible.

## Complexity Tracking

No violations. The feature adds one new top-level directory (`ops/`), one new CI workflow, and one root-level document (`OPERATIONS.md`). Each earns its place; nothing is speculative. `ops/` sub-directory fan-out (`onboarding/`, `neon/`, `jira/`, `github/`) is justified by the four distinct vendor surfaces each documents.

## Phase 0 — Research (resolved in [research.md](research.md))

Four open questions from the spec that shape the design:

1. What is the canonical structure for SpecKit → Jira sync so each feature / user story / task has a durable, queryable link?
2. How do we name NexCognit's GitHub org, Atlassian project key, and Neon project consistently, and how do we reconcile the "NexCognit" vs "NextCognit" typo confusion if either org name already exists?
3. What is the minimum CI workflow that enforces `OPERATIONS.md`-update-on-process-change (SC-009) without becoming annoying noise?
4. What break-glass procedure do we encode for Neon console edits, so FR-005 + SC-008 are cleanly enforceable via Jira automation?

Phase 0 output: [research.md](research.md).

## Phase 1 — Design & Contracts

**Prerequisites**: Phase 0 complete.

Phase 1 output artifacts (produced in this run):
- [data-model.md](data-model.md) — artifact inventory across vendor systems: Neon project, Jira project + issue hierarchy, GitHub org + repos, Break-Glass Incident record, OPERATIONS.md section schema.
- [contracts/neon-operations.md](contracts/neon-operations.md) — allowed / disallowed Neon operations with the specific Neon MCP tool to use for each.
- [contracts/jira-sync.md](contracts/jira-sync.md) — the SpecKit-feature-directory ↔ Jira-Epic / user-story ↔ Story / task ↔ Task mapping, plus the PR-commit-message → Jira-state-transition rules.
- [contracts/github-setup.md](contracts/github-setup.md) — step-by-step NexCognit GitHub org provisioning + three repos + branch-protection configuration, with preservation of the `harry0703/MoneyPrinterTurbo` fork parent.
- [quickstart.md](quickstart.md) — "how to set up VisualAI ops from scratch" for a new NexCognit admin.

Agent context update: [`.specify/scripts/bash/update-agent-context.sh claude`](../../.specify/scripts/bash/update-agent-context.sh) executed after Phase 1 artifacts land.

**Post-design re-check**: Constitution Check re-evaluated against produced artifacts. Still ✅ PASS on all principles. Principle II spirit ("upstream-compatible fork") held by isolating all new material under `ops/`, `OPERATIONS.md`, and `.github/workflows/ops-guard.yml` — none of which conflict with upstream MPT paths.
