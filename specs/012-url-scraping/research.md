# Phase 0 Research: URL Scraping for Step 1 Input

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**: 2026-05-02

## R1 — HTML parser choice

**Decision**: **Cheerio** (`cheerio` ≥ 1.0).

**Rationale**: Cheerio implements a familiar jQuery-like API on top of `parse5` (a spec-compliant HTML5 parser). Pure JS, no native deps, bundle-friendly. Used widely in Next.js server-route contexts. Zero attack surface compared to running raw regex against HTML (the classic anti-pattern). Specifically:

- Selector syntax (`$('meta[property="og:title"]').attr('content')`) maps trivially to the priority extraction order in FR-003.
- Handles malformed HTML gracefully (most product pages are not pristine).
- ~500 KB unpacked; cleanly tree-shakeable in the server bundle.
- Works on streaming responses if needed (we don't need this at v1 — full body fits in 5 MB cap).

**Alternatives considered**:
- **`node-html-parser`** — faster, smaller. Rejected: less mature ecosystem; jQuery-style API in Cheerio is more readable.
- **`linkedom`** — full DOM emulation. Rejected: 4× larger, overkill for our extraction (we just need `meta`, `title`, `h1`, first `img` selectors).
- **Raw `parse5` directly** — most flexible. Rejected: forces us to write traversal code Cheerio gives for free.
- **A pre-built scraper SaaS** (e.g., `unfurl.io`, `iframely`) — rejected: external dependency, ongoing cost, latency, and Principle IV concern (those are external API calls). The whole feature stays in our own server.

## R2 — HTML sanitization for the returned text fields

**Decision**: **`sanitize-html`** (≥ 2.13) with a "text-only" config — strips ALL tags + ALL attributes from extracted strings. Defense-in-depth even though we only return `textContent` (which is already tag-free).

**Sanitizer config**:

```ts
const TEXT_ONLY = { allowedTags: [], allowedAttributes: {} };
sanitizeHtml(extractedTitle, TEXT_ONLY);
```

**Rationale**: We're showing extracted text from arbitrary URLs in the wizard's preview UI. Even though we extract `textContent` (no markup), an attacker-controlled site could include unicode bidi-override tricks, zero-width chars, or invisible HTML entities. Running everything through `sanitize-html` is paranoia-grade defense and costs almost nothing.

**Alternatives considered**:
- **`xss`** library — older, less actively maintained. Rejected.
- **Skip sanitization** (rely on React's auto-escaping for rendering safety) — rejected: React only protects HTML rendering; doesn't protect against the wizard accidentally building a malicious URL or shell-quoting the value somewhere later. Defense-in-depth wins.
- **DOMPurify (browser-side)** — rejected: we sanitize server-side BEFORE returning to the browser, so a future change in how the wizard uses the text can't accidentally re-introduce XSS.

## R3 — SSRF protection (FR-006, SC-006)

**Decision**: A hand-written `assertSafeUrl(url: string): Promise<void>` gate that runs BEFORE any fetch:

1. Parse via `URL` constructor; reject if it throws.
2. Reject if scheme is anything other than `http:` or `https:`. Specifically blocks `file:`, `data:`, `javascript:`, `gopher:`, `ftp:`, `chrome:`.
3. Resolve the hostname via `dns.promises.lookup(host, { all: true })`.
4. Reject if ANY resolved IP is:
   - Loopback (`127.0.0.0/8`, `::1`)
   - Link-local (`169.254.0.0/16`, `fe80::/10`)
   - RFC 1918 private (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`)
   - Multicast / reserved (`0.0.0.0/8`, `224.0.0.0/4`, `240.0.0.0/4`)
5. After redirects, re-run the gate on the final URL. Any redirect to a blocked target → refuse the response (don't follow). `undici` exposes `redirect: 'manual'` for this.

The gate lives in `visualai-frontend/src/lib/ssrf.ts`; `node:net` provides `isIPv4` / `isIPv6` and a small CIDR helper handles the range checks.

**Rationale**: SSRF on a server-side fetch endpoint is a well-known attack class. The protection MUST happen BEFORE the fetch (DNS resolution attack) and BEFORE following redirects (redirect-to-private-IP attack). The CIDR rules are stable and exhaustive at IPv4 + IPv6 levels.

**Alternatives considered**:
- **Library `is-private-ip` / `private-ip`** — rejected: small libraries with churn risk for security-critical code; rolling our own is ~80 lines and easier to audit.
- **HTTP-level allowlist** (only allow scraping pre-approved domains) — rejected: defeats the feature's value. Creators paste arbitrary product URLs.
- **Proxy through a third-party scraper** — rejected (R1 alt-considered).

## R4 — Robots.txt enforcement (FR-004)

**Decision**: **`robots-parser`** library + per-host in-memory cache with 1-hour TTL.

**Flow**:
1. On each scrape request, derive `https://<host>/robots.txt`.
2. Check the cache. If hit and TTL fresh → use cached parse.
3. On cache miss: fetch `robots.txt` (with 5 s timeout, 100 KB cap), parse with `robots-parser`, cache.
4. If `robots.txt` fetch fails (404, network error, etc.) → treat as "no rules apply" (RFC 9309 default).
5. If `robots.txt` explicitly disallows our path for `User-Agent: *` (or any UA we send) → refuse the scrape with `error_code: "robots_blocked"`.

The cache is `Map<hostname, { parsed: RobotsParser, expiresAt: number }>` in module scope. Memory bound: tens of KB per host × low-thousand hosts = small.

**Rationale**: Respecting `robots.txt` is a brand-safety + ethical floor. The 1-hour TTL is the standard convention (most CDNs and search bots use 1–24 hours). Caching prevents hammering target sites with `robots.txt` fetches on every wizard paste.

**Alternatives considered**:
- **No robots.txt enforcement** — rejected per FR-004; spec is explicit that this is non-negotiable.
- **Persistent disk cache** — overkill at v1 (memory cache rebuilds on Next.js cold start in milliseconds; per-host robots.txt is small).
- **Fetch robots.txt asynchronously and check after the page fetch already started** — rejected: violates the "respect intent" principle. Robots check must gate the page fetch.

## R5 — Rate limiting (FR-012)

**Decision**: Per-IP sliding-window counter, in-memory at v1. 30 requests / 60 seconds.

**Implementation shape**: `Map<ip, number[]>` where the array stores timestamps (ms). On each request:
1. Strip timestamps older than `Date.now() - 60_000`.
2. If remaining length ≥ 30 → return `429 rate_limited`.
3. Otherwise push current timestamp.

A periodic cleanup (every 5 minutes) sweeps entries whose all timestamps are >5 min old.

**Rationale**: A scrape is more expensive than a typical API call (1 outbound HTTP request, 1 robots.txt fetch on cache miss, ~5 KB parse). Rate-limiting protects the wizard from accidental loops + occasional abuse. 30 req/min is generous for legitimate use (1 paste per 2 seconds is fast).

**Alternatives considered**:
- **Token bucket** — equally fine; sliding window is simpler to reason about.
- **External rate-limit service** (Upstash / Redis) — rejected at v1: in-memory is enough until we have multiple Next.js instances behind a load balancer. When debt #2 (multi-tenant) lands in Step 2, the rate limiter scopes per-tenant via the same path-rewrite uploads inherit.
- **Per-tenant rate limit** — deferred to Step 2 with debt #2.

## R6 — Test mocking strategy

**Decision**: **MSW** (`msw` ≥ 2.x) for request-level mocking + **Vitest** as the test runner.

**Pattern**:
```ts
import { setupServer } from 'msw/node';
import { http } from 'msw';

const server = setupServer(
  http.get('https://acmebrew.com/products/cold-brew-kit', () =>
    new Response('<html><head><meta property="og:title" content="..."/></head></html>', {
      headers: { 'content-type': 'text/html' },
    }),
  ),
  http.get('https://acmebrew.com/robots.txt', () =>
    new Response('User-agent: *\nAllow: /', { headers: { 'content-type': 'text/plain' } }),
  ),
);
```

Tests register fixtures per scenario — including failure modes (404, 403, 5xx, redirect loop, robots.txt-disallowed, JS-only SPA stub).

**Rationale**: MSW is the standard for mocking HTTP at the test layer in Node.js + Vitest. It works at the `undici` layer (which Next.js uses), so the route's actual fetch code runs against the mock. No changes to production code for testability. Avoids brittle hand-rolled spies.

**Alternatives considered**:
- **Real network calls in CI** — rejected: flaky, slow, ethics issues (test traffic to real sites).
- **`nock`** — older, similar shape to MSW. MSW has better TypeScript support and is more actively maintained.
- **Hand-mocked `fetch`** — rejected: requires custom DI in the route to swap fetch implementations; MSW is cleaner.

## R7 — JS-rendering fallback rationale

**Decision**: NO JS rendering at v1. Static HTML fetch only. SPAs that don't pre-render their content trigger `error_code: "no_useful_content"` and route to the user-facing fallback ("paste a description instead").

**Why deferred**:

1. **Operational cost**: a Playwright / Puppeteer fallback adds ~300 MB of Chromium binary to the deployed image. Significant.
2. **Latency cost**: cold-start a headless browser + wait for JS hydration → 5–15 s per scrape; closer to 30 s on serverless cold-start. Breaks SC-003's p99 budget.
3. **Complexity cost**: Chromium needs to be told when to consider the page "ready" (load event vs network-idle vs DOM-stable). Hard to get right; easy to time out wrong.
4. **Unclear ROI**: many of the most useful product pages (Shopify storefronts, marketing landing pages, traditional CMS-driven sites) DO have OG tags in their static HTML. Modern e-commerce stacks are usually SSR-friendly. We don't know yet how often we'd actually need JS rendering.

**Fallback path in v1**: if static fetch returns minimal HTML (no `og:*`, no `<title>` content, no `<meta name="description">`, no `<h1>`), the extractor returns `error_code: "no_useful_content"`, the wizard shows "we couldn't find readable content on that page — paste a description instead," and the creator continues with manual entry. The result is honest: we tried, we failed transparently, the user has a clear path forward.

**v2 escalation criteria**: re-evaluate when ≥ 20% of attempted scrapes hit `no_useful_content`. Add Playwright then. Operator instrumentation: log the count, add to the operator dashboard once metrics infra exists.

**Alternatives considered**:
- **Add Playwright at v1** — rejected for the cost reasons above.
- **Use a SaaS scraper for JS rendering only** — rejected per R1 alt-considered.

## R8 — Composing the enriched subject string

**Decision**: A pure function `composeEnrichedSubject({title, description, sourceDomain}): string` that produces a deterministic format:

```ts
`${title}. ${description}. (sourced from ${sourceDomain})`
```

With a `MAX_SUBJECT_LEN = 500` cap. If the composed string exceeds the cap, truncate the description side first (it's typically the longest), then the title, never the source attribution. Truncation suffix: `…`.

**Rationale**: The composed string is just text the existing LLM prompt template at `app/services/llm.py:603-628` consumes as `{product_info}`. The `(sourced from <domain>)` suffix gives the LLM useful context (it can decide whether to use the brand name explicitly or generically). The 500-char cap is generous for most product pages but bounds prompt budget — anything longer is probably scraping noise rather than signal.

**Alternatives considered**:
- **Send title + description + URL as separate fields** — rejected: would require Layer 3 schema change (FR-011 forbids).
- **JSON-encode the structured data into the subject** — rejected: ugly, harder for the LLM to consume than natural-language sentences.
- **Always include the URL in the subject** — rejected: defeats the purpose. The LLM should NEVER see the URL string itself; it should see the human-meaningful content extracted from the URL.

## R9 — Wizard URL-detection regex (FR-001)

**Decision**: A simple regex: `^https?:\/\/\S+$` after `String.prototype.trim()`. Detected only on PASTE events + on input stabilization (300 ms debounce). Does NOT detect URLs without scheme (e.g., `acmebrew.com` is treated as plain text).

**Rationale**: Strict scheme requirement keeps false positives at zero. Creators who genuinely want URL behavior need to type `https://...` — same convention browsers use for autocomplete. Trying to detect domain-like strings (`example.com`) creates ambiguity (is "Apple" a brand or an example.com?).

**Alternatives considered**:
- **Detect `domain.tld` as URL** — rejected per the ambiguity above.
- **Detect on every keystroke** — rejected: noisy + spawns scrape requests for partial URLs.
- **Manual "Use as URL" toggle button** — rejected per FR-001's auto-trigger requirement; scraping should "just work" for paste-a-URL behavior.

## R10 — Smoke + integration test layout

**Decision**: Three test files under `visualai-frontend/tests/`:

1. **`url-scrape.test.ts`** — pure unit tests for `isUrlLike(input: string)` + `composeEnrichedSubject(parts)`. No mocks needed; fast (<100 ms total).
2. **`ssrf.test.ts`** — pure unit tests for `assertSafeUrl(url)`. Includes the SC-006 fixed test set: `http://localhost`, `http://127.0.0.1`, `http://192.168.1.1`, `http://10.0.0.1`, `file:///etc/passwd`, `data:text/html,...`, `javascript:alert(1)`. All MUST throw the SSRF error.
3. **`scrape-route.test.ts`** — integration tests for the API route using MSW. Covers every `error_code` from the contract: `fetch_404`, `fetch_403`, `fetch_timeout`, `robots_blocked`, `no_useful_content`, `non_html_response`, `ssrf_blocked`, `redirect_loop`, `tls_error`, `rate_limited`. Plus the happy path with a synthetic OG-rich HTML stub.

Total run time target: <10 s for the whole suite.

**Rationale**: The constitution's pytest-gate rule doesn't apply (no Python), but the spirit (smoke tests for new code paths) does. Vitest + MSW is the JS analog of pytest + responses.

**Alternatives considered**:
- **Playwright end-to-end** — overkill for v1; covered by manual quickstart for now.
- **Skip integration tests, only unit tests** — rejected: the route's error-code handling is the most important contract surface; skipping integration tests would mean SC-002's "100% of failures surface as typed errors" lacks automated verification.

## Summary

All NEEDS-CLARIFICATION items resolved. Three new runtime deps (`cheerio`, `sanitize-html`, `robots-parser`) + two dev deps (`vitest`, `msw`) — all small, pure-JS, no native bindings. Layer 3 stays untouched. SSRF + robots.txt protection are the security floors. JS-rendering fallback deferred to v2 with explicit escalation criteria. The plan is implementation-ready.
