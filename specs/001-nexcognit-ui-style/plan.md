# Implementation Plan: VisualAI UI Style — Nexcognit Design Language

**Branch**: `001-nexcognit-ui-style` | **Date**: 2026-04-19 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from [/specs/001-nexcognit-ui-style/spec.md](spec.md)

## Summary

Establish the VisualAI frontend's design-system foundation — a single source of truth for color palette, typography scale, surface hierarchy, and seven reusable component patterns (Stepper, Content Card, Option Card, Primary Button, Secondary Button, Text Input / Textarea, Select) — derived from the Nexcognit "AI Agent Onboarding" Figma frame. Every VisualAI screen (Dashboard, Creation Wizard, Asset Library, Billing, Onboarding, Admin Credit Panel) composes against these tokens and components.

Technical approach: all work lands in the sibling repo `../visualai-frontend/` (created tonight in Step 1 of the 5-step build plan). Tokens are declared once in a generated Tailwind theme extension (palette + typography + spacing + radius + stroke), exposed as semantic CSS variables for runtime use, and consumed by a shadcn/ui component library that is re-themed to match the Figma instead of shadcn's stock defaults. Component patterns are thin wrappers over shadcn primitives (Radix under the hood) that pin our token choices, interaction states, and accessibility behavior. The rendering-engine repo (this repo, Layer 3, per constitution Principle I) is NOT touched; the legacy Streamlit WebUI continues to run on its own styling during transition and is explicitly out of scope for adopting these tokens.

## Technical Context

**Language/Version**:
- TypeScript 5.x (strict mode).
- No runtime code in this repo.

**Primary Dependencies**:
- Next.js 15 (App Router, React 19 Server Components).
- Tailwind CSS 4 (configured via CSS-first `@theme` directive; fallback to v3 config style if v4 maturity is insufficient at setup time — decided in [research.md Q1](research.md)).
- shadcn/ui (copy-in components, re-themed) built on Radix UI primitives.
- `lucide-react` for icons.
- Roboto from Google Fonts (self-hosted via `next/font/google`).
- class-variance-authority + tailwind-merge for component variant composition.

**Storage**:
- No runtime storage. Tokens and component source live in `src/lib/tokens/` and `src/components/ui/` in the frontend repo.
- Build-time: Tailwind compiles tokens into utility classes.

**Testing**:
- **Vitest** for unit-level utilities (class name builders, token helpers).
- **Playwright** with the `@axe-core/playwright` integration for component-level accessibility + visual regression on the seven component patterns.
- **Storybook** (optional, added later) for isolated component documentation; not a Step 1 requirement.

**Target Platform**:
- Evergreen browsers: Chrome, Firefox, Safari, Edge (last 2 major versions each).
- Viewports 360 px to 1920 px wide (FR-017).

**Project Type**: Web application — frontend only (Layer 1 per Master Spec §4). This feature produces no backend code.

**Performance Goals**:
- Bundle impact for the token system + 7 primitive components: ≤ 30 KB gzipped JS over and above the Next.js baseline.
- First contentful paint with tokens applied: ≤ 1.5 s on a cold cache over a 4G connection.
- Zero layout shift between token-less initial render and token-applied render (tokens are in the critical CSS, not runtime-loaded).
- Hover transitions: ≤ 150 ms per FR (US3 acceptance scenario 2); progress-bar animation ≤ 250 ms (US2 acceptance scenario 3).

**Constraints**:
- WCAG 2.1 AA minimum on every text/background pair (FR-015, SC-003).
- Dark mode only, no light-mode variant (FR-018).
- Roboto only, four weights; no secondary display typeface (FR-002).
- Lucide icons only; no emojis; no other icon libraries (FR-013).
- 1 px border weight across the entire catalog (FR-004).
- All hover/transition animations respect `prefers-reduced-motion: reduce` (FR-016).
- Token values pinned to exact hex/px listed in the spec; no "close enough" substitutions.

**Scale/Scope**:
- Target: every VisualAI screen. Measured immediately by: Dashboard (1), Mode 2 Creation Wizard (1 × 4 steps), Asset Library placeholder (1), Billing placeholder (1), Admin Credit Panel (1 — from spec 003). ~8 screens in Step 1–2 scope.
- Token catalog: ~20 semantic color tokens, 6 typography tokens, 4 spacing tokens, 3 radius tokens.
- Component catalog: 7 patterns.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Evaluated against [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md) v1.0.0.

| Principle | Status | Notes |
|---|---|---|
| **I. Layer 3 Scope — Rendering Only** (NON-NEGOTIABLE) | ✅ PASS | Zero changes to this repository. All artifacts land in the sibling `../visualai-frontend/` repo (Layer 1). |
| **II. Surgical Fork Discipline** | ✅ PASS | No edits to `material.py`, `llm.py`, `voice.py`, `schema.py`, or `app/controllers/`. Upstream MPT is untouched. |
| **III. Multi-Tenant Context Propagation** | ✅ N/A | Design tokens and components are tenant-agnostic. No user, tenant, or generation data flows through this feature. |
| **IV. External Asset Acceptance Over Direct API Calls** | ✅ N/A | No video generation logic involved. |
| **V. Mode-Aware Rendering Contract** | ✅ N/A | Design system is mode-orthogonal. Modes 1–5 will all consume the same tokens and components. |

**Violations**: none.

**Complexity justification required**: no.

## Project Structure

### Documentation (this feature)

```text
specs/001-nexcognit-ui-style/
├── spec.md              # /speckit-specify output (done)
├── checklists/
│   └── requirements.md  # validation checklist (done)
├── plan.md              # this file
├── research.md          # Phase 0 output (this run)
├── data-model.md        # Phase 1 output (this run)
├── quickstart.md        # Phase 1 output (this run)
├── contracts/
│   ├── design-tokens.md      # TypeScript / CSS-var token shape
│   ├── component-api.md      # Prop types and state machines for 7 patterns
│   └── theming-integration.md # How Tailwind + shadcn consume tokens
└── tasks.md             # /speckit-tasks output (next command)
```

### Source Code (sibling frontend repository)

All implementation lives in `/Users/amraeid/Dropbox/Dev.lab/Cursor-Cluade/NexCognit-Content-generator/visualai-frontend/`. This repo (`MoneyPrinterTurbo`, Layer 3) is untouched.

```text
visualai-frontend/                                # sibling of MoneyPrinterTurbo
├── src/
│   ├── app/
│   │   ├── layout.tsx                           # Root layout; loads Roboto; applies dark class
│   │   ├── globals.css                          # Tailwind base + token @theme directive + CSS vars
│   │   └── page.tsx                             # Dashboard placeholder (Step 1 build)
│   ├── components/
│   │   └── ui/                                  # NEW: seven component patterns
│   │       ├── Stepper.tsx                      # FR-006
│   │       ├── ContentCard.tsx                  # FR-007
│   │       ├── OptionCard.tsx                   # FR-008
│   │       ├── Button.tsx                       # FR-009 + FR-010 (variants: primary, secondary)
│   │       ├── Input.tsx                        # FR-011
│   │       ├── Textarea.tsx                     # FR-011
│   │       └── Select.tsx                       # FR-012
│   └── lib/
│       └── tokens/
│           ├── colors.ts                        # NEW: palette tokens with semantic names
│           ├── typography.ts                    # NEW: type scale tokens
│           ├── spacing.ts                       # NEW: spacing + radius tokens
│           └── index.ts                         # Re-export
├── tests/
│   ├── accessibility/
│   │   └── components.spec.ts                   # Playwright + axe-core per component
│   ├── visual/
│   │   └── components.spec.ts                   # Visual regression per component at 3 viewports
│   └── unit/
│       └── tokens.test.ts                       # Token presence + format checks
├── tailwind.config.ts                           # NEW: extends theme from src/lib/tokens
├── next.config.ts
├── package.json
└── tsconfig.json
```

**Structure Decision**: Frontend repository is the **only** target. No change here. This feature does not create a new backend or modify any backend. The design system is purely in the frontend repo and consumed by every screen-level feature (Mode 2 Creation Wizard, Admin Credit Panel, etc.) that lands in later features.

## Complexity Tracking

No violations. The seven component patterns are the minimum needed to compose the seven referenced screen compositions (Dashboard, Wizard, Library, Billing, Onboarding, Admin panel, plus the 5 Agent Mode cards). Each pattern earns its place via FR-### and at least one acceptance scenario.

## Phase 0 — Research (resolved in [research.md](research.md))

Five Phase-0 design questions:

1. **Tailwind v3 vs v4**: which version does the frontend repo target for Step 1?
2. **Token distribution pattern**: CSS variables, Tailwind theme, or both? What's the source of truth and what's the consumer surface?
3. **Dark-mode-only strategy**: hard-code `class="dark"` on `<html>`, or use `next-themes` with a pinned theme?
4. **Icon tree-shaking**: how to minimize bundle impact while using `lucide-react`?
5. **Accessibility testing workflow**: Playwright + axe-core per-component vs higher-level scans?

Phase 0 output: [research.md](research.md).

## Phase 1 — Design & Contracts

**Prerequisites**: Phase 0 complete.

Phase 1 output artifacts (produced in this run):

- [data-model.md](data-model.md) — entities: Design Token (with sub-types: Color, Typography, Spacing, Radius, Stroke, Motion), Component Pattern (with interaction-state machines), Screen Composition (cross-reference map).
- [contracts/design-tokens.md](contracts/design-tokens.md) — the authoritative TypeScript shape and CSS-variable naming convention; what downstream features consume.
- [contracts/component-api.md](contracts/component-api.md) — prop types, variants, and state machines for the seven component patterns.
- [contracts/theming-integration.md](contracts/theming-integration.md) — how Tailwind's theme extension and shadcn/ui's CSS-var pattern hand off the token values end-to-end.
- [quickstart.md](quickstart.md) — the minimum set of commands to scaffold `../visualai-frontend/` with these tokens applied, end-to-end, from a clean directory.

Agent context update: [`.specify/scripts/bash/update-agent-context.sh claude`](../../.specify/scripts/bash/update-agent-context.sh) runs after Phase 1 artifacts land.

**Post-design re-check**: Constitution Check re-evaluated against produced artifacts. Still ✅ PASS on all principles — no change. No new complexity introduced.
