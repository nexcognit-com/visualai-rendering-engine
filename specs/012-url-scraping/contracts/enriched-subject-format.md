# Contract: Enriched Subject Composition

**Feature**: [spec.md](../spec.md) | **Plan**: [plan.md](../plan.md) | **Data Model**: [data-model.md §Entity 3](../data-model.md)

The pure function `composeEnrichedSubject(parts)` that turns wizard-side scrape results (with edits applied) into the text string sent to MPT as `video_subject`. This is the **single point** where structured scrape data collapses into plain text — and where Layer 1's URL-aware UX hands off to Layer 3's URL-unaware engine.

## Function signature

```ts
import { composeEnrichedSubject, MAX_SUBJECT_LEN } from "@/lib/url-scrape";

export interface EnrichedSubjectInput {
  title: string;        // required, non-empty after trim
  description: string;  // required, non-empty after trim
  sourceDomain: string; // required, non-empty after trim, hostname-only (no scheme/port/path)
}

export const MAX_SUBJECT_LEN: number; // 500

export function composeEnrichedSubject(parts: EnrichedSubjectInput): string;
```

## Output format

```
${title}. ${description}. (sourced from ${sourceDomain})
```

Example for `{title: "Cold Brew Kit", description: "32 oz of slow-steeped goodness.", sourceDomain: "acmebrew.com"}`:

```
Cold Brew Kit. 32 oz of slow-steeped goodness. (sourced from acmebrew.com)
```

## Truncation algorithm

If composed length > 500 chars (`MAX_SUBJECT_LEN`):

1. **Truncate description first.** Keep title + `(sourced from ...)` intact. Trim description and append `…` (single Unicode horizontal ellipsis, U+2026).
2. **If still over.** Truncate title with `…`. Keep description (now truncated to fit) + source attribution.
3. **NEVER drop the `(sourced from <domain>)` suffix.** It's the LLM's provenance signal; keeping it is non-negotiable.

The algorithm is greedy: try description-only truncation first; only touch title if necessary.

## Behavior contract

| Property | Guarantee |
|---|---|
| Pure | No side effects. Same inputs → same output. Idempotent. |
| Output is plain text | No markup, no HTML entities, no zero-width chars, no leading/trailing whitespace. (Inputs arrive sanitized server-side.) |
| Output ALWAYS ends with `(sourced from <domain>)` | The truncation algorithm preserves this suffix. |
| Output length ≤ `MAX_SUBJECT_LEN` (500) | Always. Hard cap. |
| Empty inputs throw | `EnrichedSubjectError("empty_field", whichField)` if title or description is empty after trim. |
| `sourceDomain` is host-only | Validated; throws `EnrichedSubjectError("invalid_domain")` if it contains scheme / port / path. |

## Error type

```ts
type EnrichedSubjectErrorCode = "empty_field" | "invalid_domain";

export class EnrichedSubjectError extends Error {
  constructor(public code: EnrichedSubjectErrorCode, public details?: string) {
    super(`composeEnrichedSubject failed: ${code}${details ? ` (${details})` : ''}`);
    this.name = "EnrichedSubjectError";
  }
}
```

In practice the wizard's submit handler catches these and reverts to the raw input as a defensive fallback. Should never happen if the upstream UI path validates correctly.

## Examples

### Short content — no truncation

```ts
composeEnrichedSubject({
  title: "Hand-painted ceramic mug",
  description: "Microwave-safe; dishwasher-safe; 12 oz.",
  sourceDomain: "ceramicstudio.example",
});
// → "Hand-painted ceramic mug. Microwave-safe; dishwasher-safe; 12 oz. (sourced from ceramicstudio.example)"
// length: 110 chars
```

### Long content — description truncated

```ts
composeEnrichedSubject({
  title: "Premium Cold Brew Kit",
  description: "Hand-crafted from Ethiopian beans roasted in our small-batch facility every Tuesday morning before dawn, packed with the care of artisans who have been roasting coffee for three generations, delivering flavors that range from bright citrus notes to deep chocolate undertones with hints of caramel and a smooth, lingering finish that pairs perfectly with milk or stands alone for those who prefer their cold brew unadulterated.",
  sourceDomain: "acmebrew.com",
});
// → "Premium Cold Brew Kit. Hand-crafted from Ethiopian beans roasted in our small-batch facility every Tuesday morning before dawn, packed with the care of artisans who have been roasting coffee for three generations, delivering flavors that range from bright citrus notes to deep chocolate undertones with hints of caramel and a smooth, lingering finish that pairs perfectly with milk or stands…. (sourced from acmebrew.com)"
// length: exactly 500 chars (truncated description; title + suffix intact)
```

### Empty input — throws

```ts
composeEnrichedSubject({
  title: "   ",  // empty after trim
  description: "Valid description",
  sourceDomain: "example.com",
});
// → throws EnrichedSubjectError("empty_field", "title")
```

### Invalid domain — throws

```ts
composeEnrichedSubject({
  title: "Test",
  description: "Test",
  sourceDomain: "https://example.com:8080/path",  // includes scheme/port/path
});
// → throws EnrichedSubjectError("invalid_domain")
```

## Tests (Vitest)

The function is tested in `visualai-frontend/tests/url-scrape.test.ts`. Test cases:

| Test ID | Input | Expected output |
|---|---|---|
| ES-1 | Short title + short description | composes correctly; ends with attribution |
| ES-2 | Title at 200 chars + description at 500 chars | composes; truncates description side first |
| ES-3 | Title at 100 chars + description at 1000 chars | composes; description truncated to fit; title intact |
| ES-4 | Title at 1000 chars + description at 100 chars | composes; description intact; title truncated |
| ES-5 | Empty title | throws `EnrichedSubjectError("empty_field", "title")` |
| ES-6 | Empty description | throws `EnrichedSubjectError("empty_field", "description")` |
| ES-7 | Whitespace-only title | throws `EnrichedSubjectError("empty_field", "title")` |
| ES-8 | sourceDomain with scheme (`https://example.com`) | throws `EnrichedSubjectError("invalid_domain")` |
| ES-9 | sourceDomain with path (`example.com/foo`) | throws `EnrichedSubjectError("invalid_domain")` |
| ES-10 | Output always ends with `(sourced from <domain>)` for happy path | regex assertion across all happy-path tests |
| ES-11 | Output never exceeds `MAX_SUBJECT_LEN` (500) | length check across all tests |

These 11 tests are the contract surface for `/speckit-tasks` to schedule.

## What this contract does NOT cover

- **Translation / locale handling** — the function is locale-agnostic; the caller passes whatever language the title and description are in. The LLM downstream handles language detection.
- **Markdown / formatting in output** — explicitly not — output is plain text only.
- **Brand voice augmentation** (Brand Library v2 hook) — the pure function takes only the three input fields. v2 may layer a `brandVoice?: string` parameter that prepends a tone hint; the v1 contract is forward-compatible (additive optional param).
- **URL inclusion in subject** — explicitly NEVER included. Only `sourceDomain` (host-only) makes it through. The URL is dropped at the wizard's API call boundary; downstream code never sees it.
