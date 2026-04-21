# Quickstart: VisualAI UI Style — Scaffold & Validate

**Feature**: 001-nexcognit-ui-style

Condensed command-by-command scaffold of `../visualai-frontend/` with this feature's tokens and components applied, plus validation steps.

Target duration: **~90 minutes** from empty directory to a dev server rendering a tokenized dashboard placeholder.

---

## Prerequisites

- Node.js 20+, pnpm 9+, git configured.
- Clone sibling to `MoneyPrinterTurbo/`:
  ```
  /Users/amraeid/Dropbox/Dev.lab/Cursor-Cluade/NexCognit-Content-generator/
  ├── MoneyPrinterTurbo/         # Layer 3 rendering engine (this repo)
  └── visualai-frontend/         # Layer 1 frontend (created by this quickstart)
  ```

---

## 1. Scaffold (≈ 5 min)

```sh
cd /Users/amraeid/Dropbox/Dev.lab/Cursor-Cluade/NexCognit-Content-generator/
pnpm create next-app@latest visualai-frontend \
  --typescript \
  --app \
  --src-dir \
  --tailwind \
  --eslint \
  --import-alias "@/*"

cd visualai-frontend
pnpm add lucide-react class-variance-authority clsx tailwind-merge
pnpm add -D @axe-core/playwright playwright @playwright/test vitest
```

---

## 2. Drop in the token source files (≈ 10 min)

Create the token files per [contracts/design-tokens.md](contracts/design-tokens.md):

```sh
mkdir -p src/lib/tokens
```

- `src/lib/tokens/colors.ts` — 9 color tokens, `as const`.
- `src/lib/tokens/typography.ts` — 6 typography tokens.
- `src/lib/tokens/spacing.ts` — spacing + stroke + radius.
- `src/lib/tokens/motion.ts` — three motion tokens.
- `src/lib/tokens/index.ts` — re-export.

Copy-paste the exact shape from the contract. Values must match the spec exactly (hex values from Figma node `1:110`).

---

## 3. Overwrite `src/app/globals.css` (≈ 5 min)

Replace the generated file with the full `@theme` block from [contracts/design-tokens.md §"CSS variable emission"](contracts/design-tokens.md). Include the `prefers-reduced-motion` override.

---

## 4. Wire Roboto in `src/app/layout.tsx` (≈ 5 min)

Copy the `layout.tsx` snippet from [contracts/theming-integration.md §7](contracts/theming-integration.md). Hard-code `className="dark"` on `<html>`.

---

## 5. Initialize shadcn/ui (≈ 15 min)

```sh
pnpm dlx shadcn@latest init
```

Answer prompts per [contracts/theming-integration.md §5](contracts/theming-integration.md). **Immediately delete** shadcn's CSS-var block from `globals.css` — keep only the NexCognit `@theme`.

Add base primitives:

```sh
pnpm dlx shadcn@latest add button input textarea
```

Re-theme each by replacing `bg-primary`/`text-primary-foreground` with NexCognit token classes (`bg-accent`/`text-primary`).

---

## 6. Build the seven component patterns (≈ 30 min)

Author new or re-theme:

- `src/components/ui/Stepper.tsx` (new) — per component-api.md
- `src/components/ui/ContentCard.tsx` (new)
- `src/components/ui/OptionCard.tsx` (new)
- `src/components/ui/Button.tsx` (re-theme from shadcn)
- `src/components/ui/Input.tsx` (re-theme)
- `src/components/ui/Textarea.tsx` (re-theme)
- `src/components/ui/Select.tsx` (new, wrapping Radix)

Each export named props + component. Reference tokens only; no hex.

---

## 7. Add the ESLint token-guard rule (≈ 5 min)

Edit `eslint.config.mjs` to add the `no-restricted-syntax` rules per [contracts/theming-integration.md §8](contracts/theming-integration.md).

Verify:

```sh
pnpm lint
# Then deliberately write a hex value in src/components/ui/Stepper.tsx
# Run lint again — MUST fail with the custom message.
# Revert the test hex.
```

---

## 8. Set up Playwright + axe-core (≈ 15 min)

Create `playwright.config.ts` per theming-integration.md §9.

Build `src/app/sandbox/<component>/page.tsx` routes that render each component in its interaction states.

Write `tests/accessibility/<component>.spec.ts` for all seven patterns; each test runs axe in at least 3 states (default, hover, focus).

Run:

```sh
pnpm playwright install
pnpm playwright test
```

All tests MUST pass with zero a11y violations.

---

## 9. Smoke-test the dashboard placeholder (≈ 5 min)

Make `src/app/page.tsx` a minimal dashboard:

```tsx
import { Home, Folder, Briefcase, CreditCard } from "lucide-react";
import { OptionCard } from "@/components/ui/OptionCard";

export default function Dashboard() {
  return (
    <main className="min-h-screen bg-background text-primary p-6">
      <h1 className="text-h1 text-primary mb-6">What are you making today?</h1>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <OptionCard icon={Home}       title="Short Marketing Video"   description="15–90s vertical ad" />
        <OptionCard icon={Folder}     title="Product Shoot Generator" description="Coming in Step 3" comingSoon />
        <OptionCard icon={Briefcase}  title="UGC Avatar Ad"           description="Coming in Step 4" comingSoon />
        <OptionCard icon={CreditCard} title="Faceless Channel"        description="Coming in Step 3" comingSoon />
      </div>
    </main>
  );
}
```

Then:

```sh
pnpm dev
# Open http://localhost:3000
```

Expected: dark slate background, white heading, 4 option cards in the 2-column grid, each styled per tokens, one card interactive and three showing coming-soon states.

---

## 10. Verify Success Criteria (≈ 15 min)

Walk through [spec.md §Success Criteria](spec.md):

| SC | Validation |
|---|---|
| SC-001 (trust rating ≥ 7/10) | Manual user test post-Step 1; not automated |
| SC-002 (visual consistency) | Playwright visual-regression passes across 3 viewports |
| SC-003 (WCAG AA) | `pnpm playwright test tests/accessibility` → 0 violations |
| SC-004 (wizard completion time) | Out of scope here; validated when spec 002's wizard ships |
| SC-005 (option-grid selection ≤ 5 s) | Out of scope here; validated post-launch |
| SC-006 (keyboard nav) | Manual keyboard-only walkthrough of sandbox routes |
| SC-007 (no dead design) | Confirm every token + pattern consumed by at least the dashboard placeholder |

At the end of this quickstart, SC-002, SC-003, SC-006, and SC-007 can be verified. The user-facing SCs (SC-001, SC-004, SC-005) wait for later features.

---

## What happens if a step fails

| Step | Symptom | Fix |
|---|---|---|
| 1 | `create-next-app` fails | Check Node version (needs 18.17+); clear pnpm cache |
| 3 | Classes like `bg-card` don't apply | Verify `globals.css` has the `@theme` block and Tailwind scanned `src/**`; restart dev server |
| 5 | shadcn init overwrites `globals.css` | Restore the NexCognit `@theme` block from git |
| 6 | Components render with wrong colors | Audit the re-themed classes; remove any `bg-primary` / `text-primary-foreground` shadcn defaults |
| 8 | axe finds contrast violations | Spec's tokens pass WCAG AA by design; violation means a component is mis-combining tokens (e.g., muted text on muted background) |

---

## After this quickstart completes

This feature is "implementation ready." The next SpecKit step is `/speckit-tasks` on this branch (`001-nexcognit-ui-style`) to break the above into an ordered task list that Step 1 can execute.

In parallel, the Step 1 MVP build uses these tokens and components immediately — the Creation Wizard, Dashboard, and Admin Credit Panel will all compose from this design system.
