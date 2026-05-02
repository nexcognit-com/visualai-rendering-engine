# Phase 1 Data Model: URL Scraping for Step 1 Input

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Research**: [research.md](./research.md)

This is a Layer-1-only feature; the data model is entirely TypeScript types + in-memory caches inside the Next.js server runtime. **Zero schema changes** to MPT (`app/models/schema.py` is untouched). All entities below live under `visualai-frontend/`.

---

## Entity 1 — `ScrapeResult` (server → wizard)

**File**: `visualai-frontend/src/lib/url-scrape.ts` (new TypeScript module)

The shape returned by `POST /api/scrape-url` to the browser. Discriminated union by `ok`.

### TypeScript shape

```ts
export type ScrapeResult =
  | ScrapeSuccess
  | ScrapeError;

export interface ScrapeSuccess {
  ok: true;
  title: string;
  description: string;
  image_url: string | null;
  source_domain: string;
  raw_html_size: number;       // bytes; for ops debugging only
  scrape_elapsed_ms: number;   // server-side wall-clock for SC-003 verification
}

export interface ScrapeError {
  ok: false;
  error_code: ScrapeErrorCode;
  detail: string;              // human-readable; safe to render in the wizard verbatim
}

export type ScrapeErrorCode =
  | "fetch_404"
  | "fetch_403"
  | "fetch_5xx"
  | "fetch_timeout"
  | "robots_blocked"
  | "no_useful_content"
  | "non_html_response"
  | "ssrf_blocked"
  | "redirect_loop"
  | "tls_error"
  | "rate_limited"
  | "url_invalid";
```

### Field-level contract

| Field | Type | Required when | Constraint |
|---|---|---|---|
| `ok` | `true \| false` | always | discriminator |
| `title` | `string` | `ok === true` | trimmed; `length ≤ 200` (truncated server-side); HTML-stripped via sanitize-html |
| `description` | `string` | `ok === true` | trimmed; `length ≤ 500` (truncated); HTML-stripped |
| `image_url` | `string \| null` | `ok === true` | absolute URL of the OG image OR `null` if none extractable. Same-origin or absolute https URL only. |
| `source_domain` | `string` | `ok === true` | hostname of the input URL (no scheme, no port). e.g. `acmebrew.com` |
| `raw_html_size` | `number` | `ok === true` | bytes consumed (≤ 5 MB cap from FR-005) |
| `scrape_elapsed_ms` | `number` | `ok === true` | wall-clock time the server spent on this scrape; surfaced for SC-003 verification but NOT shown in the wizard UI |
| `error_code` | `ScrapeErrorCode` | `ok === false` | one of the 12 documented codes |
| `detail` | `string` | `ok === false` | safe to render verbatim; never includes raw HTML, never includes the bearer / secrets |

### Sanitization invariants (enforced server-side before return)

1. `title` and `description` MUST be plain text only — no markup, no HTML entities like `&amp;` (decoded), no zero-width chars (`​-‍﻿` stripped).
2. `image_url` MUST be `null` if it isn't a parseable absolute URL with `http:` or `https:` scheme.
3. `source_domain` MUST NOT include credentials (`user:pass@`), port, or path.
4. `detail` strings are picked from a fixed table (see [contracts/scrape-endpoint.md](./contracts/scrape-endpoint.md)) — they're translation-friendly constants, not server-generated free text.

### Lifecycle

`ScrapeResult` is computed once per `POST /api/scrape-url` request and returned synchronously. It's never persisted. The wizard holds it in React state until the creator clicks Use / Edit / Clear or navigates away.

---

## Entity 2 — `WizardScrapeState` (wizard React state)

**File**: `visualai-frontend/src/app/modes/short-video/page.tsx` (modified)

Ephemeral state inside the Mode 2 wizard component. Tracks the lifecycle of the URL-scraping interaction inside Step 1.

### TypeScript shape

```ts
type WizardScrapeMode = "text" | "scraping" | "preview" | "error";

interface WizardScrapeState {
  mode: WizardScrapeMode;
  result: ScrapeResult | null;       // populated when mode === "preview" or "error"
  editedTitle: string | null;        // overrides result.title when set
  editedDescription: string | null;  // overrides result.description when set
  url: string;                       // the URL the creator pasted; used for "use as plain text" fallback
}
```

### State transitions

```text
[input changed, no URL detected] ──────────────► mode: "text"
                                                  result: null
                                                  
[URL detected on paste/blur]    ──────────────► mode: "scraping"
                                                  result: null
                                                  
[scrape completes ok=true]      ──────────────► mode: "preview"
                                                  result: <ScrapeSuccess>
                                                  
[scrape completes ok=false]     ──────────────► mode: "error"
                                                  result: <ScrapeError>
                                                  
[creator clicks Use this]       ──────────────► (state stays "preview"; submit button uses composed enriched subject)

[creator edits title or desc]   ──────────────► (state stays "preview"; editedTitle / editedDescription updated)

[creator clicks Clear]          ──────────────► mode: "text"
                                                  result: null

[creator clicks "use as text"]  ──────────────► mode: "text"
                                                  Step 1 input value: <url>
```

### Validation invariants

1. When `mode === "scraping"`, the wizard MUST show a non-blocking spinner under the input. The next-step button is disabled.
2. When `mode === "preview"`, the wizard MUST show the title + description + image + source-domain badge + Use / Edit / Clear actions.
3. When `mode === "error"`, the wizard MUST show the typed error from `result.detail` + a "use as plain text" fallback button.
4. The wizard's submit handler MUST NOT send any URL string in `video_subject` — only the composed enriched subject (Entity 3). If `mode === "text"` (creator dismissed the scrape OR no URL was pasted), the existing behavior applies — submit handler sends the input field's text as-is.

---

## Entity 3 — `EnrichedSubject` (computed string sent to MPT)

**File**: `visualai-frontend/src/lib/url-scrape.ts` — function `composeEnrichedSubject`

Pure function that takes the wizard's current scrape state (with edits applied) and returns the text the wizard will submit as `video_subject`.

### Signature + behavior

```ts
export interface EnrichedSubjectInput {
  title: string;
  description: string;
  sourceDomain: string;
}

export const MAX_SUBJECT_LEN = 500;

export function composeEnrichedSubject(parts: EnrichedSubjectInput): string;
```

### Algorithm

1. Trim each input field. Reject if `title` or `description` is empty after trim → throw `EnrichedSubjectError("empty_field")`.
2. Compose: `${title}. ${description}. (sourced from ${sourceDomain})`.
3. If `result.length > MAX_SUBJECT_LEN`, truncate the **description** side first using `…` suffix; if still too long, truncate the **title**. NEVER drop the `(sourced from ...)` attribution.
4. Return the composed string.

### Invariants

1. The output is plain text only — no markup, no quotes that need escaping, no leading/trailing whitespace.
2. The function is pure: same inputs → same output. No side effects.
3. The output ALWAYS ends with `(sourced from <domain>)` so the LLM has provenance context. Tests assert this suffix exists.
4. `title` and `description` arrive already sanitized (Entity 1's invariants enforced server-side).

---

## Entity 4 — `RobotsTxtCacheEntry` (server in-memory cache)

**File**: `visualai-frontend/src/app/api/scrape-url/route.ts` — module-scoped `Map`

### TypeScript shape

```ts
interface RobotsTxtCacheEntry {
  parsed: ReturnType<typeof robotsParser>; // robots-parser instance
  expiresAt: number;                       // ms since epoch
}

const robotsCache = new Map<string, RobotsTxtCacheEntry>();
const ROBOTS_TTL_MS = 60 * 60 * 1000;      // 1 hour
```

### Lifecycle

- **Set**: on each cache miss, fetch `https://<host>/robots.txt`, parse, store with `expiresAt = Date.now() + ROBOTS_TTL_MS`.
- **Get**: on each scrape request, look up by `URL(request.url).host`. If hit and not expired, use. If expired, treat as miss.
- **Eviction**: lazy on TTL check. No background sweep at v1 — a periodic sweep can be added if memory pressure becomes an issue.
- **Reset**: cleared on Next.js server cold start. Acceptable — robots.txt is a public file; re-fetching is cheap.

### Invariants

1. Cache key is the lowercase hostname (no port, no scheme).
2. On cache miss: if the `robots.txt` fetch fails (404, network, etc.) → store an "all-allowed" entry with normal TTL. Per RFC 9309: missing robots.txt = no rules.
3. On cache miss: if the `robots.txt` is over 100 KB → ignore (cap), store an "all-allowed" entry. Pathological robots.txt files are out of scope.

---

## Entity 5 — `RateLimitWindow` (server in-memory cache)

**File**: `visualai-frontend/src/app/api/scrape-url/route.ts` — module-scoped `Map`

### TypeScript shape

```ts
const rateLimit = new Map<string, number[]>();  // ip → [timestamp_ms, ...]
const RATE_LIMIT_PER_MIN = 30;
const RATE_LIMIT_WINDOW_MS = 60_000;
```

### Lifecycle

- **Get on each request**: lookup by client IP (from `X-Forwarded-For` first hop, fallback to socket address).
- **Filter**: remove timestamps older than `Date.now() - RATE_LIMIT_WINDOW_MS`.
- **Check**: if remaining length ≥ `RATE_LIMIT_PER_MIN` → return HTTP 429 with `error_code: "rate_limited"`.
- **Append**: push `Date.now()` to the array.
- **Periodic sweep** (every 5 minutes): remove entries whose all timestamps are older than 5 minutes.

### Invariants

1. The IP extractor MUST handle proxy/CDN headers correctly — first hop in `X-Forwarded-For`, fallback to socket. Misuse → false-positive rate-limits.
2. The counter is process-global. In a multi-instance deployment, the actual rate seen by a target site is `instance_count × 30`. Acceptable at v1; tightened in Step 2 with a shared store.

---

## Entity 6 — `SsrfGate` (server-side validation function)

**File**: `visualai-frontend/src/lib/ssrf.ts`

Pure async function `assertSafeUrl(url: string): Promise<void>` — throws on any blocked target.

### Refusal rules (exhaustive at v1)

| Rule | Refusal trigger | Error class |
|---|---|---|
| Scheme allowlist | URL scheme not `http:` or `https:` | `SsrfError("scheme_blocked", scheme)` |
| Loopback IPv4 | Hostname or any resolved IP in `127.0.0.0/8` | `SsrfError("loopback")` |
| Loopback IPv6 | `::1` | `SsrfError("loopback")` |
| Link-local IPv4 | `169.254.0.0/16` | `SsrfError("link_local")` |
| Link-local IPv6 | `fe80::/10` | `SsrfError("link_local")` |
| RFC 1918 private (10.x) | `10.0.0.0/8` | `SsrfError("private_range")` |
| RFC 1918 private (172.16-31) | `172.16.0.0/12` | `SsrfError("private_range")` |
| RFC 1918 private (192.168.x) | `192.168.0.0/16` | `SsrfError("private_range")` |
| Multicast / reserved IPv4 | `0.0.0.0/8`, `224.0.0.0/4`, `240.0.0.0/4` | `SsrfError("reserved_range")` |
| URL parse failure | `new URL(input)` throws | `SsrfError("url_invalid")` |
| DNS resolution failure | `dns.lookup` rejects | `SsrfError("dns_failed", host)` |

### Invariants

1. Called BEFORE any fetch attempt.
2. Called AGAIN after each redirect's `Location` header is parsed (before following).
3. `dns.lookup` uses `{ all: true }` so we see every resolved IP — refuse if ANY is blocked. Defense against IPv6/IPv4 DNS pinning attacks.
4. The function is **pure-ish** — it does DNS I/O but has no other side effects. Idempotent for cacheable hosts.

---

## Entity 7 — `ScrapeRouteRequest` (browser → server)

**File**: implicit in `visualai-frontend/src/app/api/scrape-url/route.ts`

The shape the wizard sends to the API route.

### TypeScript shape

```ts
interface ScrapeRouteRequest {
  url: string;  // the URL the creator pasted
}
```

### Validation (Zod schema in route handler)

```ts
const RequestSchema = z.object({
  url: z.string().url("must be a valid URL").max(2048, "URL too long"),
});
```

### Invariants

1. Returns 400 `url_invalid` if `url` is missing, non-string, or > 2048 chars.
2. Pre-fetch SSRF gate runs before any I/O.

---

## Cross-entity relationships

```text
[creator pastes URL]
       ↓
[wizard's URL detector — FR-001 regex]                        (Entity 9 — detection logic in url-scrape.ts)
       ↓
[POST /api/scrape-url with {url: ...}]                        (Entity 7 — ScrapeRouteRequest)
       ↓
[server: assertSafeUrl(url)]                                   (Entity 6 — SsrfGate)
       ↓
[server: rate-limit check]                                     (Entity 5 — RateLimitWindow)
       ↓
[server: robots.txt cache lookup + parse]                      (Entity 4 — RobotsTxtCacheEntry)
       ↓
[server: undici fetch with redirect=manual + 5MB+10s caps]    (no entity — pure HTTP I/O)
       ↓
[server: cheerio extract og:title / og:description / og:image / <h1>]
       ↓
[server: sanitize-html on extracted strings]
       ↓
[return ScrapeResult]                                          (Entity 1 — ScrapeResult)
       ↓
[wizard updates state]                                         (Entity 2 — WizardScrapeState)
       ↓
[creator interacts: Use / Edit / Clear / "use as plain text"]
       ↓
[on submit: composeEnrichedSubject(...)]                       (Entity 3 — EnrichedSubject)
       ↓
[POST /api/generate {subject: <enriched text>, ...}]            (existing — unchanged)
       ↓
[Layer 3 / MPT: receives PLAIN TEXT in video_subject]
```

**Source-of-truth invariants**:

- `ScrapeResult` is the SINGLE source of truth for what was extracted. Edits in the wizard NEVER mutate the `ScrapeResult` itself — they live in `editedTitle` / `editedDescription` so the original scrape is recoverable for "Reset to scraped" UX (a future polish).
- The composed `EnrichedSubject` is the SINGLE point at which extracted + edited fields collapse into one string. Once composed, downstream code only sees text.
- The URL is NEVER part of the enriched subject string. Only the `source_domain` (host-only) makes it through.

---

## What is NOT modeled (deliberately)

- **Persisted scrape history** — every scrape is ephemeral; nothing reaches disk on the server side. Per spec §Open Follow-Ups, persistence lands with Brand Library work in Step 5.
- **Per-creator scrape preferences** (e.g., "always use OG description over meta description") — defaults are good enough at v1; user override is via inline editing.
- **Server-side translation / locale handling** — extracted content stays in its native language; the LLM handles translation downstream if needed.
- **Multi-URL extraction in one paste** — only the first URL is scraped; rest discarded with a wizard hint.
- **Image proxy for og:image** — the wizard renders `image_url` directly via `<img>`. No proxying; if the target site blocks hotlinking, the image fails to load and the wizard shows a placeholder. Acceptable at v1.
- **Telemetry events** ("scrape attempted", "scrape succeeded", "scrape failed by error_code") — no observability infra in scope. Server logs (FR-013) cover ops needs.
- **Retry-on-failure with backoff** — single attempt per scrape. Creator manually re-pastes if they want to retry.

---

## Schema diff summary

For audit clarity, here's the entirety of the schema delta this feature introduces:

```diff
# app/models/schema.py        (Layer 3 — Python)
# (NO CHANGES — Layer 3 is untouched. video_subject already accepts arbitrary text.)
```

That's intentional. The whole point of Layer-1-only scoping is that the rendering engine sees no new shape — only enriched-text in `video_subject`. The TypeScript types above are the entire data model contribution.
