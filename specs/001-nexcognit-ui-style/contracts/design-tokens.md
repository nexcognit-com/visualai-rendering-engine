# Contract: Design Token Shape

**Feature**: 001-nexcognit-ui-style
**Consumer**: downstream features that compose UI using these tokens (specs 002, 003, and every future visual feature).
**Authority**: this document + [spec.md FR-001..FR-005](../spec.md) + [data-model.md](../data-model.md).

This contract defines the **TypeScript shape** of the token system and the **CSS variable naming convention**. Downstream features reference tokens by name and receive a guarantee that the name exists, the value conforms to the shape, and the accompanying CSS variable is live.

---

## TypeScript shape (in `src/lib/tokens/`)

### `colors.ts`

```ts
export const colors = {
  background:   "#020617",
  card:         "#0F172A",
  elevated:     "#1E293B",
  borderSubtle: "#334155",
  borderStrong: "#475569",
  textPrimary:  "#FFFFFF",
  textMuted:    "#94A3B8",
  accent:       "#3B82F6",
  accentTrack:  "#3B82F633",
} as const satisfies Record<string, `#${string}`>;

export type ColorToken = keyof typeof colors;
```

### `typography.ts`

```ts
export const typography = {
  h1:          { size: "30px", weight: 700, lineHeight: "36px", letterSpacing: "0" },
  h3:          { size: "20px", weight: 600, lineHeight: "28px", letterSpacing: "0" },
  sectionTitle:{ size: "16px", weight: 600, lineHeight: "16px", letterSpacing: "-0.4px" },
  body:        { size: "14px", weight: 400, lineHeight: "20px", letterSpacing: "0" },
  small:       { size: "12px", weight: 400, lineHeight: "16px", letterSpacing: "0" },
  button:      { size: "14px", weight: 600, lineHeight: "20px", letterSpacing: "0" },
} as const;

export type TypographyToken = keyof typeof typography;
export const fontFamily = "Roboto, system-ui, sans-serif";
export const fontWeights = [400, 500, 600, 700] as const;
```

### `spacing.ts`

```ts
export const spacing = {
  "1": "4px",
  "2": "8px",
  "4": "16px",
  "6": "24px",
} as const;

export const stroke = {
  "1": "1px",
} as const;

export const radius = {
  button: "8px",
  card:   "12px",
  pill:   "999px",
} as const;

export type SpacingToken = keyof typeof spacing;
export type RadiusToken  = keyof typeof radius;
```

### `motion.ts`

```ts
export const motion = {
  hover:    { duration: "150ms", easing: "ease-out" },
  progress: { duration: "250ms", easing: "ease-out" },
  fast:     { duration: "100ms", easing: "ease-out" },
} as const;

export type MotionToken = keyof typeof motion;
```

### `index.ts` re-export

```ts
export * from "./colors";
export * from "./typography";
export * from "./spacing";
export * from "./motion";
```

---

## CSS variable emission (in `src/app/globals.css`)

Tailwind v4 `@theme` directive emits CSS variables from the token objects. The mapping:

| Token object key | CSS variable name |
|---|---|
| `colors.background` | `--color-background` |
| `colors.card` | `--color-card` |
| `colors.elevated` | `--color-elevated` |
| `colors.borderSubtle` | `--color-border-subtle` |
| `colors.borderStrong` | `--color-border-strong` |
| `colors.textPrimary` | `--color-text-primary` |
| `colors.textMuted` | `--color-text-muted` |
| `colors.accent` | `--color-accent` |
| `colors.accentTrack` | `--color-accent-track` |
| `typography.h1.size` | `--text-h1-size` |
| `typography.h1.weight` | `--text-h1-weight` |
| `typography.h1.lineHeight` | `--text-h1-line-height` |
| (same pattern for h3, sectionTitle, body, small, button) | |
| `spacing.4` | `--spacing-4` (Tailwind v4 auto-derives) |
| `radius.button` | `--radius-button` |
| `radius.card` | `--radius-card` |
| `radius.pill` | `--radius-pill` |
| `motion.hover.duration` | `--motion-hover-duration` |

```css
/* src/app/globals.css — excerpt */
@import "tailwindcss";

@theme {
  --color-background: #020617;
  --color-card: #0F172A;
  --color-elevated: #1E293B;
  --color-border-subtle: #334155;
  --color-border-strong: #475569;
  --color-text-primary: #FFFFFF;
  --color-text-muted: #94A3B8;
  --color-accent: #3B82F6;
  --color-accent-track: #3B82F633;

  --font-family-sans: "Roboto", system-ui, sans-serif;

  --text-h1-size: 30px;
  --text-h1-weight: 700;
  --text-h1-line-height: 36px;

  --radius-button: 8px;
  --radius-card: 12px;
  --radius-pill: 999px;

  --motion-hover-duration: 150ms;
  --motion-progress-duration: 250ms;
}

@media (prefers-reduced-motion: reduce) {
  * {
    transition-duration: 0s !important;
    animation-duration: 0s !important;
  }
}
```

---

## Tailwind class catalog (derived from tokens)

Downstream features use these utility classes; they are the primary consumer surface.

| Purpose | Tailwind class | Resolves to |
|---|---|---|
| Page background | `bg-background` | `background-color: var(--color-background)` |
| Card background | `bg-card` | `background-color: var(--color-card)` |
| Elevated / hover surface | `bg-elevated` | `background-color: var(--color-elevated)` |
| Subtle border | `border-subtle` | `border-color: var(--color-border-subtle)` |
| Strong border | `border-strong` | `border-color: var(--color-border-strong)` |
| Primary text | `text-primary` | `color: var(--color-text-primary)` |
| Muted text | `text-muted` | `color: var(--color-text-muted)` |
| Accent (any use) | `bg-accent`, `text-accent`, `border-accent`, `ring-accent` | respective `var(--color-accent)` |
| Accent track | `bg-accent-track` | `background-color: var(--color-accent-track)` |
| H1 text | `text-h1` | composite of size/weight/line-height |
| Body text | `text-body` | composite |
| Button radius | `rounded` | `border-radius: var(--radius-button)` |
| Card radius | `rounded-xl` | `border-radius: var(--radius-card)` |
| Pill / circle | `rounded-full` | `border-radius: var(--radius-pill)` |
| Focus ring | `focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background` | 2 px accent outline, 2 px offset |

---

## Runtime access pattern (TypeScript)

Rare cases when a component needs a token value at runtime (not as a Tailwind class):

```ts
import { colors } from "@/lib/tokens";

// OK — using the TS token as a source of truth
const chartBar = { fill: colors.accent };

// OK — using the CSS variable form for dynamic styles
<div style={{ backgroundColor: "hsl(var(--color-card))" }} />

// NOT OK — hard-coded hex in component source
<div style={{ backgroundColor: "#0F172A" }} />   // ESLint rule blocks this
```

ESLint rule `no-restricted-syntax` forbids hex-color literals (regex `#[0-9a-fA-F]{3,8}`) in files under `src/components/**/*.{ts,tsx}` and `src/app/**/*.{ts,tsx}`. The only files allowed to contain raw hex are `src/lib/tokens/*.ts` and `src/app/globals.css`.

---

## Backwards-compatibility and versioning

- Adding a new token (new color, new typography slot): MINOR design-system bump (v1.1.0). No migration required.
- Changing a token value: MAJOR bump. Requires an announcement; downstream features may need to visually re-verify.
- Removing a token: MAJOR bump. Requires a codemod or migration guide.

This contract is versioned with the spec; the spec's version line governs.

---

## What this contract does NOT cover

- Animation keyframes (future spec when we need loading skeletons, etc.).
- Icon size / stroke-width recommendations (future spec when the icon inventory grows past ~20).
- Elevation / shadow tokens (Figma node `1:110` uses one subtle shadow on the Content Card; documented in `component-api.md` rather than the token catalog since it's used only there).
- Light mode variants (FR-018 forbids; future spec if added).
