# Contract: Theming Integration (Tailwind + shadcn/ui + Tokens)

**Feature**: 001-nexcognit-ui-style
**Consumer**: the frontend repo's setup engineer (tonight in Step 1) and anyone adding new shadcn/ui components later.
**Authority**: this document + [research.md Q1–Q2](../research.md) + [contracts/design-tokens.md](design-tokens.md).

End-to-end explanation of how a token value in TypeScript ends up rendering as a pixel on screen, via Tailwind v4's CSS-first theming and shadcn/ui's CSS-variable pattern.

---

## The flow, end-to-end

```
┌─────────────────────────────────────────────────────┐
│ 1. Source of truth                                  │
│    src/lib/tokens/colors.ts                         │
│    export const colors = { card: "#0F172A", ... }   │
└────────────┬────────────────────────────────────────┘
             │
             │ A build-time script (Step 3 of setup)
             │ syncs TS token values into globals.css.
             │ In Step 1, hand-synced.
             ▼
┌─────────────────────────────────────────────────────┐
│ 2. CSS-variable emission                            │
│    src/app/globals.css                              │
│    @theme { --color-card: #0F172A; ... }            │
└────────────┬────────────────────────────────────────┘
             │
             │ Tailwind v4 picks up @theme at build time.
             ▼
┌─────────────────────────────────────────────────────┐
│ 3. Tailwind utility generation                      │
│    `bg-card` class now resolves to:                 │
│    `background-color: var(--color-card);`           │
└────────────┬────────────────────────────────────────┘
             │
             │ shadcn/ui components, which shadcn's init
             │ script drops into src/components/ui/,
             │ consume these utilities directly:
             │   className="bg-card text-primary"
             ▼
┌─────────────────────────────────────────────────────┐
│ 4. Component render                                 │
│    <OptionCard className="bg-card ..." />           │
│    Resolves to CSS var, resolves to hex, paints.    │
└─────────────────────────────────────────────────────┘
```

---

## Step-by-step setup (one-time, in the frontend repo)

### 1. Scaffold Next.js with Tailwind v4

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
```

### 2. Install peer dependencies

```sh
pnpm add lucide-react class-variance-authority clsx tailwind-merge
pnpm add -D @axe-core/playwright playwright @playwright/test vitest
```

### 3. Drop in the token source files

Create `src/lib/tokens/colors.ts`, `typography.ts`, `spacing.ts`, `motion.ts`, `index.ts` per [contracts/design-tokens.md](design-tokens.md).

### 4. Overwrite `src/app/globals.css`

Replace whatever `create-next-app` generated with the full `@theme` block from [design-tokens.md](design-tokens.md) §"CSS variable emission."

Include the `prefers-reduced-motion` global override.

### 5. Initialize shadcn/ui, pinned to the NexCognit theme

```sh
pnpm dlx shadcn@latest init
```

When prompted:
- Style: `Default`
- Base color: pick any; we'll overwrite the CSS variables.
- Global CSS: `src/app/globals.css` (already exists)
- Tailwind config: `tailwind.config.ts`
- Components directory: `@/components`
- Utilities directory: `@/lib/utils`
- CSS variables: **Yes**
- React Server Components: **Yes**

After init, shadcn has written its own CSS variables into `globals.css` (things like `--background`, `--foreground`, `--primary`). **Delete shadcn's block** and keep only the NexCognit `@theme` block. Update shadcn components to reference NexCognit tokens instead of shadcn's defaults when you add them.

### 6. Add the seven component patterns

```sh
pnpm dlx shadcn@latest add button input textarea
```

Each shadcn import creates a `src/components/ui/<name>.tsx` file. Edit each to:
- Replace `bg-primary` / `text-primary-foreground` etc. with NexCognit tokens (`bg-accent` / `text-primary`).
- Drop light-mode variants.
- Add the focus ring per design-tokens contract.

For components shadcn doesn't ship stock (`Stepper`, `ContentCard`, `OptionCard`), author fresh in `src/components/ui/` following [component-api.md](component-api.md).

### 7. Wire Roboto via `next/font`

`src/app/layout.tsx`:

```tsx
import { Roboto } from "next/font/google";

const roboto = Roboto({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-family-sans",
  display: "swap",
});

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`dark ${roboto.variable}`}>
      <body className="bg-background text-primary antialiased">
        {children}
      </body>
    </html>
  );
}
```

Notes:
- `className="dark"` is hard-coded per [research.md Q3](../research.md). No theme toggle.
- `bg-background text-primary` comes from the NexCognit tokens.

### 8. Add the ESLint token-guard rule

`eslint.config.mjs`:

```js
// … existing config …
rules: {
  "no-restricted-syntax": [
    "error",
    {
      selector: "Literal[value=/^#[0-9a-fA-F]{3,8}$/]",
      message: "Use a design token from @/lib/tokens instead of a raw hex color. See specs/001-nexcognit-ui-style/contracts/design-tokens.md.",
    },
    {
      selector: "TemplateElement[value.raw=/#[0-9a-fA-F]{3,8}/]",
      message: "Use a design token from @/lib/tokens instead of a raw hex color.",
    },
  ],
}
```

Exceptions: the rule is disabled in `src/lib/tokens/*.ts` and `src/app/globals.css` (the only files allowed to declare hex values).

### 9. Configure Playwright with axe-core

`playwright.config.ts`:

```ts
export default {
  testDir: "tests",
  projects: [
    { name: "desktop", use: { viewport: { width: 1440, height: 900 } } },
    { name: "tablet",  use: { viewport: { width: 768,  height: 1024 } } },
    { name: "mobile",  use: { viewport: { width: 360,  height: 640 } } },
  ],
  webServer: { command: "pnpm dev", port: 3000, reuseExistingServer: !process.env.CI },
};
```

Per-component accessibility test template (`tests/accessibility/option-card.spec.ts`):

```ts
import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("OptionCard has no a11y violations in default state", async ({ page }) => {
  await page.goto("/sandbox/option-card?state=default");
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});
```

A dedicated sandbox route `/sandbox/<component>?state=<state>` renders the component isolated in each of its interaction states for testing.

---

## Ongoing maintenance rules

1. **Never add a hex value outside `src/lib/tokens/*.ts` or `src/app/globals.css`.** The ESLint rule is load-bearing.
2. **Never add a shadcn primitive without re-theming it.** shadcn's defaults are NOT our tokens; verify the component's classes use NexCognit tokens (`bg-card`, not `bg-card-foreground`) before committing.
3. **Never hard-code a transition duration in a component.** Use `transition-[property] duration-[--motion-*-duration]` or the Tailwind arbitrary property syntax. The motion tokens are the only source of transition timing.
4. **When adding a new token**: update `src/lib/tokens/*.ts`, the `@theme` block in `globals.css`, and (if a new Tailwind utility family) the Tailwind config. All three land in the same PR.
5. **When updating a token value**: it's a MAJOR version bump of this spec (v2.0.0). Review every screen composition that consumes the token.
6. **Light-mode variants are forbidden** until a future spec explicitly adds one.

---

## Failure modes and debugging

| Symptom | Likely cause | Fix |
|---|---|---|
| Class `bg-card` doesn't render | Missing `@theme` block in `globals.css` or Tailwind didn't scan the file | Verify `globals.css` has the token block; ensure `src/**/*.{ts,tsx}` is in Tailwind's content globs (v4 auto-scans `src`) |
| shadcn component renders with wrong colors | shadcn's own CSS-variable block wasn't deleted; it's overriding ours | Remove any `--background`, `--foreground`, `--primary` etc. declarations that aren't in our token namespace |
| Flash of unstyled content | Roboto loading blocks first paint | Confirm `display: "swap"` on the Roboto import |
| Focus ring looks different on one component | Component declared its own focus ring | Remove the custom focus styling; inherit from the global `focus-visible:ring-*` pattern |
| Dark styling reverts to shadcn defaults after adding a new shadcn component | `pnpm dlx shadcn@latest add` rewrote `globals.css` | Diff `globals.css` against main; restore the `@theme` block |

---

## What this contract does NOT cover

- Component-level business logic (e.g., `OptionCard`'s `onClick` handler when used in the Agent Mode dashboard is a concern of the feature that composes it, not of this design-system contract).
- State management (Zustand / TanStack Query) — future feature specs define that.
- Animation keyframes for loading skeletons — future spec when needed.
- A light-mode theme — explicitly forbidden by FR-018.
- Brand asset handling (logos, illustrations) — future spec.
