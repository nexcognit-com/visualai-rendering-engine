<!--
Sync Impact Report
==================
Version: 1.0.2 (PATCH — 2026-04-21)
  - Clarified §Technology Constraints → Database: application code MUST NOT
    embed tenant/credit/user schema or ORM; Neon DDL under ops/neon/migrations/
    is allowed as Layer 4 operational artifacts (SpecKit/spec 004), not runtime
    engine logic.
  - No principle added, removed, or redefined. Templates: no updates required.

Version: 1.0.1 (PATCH — 2026-04-19)
  - Retired stale 16-week MVP roadmap reference in §"Development Workflow"
  - Replaced with pointer to the 5-step build plan at
    /Users/amraeid/.claude/plans/can-you-confirm-that-dapper-emerson.md
  - No principle added, removed, or redefined. Templates: no updates required.

Version: 1.0.0 (initial — 2026-04-19)
Ratification: 2026-04-19 (initial adoption)

Modified principles (template placeholder → concrete, VisualAI-aligned):
- [PRINCIPLE_1] → I. Layer 3 Scope — Rendering Only (NON-NEGOTIABLE)
- [PRINCIPLE_2] → II. Surgical Fork Discipline
- [PRINCIPLE_3] → III. Multi-Tenant Context Propagation
- [PRINCIPLE_4] → IV. External Asset Acceptance Over Direct API Calls
- [PRINCIPLE_5] → V. Mode-Aware Rendering Contract

Added sections:
- Section 2: Technology Constraints
- Section 3: Development Workflow
- Governance (filled from placeholder)

Removed sections: none

Templates requiring updates:
- ✅ .specify/templates/plan-template.md (no patch required — defers to constitution via generic "Constitution Check" gate)
- ✅ .specify/templates/spec-template.md (no patch required — generic; Agent Mode and tenant context expressible in existing Key Entities / Functional Requirements sections)
- ✅ .specify/templates/tasks-template.md (no patch required — generic; JWT middleware, mode registry, and fork-surface discipline fit within existing Foundational / User Story phases)

Deferred TODOs: none
-->

# VisualAI Rendering Engine Constitution

## Core Principles

### I. Layer 3 Scope — Rendering Only (NON-NEGOTIABLE)

This repository is strictly the VisualAI Rendering Engine. It MUST NOT implement
user management, authentication issuance, credit ledgers, Stripe billing, or
multi-tenant CRUD — those are owned by Layer 2 (Orchestration API) and Layer 4
(Neon PostgreSQL). The engine accepts signed render jobs, assembles MP4 output,
and returns asset URLs. Any PR introducing user/credit/billing business logic
inside this repo is out of scope and MUST be rejected.

Rationale: keeps the GPU-heavy rendering tier decoupled and horizontally
scalable per the 5-Layer architecture in §4 of the VisualAI Master Spec.

### II. Surgical Fork Discipline

Modifications to the upstream MoneyPrinterTurbo codebase MUST be confined to
the five surfaces called out in §5 of the Master Spec:
`app/services/material.py`, `app/services/llm.py`, `app/services/voice.py`,
`app/models/schema.py`, and the video controllers under `app/controllers/`.
Core FFmpeg/MoviePy assembly code and shared utilities MUST remain
upstream-compatible so periodic rebases onto `harry0703/MoneyPrinterTurbo`
stay low-conflict. Changes outside these surfaces require explicit
justification in the PR body.

Rationale: surgical forks survive; sprawling forks die. Upstream security and
bugfix absorption is a strategic asset.

### III. Multi-Tenant Context Propagation

Every render job MUST carry `user_id`, `tenant_id`, `mode`, and `product_id`
through the extended `VideoParams` schema. JWT middleware on the video
controllers MUST validate these fields and verify the credit hold (issued by
Layer 2) before a render starts. Rendering code MUST log tenant context in
every structured log line and embed it in generated filenames and metadata.
Jobs missing tenant context MUST be rejected with HTTP 400, never rendered
under a default tenant.

Rationale: multi-tenant safety is a hard boundary; a single mis-tagged asset
is a data leak across agency clients.

### IV. External Asset Acceptance Over Direct API Calls

Image, video, and voice assets arrive from the Orchestration API as
pre-signed URLs or inline payloads. This engine MUST NOT call NanoBanana,
Veo 3.1, ElevenLabs, Kling, Runway, or any other generation API directly
from Layer 3 code. The single retained exception is Pexels stock footage,
allowed ONLY inside the Mode 5 (Faceless Channel Automation) code path.
All other `material.py` provider integrations inherited from upstream MPT
MUST be removed or gated behind Mode 5.

Rationale: centralizing model routing in Layer 2.5 is the Master Spec's
differentiator (§4, §5.1); bypassing it fragments cost controls and
fallback logic.

### V. Mode-Aware Rendering Contract

The engine supports exactly the five Agent Modes defined in §3 of the
Master Spec: (1) Product Shoot Generator, (2) Short Marketing Video,
(3) Long-Form Product Marketing Video, (4) UGC Avatar Ad, and
(5) Faceless Channel Automation. Each mode's prompt templates, script
length bounds, pacing rules, aspect ratio, and subtitle positioning MUST
be declared in a single `app/services/modes/` registry — not scattered
across service files. Adding a new mode requires a constitution amendment
(MINOR version bump).

Rationale: the five modes are the product; drift between spec and code
here is a product failure, not a code-quality issue.

## Technology Constraints

- **Runtime**: Python 3.11 or 3.12 only; environment managed via `uv` and
  `pyproject.toml`. No ad-hoc `pip install` in scripts.
- **Deployment target**: GPU-capable host (RunPod or equivalent) via the GPU
  Dockerfile. Docker Compose remains valid for local development. CPU-only
  deployment is unsupported for production.
- **System dependencies**: FFmpeg and ImageMagick are hard requirements at
  render time. Import-time failures MUST be avoided so the API can start
  for health checks; missing-binary errors surface at render invocation
  with a clear message.
- **Database**: The rendering application (`app/`, controllers, services) MUST
  NOT embed PostgreSQL schema, ORM models, or migration runners for tenant,
  credit, or user data — those belong in Layer 2 and Layer 4. Neon PostgreSQL
  is owned by Layer 4 and accessed only by Layer 2 at runtime. **Exception**:
  committed SQL files under `ops/neon/migrations/` are allowed as **Layer 4 DDL
  artifacts** when tracked by SpecKit / spec 004 governance (reviewed, applied
  via Neon MCP or ops pipeline). They MUST NOT be imported or executed by the
  engine at render time and MUST NOT introduce credit-ledger business logic
  into this codebase. Redis usage in this repo is limited to transient
  render-progress state and MUST NOT be treated as a source of truth.
- **Observability**: Structured logging via `loguru`. Every log line for a
  render job MUST include `tenant_id`, `user_id`, and `generation_id`.
  Direct `print()` in service or controller code is prohibited;
  `logging.*` stdlib calls MUST be routed into loguru sinks.
- **Secrets**: API keys (Pexels for Mode 5, any retained fallback providers)
  MUST come from environment variables or untracked config files. Commits
  introducing secrets MUST be rejected.

## Development Workflow

- Feature work flows through SpecKit:
  `/speckit-specify` → `/speckit-clarify` → `/speckit-plan` →
  `/speckit-tasks` → `/speckit-implement`.
- Commit subjects use Conventional Commits (`feat:`, `fix:`, `docs:`,
  `chore:`, `build:`, `refactor:`, `test:`). Version bumps in
  `pyproject.toml` land in a dedicated `chore:` commit.
- PRs touching the five fork-surface files listed in Principle II MUST
  reference the affected Agent Mode(s) and cite the relevant Master Spec
  section in the PR body.
- Delivery sequencing follows the 5-step build plan at
  [`~/.claude/plans/can-you-confirm-that-dapper-emerson.md`](/Users/amraeid/.claude/plans/can-you-confirm-that-dapper-emerson.md).
  Step 1 ships Mode 2 on the existing engine; each subsequent step burns
  down tracked principle debts. Principle III/IV/V relaxations active
  during Step 1 are logged in `STEP1_DEBT.md` at the repo root.
- `pytest test/` MUST pass locally before a PR is opened. New mode code
  requires at least one smoke test exercising the rendering path with
  mocked Layer 2 inputs.

## Governance

This constitution supersedes informal conventions. It applies only to this
repository (Layer 3). Cross-layer architectural changes require alignment
with the VisualAI Master Spec and approval from the NexCognit CEO
(Amr Eid).

Amendments follow SpecKit semantic versioning:

- **MAJOR**: principle removal or redefinition, or a change to the Agent
  Mode set.
- **MINOR**: new principle, new section, or new Agent Mode.
- **PATCH**: wording clarifications, typo fixes, non-semantic refinements.

Amendments land via pull request and MUST update the Sync Impact Report and
version line atomically. All PRs MUST verify compliance with this
constitution; complexity or deviation MUST be justified in the PR body.

Runtime guidance lives in `README.md`, `CLAUDE.md`, and the VisualAI
Master Spec. Those documents MUST be updated in the same PR when a
principle changes their stated behavior.

**Version**: 1.0.2 | **Ratified**: 2026-04-19 | **Last Amended**: 2026-04-21
