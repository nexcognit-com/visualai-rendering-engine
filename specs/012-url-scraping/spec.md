# Feature Specification: URL Scraping for Step 1 Input

**Feature Branch**: `012-url-scraping`
**Created**: 2026-05-02
**Status**: Draft
**Input**: User description: "URL scraping for Step 1 input — when the user pastes a URL, fetch + extract content (title, meta description, OG tags, primary image, key product info) so the LLM gets real business context instead of just the raw URL string. Resolves the 'agent silently treats URL as text' capability gap discovered during testing."

## Overview

Close the most significant capability gap in the Mode 2 wizard's Step 1 input: today, when a creator pastes a URL like `https://acmebrew.com/products/cold-brew-kit`, the system silently sends that raw string to the LLM as `{product_info}` text — no fetch, no content extraction, no real understanding of the business. The LLM either hallucinates a product description from the URL pattern alone or writes generic ad copy that has nothing to do with the actual product. The wizard's input label even invites this behavior ("paste a product name, **a URL**, or a topic"), so the failure is doubly bad: we promise the URL has meaning, then secretly treat it as a meaningless string.

This feature adds a real URL-fetching step **in Layer 1 (`visualai-frontend`)** before the render request reaches MPT. When the wizard detects a URL in Step 1, the frontend's server-side route fetches the page (with a real User-Agent and respectful rate limits), extracts structured business context — page title, meta description, Open Graph tags (og:title / og:description / og:image), the first H1, and the primary product image — and presents that extracted preview to the creator for review/edit BEFORE submission. The wizard then composes a richer, prompt-friendly subject string from the extracted fields and sends THAT to MPT as `video_subject`. **Layer 3 (this MPT repo) sees only the enriched text — it never sees the URL itself**.

This Layer-1-only scoping resolves what would otherwise be a Principle IV concern: the constitution restricts direct external HTTP calls in Layer 3 to Mode 5. By keeping the scraping fully in Layer 1 and feeding only text to Layer 3, the rendering engine stays pure and Principle IV stays untouched. When Layer 2 (Orchestration API) lands in Step 2 of the build plan, the scraping naturally moves there with no schema change.

This is the audio counterpart's positional cousin: spec 010 surfaced existing engine capability through the wizard; spec 012 ADDS a new pre-render step entirely outside the engine.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Creator pastes a product URL and the rendered video reflects real product details (Priority: P1)

A creator pastes `https://acmebrew.com/products/cold-brew-kit` into Step 1's input field. Within ~3 seconds the wizard shows a small "Read from URL" preview card under the input: the product's actual title ("Cold Brew Concentrate Kit — 32 oz"), its real one-line description ("Slow-steeped at home overnight; tastes like our cafe's"), and a thumbnail of the product image. The creator either accepts the preview as-is, edits it ("change 'cafe' to 'coffeehouse'"), or clears it and pastes their own description. They submit. The rendered MP4's voiceover script is grounded in the real product — not generic ad-speak generated from the URL pattern alone.

**Why this priority**: This is the entire reason the feature exists. Without P1, "paste a URL" remains a lie — the wizard says it'll use the URL but secretly throws it away. Every creator who tests with a URL today gets misleading output. P1 is the floor.

**Independent Test**: Render two videos for the same URL — one with the wizard's URL-scraping path active, one with the input forced to plain text mode (URL pasted as `Cold brew kit`). The scraping render's voiceover MUST mention specific product details from the page (e.g., "32 oz", "overnight steep", or whatever the real OG description names); the plain-text render MUST be visibly more generic. A human reviewer correctly identifies the scraping render in 9/10 trials.

**Acceptance Scenarios**:

1. **Given** a creator pastes a URL into Step 1's input field, **When** the wizard detects it's a URL (regex / scheme check), **Then** the wizard automatically calls the scrape endpoint and shows the extracted preview within 5 s under the input.
2. **Given** the scrape returned a title + description + image, **When** the creator clicks "Use this", **Then** the wizard combines those fields into an enriched subject string (e.g., `"Cold Brew Concentrate Kit — 32 oz. Slow-steeped at home overnight; tastes like our cafe's. (sourced from acmebrew.com)"`) and proceeds to Step 2 with that string in state.
3. **Given** the creator wants to edit the extracted preview, **When** they click "Edit", **Then** the title and description fields become inline-editable and saving propagates to the subject string the wizard will submit.
4. **Given** the creator wants to discard the scraped result and write their own, **When** they click "Clear", **Then** the input field returns to plain-text mode and submission proceeds as if no URL was ever pasted (zero regression for the existing text-only flow).
5. **Given** the rendered video completes, **When** the creator listens to the voiceover, **Then** specific phrases or facts from the scraped page are present in the script — not just generic ad language.

---

### User Story 2 — Scraping failures surface clearly with a graceful fallback (Priority: P1)

The creator pastes a URL that can't be scraped — could be many reasons: a 404 page, a site that returns HTTP 403 to non-browser User-Agents, a JS-only single-page application that has no useful HTML at the document root, a site whose robots.txt forbids scraping, a timeout, a TLS error, a non-HTML response (PDF, image), or simply no OG/meta data. The wizard must NOT silently fall through to "treat the URL as text" because that's the exact failure mode this feature is meant to fix. Instead, the wizard surfaces a clear typed error with the underlying reason and a one-click "use as plain description instead" fallback. The creator chooses explicitly: retry, paste a description, or proceed knowingly with the raw URL as text.

**Why this priority**: Same priority as US1 because a silent failure here is the EXACT bug we're trying to fix. Without P2, scrapes that fail silently re-introduce the original problem at a new layer. P2 makes the feature honest about its boundaries.

**Independent Test**: Trigger each failure mode (404, 403, robots.txt-blocked, JS-only SPA with no static HTML, timeout, non-HTML response, invalid URL, TLS error). For each, the wizard MUST display a typed error message naming the cause AND offer the explicit fallback. Zero silent degradations — if the test sees the URL accepted and a render proceed without either a successful preview or a visible error, the test fails.

**Acceptance Scenarios**:

1. **Given** the URL returns 404, **When** the wizard scrapes, **Then** a typed error appears: "Couldn't reach that page (404 Not Found). Paste a description instead, or try a different URL."
2. **Given** the URL is blocked by robots.txt, **When** the wizard scrapes, **Then** a typed error: "This site asks not to be scraped. Paste a description of your product instead."
3. **Given** the page is a JS-only SPA with no useful static HTML, **When** the wizard extracts, **Then** a typed error: "We couldn't find readable content on that page. Paste a description instead."
4. **Given** the scrape times out (>10 s), **When** the timeout fires, **Then** a typed error: "That page took too long to load. Try again or paste a description."
5. **Given** the URL returns a PDF / image / non-HTML content, **When** the wizard scrapes, **Then** a typed error: "That URL points to a `<content type>` file, not a webpage. Paste a description instead."
6. **Given** any of the above failures, **When** the creator clicks the offered "use as plain text" fallback, **Then** the wizard switches to plain-text mode with the URL string pre-populated in the input field; the creator can edit and submit normally.

---

### User Story 3 — Creator sees and edits the extracted business context before submitting (Priority: P2)

The scrape succeeded, but the extracted title is too long ("Cold Brew Concentrate Kit | Acme Brew Co. | Free Shipping on Orders Over $50"), the description starts with brand boilerplate, or the OG image isn't the most representative shot. The wizard surfaces all extracted fields as editable, lets the creator trim/rewrite/swap inline, and only sends the cleaned-up version to MPT. Defaults are good enough for many cases — but the override path is essential for branding-aware creators.

**Why this priority**: lifts the feature from "OK for casual creators" to "good for serious marketers." Without P3, creators with editorial standards reject auto-extracted output and lose trust. P2 because basic auto-extraction (P1) covers the demo path; editing is the polish that separates "working" from "shippable."

**Independent Test**: After a successful scrape, every extracted field MUST be editable inline. Edits MUST persist to the wizard's submission payload. Reset / undo MUST be visible. Verified by editing each field and confirming the submitted `video_subject` reflects the edit.

**Acceptance Scenarios**:

1. **Given** a successful scrape preview, **When** the creator clicks any extracted field (title, description), **Then** the field becomes inline-editable with a clear save / cancel UX.
2. **Given** the creator edited the description, **When** they submit, **Then** the enriched subject string sent to MPT contains the edited text, not the original scrape.
3. **Given** the creator made a long description shorter, **When** the wizard re-composes the subject string, **Then** the field length stays under the practical LLM-prompt budget (the wizard truncates if needed and shows a warning).

---

### User Story 4 — Brand Library forward-compat hook (Priority: P3, deferred implementation)

When the Brand Library feature lands (Step 5 of the build plan), a tenant's saved business profile (logo + brand voice + key product taxonomy) can pre-fill or augment the URL scrape. v1 of this spec implements per-render scraping only; the spec ensures the structured output shape can later be merged with Brand Library entries without schema change.

**Why this priority**: same rationale as spec 009 / 010's matching stories — schema-shape forward-compat is cheap to get right today, expensive later.

**Independent Test**: review the structured output schema (Entity 2 below) against the future Brand Library output shape; confirm a `source: "brand-library" | "url-scrape" | "manual"` discriminator can be added without breaking v1.

---

### Edge Cases

- **URL with tracking parameters** (`?utm_source=...&utm_campaign=...`): scrape uses the URL as-is; tracking params don't affect the scrape but pollute the displayed source link. The wizard SHOULD strip common tracking params from the displayed URL but submit them as-is to the scrape endpoint (some sites legitimately use query params for content).
- **Very large pages** (> 5 MB HTML): the scrape endpoint truncates the response body at 5 MB to bound memory + parse time. Extracts use whatever's in the first 5 MB.
- **Site requires JavaScript** (SPA / hydration-only content): the static fetch returns minimal HTML with no useful OG/meta. Treated as P2 failure mode; v1 does NOT add a headless-browser fallback (deferred to v2 follow-up — see Open Follow-Ups).
- **Login-walled pages**: the scrape sees the login page, not the real content. Detected by heuristic (presence of password input, "sign in" headings) — emits the P2 error: "This page requires login. Paste a description instead."
- **Paywall walls**: similar to login-walls. Detected by heuristic where possible; if missed, the scrape returns whatever HTML the publisher shows non-subscribers (which is usually a teaser snippet — sometimes useful as ad context, sometimes not). Fallback to user editing.
- **Redirect loops** (>5 hops): aborted with a typed error.
- **HTTPS certificate errors**: aborted with a typed error; the wizard does NOT offer a "trust anyway" option (security floor).
- **Localhost / private-IP URLs** (`http://localhost:8080/...`, `http://192.168.x.x/...`, `http://10.x.x.x/...`): the scrape endpoint refuses these — treated as the same class as login-wall. **Server-side request forgery (SSRF) protection**: the scrape resolver blocks loopback + RFC 1918 + link-local addresses unconditionally.
- **URLs to file:// / data: / javascript: schemes**: refused; only `http://` and `https://` are accepted. Same SSRF protection.
- **Site blocks the User-Agent we use**: the wizard tries one fallback User-Agent (a common browser UA), and if both fail, surfaces the P2 error with the underlying HTTP status.
- **Robots.txt explicitly disallows scraping**: respected; emits the P2 robots.txt error. The wizard does NOT offer an "override robots.txt" toggle. The creator can paste a description manually.
- **Multiple URLs in the same input** (e.g., the creator pasted three URLs separated by commas): only the first URL is scraped; the rest are ignored. Wizard hint: "Only the first URL was used. Remove the others or pick a different one."
- **Scraping the same URL twice in the same wizard session**: results MAY be cached client-side for 5 minutes (UX nicety, not requirement); after that, re-fetched.
- **MPT pipeline receives the enriched subject and passes through unchanged**: the engine doesn't know or care that the subject was URL-derived. Layer 3 stays pure (Principle I + IV preserved).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The wizard MUST detect URL inputs in Step 1 by regex pattern (`^https?://[^\s]+$` after trim) AND auto-trigger scraping within 500 ms of input stabilization (debounce on typing, fire on paste). The detection logic MUST live in Layer 1 (`visualai-frontend`) — Layer 3 stays unchanged.
- **FR-002**: A new server-side route in the frontend (`POST /api/scrape-url`) MUST accept `{url: string}` and return `{ok: true, title, description, image_url, source_domain, raw_html_size}` on success OR `{ok: false, error_code, detail}` on failure. The route lives in Next.js's server runtime — no browser-side cross-origin fetches (same-origin contract).
- **FR-003**: The scrape endpoint MUST extract these fields in priority order:
  1. **Title**: `og:title` → `<title>` → first `<h1>`
  2. **Description**: `og:description` → `<meta name="description">` → first paragraph of body content
  3. **Image**: `og:image` → first `<img>` with reasonable dimensions
  4. **Source domain**: parsed from the input URL
  All HTML content MUST be sanitized (script tags stripped, no executable content) before being returned to the browser.
- **FR-004**: The scrape endpoint MUST respect `robots.txt` — fetch it for the target host, parse it, and refuse to scrape if the path is disallowed for the User-Agent used. The robots.txt fetch MUST be cached server-side for 1 hour per host to avoid hammering target sites.
- **FR-005**: The scrape endpoint MUST cap fetch size at 5 MB and total time at 10 s. Beyond either, the request aborts and returns a typed error.
- **FR-006**: The scrape endpoint MUST refuse to fetch loopback / RFC 1918 / link-local IPs (SSRF protection). Schemes other than `http://` and `https://` MUST be refused. Maximum 5 redirect hops.
- **FR-007**: The wizard MUST surface a preview card under the input within 500 ms of receiving the scrape result, showing title + description + image thumbnail + source domain. The preview is editable inline (FR-008) and dismissable.
- **FR-008**: All extracted text fields (title, description) MUST be editable inline in the preview card. Edits propagate to the wizard's submitted `video_subject` string, which is composed as `"<edited title>. <edited description>. (sourced from <domain>)"`. The wizard truncates the composed string if it exceeds the LLM prompt budget (~500 chars at v1).
- **FR-009**: Every scrape failure MUST surface as a typed error in the wizard with: (a) the cause in plain language; (b) a "use as plain text" fallback button that pre-populates the input with the URL string. The wizard MUST NOT silently fall through to text-mode without showing the error.
- **FR-010**: When the creator dismisses the scrape preview or chooses "use as plain text", the wizard's behavior MUST be byte-equivalent to the existing pre-spec-012 behavior — same MPT request body, same render output. Zero regression for the established text-only path.
- **FR-011**: The MPT engine (`app/services/llm.py`, `app/services/material.py`, `app/services/task.py`, `app/models/schema.py`) MUST NOT be modified by this feature. The enriched subject string is just text — the existing pipeline accepts it without code change.
- **FR-012**: The scrape endpoint MUST rate-limit by client IP at v1: maximum 30 requests per minute per IP (sliding window). When debt #2 (multi-tenant) repays in Step 2, the limit MAY scope per-tenant. Returns HTTP 429 `rate_limited` on excess.
- **FR-013**: The scrape endpoint MUST log every fetch (URL, status, response size, elapsed time) at INFO level for ops visibility. Failures log at WARNING with reason. Logs go to whatever Next.js's server logger is wired to (no new infrastructure).
- **FR-014**: The structured scrape output schema MUST be forward-compatible with future Brand Library augmentation: an optional `source: "url-scrape" | "brand-library" | "manual"` discriminator field MAY be added in v2 without breaking v1 consumers.

### Key Entities

- **URL Input**: a string the creator paste into Step 1. The wizard's URL-detection regex (FR-001) classifies it as URL or plain text. Once classified as URL, the wizard hands it to the scrape endpoint and switches into scraping UI mode until the response (success or failure) lands.
- **Scrape Result**: structured output from the scrape endpoint. Fields:
  - `ok: boolean` — success / failure discriminator
  - On success: `title: string`, `description: string`, `image_url: string | null`, `source_domain: string`, `raw_html_size: integer`
  - On failure: `error_code: "fetch_404" | "fetch_403" | "fetch_timeout" | "robots_blocked" | "no_useful_content" | "non_html_response" | "ssrf_blocked" | "redirect_loop" | "tls_error" | "rate_limited"`, `detail: string` (human-readable)
  All text content already sanitized (no scripts, no inline event handlers).
- **Wizard Scrape State**: ephemeral state in the wizard tracking the current scrape's lifecycle:
  - `mode: "text" | "scraping" | "preview" | "error"`
  - `result: ScrapeResult | null`
  - `editedTitle: string | null` (overrides `result.title` when set)
  - `editedDescription: string | null` (overrides `result.description` when set)
  - `error: { code: string, detail: string } | null`
  Cleared on input change or wizard reset.
- **Enriched Subject**: the composed text string the wizard sends to MPT as `video_subject`. Built from `(editedTitle ?? result.title) + ". " + (editedDescription ?? result.description) + ". (sourced from " + result.source_domain + ")"`. Truncated to ~500 chars if needed.
- **Robots.txt Cache**: server-side per-host cache of parsed robots.txt rules, TTL 1 hour. Memory-only at v1 (lost on Next.js server restart); v2 may persist.
- **Rate Limit Counter**: per-IP sliding-window counter, in-memory at v1.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a representative test set of 10 product URLs (e-commerce, marketing landing pages, single-product Shopify stores), the rendered video's voiceover MUST mention at least one specific factual detail from the scraped page in ≥ 80% of cases. Verified by spot-listening + comparison against the scraped `description` field.
- **SC-002**: 100% of scrape failures MUST produce a typed error visible in the wizard with a "use as plain text" fallback. Zero silent fallbacks. Verified by inducing each of the 10 documented error_code conditions.
- **SC-003**: Scrape endpoint p95 latency ≤ 5 s; p99 ≤ 10 s (matches the timeout cap). Measured by timing 50 scrapes against a mix of fast and slow real-world product URLs.
- **SC-004**: For URLs that today (pre-spec-012) produced clean text-only renders, post-spec-012 behavior MUST be byte-equivalent IF the creator dismisses the preview or chooses "use as plain text" (zero regression contract). Verified by matched-pair render comparison.
- **SC-005**: The wizard's UX from "URL pasted" to "preview shown or error displayed" MUST complete in ≤ 7 s for 95% of attempts (covers fetch + parse + render). Measured wall-clock from paste event to preview/error visibility.
- **SC-006**: SSRF protection MUST refuse 100% of attempts to fetch loopback / private-IP / non-HTTP scheme targets. Verified by a fixed test set: `http://localhost`, `http://127.0.0.1`, `http://192.168.1.1`, `http://10.0.0.1`, `file:///etc/passwd`, `data:text/html,...`, `javascript:alert(1)`. All MUST return `ssrf_blocked`.
- **SC-007**: Rate limit MUST trigger on the 31st request from the same IP within a 60-second window. Verified by burst test.
- **SC-008**: The Brand Library forward-compat field shape MUST validate when extended with `source: "brand-library"` in a synthetic test (FR-014). Confirms v2 extensibility.

## Assumptions

- **Scraping happens entirely in Layer 1** (`visualai-frontend`). The MPT engine never sees the URL — only the enriched text. This keeps Principle I (Layer 3 = rendering only) and Principle IV (no direct external API calls in Layer 3) intact. When Layer 2 ships in Step 2, the scrape endpoint can move there without changing the schema.
- **The wizard's URL detection is regex-based**, not heuristic. Pasting `https://...` triggers the path; pasting `acmebrew.com` does NOT (no scheme). This is deliberate — fewer false positives than a domain-pattern detector, easier to reason about.
- **No JavaScript rendering at v1.** Static HTML fetch only. Sites that hydrate content client-side (some SPAs, modern SaaS landing pages) will return minimal HTML and trigger the `no_useful_content` error. Adding headless-browser support (Playwright / Puppeteer) is a v2+ option — significant infra overhead, deferred deliberately.
- **Robots.txt is respected unconditionally.** No "override" toggle. This is a brand-safety floor: VisualAI MUST NOT scrape sites that explicitly opt out of scraping, regardless of creator wishes.
- **The composed enriched subject string is just text** that the existing LLM prompt template at `app/services/llm.py:603-628` consumes as `{product_info}`. No prompt template changes. The LLM gets richer context as input but emits the same output shape.
- **Mode 2 only at v1.** Other modes (1/3/4/5) inherit URL handling when they ship via their own feature branches. The wizard's URL-scraping panel is per-mode UI.
- **No persistence at v1.** Scrape results are ephemeral wizard state; not saved to the task's `script.json` (the enriched subject IS saved, but as plain text — the URL provenance is lost once the render proceeds). v2 may persist scrape provenance for "regenerate from same URL" flows.
- **No multi-tenant isolation at v1.** The scrape endpoint, robots.txt cache, and rate-limit counter are all process-global. When debt #2 repays in Step 2, all three scope per-tenant — same path-rewrite pattern as uploads.
- **Layer 3 (`MoneyPrinterTurbo` repo) is NOT touched** by this feature. `git diff --stat` of MPT's working tree should show zero changes attributable to this spec. The shipping PR may co-mingle wizard changes from other specs (009 / 010 / 011), but spec 012 itself contributes zero MPT-repo edits.

## Dependencies

- **Layer 1 frontend (`visualai-frontend`)** — this feature lives entirely there. Adds a new server route at `src/app/api/scrape-url/route.ts`, a wizard component for the preview card, and TS types for the structured output.
- **Existing `/api/generate` proxy** (`visualai-frontend/src/app/api/generate/route.ts`) — unchanged. The wizard composes the enriched subject string and submits via the existing proxy, which already accepts arbitrary text in `subject`.
- **No new MPT-side endpoints, schema fields, or service-layer changes.**
- **HTML parsing library** (Cheerio or equivalent) — added to `visualai-frontend`'s `package.json`. Pure-Node, no native deps.
- **No external services.** Everything is in-process inside Next.js's server runtime.

## Constitutional Impact

| Principle | Impact | Mitigation |
|---|---|---|
| **I. Layer 3 Scope** | None — feature lives entirely in Layer 1 (`visualai-frontend`); Layer 3 (this MPT repo) is untouched. | n/a |
| **II. Surgical Fork Discipline** | None — zero touches to fork-surface files (`material.py`, `llm.py`, `voice.py`, `schema.py`, controllers). | n/a |
| **III. Multi-Tenant Context Propagation** | Layer 1 robots.txt cache + rate-limit counter are process-global at v1. Continuation of debt #2 (no tenant scoping). | Piggybacks on existing #2; no new debt. |
| **IV. External Asset Acceptance Over Direct API Calls** | NUANCED but PASS. The constitution restricts external API calls **in Layer 3** (specifically: NanoBanana / Veo / ElevenLabs / Kling / Runway / Pexels). Layer 1 scraping is NOT a Layer 3 violation, but it IS a new external-call surface. The spec deliberately confines all HTTP calls to Layer 1's server runtime so Layer 3 never sees the URL. The constitution's spirit is preserved: Layer 3 only ever receives validated text input. | Documented in §Assumptions. When Layer 2 ships in Step 2, the scrape endpoint moves there cleanly. |
| **V. Mode-Aware Rendering Contract** | None. Feature is wired into Mode 2's wizard UI; other modes get the same URL handling when they ship their own wizards. No mode registry changes. | n/a |

**Net constitutional impact**: zero new debts. The most novel constitutional consideration is Principle IV — handled by the Layer-1-only scoping, with Layer 2 being the natural future home.

## Cross-references

- [Spec 001 — UI Style](../001-nexcognit-ui-style/spec.md) — the preview card's visual treatment uses the brand tokens (border + spacing + accent for the "Read from URL" badge).
- [Spec 010 — Music Track Control](../010-music-control/spec.md) — sibling Layer-1-driven feature; same "wizard adds a step before MPT" architecture pattern.
- [Spec 011 — BGM Audit Warning](../011-bgm-audit-warning/spec.md) — sibling honest-failure-surfacing pattern; same "no silent fallback" discipline as US2 of this spec.
- [5-step build plan](/Users/amraeid/.claude/plans/can-you-confirm-that-dapper-emerson.md) — Step 2 stands up Layer 2 (Orchestration API); the scrape endpoint naturally moves there at that point.
- [Constitution v1.0.2](.specify/memory/constitution.md) — Principle IV's exact wording: "**This engine** [Layer 3] MUST NOT call NanoBanana, Veo 3.1, ElevenLabs, Kling, Runway, or any other generation API directly from Layer 3 code." Layer 1 is not bound by Principle IV.
- [STEP1_DEBT.md](../../STEP1_DEBT.md) — debt #2 (multi-tenant scoping) gains one more burndown task via this feature.

## Open Follow-Ups (deferred to v2)

1. **JavaScript-rendering fallback**: when static fetch returns minimal HTML, optionally retry with a headless browser (Playwright / Puppeteer) for SPA support. Significant infra overhead; defer until creators report this gap.
2. **Persisted scrape provenance**: save the original URL alongside the enriched subject in the task's `script.json` so My Assets can show "this video was generated from acmebrew.com". Useful for re-render workflows.
3. **Brand Library auto-augmentation**: when a tenant has a saved business profile, merge its `brand_voice` and `key_taxonomy` fields into the enriched subject for stronger brand consistency. Lands with Step 5's Brand Library.
4. **Image-driven extraction**: when og:image is found, optionally feed it to a vision model to extract additional product attributes ("looks like a 32 oz mason jar with brown label"). Out of scope for v1; orthogonal to this feature.
5. **Cache scrape results across wizard sessions**: today's 5-minute client cache only covers the current session; persisting to localStorage or a small server-side cache would speed up repeat visits.
