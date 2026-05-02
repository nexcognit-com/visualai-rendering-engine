# Implementation Plan: URL Scraping for Step 1 Input

**Branch**: `012-url-scraping` | **Date**: 2026-05-02 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/012-url-scraping/spec.md`

## Summary

Add a Layer-1 URL-fetching step before Mode 2 renders. When the wizard's Step 1 input is detected as a URL, a new server route (`POST /api/scrape-url` in `visualai-frontend/src/app/api/scrape-url/route.ts`) fetches the page using `undici` (Node 20 native), parses HTML with **Cheerio**, extracts OG tags / meta description / first H1 / primary product image, sanitizes everything via **sanitize-html**, and returns a typed `ScrapeResult`. The wizard renders an inline preview card with editable title + description; on submit it composes an enriched `video_subject` text string and sends it through the existing `/api/generate` proxy. **Layer 3 (this MPT repo) is not touched** — `git diff --stat` of the MPT working tree shows zero changes attributable to this spec.

Two non-negotiable security floors are baked into the plan: **SSRF protection** (loopback / RFC 1918 / link-local IP refusal + scheme allowlist + redirect-hop cap) and **robots.txt enforcement** (no override toggle). Plus a per-IP rate limit (30 req/min sliding window, in-memory at v1) and a 1-hour-TTL robots.txt cache to be respectful to target sites.

The feature is parallel-deliverable with specs 009 (overlays), 010 (music — already shipped), and 011 (BGM audit warning). All four extend the wizard's StepInput / StepScriptVoice components but in disjoint subtrees; merge-order doesn't matter.

## Technical Context

**Language/Version**: Node.js 20 (Next.js 16 + React 19) only — Layer 1 surface. **Zero Python changes.**
**Primary Dependencies**:
- **Cheerio** (`cheerio` ≥ 1.0) — HTML parsing. Pure-JS, no native deps. Trivially tree-shakeable.
- **sanitize-html** (`sanitize-html` ≥ 2.13) — strips scripts/event-handlers/inline-styles from extracted text fields before returning to the browser. Defense-in-depth even though we only return `textContent`.
- **robots-parser** (`robots-parser` ≥ 3.0) — RFC 9309 (Robots Exclusion Protocol) parser. ~30 KB.
- **node:dns/promises** + **node:net** (built-in) — used for SSRF protection's IP-resolution + private-range check.
- **node:undici** built-in fetch (Node 20 native). No new HTTP client needed.
- **Frontend**: existing wizard component + `next/image` for the preview thumbnail.

**Storage**: In-memory only at v1 — `Map<string, RobotsTxt>` for the 1-hour-TTL robots.txt cache and `Map<string, number[]>` for the per-IP rate-limit sliding window. Both lost on Next.js server restart, which is fine because both are best-effort caches.

**Testing**: **Vitest** for the wizard's URL-detection logic + `composeEnrichedSubject()` (matches the pattern set in spec 010 task T029). Real-fetch end-to-end tests use **MSW** (`msw`) to mock target sites — no live network calls in CI. Plus operator-side manual smoke per `quickstart.md`.

**Target Platform**: Next.js server runtime (Vercel-compatible / Node 20 / Edge runtime explicitly NOT used because we need full Node `dns` for SSRF protection — flagged for the implementation phase).

**Project Type**: Layer 1-only feature (`visualai-frontend` repo). Sibling MPT repo is read-only context.

**Performance Goals**:
- p95 scrape latency ≤ 5 s; p99 ≤ 10 s (matches the spec's SC-003 + the timeout cap in FR-005).
- Wizard "URL paste → preview rendered" wall-clock ≤ 7 s for 95% of attempts (SC-005).
- Zero performance impact on text-only flows (the regex check is constant-time).

**Constraints**:
- **Layer 3 / MPT MUST stay untouched.** No edits to `app/`, no schema changes, no router changes. Verified at the end of the implementation phase.
- **Same-origin contract preserved** — browser never makes cross-origin requests directly. All fetches go through the Next.js server route.
- **Robots.txt is unconditional** (no override toggle). FR-004.
- **SSRF allowlist** is `http://` and `https://` only (FR-006).
- **No JS-rendering fallback at v1** — static HTML fetch only. Documented in spec § Open Follow-Ups.

**Scale/Scope**:
- 1 scrape per wizard session typical, ≤ 3 in pathological re-paste flows (5-min client-side cache covers most repeats).
- Rate limit: 30 req/min per IP (FR-012).
- Bundled robots.txt cache target: support 1000+ unique hosts in 1-hour windows without memory pressure (entries are small, ~5 KB each typical).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Verdict | Reasoning |
|---|---|---|
| **I. Layer 3 Scope — Rendering Only (NON-NEGOTIABLE)** | PASS | Feature lives entirely in Layer 1 (`visualai-frontend`). Zero Layer 3 touches; Layer 3 only ever receives plain text in `video_subject` (no schema change). |
| **II. Surgical Fork Discipline** | PASS | Zero edits to fork-surface files (`material.py`, `llm.py`, `voice.py`, `schema.py`, MPT controllers). Final implementation phase verifies via `git diff --stat origin/main..HEAD` filtered to MPT paths. |
| **III. Multi-Tenant Context Propagation** | PASS, via existing debt | Robots.txt cache + rate-limit counter are process-global at v1. Continuation of debt #2. When debt #2 repays in Step 2, both scope per-tenant via the same path-rewrite that uploads (specs 009/010) inherit. |
| **IV. External Asset Acceptance Over Direct API Calls** | NUANCED but PASS | The constitution's exact wording: "**This engine** [Layer 3] MUST NOT call NanoBanana, Veo 3.1, ElevenLabs, Kling, Runway, or any other generation API directly from Layer 3 code." Layer 1 is not bound by Principle IV. The spec's §Constitutional Impact documents this; the plan reaffirms by keeping every HTTP call inside `visualai-frontend/src/app/api/`. When Layer 2 (Orchestration API) ships in Step 2 of the build plan, the scrape endpoint moves there cleanly with no schema change — a planned migration, not a debt. |
| **V. Mode-Aware Rendering Contract** | PASS | Mode 2 wizard surface only. Other modes inherit the same URL-handling pattern when they ship their own wizards. No mode-registry changes. |
| **§Technology Constraints — Runtime** | PASS | Layer 3 runtime (Python) untouched. Layer 1 adds 3 small JS deps (Cheerio + sanitize-html + robots-parser); none are GPU-relevant. |
| **§Technology Constraints — Database** | N/A | No DB. In-memory caches only. |
| **§Technology Constraints — Observability** | PASS | Layer 3 loguru discipline untouched. Layer 1 logs go to Next.js's server logger (FR-013); no new infra. |
| **§Technology Constraints — Secrets** | PASS | No API keys; no auth tokens. Public web scraping only. |
| **§Development Workflow — fork-surface PR rule** | DOES NOT APPLY | This PR doesn't touch any fork-surface files. The PR description notes that explicitly so reviewers don't expect a Mode reference. |
| **§Development Workflow — pytest gate** | DOES NOT APPLY | No Python changes. The frontend's Vitest suite is the equivalent gate; the implementation PR runs it before merge. |

**Gate result**: PASS. No NEW debts. One existing debt (#2 multi-tenant scoping) gains one more burndown task. Re-check post-Phase 1.

## Project Structure

### Documentation (this feature, in this repo)

```text
specs/012-url-scraping/
├── plan.md                    # This file
├── research.md                # Phase 0 — Cheerio vs alternatives, SSRF resolver design, robots.txt cache strategy, rate-limit window choice, JS-rendering-deferral rationale, sanitize-html config, MSW vs real fetch in tests
├── data-model.md              # Phase 1 — ScrapeResult / ErrorResult / WizardScrapeState / RobotsTxtCacheEntry / RateLimitWindow entities + validation rules
├── quickstart.md              # Phase 1 — operator runbook covering SC-001 through SC-008
├── contracts/
│   ├── scrape-endpoint.md           # POST /api/scrape-url HTTP contract: request shape, success/error schemas, error_code taxonomy
│   ├── ssrf-protection.md           # Refusal rules + acceptance test set
│   └── enriched-subject-format.md   # How wizard composes the final video_subject text from the editable fields
├── checklists/
│   └── requirements.md        # Spec quality checklist (already created)
├── spec.md                    # Feature specification
└── tasks.md                   # Phase 2 — produced by /speckit.tasks (NOT here)
```

### Source code changes (Layer 3 — this repo)

```text
(NONE — Layer 3 is deliberately untouched.)
```

### Source code changes (Layer 1 — `visualai-frontend/`)

```text
visualai-frontend/
├── package.json                                 # MODIFIED: add cheerio, sanitize-html, robots-parser, msw, vitest (latter two dev deps)
├── vitest.config.ts                             # NEW (if missing) — vitest config with jsdom env for component tests
└── src/
    ├── lib/
    │   ├── url-scrape.ts                        # NEW — TS types + composeEnrichedSubject() + isUrlLike() detector
    │   └── ssrf.ts                              # NEW — SSRF gate: scheme allowlist + DNS resolve + private-IP refuser
    ├── app/
    │   ├── api/
    │   │   └── scrape-url/
    │   │       └── route.ts                     # NEW — POST handler: validate input → SSRF gate → robots.txt check → fetch → Cheerio extract → sanitize → return typed result
    │   └── modes/short-video/
    │       └── page.tsx                         # MODIFIED — Step 1 detects URL inputs, fires scrape, shows preview card with inline-editable title + description, "use as plain text" fallback button
    └── tests/
        ├── url-scrape.test.ts                   # NEW — vitest tests for isUrlLike + composeEnrichedSubject (FR-001, FR-008)
        ├── ssrf.test.ts                         # NEW — vitest tests for SSRF gate (FR-006, SC-006)
        └── scrape-route.test.ts                 # NEW — vitest + MSW tests for the API route (covers all error_code paths from contracts/scrape-endpoint.md)
```

**Files explicitly NOT touched**:
- Anything under `MoneyPrinterTurbo/` (Layer 3) — Principle I + II.
- `visualai-frontend/src/app/api/generate/route.ts` — already accepts arbitrary text in `subject`. The wizard composes the enriched text and submits via the existing proxy.

**Structure Decision**: Layer 1-only feature. The wizard's `page.tsx` gains URL detection + a preview card; a new server route + two helper modules + a Vitest suite ship alongside. Net `visualai-frontend` footprint: ~6 new files + 1 modified file + 3 new dev/runtime deps.

## Cross-spec coordination

| Other spec | Shared file with this spec | Conflict? |
|---|---|---|
| Spec 009 (overlays) | `visualai-frontend/src/app/modes/short-video/page.tsx` | No semantic conflict — overlays panel is in Step 3, URL scraping is in Step 1. Different JSX subtrees. Lexical merge order matters but is mechanical. |
| Spec 010 (music control) | `visualai-frontend/src/app/modes/short-video/page.tsx` | Same as 009 — Step 3 vs Step 1. Already merged for spec 010 (shipped 2026-05-02). |
| Spec 011 (BGM audit warning) | `visualai-frontend/src/app/api/history/route.ts` and `app/assets/page.tsx` | No conflict — spec 012 does NOT touch My Assets or history. |

The implementation order is a non-issue between 009/010/011/012 because each touches a different region of the wizard.

## Complexity Tracking

> No NEW Constitution violations. Section minimal.

This feature deliberately rejects four heavier alternatives:

- **JavaScript-rendering fallback** (Playwright / Puppeteer for SPAs) — rejected per spec §Open Follow-Ups: significant infra (headless Chromium runtime, ~300 MB Docker image bloat, much higher per-request memory), unclear ROI without first measuring how many target sites actually need it. Layer in v2 only if creator feedback demands.
- **Server-side persistence of scrape results** — rejected: ephemeral wizard state is enough. Persisting would create a new schema (which spec 012 explicitly avoids) and a new privacy surface. Defer to Brand Library work in Step 5.
- **Auto-extracting product attributes via image OCR / vision model** (e.g., extract "32 oz" from a label photo) — rejected: orthogonal to this feature; would require an external vision API (and re-open Principle IV territory). Listed as v2+ Open Follow-Up.
- **Browser-side scraping via fetch+CORS proxy** — rejected: cross-origin restrictions + CORS proxy operational cost. Server-side fetch in Next.js is strictly cleaner and gives us SSRF + rate-limit control.

## Re-evaluation post-Phase 1

After data-model + contracts + quickstart land, re-check:

- **Principle I**: still PASS — no Layer 3 file touched.
- **Principle II**: still PASS — no fork-surface touched.
- **Principle IV nuance**: still PASS — every HTTP call documented in contracts is in Layer 1's server runtime. The contract files explicitly disclaim Layer 3 involvement.
- **Security floors**: SSRF protection contract enumerates 100% of refusal rules; robots.txt enforcement has no override path.

The post-design check has nothing new to flag. Plan is implementation-ready.
