# Quickstart: URL Scraping for Step 1 Input

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Audience**: developers verifying the feature; operators reproducing SC-001..SC-008.

---

## Part 1 — Verify zero regression for plain-text inputs (SC-004)

```sh
# Terminal 1 — MPT backend on :8090 (unchanged)
cd MoneyPrinterTurbo && python main.py

# Terminal 2 — visualai-frontend on :3001
cd visualai-frontend && pnpm dev
```

In your browser at `http://localhost:3001`:

1. Click "Short Marketing Video".
2. In Step 1, type a plain-text description (NOT a URL): e.g. `Hand-painted ceramic mug — microwave-safe`.
3. Continue through the wizard normally.
4. Submit.

**Pass criterion**: render proceeds and completes exactly as before this feature shipped. The wizard's URL detector never fires (no `https?://` scheme), the scrape endpoint is never called, and `video_subject` is the raw text. Confirms FR-010 + SC-004.

---

## Part 2 — Verify happy-path URL scrape (SC-001, P1 acceptance)

In Step 1:

1. Paste a real product URL with reasonable OG tags. Good examples to test:
   - `https://www.basicapparel.com/products/...` (any Shopify storefront)
   - `https://huckberry.com/store/...` (e-commerce with rich OG tags)
   - `https://www.allbirds.com/products/mens-tree-runners` (or any specific shoe)
2. Within ~5 s the wizard MUST show a preview card under the input with:
   - Product title (extracted from og:title)
   - Description (extracted from og:description or meta description)
   - Image thumbnail (from og:image)
   - Source domain badge (e.g., "from allbirds.com")
   - Three actions: **Use this** (primary), **Edit**, **Clear**
3. Click **Use this** and continue through the wizard. Submit.

**Pass criteria**:

- The preview card appeared within 5 s (SC-005 measurable).
- The rendered MP4's voiceover **specifically mentions product details from the page** — not generic ad-speak. Spot-listen and confirm.
- For 8/10 product URLs, the script reflects real product details (SC-001 ≥ 80% threshold).

To verify the LLM saw the enriched subject:

```sh
# After submission, find the task and inspect the script.json
ls -t storage/tasks/ | head -1
cat storage/tasks/<latest-task-id>/script.json | jq '.params.video_subject'
```

The `video_subject` field MUST contain the enriched text — title + description + `(sourced from <domain>)`. The raw URL MUST NOT appear.

---

## Part 3 — Verify scrape failure surfaces clearly (SC-002, P1 acceptance)

Test each failure mode. For each: paste the URL, observe the wizard, verify it shows a typed error AND a "use as plain text" fallback.

| Test | URL | Expected error | Wizard message |
|---|---|---|---|
| 404 | `https://example.com/this-page-definitely-does-not-exist-12345` | `fetch_404` | "Couldn't reach that page (404 Not Found)…" |
| 403 | (find a site that 403s bots; or use `https://www.linkedin.com/in/<some-profile>`) | `fetch_403` | "That page blocks automated access…" |
| Timeout | (synthetic — add a slow target via MSW in tests) | `fetch_timeout` | "That page took too long to load…" |
| Robots-blocked | `https://www.facebook.com/some-page` (Facebook's robots.txt is restrictive) | `robots_blocked` | "This site asks not to be scraped…" |
| Non-HTML | `https://example.com/sample.pdf` (any PDF link) | `non_html_response` | "That URL points to a PDF file, not a webpage…" |
| Invalid URL | `not a url at all` | `url_invalid` | "That doesn't look like a valid URL." |

**Pass criterion (SC-002)**: 100% of failure modes surface as typed error + fallback button. ZERO silent fallbacks.

For each failure, verify clicking **"Use as plain text"** populates the input with the URL string and lets the creator submit anyway (with the URL treated as plain text — same path as Part 1).

---

## Part 4 — Verify SSRF protection (SC-006)

Try to scrape each of these — every one MUST be refused with `error_code: "ssrf_blocked"`.

| URL | Expected refusal reason |
|---|---|
| `http://localhost` | loopback |
| `http://127.0.0.1` | loopback |
| `http://localhost:5432/` | loopback (port doesn't matter) |
| `http://192.168.1.1` | private_range (RFC 1918) |
| `http://10.0.0.1` | private_range (RFC 1918) |
| `http://169.254.169.254` | link_local (AWS metadata endpoint — most famous SSRF target) |
| `file:///etc/passwd` | scheme_blocked |
| `data:text/html,<script>alert(1)</script>` | scheme_blocked |
| `javascript:alert(1)` | scheme_blocked |

**Pass criterion (SC-006)**: 100% refusal rate on all 9 URLs. The wizard shows: "That URL points to a non-public address. Paste a description instead."

---

## Part 5 — Verify rate limit (SC-007)

Open DevTools → Network panel. From the wizard's URL input, paste 31 different valid URLs in rapid succession (within 60 s).

**Pass criterion (SC-007)**: the 31st request returns HTTP 429 with `error_code: "rate_limited"`. Earlier 30 succeed (subject to other validation). Wizard shows the rate-limit message.

Wait 60 s. Re-paste. Should succeed again.

---

## Part 6 — Verify inline editing (SC-005, P2 acceptance)

After a successful scrape:

1. Click **Edit** on the preview card.
2. The title and description fields MUST become inline-editable.
3. Edit the title (e.g., trim "| Acme Brew Co. | Free Shipping…" off the end).
4. Save.
5. Submit the wizard.

**Pass criterion**:

```sh
cat storage/tasks/<task-id>/script.json | jq '.params.video_subject'
```

The `video_subject` MUST contain your edited title — NOT the original scraped title.

---

## Part 7 — Verify schema forward-compat (SC-008)

```sh
cd visualai-frontend
pnpm vitest tests/url-scrape.test.ts -t "ScrapeResult is forward-compatible"
```

This test instantiates a `ScrapeResult` with the v2 `source: "brand-library"` discriminator and asserts the v1 type tolerates it (zero schema break). Should pass.

---

## Part 8 — Run all unit + integration tests

```sh
cd visualai-frontend
pnpm vitest run
```

**Expected**: ~58 tests pass:

- 11 from `url-scrape.test.ts` (compose + isUrlLike)
- 26 from `ssrf.test.ts` (SP-1..SP-26 from contracts/ssrf-protection.md)
- 15 from `scrape-route.test.ts` (SE-1..SE-15 from contracts/scrape-endpoint.md)
- ~6 from existing tests if any

Total wall clock < 10 s. If anything fails, the contract section it implements is violated — fix the offending code, not the test.

---

## Part 9 — Verify Layer 3 / MPT untouched (FR-011)

```sh
cd MoneyPrinterTurbo
git diff --stat origin/main..HEAD -- 'app/' 'main.py' 'requirements.txt'
```

**Pass criterion (FR-011)**: ZERO lines changed under `app/`, `main.py`, or `requirements.txt`. If anything changed, this feature is in violation of its core constraint and MUST be reworked before merge.

---

## Operator runbook — interpreting `error_code` in the server logs

```sh
# Tail the Next.js server log; filter for scrape failures:
pnpm dev 2>&1 | grep -E "(scrape|ssrf|rate)"
```

| Log pattern | What it means | Action |
|---|---|---|
| `scrape ok url=... elapsed=...ms` | Happy path | none |
| `scrape failed code=fetch_timeout url=...` | Slow site or unreachable | usually no action; if frequent, consider raising the cap |
| `scrape failed code=ssrf_blocked rule=loopback host=...` | An attempted SSRF was blocked | review host; could be a misconfigured creator paste OR an attack |
| `scrape failed code=robots_blocked host=...` | Site opted out | none — respect the opt-out |
| `scrape failed code=rate_limited ip=...` | Per-IP burst exceeded | check if it's a real abuse pattern; raise the cap if it's a power user |
| `scrape failed code=no_useful_content host=...` | Site has no extractable OG/meta data | candidate for v2 JS-rendering fallback (track count) |

If `no_useful_content` exceeds 20% of attempts over a week, that's the trigger to add the JS-rendering fallback per spec §Open Follow-Ups.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| URL paste shows "scraping…" forever | Server timeout misconfigured | Check that the route's 10s timeout is enforced; check Next.js dev server logs |
| Preview card shows but image is broken | Target site blocks hotlinking | Acceptable v1 behavior — wizard shows broken-image placeholder |
| Scrape succeeds but voiceover sounds generic | Extracted description was too generic OR the LLM ignored it | Verify `script.json` has the enriched subject; if yes, the LLM ignored it (not our bug) |
| All URL pastes return `ssrf_blocked` | DNS resolver misconfigured (resolves everything to localhost) | Check `/etc/resolv.conf`; the Node `dns.lookup` should return public IPs for public domains |
| Test `SP-10` fails (AWS metadata endpoint not blocked) | Implementation regression | Most important SSRF test — fix immediately, this is a real attack vector |

---

## Related contracts

- [contracts/scrape-endpoint.md](./contracts/scrape-endpoint.md) — `POST /api/scrape-url` HTTP shape + 15 acceptance tests
- [contracts/ssrf-protection.md](./contracts/ssrf-protection.md) — exhaustive refusal rules + 26 acceptance tests
- [contracts/enriched-subject-format.md](./contracts/enriched-subject-format.md) — `composeEnrichedSubject` function + 11 acceptance tests
