# Implementation Plan: NexCognit Brand Skill for UI

**Branch**: `007-nexcognit-brand-skill` | **Date**: 2026-04-25 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/007-nexcognit-brand-skill/spec.md`

## Summary

Package the NexCognit visual brand defined in [spec 001](../001-nexcognit-ui-style/spec.md) into an Anthropic Skills-format artifact (`SKILL.md` + reference docs + worked examples) installed at `.claude/skills/nexcognit-brand/` inside each consuming NexCognit web repo. v1 targets Claude Code only (clarification Q1), uses independent semver with a `tracks_spec_001` manifest field for drift detection (Q2), is opt-in via repo-local install (Q3), enforces a tiered substitute/refuse policy on off-brand input (Q4), and is verified via a fixed-prompt side-by-side comparison run (Q5). The Skill artifact itself lives in `visualai-frontend` (Layer 1); this repo owns only the planning artifacts under `specs/007-nexcognit-brand-skill/`.

## Technical Context

**Language/Version**: Markdown (CommonMark) + YAML frontmatter — no executable code. The Skill's "runtime" is Claude Code's built-in Skills loader.
**Primary Dependencies**: Anthropic Claude Code Skills format (frontmatter schema observed in `.claude/skills/speckit-*/SKILL.md` in this repo). Spec 001's token catalog (color, typography, spacing, radius, components, a11y).
**Storage**: Git-tracked plain files. Each consuming repo carries its own copy at `.claude/skills/nexcognit-brand/` (~10 markdown files).
**Testing**: Side-by-side comparison harness — fixed prompt set executed against Claude Code with-Skill vs without-Skill; outputs scored against the spec 001 brand checklist and timed to acceptance (per clarification Q5). No pytest, no CI gate at v1.
**Target Platform**: Claude Code (any host OS) loading repo-local Skills. No browser, no server.
**Project Type**: Tooling artifact (an AI-assistant skill bundle). Not a library, CLI, web service, or runtime feature.
**Performance Goals**: Total Skill content (frontmatter + body + references) MUST fit comfortably in Claude Code's recommended system-instruction budget so the developer never has to choose between "load the Skill" and "give the agent room to work" (SC-004). Research target: keep total size under ~30 KB across all Skill files.
**Constraints**: Pure-markdown Skill content (Claude Code doesn't execute code in skills). Off-brand handling logic is encoded as agent-readable rules, not as a code-side validator. Repo-local install only at v1 (no user-global install per Q3). No telemetry plumbing at v1 (Q5).
**Scale/Scope**: One Skill artifact, ~10 documents, ~7 component patterns with worked examples, consumed initially by `visualai-frontend` only. Future consumers (Layer 2 admin panels, marketing pages) inherit the same artifact via repo-local copy.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution v1.0.2 governs the Layer 3 Rendering Engine (this repo). Spec 007's deliverable lives in **Layer 1** (`visualai-frontend`); this repo owns only the planning artifacts under `specs/007-nexcognit-brand-skill/`. The principles are evaluated in that light.

| Principle | Verdict | Reasoning |
|---|---|---|
| **I. Layer 3 Scope — Rendering Only (NON-NEGOTIABLE)** | PASS | The Skill artifact is Layer 1 tooling and MUST NOT be installed inside this repo's `app/` or runtime tree. The plan explicitly forbids committing any Skill artifact files to Layer 3 source directories. The only Layer 3 footprint is `specs/007-nexcognit-brand-skill/` (planning docs), consistent with how features 001/002/003 already use this repo for cross-layer SpecKit governance. |
| **II. Surgical Fork Discipline** | PASS | None of the five fork-surface files (`material.py`, `llm.py`, `voice.py`, `schema.py`, controllers) are touched. The feature is text-only and Layer-1 scoped. |
| **III. Multi-Tenant Context Propagation** | N/A | The Skill never sees a render job. No `tenant_id` / `user_id` / `generation_id` flow through it. |
| **IV. External Asset Acceptance Over Direct API Calls** | N/A | The Skill makes zero network calls. It is a static markdown bundle. |
| **V. Mode-Aware Rendering Contract** | N/A | The five Agent Modes are rendering-pipeline concerns. The Skill is a UI brand artifact. |
| **§Technology Constraints — Database** | N/A | No PostgreSQL schema, no Redis, no DDL. |
| **§Technology Constraints — Observability** | PASS | No render jobs, no log lines, no `loguru` requirement. |
| **§Technology Constraints — Secrets** | PASS | No API keys. |
| **§Development Workflow — SpecKit flow** | PASS | This plan follows `/speckit.specify` → `/speckit.clarify` → `/speckit.plan`. |
| **§Development Workflow — fork-surface PR rule** | N/A | None of the five fork-surface files are touched. |
| **§Development Workflow — pytest gate** | N/A | No Python code shipped; pytest is irrelevant. The feature's verification is the side-by-side run defined in Q5. |

**Gate result**: PASS. No violations to justify. Re-check post-Phase 1.

## Project Structure

### Documentation (this feature, in this repo)

```text
specs/007-nexcognit-brand-skill/
├── plan.md                    # This file
├── research.md                # Phase 0 — Skills format, spec 001 token resolution, side-by-side harness design
├── data-model.md              # Phase 1 — Manifest, Token Set, Component Pattern, A11y Rule, Worked Example entities
├── quickstart.md              # Phase 1 — installer/consumer runbook
├── contracts/
│   ├── skill-manifest-schema.md       # Frontmatter schema and required fields
│   ├── activation-contract.md         # Activation behavior, scope declarations, version-mismatch surface
│   └── compliance-check-contract.md   # Tiered substitute/refuse rules (encodes FR-006)
├── checklists/
│   └── requirements.md        # Existing spec quality checklist
├── spec.md                    # Feature specification (clarified)
└── tasks.md                   # Phase 2 — produced by /speckit.tasks (NOT here)
```

### Skill artifact (deliverable, in `visualai-frontend` repo)

The Skill artifact is **not** committed to this Layer 3 repo. It is built per this plan and installed in each consuming Layer 1 surface. v1 target consumer: `../visualai-frontend/`.

```text
visualai-frontend/.claude/skills/nexcognit-brand/
├── SKILL.md                   # Entry point — manifest frontmatter + agent guidance overview
├── tokens.md                  # Color / typography / spacing / radius / shadow / motion catalog (from spec 001 FR-001..FR-005)
├── components.md              # Stepper, Content Card, Option Card, Primary/Secondary Button, Input/Textarea, Select (from spec 001 FR-006..FR-013)
├── accessibility.md           # Focus ring, contrast, reduced-motion, color-blind, semantic markup (from spec 001 FR-014..FR-018)
├── compliance-check.md        # Tiered substitute/refuse policy (encodes FR-006 of this spec; references contracts/compliance-check-contract.md)
├── activation.md              # Activation scope declaration; v1-Claude-Code-only; repo-local-only constraint
├── examples/
│   ├── primary-button.tsx
│   ├── secondary-button.tsx
│   ├── option-card.tsx
│   ├── content-card.tsx
│   ├── stepper.tsx
│   ├── text-input.tsx
│   └── confirmation-dialog.tsx
└── CHANGELOG.md               # Per FR-009 update procedure: version bumps + tracked spec 001 version
```

**Structure Decision**: The deliverable lives entirely in `visualai-frontend/.claude/skills/nexcognit-brand/`. This MPT repo only owns the SpecKit planning artifacts under `specs/007-nexcognit-brand-skill/`. This separation honours Constitutional Principle I (Layer 3 scope) — runtime engine code stays untouched, and the Layer 1 tooling artifact lives in the Layer 1 repo where it belongs. Future consumers (Layer 2 admin panels, marketing pages) install their own copy of the Skill at the same relative path.

## Complexity Tracking

> No Constitution violations. Section intentionally empty.

The plan deliberately rejects three alternatives that would have added complexity without v1 value:

- **User-global Skill install** at `~/.claude/skills/nexcognit-brand/` — rejected per clarification Q3 because it would bleed brand opinions into every Claude Code session, including non-NexCognit work.
- **Multi-tool packaging at v1** (Cursor, Codex, Copilot) — rejected per clarification Q1 because the team uses only Claude Code today; cross-tool support is deferred to a follow-up version via FR-009.
- **Telemetry-instrumented success measurement** — rejected per clarification Q5 because building observability the team doesn't have today would expand v1 scope past the planning budget; side-by-side runs produce real numbers without that infrastructure.
