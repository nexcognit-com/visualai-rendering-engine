# Contract: Scrape Endpoint

**Feature**: [spec.md](../spec.md) | **Plan**: [plan.md](../plan.md) | **Data Model**: [data-model.md §Entity 1](../data-model.md)

The HTTP shape of `POST /api/scrape-url` — Layer 1 server route that fetches a URL, extracts business context, and returns a typed result. This endpoint never reaches Layer 3 / MPT.

## Endpoint

```
POST /api/scrape-url
```

## Authentication

v1: none (Step 1 of the build plan is single-user, no auth — debt #2 in `STEP1_DEBT.md`). When debt #2 repays in Step 2, this endpoint inherits Layer 2's JWT middleware.

## Request

| Aspect | Value |
|---|---|
| Content-Type | `application/json` |
| Body shape | `{ url: string }` |
| URL constraint | Must be a parseable URL ≤ 2048 chars; scheme `http:` or `https:` only |

```sh
curl -X POST http://localhost:3001/api/scrape-url \
  -H "Content-Type: application/json" \
  -d '{"url": "https://acmebrew.com/products/cold-brew-kit"}'
```

## Success response

**Status**: 200 OK
**Body**:

```json
{
  "ok": true,
  "title": "Cold Brew Concentrate Kit — 32 oz",
  "description": "Slow-steeped at home overnight; tastes like our cafe's.",
  "image_url": "https://acmebrew.com/cdn/cold-brew-kit-hero.jpg",
  "source_domain": "acmebrew.com",
  "raw_html_size": 184320,
  "scrape_elapsed_ms": 1247
}
```

| Field | Type | Notes |
|---|---|---|
| `ok` | `true` | discriminator |
| `title` | string ≤ 200 chars | extracted by priority: og:title → `<title>` → first `<h1>` |
| `description` | string ≤ 500 chars | extracted by priority: og:description → meta name=description → first `<p>` |
| `image_url` | string \| null | absolute https URL of the og:image, or null if none extractable |
| `source_domain` | string | hostname only (no scheme, no port) |
| `raw_html_size` | int | bytes consumed; useful for ops debugging |
| `scrape_elapsed_ms` | int | server-side wall-clock; lets ops verify SC-003 |

## Error responses

All errors share this shape:

```json
{
  "ok": false,
  "error_code": "<code>",
  "detail": "<human-readable>"
}
```

| HTTP | `error_code` | Trigger | Wizard UX (verbatim) |
|---|---|---|---|
| 400 | `url_invalid` | URL is missing, non-string, > 2048 chars, or `new URL()` throws | "That doesn't look like a valid URL." |
| 400 | `ssrf_blocked` | Scheme not http/https, OR resolved IP is loopback / RFC 1918 / link-local / multicast / reserved | "That URL points to a non-public address. Paste a description instead." |
| 403 | `robots_blocked` | Target site's robots.txt disallows the path for our User-Agent | "This site asks not to be scraped. Paste a description of your product instead." |
| 404 | `fetch_404` | Target returned 404 | "Couldn't reach that page (404 Not Found). Try a different URL." |
| 403 | `fetch_403` | Target returned 403 (anti-bot, etc.) | "That page blocks automated access. Paste a description instead." |
| 502 | `fetch_5xx` | Target returned any 5xx | "The site is currently down or unreachable. Try again or paste a description." |
| 504 | `fetch_timeout` | Total scrape time exceeded 10 s | "That page took too long to load. Try again or paste a description." |
| 422 | `non_html_response` | Target returned a non-HTML content-type (PDF, image, JSON, etc.) | "That URL points to a `<content type>` file, not a webpage. Paste a description instead." |
| 422 | `no_useful_content` | HTML loaded but no extractable og:* / `<title>` / meta description / `<h1>` | "We couldn't find readable content on that page. Paste a description instead." |
| 421 | `redirect_loop` | More than 5 redirect hops | "That URL redirects too many times. Try the final destination directly." |
| 421 | `tls_error` | TLS / certificate error | "We couldn't verify that site's security certificate. Try a different URL." |
| 429 | `rate_limited` | Per-IP sliding window exceeded 30 req/min | "Too many scrape requests. Please wait a moment and try again." |

## Behavior contract (validation order)

The server runs these checks in order; the first failure short-circuits.

1. **Request shape validation** (Zod) → 400 `url_invalid` if missing or malformed.
2. **Rate limit** (per-IP sliding window, 30 req/min) → 429 `rate_limited` on excess.
3. **SSRF gate** (`assertSafeUrl`) → 400 `ssrf_blocked` for any rule violation. Runs BEFORE DNS-leaking fetch.
4. **Robots.txt check** (cached lookup with 1h TTL) → 403 `robots_blocked` if disallowed.
5. **Fetch** with `undici`:
   - `redirect: 'manual'` so we re-run SSRF on each Location header.
   - 5 MB body cap → abort with `fetch_timeout` if exceeded (treats too-large as timeout for simplicity at v1).
   - 10 s total timeout → abort with `fetch_timeout` on expiration.
   - 5 redirect-hop cap → `redirect_loop` if exceeded.
   - TLS errors → `tls_error`.
   - 4xx/5xx status codes → respective `fetch_404` / `fetch_403` / `fetch_5xx`.
6. **Content-type check** → 422 `non_html_response` if not `text/html` (or `application/xhtml+xml`).
7. **HTML parse + extract** (Cheerio) — if no extractable title OR no extractable description, → 422 `no_useful_content`.
8. **Sanitize** extracted strings (`sanitize-html` with text-only config) → strip any markup that snuck through textContent.
9. **Truncate** title to 200 chars, description to 500 chars (suffix with `…`).
10. **Return 200** with the success payload.

## SSRF protection details

See [`ssrf-protection.md`](./ssrf-protection.md) for the exhaustive refusal rules + acceptance test set.

## Robots.txt enforcement details

- Fetch `https://<host>/robots.txt` with a 5 s timeout and 100 KB body cap.
- Parse with `robots-parser`.
- If our User-Agent (or `*`) is disallowed for the target path → `robots_blocked`.
- Cache the parsed result per-host for 1 hour.
- If `robots.txt` fetch returns 404 / network error / parse error → treat as "no rules" (RFC 9309 default).
- **No "override" toggle** — this is a non-negotiable security floor.

## Rate limit details

- Sliding window: timestamps within `Date.now() - 60_000` ms count toward the 30-req limit.
- Identifier: client IP (first hop in `X-Forwarded-For`, fallback to socket address).
- Counter is in-memory at v1; lost on server restart; per-process. Multi-instance deployments see effective rate = 30 × instance count.
- Periodic cleanup (every 5 min) sweeps entries with all-stale timestamps.

## Response headers

| Header | Value | Notes |
|---|---|---|
| `Content-Type` | `application/json; charset=utf-8` | always |
| `Cache-Control` | `no-store` | scrape results never cached at the HTTP layer |
| `X-Scrape-Elapsed-Ms` | integer | duplicate of body field for ops observability |

## Examples

### Successful scrape

```sh
curl -X POST http://localhost:3001/api/scrape-url \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/products/widget"}'
```

→ 200:

```json
{
  "ok": true,
  "title": "Widget — Premium Quality",
  "description": "Hand-crafted widgets for the modern artisan.",
  "image_url": "https://example.com/widget-hero.jpg",
  "source_domain": "example.com",
  "raw_html_size": 47820,
  "scrape_elapsed_ms": 423
}
```

### Robots-blocked

```sh
curl -X POST http://localhost:3001/api/scrape-url \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example-no-bots.com/page"}'
```

→ 403:

```json
{
  "ok": false,
  "error_code": "robots_blocked",
  "detail": "This site asks not to be scraped. Paste a description of your product instead."
}
```

### SSRF blocked

```sh
curl -X POST http://localhost:3001/api/scrape-url \
  -H "Content-Type: application/json" \
  -d '{"url": "http://localhost:3306/"}'
```

→ 400:

```json
{
  "ok": false,
  "error_code": "ssrf_blocked",
  "detail": "That URL points to a non-public address. Paste a description instead."
}
```

## Verification (drives task design)

Each row of the error table becomes a Vitest + MSW integration test:

| Test ID | Setup | Expected |
|---|---|---|
| SE-1 | Valid OG-rich product page | 200 with all fields populated |
| SE-2 | Page with og:title only (no og:description) | 200; description falls back to `<meta name=description>` then `<p>` |
| SE-3 | Page with NO og + NO meta + NO h1 | 422 `no_useful_content` |
| SE-4 | Target returns 404 | 404 `fetch_404` |
| SE-5 | Target returns 403 | 403 `fetch_403` |
| SE-6 | Target returns 500 | 502 `fetch_5xx` |
| SE-7 | Target hangs > 10 s | 504 `fetch_timeout` |
| SE-8 | robots.txt disallows the path | 403 `robots_blocked` |
| SE-9 | URL is http://localhost | 400 `ssrf_blocked` |
| SE-10 | URL is file:///etc/passwd | 400 `ssrf_blocked` |
| SE-11 | URL points to a PDF | 422 `non_html_response` |
| SE-12 | 6 redirect hops | 421 `redirect_loop` |
| SE-13 | Same IP fires 31 requests in 60 s | 31st returns 429 `rate_limited` |
| SE-14 | Body field missing from request | 400 `url_invalid` |
| SE-15 | URL > 2048 chars | 400 `url_invalid` |

These 15 tests are the contract surface for `/speckit-tasks` to schedule.
