# Phase 0 Research: NexCognit Brand Skill for UI

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**: 2026-04-25

## R1 — Anthropic Claude Code Skills format

**Decision**: Adopt the same `SKILL.md` shape that this repo's existing SpecKit skills use (observed at [.claude/skills/speckit-specify/SKILL.md](../../.claude/skills/speckit-specify/SKILL.md), `speckit-clarify/SKILL.md`, etc.). Frontmatter is YAML; body is markdown read by the agent at activation.

**Frontmatter schema** (from observed examples plus the new fields this Skill needs):

```yaml
---
name: "nexcognit-brand"
description: "NexCognit visual brand and design language enforcement for UI work in NexCognit web frontends. Applies the spec 001 token catalog (color, typography, spacing, radius, shadow, motion), the documented component patterns (Stepper, Content Card, Option Card, Buttons, Inputs, Select), and the WCAG-AA accessibility rules. Activates when an agent is producing UI code in a repo that has this Skill installed at .claude/skills/nexcognit-brand/."
argument-hint: "(no arguments — Skill activates on relevance)"
compatibility: "Claude Code only at v1. Cursor / Codex / Copilot deferred. Repo-local install at .claude/skills/nexcognit-brand/ — never user-global."
metadata:
  author: "NexCognit (Amr Eid)"
  source: "specs/007-nexcognit-brand-skill (in nexcognit-com/visualai-rendering-engine)"
  skill_version: "1.0.0"
  tracks_spec_001: "v1.0"
  activation_scope: "NexCognit web frontends — repo-local only"
user-invocable: true
disable-model-invocation: false
---
```

**Rationale**: matching the existing SpecKit skill shape avoids inventing a parallel format. The two new metadata fields (`skill_version`, `tracks_spec_001`) carry the manifest data required by FR-005 without adding any new top-level keys the loader doesn't already accept. `disable-model-invocation: false` lets the agent self-activate when relevance is detected (per the activation strategy chosen in clarification Q3); the repo-local install scopes that auto-detection to NexCognit surfaces.

**Alternatives considered**:
- **Custom JSON manifest in a sidecar `manifest.json`** — rejected: introduces a second file the loader doesn't read, splitting the source of truth.
- **Encode versioning in the file path** (e.g., `nexcognit-brand-1.0.0/SKILL.md`) — rejected: breaks the convention that Skills live at a stable name; would force every install procedure to delete-and-recreate on bumps.
- **Use `references/` subdirectory loaded on-demand** (a separate Anthropic Skills convention) — partially adopted: long content is split into siblings (`tokens.md`, `components.md`, etc.) rather than crammed into `SKILL.md`. We rely on the agent following links from `SKILL.md` to those siblings as needed, which is how the existing SpecKit skills already operate (e.g., `speckit-specify/SKILL.md` references `templates/`).

## R2 — Spec 001 token catalog resolution

**Decision**: Encode spec 001 verbatim into `tokens.md`, `components.md`, and `accessibility.md`. Spec 001 is concrete enough to copy directly — it names every color hex, typography size, weight, line-height, spacing value, and component shape with WCAG-AA ratios verified.

**Spec 001 facts the Skill must encode** (from [`specs/001-nexcognit-ui-style/spec.md`](../001-nexcognit-ui-style/spec.md), FR-001 through FR-018):

| Token group | Values |
|---|---|
| Page background | `#020617` |
| Card background | `#0F172A` |
| Elevated / hover surface | `#1E293B` |
| Subtle border | `#334155` |
| Strong border | `#475569` |
| Primary text | `#FFFFFF` |
| Muted text | `#94A3B8` |
| Primary accent | `#3B82F6` (Dodger Blue) |
| Accent track (20% opacity) | `#3B82F633` |
| Typeface | Roboto only — weights 400 / 500 / 600 / 700 |
| H1 / H3 / Section / Body / Small / Button | 30/Bold/36 · 20/SemiBold/28 · 16/SemiBold/16/-0.4ls · 14/Regular/20 · 12/Regular/16 · 14/SemiBold/20 |
| Spacing scale | 4 / 8 / 16 / 24 px |
| Stroke weight | 1 px |
| Border-radius | 8 px (buttons, option cards) · 12 px (large cards) · ≥999 px (stepper circles, progress bars) |
| Components | Stepper · Content Card · Option Card · Primary Button · Secondary/Ghost Button · Text Input · Textarea · Select · Lucide icons (1.5–2 stroke; 16/20/24/32 px) |
| Accessibility | 2 px Dodger-Blue focus ring + 2 px offset · WCAG AA (4.5:1 body, 3:1 large) · `prefers-reduced-motion: reduce` respected · color-blind-safe selection (border-width or check glyph in addition to blue) |

**Rationale**: spec 001 was clarified well enough to be the single design source of truth (assumption #1 in spec.md). The Skill becomes a faithful re-encoding, never an interpretation.

**Alternatives considered**:
- **Reference spec 001 by link instead of copying** — rejected: forces the agent to retrieve and re-parse the spec on every activation; defeats the entire purpose of a packaged Skill (FR-001 says "in a form an AI agent can apply directly without consulting the source spec").
- **Encode a subset and link the rest** — rejected: spec 001 is small enough (~250 lines) that the full token catalog fits comfortably in the size budget identified in R5.

## R3 — Activation contract (clarification Q3 made concrete)

**Decision**: Activation is governed entirely by Claude Code's existing project-level Skills auto-discovery. A repo "opts in" by committing `.claude/skills/nexcognit-brand/` to its tree. There is no marker file, no path-based heuristic, and no install at the user level.

**Behavioral expectations**:

| Situation | Behavior |
|---|---|
| Claude Code session opened in a repo with `.claude/skills/nexcognit-brand/` present | Skill is in the available-skills list at session start; the agent invokes it via the `Skill` tool when a UI-related prompt arrives. |
| Same Claude Code session with a non-UI prompt (e.g., "fix this Python bug") | Agent does not invoke the Skill. The Skill description (R1) explicitly scopes activation to UI work. |
| Claude Code session in a repo without the Skill installed | Skill is not loaded. Agent operates with no brand opinions, as if the Skill didn't exist. This is the explicit intent — non-NexCognit work is unaffected. |
| User runs `/nexcognit-brand` explicitly | Manual invocation works because `user-invocable: true` is set in the frontmatter. |
| Skill loaded but agent's session-start prelude (FR-011 visibility cue) | The Skill's `SKILL.md` instructs the agent to print a one-line "NexCognit Brand Skill v1.0.0 (tracking spec 001 v1.0) loaded" notice at first UI prompt, satisfying SC-006. |

**Rationale**: leveraging the loader's existing repo-scoped behavior is simpler than building a custom activation trigger. The "Skill presence === opt-in" signal is deterministic and removes the false-positive risk on repos that happen to share naming patterns (decided in clarification Q3, recorded in spec.md assumptions).

**Alternatives considered**:
- **Marker file `.nexcognit-brand` in repo root + custom detection logic in SKILL.md** — rejected: the Skill is already repo-local, so its mere installation is the marker.
- **Auto-activate based on filename glob (e.g., `**/*.tsx` triggers Skill)** — rejected: glob heuristics fire on non-NexCognit repos that happen to use TSX (this repo's own SpecKit skills don't have such hooks; we shouldn't invent one for this).
- **Always-on once installed user-globally** — rejected per clarification Q3.

## R4 — Side-by-side comparison harness (clarification Q5 made concrete)

**Decision**: Build a small reproducible harness as part of the Skill's CHANGELOG/release process. Manual operation, no CI gate at v1.

**Harness design**:

1. **Fixed prompt set** (10 prompts) covering the core pattern surface defined in spec 001:
   - "Add a primary CTA button that says 'Continue'."
   - "Add a secondary/ghost button that says 'Cancel'."
   - "Render a 7-step stepper at state 3-of-7 with appropriate labels."
   - "Render a 2-column option grid of 4 mode cards (Product Shoot, Short Marketing, Long-Form, UGC)."
   - "Render a content card containing a small H3 title, body text, and a primary button."
   - "Render a labelled text input with placeholder 'Enter product URL'."
   - "Render a select dropdown listing voice options (3 items)."
   - "Render a confirmation dialog for a destructive 'Delete asset' action."
   - "Render the Dashboard layout: dark canvas, sidebar, content area with H1, two cards."
   - "Render a small 'Loading…' state for the asset list."
2. **Run twice per prompt**, each in a fresh Claude Code session against the same target repo:
   - Run A: `.claude/skills/nexcognit-brand/` removed (or session in a non-NexCognit repo) → no-Skill baseline.
   - Run B: Skill installed → with-Skill output.
3. **Score each output** against a rubric derived directly from spec 001's FR-001 through FR-018: each FR contributes 1 point if satisfied, 0 if violated, partial credit only where spec 001 itself permits flexibility. Max ~18 points per output.
4. **Time each output** from prompt submission to "developer would accept without correction" (a human judgment captured by the operator running the harness).
5. **Compute SC-001 and SC-002**:
   - SC-001 (≥95% first-attempt brand compliance with Skill loaded): `(sum of with-Skill scores) / (10 × max points) ≥ 0.95`.
   - SC-002 (≥80% time reduction vs baseline): `(median with-Skill time) ≤ 0.20 × (median without-Skill time)`.

**Rationale**: gives FR-005 acceptance criteria real numbers without telemetry plumbing the team doesn't have. Human-in-the-loop scoring is acceptable at v1 because the Skill is owned by one person; future scaling can introduce automation per FR-009's update procedure.

**Alternatives considered**:
- **Automated visual diffing (Playwright/Storybook screenshots)** — rejected for v1: requires the consuming repo to have a Storybook setup, which `visualai-frontend` doesn't yet. Re-evaluate post-Step 4.
- **LLM-judge scoring** (one Claude session scores another's output) — rejected for v1: introduces an extra layer of subjectivity and requires its own validation. Manual scoring is fine for 10 prompts.

## R5 — Size budget for the Skill artifact (SC-004)

**Decision**: Target ≤ 30 KB total markdown across all Skill files; hard cap 60 KB. Measured by `wc -c` on the entire `.claude/skills/nexcognit-brand/` tree excluding the `examples/` directory (worked-example TSX is loaded only when the agent opens it explicitly).

**Estimated breakdown** (compiled from R2):

| File | Estimated size |
|---|---|
| `SKILL.md` (frontmatter + overview + pointers) | ~3 KB |
| `tokens.md` (color/type/spacing/radius/shadow/motion) | ~5 KB |
| `components.md` (7 patterns × ~1 KB each) | ~7 KB |
| `accessibility.md` (focus / contrast / reduced-motion / color-blind / semantic) | ~3 KB |
| `compliance-check.md` (tiered substitute/refuse policy from FR-006) | ~3 KB |
| `activation.md` (scope declaration, version, repo-local constraint) | ~2 KB |
| `CHANGELOG.md` (initial entry only at v1) | ~1 KB |
| **Total (frontmatter-loaded)** | **~24 KB** |
| `examples/*.tsx` (7 files, loaded only when referenced) | ~7 KB total |

**Rationale**: 24 KB of frontmatter content is comfortably within Claude Code's recommended skill description budget (the existing SpecKit skills are similar size). The worked-example TSX files load lazily when the agent decides it needs a reference shape, so they don't burn frontmatter context.

**Alternatives considered**:
- **Inline all worked examples in `components.md`** — rejected: would push frontmatter content over budget. Lazy-load via separate files per pattern is cleaner.
- **Shrink examples to pseudocode-only** — rejected: real TSX with proper Tailwind class names is more useful as an anchor than abstract pseudocode (matches FR-007 worked-example requirement).

## R6 — Update procedure (FR-009)

**Decision**: Document the procedure in `CHANGELOG.md` of the Skill itself plus a one-page operator runbook in this feature's `quickstart.md`. The procedure is:

1. Spec 001 changes land on `001-nexcognit-ui-style` (or a successor branch) in this MPT repo.
2. A maintainer pulls the change, identifies which token files in the Skill are affected, and edits `tokens.md` / `components.md` / `accessibility.md` as needed.
3. Maintainer bumps the Skill semver per the rules in FR-005:
   - PATCH for non-semantic changes (typo, clearer wording, a new worked example).
   - MINOR for any token addition or component addition.
   - MAJOR for any token removal, component removal, or breaking renaming.
4. Maintainer updates `tracks_spec_001` in the manifest to the new spec 001 version.
5. Maintainer adds a `CHANGELOG.md` entry naming the spec 001 revision and the affected files.
6. Maintainer commits the Skill update inside the consuming repo (`visualai-frontend`) and opens a PR referencing the spec 001 change.

**Verification target**: The whole procedure should be doable in ≤ 30 minutes for a typical change (per SC-005).

**Rationale**: keeps the Skill update path simple and operator-friendly. No special tooling required — a markdown editor is the only tool.

**Alternatives considered**:
- **Auto-generate the Skill from spec 001 via a script** — rejected for v1: the script becomes its own maintenance burden, and spec 001 doesn't currently have machine-readable token data. Re-evaluate when spec 001 ships JSON/YAML token output.
- **Skill lives only in this repo and is symlinked into consuming repos** — rejected: cross-repo symlinks break in `git clone` and on Windows; copy-on-install is more portable.

## R7 — Open question (low impact, deferred from clarify)

**Item**: How should the agent behave if the Skill artifact is partially corrupt (e.g., `SKILL.md` parses but `tokens.md` is missing or empty)?

**Disposition**: Defer to Phase 2. The likely answer ("agent surfaces the load failure as a one-line warning at first UI prompt and falls back to no-Skill behavior") is reasonable; tasks should add a graceful-degradation acceptance test to the side-by-side harness that simulates a missing reference file. This was flagged as Outstanding in the clarify coverage summary and is not worth blocking the plan.

## Summary

All NEEDS-CLARIFICATION items resolved. The Skill is a well-scoped, low-complexity Layer 1 tooling artifact with a clean repo-local install, a faithful re-encoding of spec 001, a deterministic activation rule, a tiered enforcement policy, and a measurable acceptance harness. No constitutional violations.
