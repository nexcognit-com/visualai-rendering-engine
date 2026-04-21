# Contract: Component Pattern APIs

**Feature**: 001-nexcognit-ui-style
**Consumer**: downstream UI features that compose screens from these components.
**Authority**: this document + [spec.md FR-006..FR-018](../spec.md) + [data-model.md](../data-model.md).

Seven component patterns. TypeScript prop types, required variants, and interaction-state machines for each. Components live at `src/components/ui/` in the frontend repo.

---

## 1. `Stepper`

**Purpose**: multi-step progress indicator with numbered circles + labels + animated progress bar. Implements FR-006, User Story 2.

```ts
export interface StepperProps {
  /** Ordered list of steps. */
  steps: StepperStep[];
  /** Index of the current step, 0-based. */
  currentIndex: number;
  /** Optional click handler for steps the user can navigate to. */
  onStepClick?: (index: number) => void;
  className?: string;
}

export interface StepperStep {
  label: string;                       // e.g., "Category"
  description?: string;                // Optional second line
  status?: "upcoming" | "current" | "completed";  // Derived from currentIndex if omitted
}
```

**Visual states**:

| State | Circle background | Circle border | Number color | Label |
|---|---|---|---|---|
| upcoming | `bg-elevated` | `border-border-strong` | `text-primary` | `text-muted` Regular |
| current | `bg-accent` | `border-accent` + blue glow | `text-primary` Bold | `text-primary` Bold |
| completed | `bg-accent` | `border-accent` | `text-primary` + check glyph | `text-muted` Regular |

**Progress bar**:
- Rendered below the row of circles.
- Track: `bg-accent-track`, rounded-full.
- Fill: `bg-accent`, animated `width: (currentIndex / (steps.length - 1)) × 100%` over 250 ms ease-out.
- Must respect `prefers-reduced-motion: reduce`.

**Accessibility**:
- Outer element uses `role="navigation"` with `aria-label="Step progress"`.
- Each step uses `aria-current="step"` on the current item only.
- Keyboard navigation: left/right arrows move focus across steps when `onStepClick` is provided.

**Responsive**:
- ≥ 768 px: horizontal row.
- < 768 px: collapse to compact "Step K of N: {current label}" text indicator.

---

## 2. `ContentCard`

**Purpose**: large container for page content. Implements FR-007.

```ts
export interface ContentCardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
  /** Optional card title rendered at top with section-title typography. */
  title?: string;
  /** Optional subtitle under the title with body-muted typography. */
  subtitle?: string;
  /** Padding preset. Default: "normal" (24 px). */
  padding?: "normal" | "compact";       // compact = 16 px
}
```

**Visual**:
- Background: `bg-card`.
- Border: 1 px `border-subtle`, `rounded-xl` (12 px).
- Subtle shadow: `shadow-sm` (Tailwind default is fine).
- Padding: 24 px normal / 16 px compact.

**Accessibility**:
- If `title` provided, the title renders as an `h2` element by default. Consumers can override via `as`.
- `role="region"` with `aria-labelledby` pointing at the title id when present.

---

## 3. `OptionCard`

**Purpose**: selectable grid item with icon + title + description. Implements FR-008, User Story 3.

```ts
export interface OptionCardProps {
  icon: React.ComponentType<{ className?: string }>;  // a Lucide icon
  title: string;
  description: string;
  selected?: boolean;
  disabled?: boolean;
  onClick?: () => void;
  /** Renders a "Coming in Step N" badge instead of selection state. */
  comingSoon?: boolean;
  className?: string;
}
```

**Visual states**:

| State | Background | Border | Title color | Description |
|---|---|---|---|---|
| default | `bg-card` | `border-subtle` (1 px) | `text-muted` | `text-muted` |
| hover | `bg-card` + subtle shadow | `border-accent` | `text-muted` | `text-muted` |
| selected | `bg-elevated` | `border-accent` (2 px) + check glyph top-right | `text-primary` SemiBold | `text-muted` |
| disabled | `bg-card` @ 50 % opacity | `border-subtle` | `text-muted` @ 50 % | no pointer events |
| comingSoon | `bg-card` @ 70 % opacity | `border-subtle` | `text-muted` | `"Coming in Step N"` badge top-right |

**Transitions**:
- Border color: 150 ms ease-out.
- Shadow: 150 ms ease-out.

**Accessibility**:
- Renders as `<button>` when `onClick` is provided; otherwise `<div role="button">`.
- `aria-pressed={selected}` when part of a radio-like group.
- Visible focus ring per design-tokens contract.
- The selection cue MUST include a check glyph in addition to the color change (FR color-blind edge case).

**Layout**:
- Uniform height within a grid row, even when titles wrap to 2 lines (FR edge case).
- Icon centered at top, 32 px square.
- Title 14 px SemiBold; description 12 px Regular; 8 px vertical spacing.

---

## 4. `Button`

**Purpose**: primary action or secondary/ghost action. Implements FR-009 and FR-010. Two variants in one component.

```ts
export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost";
  size?: "sm" | "md" | "lg";            // defaults to md
  leftIcon?: React.ComponentType<{ className?: string }>;
  rightIcon?: React.ComponentType<{ className?: string }>;
  loading?: boolean;                    // renders spinner, disables button
}
```

**Variants**:

| Variant | Background | Text | Border | Hover |
|---|---|---|---|---|
| primary | `bg-accent` | `text-primary` SemiBold | none | 10 % darker accent fill |
| secondary | `bg-elevated` | `text-primary` | `border-subtle` 1 px | `bg-card` + `border-accent` |
| ghost | transparent | `text-muted` | transparent | `bg-elevated` |

**Sizes**:

| size | Padding | Font | Icon size |
|---|---|---|---|
| sm | 8 px / 12 px | 12 px / 400 | 16 px |
| md | 10 px / 16 px | 14 px / 600 | 16 px |
| lg | 14 px / 24 px | 14 px / 600 | 20 px |

**States**: default / hover / focus / active / disabled / loading.

**Accessibility**:
- `aria-disabled` mirrors `disabled` prop.
- While `loading`, button is disabled and emits an `aria-live="polite"` announcement "Loading."
- Focus ring per design-tokens contract.

---

## 5. `Input`

**Purpose**: single-line text input. Implements FR-011.

```ts
export interface InputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "size"> {
  label?: string;
  helperText?: string;
  error?: string;                 // When present, renders error state
  leftIcon?: React.ComponentType<{ className?: string }>;
  rightElement?: React.ReactNode; // e.g., clear button, unit label
}
```

**States**:

| State | Background | Border | Text | Notes |
|---|---|---|---|---|
| default | `bg-elevated` | `border-subtle` | `text-primary` | placeholder `text-muted` |
| focus | `bg-elevated` | `border-accent` + 2 px accent glow | `text-primary` | |
| disabled | `bg-card` | `border-subtle` | `text-muted` | `cursor-not-allowed` |
| error | `bg-elevated` | destructive color (consuming spec defines) | `text-primary` | error text rendered below |

**Typography**: body (14 px Regular); label is body (14 px Regular `text-muted`); helperText is small (12 px Regular `text-muted`); error is small in destructive color.

**Accessibility**:
- `aria-describedby` points at helperText OR error when present.
- `aria-invalid={!!error}`.
- Label and input linked via `htmlFor`.

---

## 6. `Textarea`

**Purpose**: multi-line text input. Implements FR-011.

```ts
export interface TextareaProps extends Omit<React.TextareaHTMLAttributes<HTMLTextAreaElement>, "rows"> {
  label?: string;
  helperText?: string;
  error?: string;
  rows?: number;                  // defaults to 4
  /** Shows character count when maxLength is set. */
  showCount?: boolean;
}
```

Visual states match `Input`. Additional behavior:
- Auto-resize optional via `rows="auto"` in a future revision.
- Character count rendered in bottom-right using small typography when `showCount` + `maxLength` both set.

---

## 7. `Select`

**Purpose**: dropdown selector. Built on Radix `Select` primitive. Implements FR-012.

```ts
export interface SelectProps {
  label?: string;
  helperText?: string;
  error?: string;
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  disabled?: boolean;
  placeholder?: string;
  children: React.ReactNode;       // SelectItem children
}

export interface SelectItemProps {
  value: string;
  children: React.ReactNode;
  disabled?: boolean;
}
```

**Closed state**: visual parity with `Input` at rest.
**Open state**: dropdown panel mirrors OptionCard styling — `bg-card`, 1 px `border-subtle`, `rounded-xl`, items on hover show `bg-elevated`, selected item shows accent check glyph + `text-primary` SemiBold.

**Accessibility**:
- Provided automatically by Radix — `role="combobox"`, `aria-expanded`, `aria-controls`, keyboard nav.

**Responsive**: on touch devices, the dropdown expands to fill the viewport width below the trigger.

---

## Global rules (apply to all seven)

1. **Every interactive component renders the universal focus ring**: 2 px accent outline, 2 px offset, using `focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background`.
2. **No inline styles for color/typography/spacing** — Tailwind classes or CSS vars only. Enforced by ESLint.
3. **Every transition respects `prefers-reduced-motion: reduce`** via the global override in `globals.css`. No component declares its own reduced-motion handling.
4. **Emoji / ASCII icons are forbidden**. Lucide icons only (FR-013). Enforced by ESLint rule targeting non-ASCII emoji codepoints in JSX string children.
5. **All text renderings use typography tokens** — no bare `text-[14px] font-[600]` etc. Consumers use `text-body`, `text-h1`, `text-button`, etc.
6. **All components export named TypeScript types** alongside the component so consumers can type their composed variants.
