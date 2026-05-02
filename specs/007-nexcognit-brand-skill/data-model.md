# Phase 1 Data Model: NexCognit Brand Skill for UI

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Research**: [research.md](./research.md)

The Skill has no runtime database. "Data model" here means the structured artifacts the Skill carries on disk — the entities defined in spec.md (§Key Entities) made concrete with fields, relationships, and validation rules. Every entity below has a 1:1 mapping to a markdown file (or YAML frontmatter section) inside `.claude/skills/nexcognit-brand/`.

---

## Entity 1 — Skill Manifest

**File**: `SKILL.md` (YAML frontmatter only)
**Cardinality**: exactly one per Skill artifact

| Field | Type | Required | Source / Validation |
|---|---|---|---|
| `name` | string | yes | Fixed value `"nexcognit-brand"`. Loader uses this as the Skill identifier; renaming would break every consuming repo. |
| `description` | string (long) | yes | Human + agent-readable summary used by Claude Code to decide relevance. MUST mention "NexCognit", "UI", "brand", "design language" so the loader's relevance match fires for UI prompts and not for unrelated work. |
| `argument-hint` | string | yes | `"(no arguments — Skill activates on relevance)"` at v1. Reserved for a future explicit invocation vocabulary. |
| `compatibility` | string | yes | MUST state "Claude Code only at v1" verbatim. Loader does not enforce; this is a documentation contract aligned with FR-008. |
| `metadata.author` | string | yes | `"NexCognit (Amr Eid)"` |
| `metadata.source` | string | yes | Pointer back to the SpecKit spec: `"specs/007-nexcognit-brand-skill (in nexcognit-com/visualai-rendering-engine)"` |
| `metadata.skill_version` | semver string | yes | `"MAJOR.MINOR.PATCH"`. Independent cadence from spec 001 (FR-005). Bump rules in FR-005 + R6 of research.md. |
| `metadata.tracks_spec_001` | string | yes | The spec 001 version this Skill is aligned to (e.g., `"v1.0"`). Drift detector: when spec 001 advances and this field doesn't, the maintainer is signalled to update the Skill. |
| `metadata.activation_scope` | string | yes | Free-text declaration: `"NexCognit web frontends — repo-local only"`. Documents the scope decided in clarification Q3 even when the artifact is copied between repos. |
| `user-invocable` | boolean | yes | `true` — allows the developer to type `/nexcognit-brand` to invoke explicitly. |
| `disable-model-invocation` | boolean | yes | `false` — allows the agent to self-invoke when relevance is detected. |

**Validation rules**:
- `metadata.skill_version` MUST follow semver (regex `^\d+\.\d+\.\d+$`).
- `metadata.tracks_spec_001` MUST match a real spec 001 version string (initially `"v1.0"`; bumps tracked in spec 001's own version line).
- `description` MUST be ≤ 1024 characters (Claude Code Skills loader convention; oversize descriptions hurt the relevance match).
- `compatibility` MUST NOT claim Cursor / Codex / Copilot support at v1 (FR-008).

**Lifecycle**: the Manifest is rewritten on every Skill version bump. There is no draft-vs-active state at v1; if the tracked spec 001 is itself in draft, the Manifest's `description` MUST add a `(draft)` suffix and the Skill MUST surface that on first UI prompt (per spec.md edge case "Skill loaded but spec 001 has not yet been merged").

---

## Entity 2 — Brand Token Set

**File**: `tokens.md`
**Cardinality**: one document, six token groups (color, typography, spacing, radius, shadow/elevation, motion)

**Schema** (markdown sections + tables):

```markdown
## Colors
| Name | Hex | Usage |
|------|-----|-------|
| `--color-bg-page`     | #020617 | Page background |
| `--color-bg-card`     | #0F172A | Card background |
| `--color-bg-elevated` | #1E293B | Elevated / hover surface |
| `--color-border-subtle` | #334155 | Divider / subtle border |
| `--color-border-strong` | #475569 | Strong border |
| `--color-text-primary` | #FFFFFF | Primary text |
| `--color-text-muted`   | #94A3B8 | Muted text |
| `--color-accent`       | #3B82F6 | Primary accent (Dodger Blue) |
| `--color-accent-track` | #3B82F633 | Accent at 20% opacity (progress-bar track) |

## Typography
| Token | Size | Weight | Line height | Notes |
|-------|------|--------|-------------|-------|
| H1 | 30 px | 700 | 36 px | |
| H3 | 20 px | 600 | 28 px | |
| Section title | 16 px | 600 | 16 px | letter-spacing −0.4 px |
| Body | 14 px | 400 | 20 px | |
| Small / hint | 12 px | 400 | 16 px | |
| Button label | 14 px | 600 | 20 px | |

## Spacing
4 / 8 / 16 / 24 px

## Border-radius
8 px (buttons, option cards) · 12 px (large cards) · ≥999 px (stepper circles, progress bars)

## Stroke
1 px for all borders

## Motion
Hover transitions ≤ 250 ms · respect `prefers-reduced-motion: reduce`
```

**Validation rules**:
- Every hex MUST exactly match the spec 001 catalog (R2 of research.md).
- Token names MUST follow the `--color-*` / no-prefix-for-others convention used in spec 001's downstream consumer (`visualai-frontend/tailwind.config.ts`). Renaming a token forces a MAJOR bump (FR-005).
- Adding a new token forces at least a MINOR bump.

**Relationships**: every Component Pattern (Entity 3) and Worked Example (Entity 6) MUST cite tokens by name from this file rather than re-stating hex values inline. This makes the Skill's source-of-truth model crisp: tokens own values, components own composition, examples own shape.

---

## Entity 3 — Component Pattern

**File**: `components.md` (one section per pattern)
**Cardinality**: 7 patterns at v1 (matches spec 001 FR-006..FR-013)

**Per-pattern schema** (each section follows this shape):

```markdown
### <Pattern Name>

- **Purpose**: <one sentence>
- **States**: default · hover · active · disabled · focus · selected (where applicable)
- **Tokens used**: list of token names from tokens.md
- **Required attributes**: any required content slots (label, icon, description, etc.)
- **Accessibility hooks**: cross-references into accessibility.md (focus ring, semantic markup, keyboard reachability)
- **Worked example**: link to examples/<pattern>.tsx
```

**Patterns at v1**:

| # | Pattern | Spec 001 source FR |
|---|---|---|
| 1 | Stepper | FR-006 |
| 2 | Content Card | FR-007 |
| 3 | Option Card | FR-008 |
| 4 | Primary Button | FR-009 |
| 5 | Secondary / Ghost Button | FR-010 |
| 6 | Text Input + Textarea | FR-011 |
| 7 | Select / Dropdown | FR-012 |

(Lucide icons FR-013 are documented as a project-wide rule in `accessibility.md` rather than a stand-alone component.)

**Validation rules**:
- Every state listed MUST have its visual treatment specified in token names (no inline hex / size).
- Every Pattern section MUST link to a Worked Example in `examples/<pattern>.tsx`.
- Adding a new pattern MUST bump MINOR; removing one MUST bump MAJOR.

**Relationships**: Component Pattern → Brand Token Set (uses tokens), Component Pattern → Accessibility Rule (cites a11y hooks), Component Pattern → Worked Example (links to canonical TSX).

---

## Entity 4 — Accessibility Rule

**File**: `accessibility.md`
**Cardinality**: one document, ~5 rules (each derived from spec 001 FR-014..FR-018)

**Schema**:

```markdown
### <Rule name>
- **Statement**: the contract (e.g., "Every interactive element MUST expose a 2 px Dodger-Blue focus ring with 2 px offset on keyboard focus")
- **Source**: spec 001 FR-### reference
- **Tier**: refuse (FR-006 — non-substitutable) | substitute (FR-006 — substitutable token-class)
- **Verification**: how an agent confirms compliance in its own output before returning it
```

**Rules at v1**:

| # | Rule | Spec 001 FR | Tier (per FR-006 of spec 007) |
|---|---|---|---|
| 1 | Focus ring on every interactive element | FR-014 | refuse if removed |
| 2 | WCAG AA contrast on every text-on-background pair | FR-015 | refuse if violated |
| 3 | Respect `prefers-reduced-motion: reduce` | FR-016 | refuse if disabled |
| 4 | Color-blind-safe selection (not blue-alone) | spec 001 Edge Case | refuse if blue-only |
| 5 | Semantic markup for buttons / dialogs / inputs | implicit in FR-006..FR-012 | refuse if downgraded to a non-semantic `<div>` |
| 6 | Keyboard reachability for every interactive element | implicit in FR-014 | refuse if blocked |

**Validation rules**:
- Every Rule's `Statement` MUST quote spec 001 FR text where possible to keep wording consistent across drift cycles.
- Tier MUST be `refuse` for every a11y rule per spec 007's FR-006 clarification (Q4 chose tiered policy with a11y always in refuse tier).

**Relationships**: Accessibility Rule is referenced by every Component Pattern (Entity 3) that interacts with the user; Brand Compliance Check (Entity 7) inspects output against every rule.

---

## Entity 5 — Activation Scope

**File**: `activation.md`
**Cardinality**: one document

**Schema**:

```markdown
## Activation scope (v1)

- **Tool**: Claude Code only.
- **Install location**: repo-local at `.claude/skills/nexcognit-brand/`. User-global install (`~/.claude/skills/`) is NOT permitted at v1.
- **Opt-in signal**: presence of this directory in the consuming repo. There is no separate marker file.
- **Auto-activation triggers**: prompts that involve UI work — adding/modifying components, screens, layouts, dialogs, forms, navigation. Non-UI work (Python, shell, infra, data) does NOT activate the Skill.
- **Manual invocation**: `/nexcognit-brand` invokes explicitly. Useful when the developer wants to apply the Skill to a request the relevance heuristic missed.
- **Out-of-scope behavior**: when asked about UI elements not covered by the Component Pattern catalog (e.g., calendar, charting, marketing illustration, custom iconography beyond Lucide), the Skill states the gap and points the developer at spec 001 / design escalation per FR-010 of spec 007. The agent does NOT improvise off-brand defaults.

## Session-start visibility cue (FR-011)

When the Skill activates for the first UI prompt of a session, the agent MUST emit a one-line notice:

> NexCognit Brand Skill v<skill_version> (tracking spec 001 <tracks_spec_001>) loaded. Applying NexCognit visual brand to this UI request.

This satisfies SC-006 (developer can identify Skill-loaded state in ≤ 5 seconds) without a separate UI surface.
```

**Validation rules**:
- Tool list MUST be `Claude Code only` at v1; any change requires at least a MINOR Skill bump and updated FR-008 wording in spec.md.
- Visibility cue text MUST include both `skill_version` and `tracks_spec_001` so drift is visible at the moment of activation, not just on inspection.

**Relationships**: Activation Scope is consulted by Skill Manifest (Entity 1) for the visibility cue line and by Compliance Check (Entity 7) to suppress its own output when the Skill is not in fact active.

---

## Entity 6 — Worked Example

**Files**: `examples/*.tsx` (one file per Component Pattern)
**Cardinality**: 7 files at v1, matching the 7 Component Patterns.

**Schema** (each file is a real TSX snippet, not pseudocode):

```tsx
// examples/primary-button.tsx
// NexCognit Brand Skill — Worked Example: Primary Button (FR-009 of spec 001)
//
// Tokens:   --color-accent, --color-text-primary, --color-text-primary
// Radius:   8 px (per spec 001 FR-005)
// Type:     14 px / 600 / 20 px line-height (Button label, FR-003)
// Focus:    2 px Dodger-Blue ring with 2 px offset (FR-014)
// State:    default · hover (brightness +5%) · active (brightness +10%) · disabled (40% opacity)
//
export function PrimaryButton({ children, onClick, disabled }: {
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="rounded-[8px] bg-[var(--color-accent)] px-4 py-2.5 text-[14px] font-semibold leading-5 text-[var(--color-text-primary)] transition-[filter] hover:brightness-105 active:brightness-110 disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-accent)]"
    >
      {children}
    </button>
  );
}
```

**Validation rules**:
- Every file MUST cite the spec 001 FRs it satisfies in a header comment.
- Every file MUST use CSS variables from `tokens.md` rather than inline hex.
- Every file MUST be syntactically valid TSX (a Worked Example with a typo is worse than no example).

**Relationships**: Worked Example → Component Pattern (1:1), Worked Example → Brand Token Set (cites tokens by name).

---

## Entity 7 — Brand Compliance Check

**File**: `compliance-check.md`
**Cardinality**: one document — the agent's self-validation rulebook for FR-006

**Schema**:

```markdown
## Tiered policy

### Substitute tier
For these property classes, when the developer requests a value outside the documented set, the agent picks the nearest documented token, applies it, and emits a one-line explanation:

- **Color** (any background, text, border, accent, shadow tint). Nearest = lowest ΔE in OKLCH space.
- **Spacing** (margins, padding, gaps). Nearest = closest documented step in {4, 8, 16, 24}.
- **Border-radius**. Nearest = closest documented value in {8, 12, ≥999}.
- **Shadow / elevation**. Nearest = closest documented elevation token.

### Refuse tier
For these property classes, the agent refuses with a one-line reason and names the documented alternative:

- **Typography**. Approved typeface is Roboto only (FR-002). No "nearest font" — refuse and ask the developer to pick a Roboto weight.
- **Accessibility**. Any of the rules in `accessibility.md`. Refuse with citation; do not weaken under any framing including "we'll fix it later" or "just for the demo".

## Self-validation procedure

Before returning a UI snippet to the developer, the agent MUST:
1. Scan the snippet for hex colors, font names, custom radius, custom shadow → if any are not from `tokens.md`, apply Substitute tier or Refuse tier per the property class.
2. Confirm every interactive element has a visible focus state (Rule 1 of `accessibility.md`) and semantic markup (Rule 5).
3. Confirm any color-encoded state (selected, error, etc.) is also encoded by a non-color signal (border-width change or glyph), per Rule 4.
4. If any check fails, the agent rewrites the snippet to satisfy the rule before returning it. The agent MUST NOT return a snippet it knows fails the check.

## Visibility

When the agent applies a Substitute, the response MUST include a one-line note: e.g., "Substituted requested `#FF5733` with `--color-accent` (closest documented token)."
When the agent applies a Refuse, the response MUST include a one-line reason: e.g., "Cannot use Comic Sans — approved typeface is Roboto (weights 400/500/600/700). Pick a weight."
```

**Validation rules**:
- The two tiers MUST mirror exactly the FR-006 wording resolved in clarification Q4. Drift between this document and FR-006 is a v1 bug.
- The self-validation procedure MUST be a deterministic checklist (numbered steps, no "consider" / "where appropriate" hedging).

**Relationships**: Compliance Check reads from Brand Token Set (canonical values), Component Pattern (state expectations), and Accessibility Rule (refuse-tier definitions). It is the agent's "last mile" between assembling output and returning it.

---

## Cross-entity relationships

```text
Skill Manifest ──── declares ───→ Activation Scope
        │
        └── advertises ───→ Brand Token Set, Component Pattern, Accessibility Rule, Compliance Check

Brand Token Set ◄── cites ─── Component Pattern
                          ◄── cites ─── Accessibility Rule (for color in contrast checks)
                          ◄── cites ─── Worked Example
                          ◄── cites ─── Compliance Check

Component Pattern ──── 1:1 ───→ Worked Example

Accessibility Rule ──── feeds ───→ Compliance Check (refuse tier)
```

**Source-of-truth invariant**: `tokens.md` is the only file that names hex values, font weights, sizes, radii, and spacing. Every other entity references those tokens by name. A Skill update procedure (R6 of research.md) that changes a hex without updating `tokens.md` is malformed by definition.

---

## What's NOT modeled (deliberately)

- **Sub-themes / variants** (admin variant, marketing variant, dark/light variant). Spec.md assumption #6 defers v2; data-model intentionally lacks a Variant entity.
- **Telemetry events** (Skill loaded, Skill substituted, Skill refused). Clarification Q5 ruled out telemetry at v1; data-model carries no event schema.
- **Localization / i18n strings**. Spec assumes English-only audience; no Locale entity at v1.
- **Skill load-failure state** (R7 of research.md). Deferred to Phase 2 task design.
