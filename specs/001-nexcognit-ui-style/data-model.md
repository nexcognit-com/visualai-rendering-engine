# Data Model: VisualAI UI Style — Nexcognit Design Language

**Phase**: 1 — Design & Contracts
**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

"Data model" here is the token catalog and component-pattern inventory. No database, no runtime-persisted entities.

---

## Entity: Design Token (abstract)

A named, semantically-purposed visual value. Every token has:

| Field | Type | Constraints |
|---|---|---|
| `name` | string | Kebab-case, semantic (e.g., `card-background`, not `slate-900`) |
| `category` | enum | `color | typography | spacing | radius | stroke | motion` |
| `value` | string | Category-dependent; see sub-types |
| `tailwind_class` | string | The Tailwind utility prefix this token maps to (e.g., `bg-card`) |
| `css_var` | string | The emitted CSS variable (e.g., `--color-card`) |
| `source` | enum | `figma:node:1:110` (reference), `visualai-product` (product decision not in Figma) |

---

## Entity: Color Token

Extends Design Token. The nine color tokens derived from Figma node `1:110`:

| Name | Value | Tailwind | CSS var | Role |
|---|---|---|---|---|
| `page-background` | `#020617` | `bg-background` | `--color-background` | Body background, below cards |
| `card-background` | `#0F172A` | `bg-card` | `--color-card` | Content cards, elevated panels |
| `elevated-surface` | `#1E293B` | `bg-elevated` | `--color-elevated` | Hover state, selected cards, filled buttons at rest |
| `border-subtle` | `#334155` | `border-subtle` | `--color-border-subtle` | Default card and input borders |
| `border-strong` | `#475569` | `border-strong` | `--color-border-strong` | Stepper circle borders on upcoming states |
| `text-primary` | `#FFFFFF` | `text-primary` | `--color-text-primary` | Headings, body on dark surfaces |
| `text-muted` | `#94A3B8` | `text-muted` | `--color-text-muted` | Subtitles, hints, upcoming-step labels |
| `accent` | `#3B82F6` | `bg-accent` / `text-accent` / `border-accent` | `--color-accent` | Primary CTA, active stepper circle, focus ring |
| `accent-track` | `#3B82F633` | `bg-accent-track` | `--color-accent-track` | Progress-bar unfilled track, subtle accent wash |

**Validation**: every color token MUST pass WCAG 2.1 AA contrast when used as text on its intended background. Validated by an automated check during the Tailwind config build.

---

## Entity: Typography Token

Extends Design Token. Six semantic tokens:

| Name | Size | Weight | Line height | Letter spacing | Tailwind |
|---|---|---|---|---|---|
| `h1` | 30 px | 700 Bold | 36 px | 0 | `text-h1` |
| `h3` | 20 px | 600 SemiBold | 28 px | 0 | `text-h3` |
| `section-title` | 16 px | 600 SemiBold | 16 px | −0.4 px | `text-section` |
| `body` | 14 px | 400 Regular | 20 px | 0 | `text-body` |
| `small` | 12 px | 400 Regular | 16 px | 0 | `text-small` |
| `button` | 14 px | 600 SemiBold | 20 px | 0 | `text-button` |

Font family: **Roboto** (single typeface, 4 weights: 400 / 500 / 600 / 700).

**Validation**: every typography token is declared once in `src/lib/tokens/typography.ts` and every `<Text>` / heading rendering MUST reference the token, not inline size/weight values.

---

## Entity: Spacing Token

Extends Design Token. Four values + stroke weight:

| Name | Value | Tailwind |
|---|---|---|
| `space-1` | 4 px | `p-1` / `m-1` / `gap-1` |
| `space-2` | 8 px | `p-2` / `m-2` / `gap-2` |
| `space-4` | 16 px | `p-4` / `m-4` / `gap-4` |
| `space-6` | 24 px | `p-6` / `m-6` / `gap-6` |
| `stroke-1` | 1 px | `border` / `border-t` (default weight) |

Only these spacing values are allowed in components; other pixel values require explicit justification in code review.

---

## Entity: Radius Token

| Name | Value | Tailwind | Role |
|---|---|---|---|
| `radius-button` | 8 px | `rounded` | Buttons, Option Cards, form inputs |
| `radius-card` | 12 px | `rounded-xl` | Content Cards |
| `radius-pill` | 999 px | `rounded-full` | Stepper circles, progress bar |

---

## Entity: Motion Token

| Name | Value | Role |
|---|---|---|
| `transition-hover` | 150 ms ease-out | Option Card border color, Button fill |
| `transition-progress` | 250 ms ease-out | Stepper progress-bar width |
| `transition-fast` | 100 ms ease-out | Focus-ring appear |

**Constraint**: all three MUST respect `prefers-reduced-motion: reduce` — implemented via a single `@media (prefers-reduced-motion: reduce)` override in `globals.css` that zeroes all transition durations.

---

## Entity: Component Pattern (abstract)

A reusable UI building block with a fixed token set and fixed interaction states. Every Component Pattern has:

| Field | Type | Notes |
|---|---|---|
| `name` | string | Component file name (e.g., `Stepper`) |
| `tokens_consumed` | Token[] | Enumerated in `contracts/component-api.md` |
| `states` | State[] | default / hover / focus / active / disabled / selected / error |
| `accessibility` | A11yRequirement[] | Focus ring, ARIA roles, keyboard navigation |

### The seven patterns

| Name | FR | Role |
|---|---|---|
| `Stepper` | FR-006 | Numbered circles + labels + animated progress bar |
| `ContentCard` | FR-007 | Large container with 12 px radius, 1 px border, 24 px padding |
| `OptionCard` | FR-008 | Grid item with icon + title + description, hover & selected |
| `Button` (primary variant) | FR-009 | Dodger Blue fill + white SemiBold label + 8 px radius + focus ring |
| `Button` (secondary/ghost variant) | FR-010 | Transparent fill + subtle border + elevated-hover state |
| `Input` / `Textarea` | FR-011 | Dark-slate fill + 1 px border + blue-glow on focus |
| `Select` | FR-012 | Parity with Input at rest; open state mirrors OptionCard styling |

### Universal interaction states required

| State | Trigger | Visual cue |
|---|---|---|
| default | at rest | component's base token set |
| hover | pointer over | elevated background OR accent border (component-specific) |
| focus | keyboard focus | 2 px accent outline at 2 px offset (FR-014) |
| active | mouse down | depressed effect (slight scale) |
| disabled | `disabled` attr | 50 % opacity + no pointer events |
| selected (OptionCard only) | click | accent border + elevated background + primary text |
| error (Input/Textarea/Select only) | validation failure | destructive border color (defined by consuming feature's spec) |

---

## Entity: Screen Composition

A named page composition that consumes one or more Component Patterns. This feature does NOT implement any Screen Composition — it only catalogs which ones will consume the design system. Future features (Mode 2 Wizard, Admin Credit Panel, etc.) implement the compositions.

| Screen | Composed of | Owner feature |
|---|---|---|
| Dashboard | Sidebar + H1 + OptionCard (× 5 mode cards) | Step 1 build (frontend) |
| Creation Wizard | Stepper + ContentCard + Input + Select + Textarea + Button | spec 002 (video-duration-variations) |
| Asset Library | Sidebar + grid of media cards (derived from OptionCard) | Step 4+ |
| Billing & Credits | Sidebar + ContentCard + Button | Step 4 |
| Onboarding | Stepper + OptionCard + Button | Step 4 |
| Admin Credit Panel | Sidebar + ContentCard + Input + Button + audit-log table | spec 003 (admin-credit-panel) |

---

## Validation rules (enforced across the token + component system)

1. **Token exclusivity**: a component MUST NOT declare a color, size, or spacing value not present in the token catalog. Enforced by ESLint rule (`no-restricted-syntax` targeting hex regex and bare `px` values in component source).
2. **Token-to-CSS-var bijection**: every token named in `src/lib/tokens/` MUST emit exactly one CSS variable; every CSS variable MUST correspond to a token. Enforced by a build-time assertion.
3. **Component-pattern coverage**: every Screen Composition MUST be implementable using only the seven patterns (plus layout primitives). A new pattern added requires a MINOR spec amendment (v1.1.0).
4. **Dark-mode-only invariant**: no token file declares a light-mode alternative. If light mode is ever added, it's a new feature spec.
5. **Interaction-state completeness**: every interactive component MUST implement all six universal interaction states plus its pattern-specific states. Enforced by Storybook (when added) or by Playwright state-coverage tests.
6. **Transition respect for reduced-motion**: every transition MUST be wrapped in a `@media (prefers-reduced-motion: reduce)` fallback that zeroes duration. Enforced by a single global rule.
7. **Focus-ring uniformity**: every interactive component renders the same 2 px accent focus ring. Component-specific focus-ring overrides are forbidden.

---

## Relationships

```
Design Token (9 color + 6 typography + 5 spacing/stroke + 3 radius + 3 motion)
     │
     ├──► tailwind.config.ts (theme.extend references CSS vars)
     │
     ├──► src/app/globals.css (@theme { --color-*: ... } emits CSS vars)
     │
     └──► src/lib/tokens/*.ts (TypeScript source of truth, consumed at dev/build time)

Component Pattern (7 patterns)
     │
     ├──► tokens_consumed: subset of Design Token
     │
     ├──► states: 6 universal + pattern-specific
     │
     └──► composed into Screen Compositions by downstream features
```
