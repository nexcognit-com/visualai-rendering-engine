# Research: VisualAI UI Style — Nexcognit Design Language

**Phase**: 0 — Research
**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

Five Phase-0 design decisions. Decision / Rationale / Alternatives.

---

## Q1. Tailwind v3 vs v4 for the frontend repo?

**Decision**: Start on **Tailwind CSS v4** using the CSS-first `@theme` directive. Keep the option to downgrade to v3 if any critical shadcn/ui integration issue surfaces during Step 1 build — but plan for v4.

**Rationale**:
- Tailwind v4 ships a CSS-variable-based theme system natively via the `@theme` directive, which matches the spec's semantic-token model more cleanly than v3's `theme.extend` object. Less indirection between token declaration and CSS-var consumption.
- v4 is the default for `create-next-app` as of 2026; staying on v3 would mean actively downgrading during scaffolding.
- shadcn/ui has shipped a v4-compatible track since late 2025; component copy-ins use CSS variables that work with either version.
- The main v4 risk (content-detection changes, no `content` key in config) is well-documented and handled by v4's zero-config JIT scanning of `src/**/*.{ts,tsx}`.

**Alternatives considered**:
- *Tailwind v3*: safer in April 2025, but two years behind as of April 2026. Unnecessary tech debt.
- *No Tailwind at all (vanilla CSS + CSS modules)*: rejected. shadcn/ui is tied to Tailwind; abandoning Tailwind rewrites shadcn from scratch.
- *Stitches or Panda CSS*: smaller ecosystems; spec doesn't need what they offer over Tailwind v4's native CSS-first approach.

---

## Q2. Token distribution: CSS variables, Tailwind theme, or both?

**Decision**: **Both, with CSS variables as the single source of truth**. Tailwind theme extends to reference the CSS variables; class names like `bg-card` resolve to `hsl(var(--color-card))`. TypeScript token objects in `src/lib/tokens/` are generated from (or at least kept in lockstep with) the CSS-var declarations.

Flow:

```
src/lib/tokens/colors.ts (TypeScript, source of truth for values)
         │
         ▼
src/app/globals.css (@theme directive, emits --color-* CSS vars)
         │
         ▼
tailwind.config.ts (references var(--color-*))
         │
         ▼
Component consumers: `<div className="bg-card text-muted">`
         │
         OR
         ▼
Runtime consumers that need dynamic tokens: `style={{ backgroundColor: "hsl(var(--color-card))" }}`
```

**Rationale**:
- Tailwind classes are the ergonomic default for 95 % of the UI — terse, tree-shaken, co-located with markup.
- CSS variables as the emitted form (not inline hex values) give future flexibility: if someone ever wants a light mode, a variant theme, or per-tenant branding, one CSS var swap cascades through the whole app. We're not building that today (FR-018 says dark-only) but we pay zero cost to leave the door open.
- TypeScript objects in `src/lib/tokens/*.ts` mean downstream features (like the Creation Wizard spec's components) can reference tokens programmatically when needed (e.g., for `PreviewApprovalGrid`'s confidence indicators).
- Having a single source of truth (the TS objects) that *emits* both the CSS and the Tailwind config avoids the drift that plagues teams with parallel theme files.

**Alternatives considered**:
- *Tailwind theme only (no CSS variables)*: rejected. Components that need runtime-dynamic colors (very rare in this spec, but plausible for future: "preview diff overlay") have no escape hatch.
- *CSS variables only, no Tailwind extension*: rejected. Forces everyone to write `style={{ backgroundColor: "hsl(var(--color-card))" }}` everywhere; verbose and error-prone.
- *Generate tokens from a JSON schema via a build step*: overkill for a 20-color palette. Revisit if the palette grows past ~50 tokens.

---

## Q3. Dark-mode-only strategy for Next.js App Router

**Decision**: Hard-code `class="dark"` on `<html>` in `src/app/layout.tsx`. Do NOT install `next-themes` or any theme-toggle library.

**Rationale**:
- Spec FR-018 explicitly forbids a light mode for the initial rollout. Shipping theme-toggle infrastructure "just in case" violates the "no speculative complexity" principle.
- Hard-coding `class="dark"` avoids hydration-mismatch warnings entirely — the server renders dark, the client renders dark, no flash.
- When (and if) a light mode is ever spec'd, adding `next-themes` is a 30-minute migration; the CSS vars are already set up to support it (see Q2). Zero cost to defer.

**Alternatives considered**:
- *`next-themes` pinned to dark*: rejected. Adds a dependency for zero benefit while light mode doesn't exist. Increases bundle by ~3 KB gzipped.
- *Media-query-based dark mode (`prefers-color-scheme`)*: rejected. User's OS preference is irrelevant — VisualAI is dark-only by product decision.
- *`suppressHydrationWarning` on `<html>`*: unnecessary if the class is literally hard-coded (no client-side theme detection).

---

## Q4. Icon tree-shaking with `lucide-react`

**Decision**: Import named icons directly (`import { Home, Folder, Briefcase } from "lucide-react"`). Do NOT use the dynamic icon-name import pattern or the wrapper `<Icon name="home" />` pattern.

**Rationale**:
- `lucide-react` supports named exports with tree-shaking out of the box; only icons actually imported end up in the bundle.
- Dynamic imports (`import { [iconName] } from "lucide-react"`) break tree-shaking in every bundler — all 1,500 icons end up in the bundle. That's ~200 KB of SVGs.
- The wrapper pattern (`<Icon name="home" />`) is the same anti-pattern with extra steps.
- The ~12 icons VisualAI actually uses (Home, Folder, Briefcase, CreditCard, Play, Pause, X, Check, Menu, ChevronRight, Upload, Video) total ~8 KB. Acceptable.

**Alternatives considered**:
- *`@iconify` or Phosphor*: rejected. Spec mandates Lucide exclusively (FR-013).
- *Self-hosting SVGs directly*: rejected. Lucide's API stability + tree-shaking + React integration is worth the dependency.
- *Build-time SVG sprite generation*: overkill for 12 icons. Revisit if the icon count grows past ~50.

---

## Q5. Accessibility testing workflow

**Decision**: Two-layer approach:

1. **Per-component axe-core checks** via Playwright using `@axe-core/playwright`. One test file per component pattern; each test renders the component in default + hover + focus + selected states and runs axe on each DOM state.
2. **Per-route integration scans** via Playwright on the Dashboard and Creation Wizard routes, validating that compositions (not just isolated components) pass WCAG 2.1 AA.

Visual regression: Playwright screenshot diff with a 0.1 % threshold on the component-level tests only, at three viewports (360 px, 768 px, 1440 px).

Runs in CI on every PR against the frontend repo; merge blocked on failures.

**Rationale**:
- SC-003 requires 100 % WCAG AA passing. Manual review scales poorly; automated axe + visual regression gives fast, reproducible feedback.
- Component-level + integration-level catches two different bug classes: components-in-isolation (focus ring missing) vs compositions (insufficient contrast when a muted-text card sits on an elevated background).
- `@axe-core/playwright` is the de-facto standard; no custom tooling.
- Visual regression at 3 viewports catches the responsive-edge-case regressions (FR-017) cheaply.

**Alternatives considered**:
- *Storybook + `@storybook/addon-a11y`*: rejected for Step 1. Storybook adds significant setup; the per-component Playwright tests cover the same ground with less tooling. Storybook can be added later for documentation purposes.
- *Lighthouse CI*: good for full-page audits but noisy on micro-components. Complements, does not replace, axe per-component.
- *Manual a11y audits only*: rejected. Scales poorly; SC-003 demands automation.

---

## Summary

All five Phase-0 questions resolved. No unresolved NEEDS CLARIFICATION items remain. Key design choices carried into Phase 1 contracts:

- **Tailwind v4 with CSS-first `@theme`**; downgrade path documented but not expected.
- **TypeScript tokens → CSS variables → Tailwind theme**, single source of truth flows top-to-bottom.
- **Hard-coded `class="dark"`** on `<html>`; no theme library.
- **Named Lucide imports only**; 12 icons, ~8 KB total.
- **Playwright + axe-core per-component + per-route**, visual regression at 3 viewports, CI-blocking.
