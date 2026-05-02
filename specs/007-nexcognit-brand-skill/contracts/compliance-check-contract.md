# Contract: Brand Compliance Check (encodes FR-006)

**Feature**: [spec.md](../spec.md) | **Plan**: [plan.md](../plan.md) | **Data Model**: [data-model.md §Entity 7](../data-model.md)

This contract defines the deterministic checklist the agent MUST run on its own UI output before returning it. It encodes the tiered substitute/refuse policy chosen in clarification Q4 (FR-006) and the accessibility refusals (FR-003 + accessibility.md). Drift between this contract and FR-006 is a v1 bug.

## Tier definitions

### Substitute tier

When the developer requests a value outside the documented set for any of the following property classes, the agent picks the nearest documented token, applies it, and emits a one-line explanation citing the substituted token by name.

| Property class | Source set | "Nearest" rule |
|---|---|---|
| **Color** (background / text / border / accent / shadow tint) | tokens.md §Colors | Lowest perceptual distance in OKLCH space among documented tokens. Ties broken in favor of the more semantically appropriate token (e.g., `--color-accent` over `--color-border-strong` for an "interactive element" color). |
| **Spacing** (margin, padding, gap) | {4, 8, 16, 24} px | Closest absolute value. Tie broken in favor of the larger value (errs on the side of generous whitespace). |
| **Border-radius** | {8, 12, ≥999} px | Closest absolute value, with these semantic shortcuts: button-shaped → 8 px, card-shaped → 12 px, pill → ≥999 px. |
| **Shadow / elevation** | tokens.md §Shadow | Closest documented elevation token; flat surfaces use no shadow rather than substituting the smallest. |

The explanation line MUST follow this shape:

> Substituted requested `<input>` with `<token-name>` (closest documented token).

Examples:
- "Substituted requested `#FF5733` with `--color-accent` (closest documented token)."
- "Substituted requested `7px` margin with `8px` (closest documented spacing step)."
- "Substituted requested `15px` radius with `12px` (closest documented card radius)."

### Refuse tier

For these property classes, the agent refuses with a one-line reason and names the documented alternative. The agent MUST NOT pick a "closest" value and MUST NOT weaken the rule under any framing including "for the demo," "I'll fix it later," or "this is a special case."

| Property class | Source | Refusal language |
|---|---|---|
| **Typography (typeface)** | spec 001 FR-002 | "Cannot use `<requested>` — approved typeface is Roboto only (weights 400/500/600/700). Pick a weight." |
| **Typography (size/weight outside scale)** | spec 001 FR-003 | "Cannot use `<requested>` — approved sizes are H1 30/700, H3 20/600, Section 16/600, Body 14/400, Small 12/400, Button 14/600. Pick a token." |
| **Focus ring** (removal, downgrade) | spec 001 FR-014 | "Cannot remove or downgrade focus ring — keyboard-focus visibility is a non-negotiable a11y rule. Use the documented 2 px Dodger-Blue ring with 2 px offset." |
| **Contrast (failing WCAG AA)** | spec 001 FR-015 | "Cannot apply that color combination — pair fails WCAG AA contrast. Documented compliant pairs in tokens.md / accessibility.md." |
| **Reduced-motion respect** | spec 001 FR-016 | "Cannot disable `prefers-reduced-motion: reduce` handling — required a11y rule. Animation MUST honor the user OS preference." |
| **Color-only state encoding** | spec 001 Edge Case + accessibility.md Rule 4 | "Cannot encode `<state>` with color alone — color-blind-safe rule requires an additional non-color signal (border-width change or check glyph)." |
| **Semantic markup downgrade** (`<button>` → `<div>` etc.) | implicit in FR-006..FR-012 | "Cannot use a non-semantic element for an interactive control — required for a11y. Use `<button>` / `<a>` / proper form element." |
| **Keyboard reachability removal** | accessibility.md Rule 6 | "Cannot remove keyboard reachability — required a11y rule. Every interactive element MUST be reachable via Tab." |

The agent MUST NOT propose an off-brand workaround. If pressed (e.g., "I really need it just this once"), the agent MUST hold the line and offer to escalate to design.

## Self-validation procedure

Before the agent returns a UI snippet to the developer, it MUST execute this procedure in order:

1. **Scan tokens used.** For every hex, font name, custom radius, custom shadow, custom spacing in the snippet:
   - If documented in `tokens.md` → pass.
   - If undocumented and in a Substitute-tier class → apply substitution, emit one-line explanation.
   - If undocumented and in a Refuse-tier class → halt, emit refusal, ask for picker input.
2. **Check focus state on every interactive element.** Buttons, links, inputs, selects, dialogs MUST have a visible focus ring. Missing focus ring → halt, emit refusal per Rule 1.
3. **Check semantic markup.** Any interactive element rendered as `<div>` / `<span>` / `<p>` → halt, emit refusal per Semantic markup rule.
4. **Check color-only state.** Any component with a "selected", "active", "error", or "success" state encoded only by color change → halt, emit refusal per Color-only state encoding rule.
5. **Check contrast.** Every text-on-background pair → if not in the documented compliant pairs → halt, emit refusal per Contrast rule.
6. **Check reduced-motion handling.** Any animation/transition longer than 0 ms → if no `prefers-reduced-motion: reduce` handling → halt, emit refusal per Reduced-motion rule.

The agent MUST NOT return a snippet that fails any check. If a check halts, the agent rewrites the snippet before returning it (or, if the rewrite would require a refused property change, asks the developer for an explicit choice).

## Mandatory visibility

Every Substitute or Refuse action MUST be visible to the developer in the response:

- Substitutions: one line per substitution, listed at the end of the response.
- Refusals: one line per refusal, listed before the (rewritten or partial) snippet.

Silent acceptance (a snippet that quietly omits the focus ring with no note) is a v1 violation regardless of how minor.

## Examples (golden behavior)

### Example 1 — Substitute (color)

**Developer**: "Make the CTA button orange — try `#FF5733`."

**Agent (correct response)**:
```tsx
export function PrimaryButton({ children }: { children: React.ReactNode }) {
  return (
    <button className="rounded-[8px] bg-[var(--color-accent)] ...">
      {children}
    </button>
  );
}
```
> Substituted requested `#FF5733` with `--color-accent` (closest documented token).

### Example 2 — Refuse (typography)

**Developer**: "Use Comic Sans for the headers."

**Agent (correct response)**:
> Cannot use Comic Sans — approved typeface is Roboto only (weights 400/500/600/700). Pick a weight.

(No snippet. Agent waits for the developer to choose.)

### Example 3 — Refuse (focus ring removal)

**Developer**: "Remove the focus ring from the button — it looks ugly."

**Agent (correct response)**:
> Cannot remove or downgrade focus ring — keyboard-focus visibility is a non-negotiable a11y rule. Use the documented 2 px Dodger-Blue ring with 2 px offset.

### Example 4 — Substitute + refuse in same prompt

**Developer**: "Make the dialog `#FF0000` with no focus trap."

**Agent (correct response)**:
> Cannot remove focus trap — modal dialogs require focus trapping for keyboard a11y.
> Substituted requested `#FF0000` with `--color-accent` (closest documented token; for destructive context use the documented destructive variant in components.md).

(Agent then renders a corrected dialog snippet.)

## What this contract does NOT cover

- **How to pick "nearest" perceptually for color**. The agent uses its OKLCH heuristic; the contract doesn't enforce a specific algorithm. Picking a sensible nearest token is a judgement call within the documented set.
- **Layout-level brand opinions** (when to use a 2-column grid vs 3-column). Spec 001 doesn't prescribe layout; the Skill is silent on it.
- **Animation choreography** (timing curves beyond reduced-motion respect). Spec 001 only specifies "≤ 250 ms hover transition"; finer animation work is out of scope.

## Verification (drives task design)

Each example above MUST become an acceptance test in the side-by-side harness:

| Test ID | Prompt | Expected agent response shape |
|---|---|---|
| CC-1 | Color substitute (`#FF5733` → accent) | Correct snippet + one-line substitution note |
| CC-2 | Typography refuse (Comic Sans) | One-line refusal, no snippet |
| CC-3 | Focus-ring refuse | One-line refusal, original snippet preserved |
| CC-4 | Multi-issue (color sub + focus refuse) | Refusal first, then substitution, then corrected snippet |
| CC-5 | Spacing substitute (`7px` → `8px`) | Correct snippet + one-line substitution note |
| CC-6 | Color-only state (selected = blue only) | Refusal, request border-width or glyph addition |
| CC-7 | Contrast violation (white on `#94A3B8`) | Refusal with documented compliant alternative |
| CC-8 | Semantic downgrade (`<div onClick>` for a button) | Refusal, request `<button>` |

These eight tests are the contract surface for `/speckit.tasks` to schedule alongside the eight activation tests in [activation-contract.md](./activation-contract.md).
