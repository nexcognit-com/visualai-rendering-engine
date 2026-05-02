# Contract: Wizard Mode Selector UI

**Feature**: [spec.md](../spec.md) | **Plan**: [plan.md](../plan.md) | **Data Model**: [data-model.md §Entity 3](../data-model.md)

The wizard's Step 3 mode-selector UX. Pure Layer 1 contract — visual + interaction shape, plus the React state machine that backs it. Mirrors the visual language of the Music panel pills from spec 010 for consistency.

## Visual layout

```text
┌─────────────────────────────────────────────────────────────────┐
│ Script & voice                                                  │
│ Pick how the AI should handle your script.                      │
│                                                                 │
│ ┌──────────┬──────────────┬──────────┐                          │
│ │   Auto   │   Verbatim   │  Polish  │                          │
│ └──────────┴──────────────┴──────────┘                          │
│                                                                 │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ [Mode-specific textarea — see state table below]            │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                                                                 │
│ <Mode-specific helper text under the textarea>                  │
│                                                                 │
│ Voice: [Jenny (US, female) ▾]                                   │
│ ── Music panel from spec 010 ──                                 │
└─────────────────────────────────────────────────────────────────┘
```

## State machine

| `state.mode` | Pill row | Textarea | Helper text (below textarea) |
|---|---|---|---|
| `"auto"` (default) | Auto pill highlighted | Hidden (via `display: none` or React conditional render) | "Leave empty — the AI will write a script from your subject." |
| `"verbatim"` | Verbatim pill highlighted | Visible, editable | "Your text will be read verbatim as the voiceover." |
| `"polish"` | Polish pill highlighted | Visible, editable | "Type a rough brief — the AI will rewrite it as a 20-second hook → body → CTA." |

### Pill click handler

Switching modes does NOT clear `state.text`. Only the visibility of the textarea changes. If the creator types text in Verbatim, switches to Auto, then switches back to Verbatim or Polish — the text reappears.

```ts
function handleModeClick(newMode: ScriptMode, state: WizardScriptState, setState: ...) {
  setState({ mode: newMode, text: state.text });
}
```

### Textarea visibility rule

```tsx
{state.mode !== "auto" && (
  <textarea
    value={state.text}
    onChange={(e) => setState({ ...state, text: e.target.value })}
    placeholder={PLACEHOLDER[state.mode]}
    rows={6}
    ...
  />
)}
```

### Placeholder mapping

```ts
const PLACEHOLDER: Record<Exclude<ScriptMode, "auto">, string> = {
  verbatim: "Type or paste the exact script — every word will be read aloud.",
  polish: "Type a rough brief or bullet points — the AI will rewrite it as a 20-second hook → body → CTA.",
};
```

## Submit-button validation

| `state.mode` | Validation rule | Error UX (when violated) |
|---|---|---|
| `"auto"` | none — always allowed | n/a |
| `"verbatim"` | `state.text.trim().length > 0` | inline below textarea: "Add a script first, or switch to Auto." Submit blocked. |
| `"polish"` | `state.text.trim().length > 0` | inline below textarea: "Polish mode needs a brief — type some bullet points or a rough description, then try again." Submit blocked. |

The validation MUST surface within 100 ms of click (FR-006 + SC-006). React's synchronous render handles this trivially.

## Pill button visual contract

Reuses spec 010's Music panel pill class names (Tailwind utility chain) for consistency. Active state uses the brand-accent border + soft tint background. Inactive uses border-subtle + muted text.

**Active pill** (matches spec 010's `cn("rounded-... border-[var(--color-accent)] bg-[var(--color-accent)]/10 ...")` pattern):

```tsx
className={cn(
  "rounded-[var(--radius-button)] border px-3 py-2 text-sm transition-colors",
  isActive
    ? "border-[var(--color-accent)] bg-[var(--color-accent)]/10 text-[var(--color-text-primary)] font-medium"
    : "border-[var(--color-border-subtle)] bg-[var(--color-elevated)] text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]",
)}
```

This is verbatim the same shape `MusicPanel` uses; the implementation can lift it into a small shared `ModePillRow` component if desired (out of scope at v1; copy-paste is fine for two consumers).

## State persistence rules

| Action | mode persists? | text persists? |
|---|---|---|
| Click "Next" → "Back" within same wizard session | YES | YES |
| Refresh the browser tab | NO (resets to `PRISTINE_SCRIPT`) | NO |
| Submit a render and complete | YES (preserved during the polling phase, in case render fails and creator wants to retry) | YES |
| Click "Reset" or navigate away to dashboard | NO | NO |

Persistence is in-memory React state on the parent `ShortVideoWizard` component. No localStorage, no cookies, no server-side preferences (FR-011 + spec §Assumptions).

## Polish-failure recovery UX

When the render reaches `state="failed"` with `error="polish_failed"`, the Step 4 (Generate) screen shows:

```text
┌─────────────────────────────────────────────────────────────────┐
│ ❌ Polish failed                                                │
│                                                                 │
│ We couldn't polish that brief. Your text is still here — try   │
│ again, or switch to Verbatim to use it as-is.                  │
│                                                                 │
│ [ Try again with Polish ]    [ Switch to Verbatim ]            │
└─────────────────────────────────────────────────────────────────┘
```

- "Try again with Polish": resubmits the current wizard state (mode + text unchanged).
- "Switch to Verbatim": sets `state.mode = "verbatim"` (text unchanged), navigates back to Step 3 so the creator can review/adjust before re-submitting.

Mirror UX for `error="polish_brief_required"`: same shape but the body says "Polish mode needs a brief — go back to Step 3 and type something." Single button: "Back to Step 3."

## Verification (drives task design)

| Test ID | Setup | Expected |
|---|---|---|
| WMS-1 | First wizard paint | `state.mode === "auto"`; pill row shows Auto highlighted |
| WMS-2 | Click "Verbatim" pill | `state.mode` flips to `"verbatim"`; textarea visible; placeholder matches |
| WMS-3 | Click "Polish" pill | `state.mode` flips to `"polish"`; textarea visible; placeholder updates |
| WMS-4 | Click "Auto" pill (after typing in Verbatim) | `state.mode === "auto"`; textarea hidden BUT `state.text` preserved |
| WMS-5 | Click "Polish" → type brief → click "Verbatim" → click "Polish" again | text reappears unchanged |
| WMS-6 | Polish + empty text + Submit click | inline error appears within 100 ms; submit handler NOT called |
| WMS-7 | Verbatim + empty text + Submit click | inline error appears; submit handler NOT called |
| WMS-8 | Auto + Submit click | submit handler called with `{script_mode: "auto", video_script: ""}` |
| WMS-9 | Polish + valid brief + Submit click | submit handler called with `{script_mode: "polish", video_script: <brief>, script_brief: <brief>}` |
| WMS-10 | `scriptStateToParams({mode: "auto", text: "anything"})` | returns `{script_mode: "auto", video_script: ""}` (text NOT included; auto mode ignores it) |
| WMS-11 | `isPristineScript({mode: "auto", text: ""})` returns true; any other state returns false | unit test of helper |

These 11 tests are scheduled in `tasks.md` Phase 2 — most are component-state assertions on the parent wizard's React state with the textarea + pill row mounted.

## Accessibility

- Each pill button MUST be a `<button type="button">` element (not a `<div>` with click handler).
- The pill row uses `role="radiogroup"` with each pill `role="radio"` + `aria-checked` reflecting `state.mode`. Keyboard arrow-key navigation is browser-default for radio groups.
- The helper text below the textarea is associated via `aria-describedby` from the textarea so screen readers announce it.
- The "Try Verbatim instead" recovery button is a `<button type="button">` with clear focus styling.

## What this contract does NOT cover

- **Visual icon choices** for the pills — none at v1; can add lucide-react icons in v2 polish.
- **Animation** when switching modes (textarea fade-in/out) — none at v1; conditional render is fine.
- **Mobile layout** — same pill row, just narrower. No special breakpoint handling at v1.
- **Per-tenant defaults** — every wizard session starts at `"auto"` per FR-012. Tenant-scoped defaults arrive when debt #2 lands.
