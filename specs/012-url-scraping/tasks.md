---
description: "Task list for feature 012 — URL Scraping for Step 1 Input"
---

# Tasks: URL Scraping for Step 1 Input

**Input**: Design documents from `/specs/012-url-scraping/`
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Smoke + integration tests are MANDATORY. The contracts in `contracts/` define **52 acceptance tests** total (15 from scrape-endpoint, 26 from ssrf-protection, 11 from enriched-subject-format); these are scheduled as task items below. Vitest + MSW serves as the JS analog of pytest in spec 010.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing. Spec.md's four user stories:

- **US1** (P1): Creator pastes URL → scrape succeeds → render uses enriched context
- **US2** (P1): Scrape failures surface clearly with graceful "use as plain text" fallback
- **US3** (P2): Creator inline-edits extracted business context before submitting
- **US4** (P3): Brand Library forward-compat (schema-only test)

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1/US2/US3/US4)
- All file paths relative to `/Users/amraeid/Dropbox/Dev.lab/Cursor-Cluade/NexCognit-Content-generator/visualai-frontend/` unless noted

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: install runtime + dev dependencies and configure Vitest. No SpecKit feature has touched the `visualai-frontend`'s test infra yet — this feature establishes it.

- [ ] T001 Add runtime dependencies to `visualai-frontend`'s `package.json`: `cheerio` (≥ 1.0), `sanitize-html` (≥ 2.13), `robots-parser` (≥ 3.0). Add dev dependencies: `vitest` (≥ 2), `@vitest/ui`, `jsdom` (for DOM-API tests), `msw` (≥ 2). Run `pnpm install` to confirm. Path: `package.json` + `pnpm-lock.yaml`.
- [ ] T002 [P] Create `vitest.config.ts` with `jsdom` environment, path aliases mirroring `tsconfig.json` (`@/*` → `src/*`), and a `setupFiles` entry pointing at `tests/setup.ts`. Path: `vitest.config.ts`.
- [ ] T003 [P] Create the MSW server harness at `tests/setup.ts` exporting a `setupServer` instance + `beforeAll` / `afterEach` / `afterAll` hooks. Per-test handlers register via `server.use(...)`. Path: `tests/setup.ts`.

**Checkpoint**: `pnpm vitest run` exits 0 with "no tests found" — toolchain ready.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Build the shared TypeScript primitives + the API route skeleton that every user story depends on. Once Phase 2 completes, US1 / US2 / US3 / US4 can each be developed in parallel.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Shared TypeScript modules

- [ ] T004 Create `src/lib/url-scrape.ts` with all TypeScript types from [data-model.md §Entity 1 + Entity 3](./data-model.md): `ScrapeResult`, `ScrapeSuccess`, `ScrapeError`, `ScrapeErrorCode` (12-value union), `EnrichedSubjectInput`, `EnrichedSubjectError`, `MAX_SUBJECT_LEN = 500`. Implement `isUrlLike(input: string): boolean` per [research.md R9](./research.md). Implement `composeEnrichedSubject(parts)` per [contracts/enriched-subject-format.md](./contracts/enriched-subject-format.md). Path: `src/lib/url-scrape.ts`.
- [ ] T005 [P] Create `src/lib/ssrf.ts` with `SsrfError` class + `assertSafeUrl(url: string): Promise<void>` per [contracts/ssrf-protection.md](./contracts/ssrf-protection.md). Implement all 5 rule layers (URL parse, scheme allowlist, IP literal check, DNS resolve + check, redirect re-check helper). Use `node:dns/promises` and `node:net`; no external IP-range library (per [research.md R3](./research.md)). Path: `src/lib/ssrf.ts`.

### API route skeleton

- [ ] T006 Create `src/app/api/scrape-url/route.ts` skeleton: Zod request-body validation, in-memory rate-limit `Map<string, number[]>` (per [data-model.md §Entity 5](./data-model.md)), in-memory robots.txt cache `Map<string, RobotsTxtCacheEntry>` (per [data-model.md §Entity 4](./data-model.md)), and a stubbed POST handler that returns 501 for now. The actual scrape pipeline lands in US1 + US2 phases. Path: `src/app/api/scrape-url/route.ts`. (Depends on T004 + T005 for type imports.)

**Checkpoint**: Foundation ready. The new route exists (returns 501); the SSRF gate, type system, compose helper, and rate-limit + robots cache primitives are all importable. All four user stories can begin in parallel.

---

## Phase 3: User Story 1 — Happy-Path URL Scrape (Priority: P1) 🎯 MVP

**Goal**: A creator pastes a URL with proper OG tags into Step 1, the wizard scrapes it within 5 s, shows an editable preview, and the rendered MP4's voiceover meaningfully reflects real product details from the page.

**Independent Test**: Pasting a real product URL produces a wizard preview within 5 s. Submitting that preview produces a rendered MP4 whose voiceover specifically mentions facts from the scraped page (not generic ad-speak). Per SC-001, hits ≥ 80% on a fixed 10-URL test set.

### Tests for User Story 1

- [ ] T007 [P] [US1] Vitest tests for `composeEnrichedSubject` happy path: ES-1 (short content, no truncation), ES-2 (description-side truncation), ES-3 (truncate description first then title), ES-4 (truncate title when description short), ES-10 (always ends with `(sourced from <domain>)`), ES-11 (output ≤ MAX_SUBJECT_LEN). Path: `tests/url-scrape.test.ts`.
- [ ] T008 [P] [US1] Vitest test for `isUrlLike` detection: positive cases (`https://...`, `http://...`), negative cases (`example.com`, `not a url`, `ftp://...`, empty string, whitespace). Path: `tests/url-scrape.test.ts`.
- [ ] T009 [P] [US1] Integration tests SE-1 (valid OG-rich page) + SE-2 (og:title only, fallback to meta description) using MSW to mock the target site. Path: `tests/scrape-route.test.ts`.

### Implementation for User Story 1

- [ ] T010 [US1] Wire Cheerio extraction into the route handler at `src/app/api/scrape-url/route.ts`: implement priority extraction for title (og:title → `<title>` → first `<h1>`), description (og:description → `<meta name="description">` → first `<p>`), image (og:image → first reasonable `<img>`), source_domain. Path: `src/app/api/scrape-url/route.ts`.
- [ ] T011 [US1] Wire `sanitize-html` with the text-only config from [research.md R2](./research.md) onto extracted title + description before they leave the route handler. Path: `src/app/api/scrape-url/route.ts`. (Depends on T010.)
- [ ] T012 [US1] Implement truncation: title ≤ 200 chars, description ≤ 500 chars, suffix with U+2026 ellipsis when shortened. Path: `src/app/api/scrape-url/route.ts`. (Depends on T011.)
- [ ] T013 [US1] Add URL detection to wizard's Step 1 in `src/app/modes/short-video/page.tsx`: on input change/paste, run `isUrlLike(value)` (debounced 300 ms); if true, transition wizard scrape state to `"scraping"` and POST to `/api/scrape-url`. Path: `src/app/modes/short-video/page.tsx`.
- [ ] T014 [US1] Build the scrape-preview card UI under the Step 1 input: shows image thumbnail (with placeholder fallback), title (h4-style), description (small body), source-domain badge, and three action buttons (`Use this`, `Edit`, `Clear`). Render only when `wizardScrapeState.mode === "preview"`. Path: `src/app/modes/short-video/page.tsx`. (Depends on T013.)
- [ ] T015 [US1] Wire `Use this` button: calls `composeEnrichedSubject({ title, description, sourceDomain })`, stores the result as the wizard's `subject` state, advances to Step 2. Path: `src/app/modes/short-video/page.tsx`. (Depends on T014 + T004 import.)
- [ ] T016 [US1] Wire `Clear` button: resets wizard scrape state to `{mode: "text"}`, restores the input field for plain-text use. Path: `src/app/modes/short-video/page.tsx`. (Depends on T014.)
- [ ] T017 [US1] Run [quickstart.md Part 2](./quickstart.md) manual end-to-end: paste a real product URL, verify preview within 5 s, submit, listen to the rendered MP4, confirm the voiceover mentions specific page facts. Repeat for 10 product URLs; ≥ 8 must pass per SC-001. Path: manual verification.

**Checkpoint**: User Story 1 fully functional. Creator can paste a URL, see a preview, and ship a brand-aware video. MVP delivered.

---

## Phase 4: User Story 2 — Failure Surfacing + "Use as Plain Text" Fallback (Priority: P1)

**Goal**: Every scrape failure (404, 403, timeout, robots-blocked, JS-only SPA, non-HTML, SSRF, redirect loop, TLS error, rate-limited, invalid URL) surfaces as a typed error in the wizard with a clear "use as plain text" fallback button. Zero silent fallbacks.

**Independent Test**: Inducing each of the 12 failure modes (per SE-1..SE-15 + SP-1..SP-26 + the AWS metadata SSRF target) produces a visible typed error message AND a working fallback button. No render starts on failure. Per SC-002, 100% of attempts surface as errors.

### Tests for User Story 2

- [ ] T018 [P] [US2] Vitest integration tests SE-3 (no_useful_content), SE-4 (404), SE-5 (403), SE-6 (5xx), SE-7 (timeout), SE-11 (non_html_response), SE-12 (redirect_loop), SE-14 (url_invalid missing field), SE-15 (url_invalid > 2048 chars) using MSW handlers. Each MUST verify HTTP status + `error_code` + `detail` are correct per [contracts/scrape-endpoint.md](./contracts/scrape-endpoint.md). Path: `tests/scrape-route.test.ts`.
- [ ] T019 [P] [US2] Vitest integration tests SE-8 (robots_blocked) and SE-13 (rate_limited) — these need stateful MSW setup (robots.txt fetch) and timing setup (31 requests in 60 s). Path: `tests/scrape-route.test.ts`.
- [ ] T020 [P] [US2] Vitest unit tests SP-1..SP-26 — all 26 SSRF refusal cases from [contracts/ssrf-protection.md](./contracts/ssrf-protection.md). Includes the AWS metadata endpoint (SP-10) and the redirect re-check (SP-25 + SP-26). Path: `tests/ssrf.test.ts`.

### Implementation for User Story 2

- [ ] T021 [US2] Wire the SSRF gate (`assertSafeUrl`) into the route's pipeline as step 3 of [contracts/scrape-endpoint.md §Behavior contract](./contracts/scrape-endpoint.md). Calls `assertSafeUrl(parsed.url)` before any fetch. On `SsrfError`, returns 400 `ssrf_blocked` with the documented detail string. Path: `src/app/api/scrape-url/route.ts`.
- [ ] T022 [US2] Implement robots.txt cache + check in the route. On request: derive `https://<host>/robots.txt`, hit cache OR fetch (5s timeout, 100KB cap), parse with `robots-parser`, check the path against the User-Agent. On disallow → 403 `robots_blocked`. Cache TTL 1h per host. Path: `src/app/api/scrape-url/route.ts`. (Depends on T021.)
- [ ] T023 [US2] Implement rate limiter in the route per [data-model.md §Entity 5](./data-model.md): per-IP sliding window (30 req / 60 s), in-memory `Map<string, number[]>`, periodic 5-min cleanup. On excess → 429 `rate_limited`. Path: `src/app/api/scrape-url/route.ts`. (Depends on T021.)
- [ ] T024 [US2] Implement undici fetch with `redirect: 'manual'`, 5MB body cap, 10s total timeout, 5-redirect-hop cap, TLS error handling. On each redirect's `Location` header, run `assertSafeUrl()` again. Map errors to typed responses (`fetch_404`, `fetch_403`, `fetch_5xx`, `fetch_timeout`, `redirect_loop`, `tls_error`). Path: `src/app/api/scrape-url/route.ts`. (Depends on T022.)
- [ ] T025 [US2] Add content-type check after fetch: reject if not `text/html` / `application/xhtml+xml` → 422 `non_html_response` with the content-type interpolated into the detail message. Path: `src/app/api/scrape-url/route.ts`. (Depends on T024.)
- [ ] T026 [US2] Add the no-useful-content branch in the extractor: if title AND description AND `<h1>` are all empty post-extraction, return 422 `no_useful_content` instead of an empty success payload. Path: `src/app/api/scrape-url/route.ts`. (Depends on T010 + T025.)
- [ ] T027 [US2] Build the error-state UI in the wizard's Step 1 preview area: when `wizardScrapeState.mode === "error"`, show the typed error message (from `result.detail`) + a "Use as plain text" button + a "Try a different URL" link. Path: `src/app/modes/short-video/page.tsx`. (Depends on T013.)
- [ ] T028 [US2] Wire the "Use as plain text" button: sets `wizardScrapeState.mode = "text"`, populates the Step 1 input with the URL string, lets the creator submit normally (the URL ends up in `video_subject` as text — same path Mode 2 had pre-spec-012). Path: `src/app/modes/short-video/page.tsx`. (Depends on T027.)
- [ ] T029 [US2] Run [quickstart.md Part 3 + Part 4 + Part 5](./quickstart.md): exercise every documented failure mode end-to-end through the wizard, confirm the typed error message + fallback button appear in each case. SC-002 acceptance: zero silent fallbacks. SC-006 acceptance: 100% SSRF refusal. SC-007 acceptance: 31st request returns 429. Path: manual verification.

**Checkpoint**: User Story 2 complete. Every scrape failure mode is honest with the user. Both US1 (happy path) and US2 (failure path) work end-to-end.

---

## Phase 5: User Story 3 — Inline Editing of Extracted Context (Priority: P2)

**Goal**: After a successful scrape, the creator can inline-edit the title and description before submitting. Edits persist to the wizard's submitted `video_subject`.

**Independent Test**: After a successful scrape, click `Edit`. Title + description fields become inline-editable. Edit a value, save. Submit. The task's `script.json` shows `video_subject` containing the EDITED text, NOT the original scraped text.

### Tests for User Story 3

- [ ] T030 [P] [US3] Vitest tests ES-5..ES-9 (validation: empty title, empty description, whitespace-only title, sourceDomain with scheme, sourceDomain with path) — each MUST throw `EnrichedSubjectError` with the documented `code`. Path: `tests/url-scrape.test.ts`.

### Implementation for User Story 3

- [ ] T031 [US3] Add `editedTitle: string | null` and `editedDescription: string | null` fields to the wizard's `WizardScrapeState` per [data-model.md §Entity 2](./data-model.md). Path: `src/app/modes/short-video/page.tsx`. (Depends on T013.)
- [ ] T032 [US3] Wire the `Edit` button on the preview card: toggles each field into an `<input>` / `<textarea>` with save / cancel actions. Saving sets `editedTitle` / `editedDescription`; canceling reverts. Path: `src/app/modes/short-video/page.tsx`. (Depends on T031.)
- [ ] T033 [US3] When `Use this` fires, the submit handler MUST use `editedTitle ?? result.title` and `editedDescription ?? result.description` when calling `composeEnrichedSubject`. Path: `src/app/modes/short-video/page.tsx`. (Depends on T015 + T031.)
- [ ] T034 [US3] Run [quickstart.md Part 6](./quickstart.md): scrape a URL, click `Edit`, modify the title, submit. Verify `script.json`'s `video_subject` contains the edited text. Path: manual verification.

**Checkpoint**: User Story 3 complete. Creators with editorial standards can curate the LLM input.

---

## Phase 6: User Story 4 — Brand Library Forward-Compat (Priority: P3, schema-only)

**Goal**: The `ScrapeResult` shape accepts a future `source: "brand-library" | "url-scrape" | "manual"` discriminator without breaking the v1 type. Per FR-014 + SC-008.

**Independent Test**: Vitest test instantiates a synthetic `ScrapeResult` with `source: "brand-library"` and the v1 type validates it (TypeScript compile passes; runtime check passes).

### Tests for User Story 4

- [ ] T035 [P] [US4] Vitest test "ScrapeResult is forward-compatible": create a synthetic object matching the v1 `ScrapeSuccess` shape PLUS an optional `source: "brand-library"` field; assert TypeScript accepts it via a structural type test. Path: `tests/url-scrape.test.ts`.

**Checkpoint**: Forward-compat hook locked in. Brand Library work in Step 5 won't require a v1 schema migration.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: tasks that span multiple stories or finalize the feature for merge.

- [ ] T036 [P] Run [quickstart.md Part 1](./quickstart.md): verify zero regression for plain-text inputs. Submitting a non-URL string in Step 1 MUST produce identical pipeline behavior to today's text-only flow. Path: manual verification.
- [ ] T037 [P] Run the full Vitest suite: `pnpm vitest run`. Expected: 52 tests pass (15 SE + 26 SP + 11 ES). Total wall clock < 10 s. Path: manual verification + CI gate.
- [ ] T038 [P] Update `STEP1_DEBT.md` cross-reference table: note that spec 012 continues debt #2 (no tenant scoping on the rate-limit counter, robots cache, and scrape endpoint itself) and is bounded to Layer 1 (no Layer 3 file touches at all). Path: `MoneyPrinterTurbo/STEP1_DEBT.md`.
- [ ] T039 Run [quickstart.md Part 9](./quickstart.md) — final constitution compliance check. `git -C MoneyPrinterTurbo diff --stat origin/main..HEAD -- 'app/' 'main.py' 'requirements.txt'` MUST show ZERO changes. If anything in MPT changed, this feature is in violation of FR-011 / Principle II and MUST be reworked before merge. Path: manual verification.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies. Start immediately.
- **Foundational (Phase 2)**: Depends on Phase 1. **BLOCKS all user stories.**
- **User Stories (Phase 3+)**: All depend on Phase 2.
  - US1 (P1) is the MVP path. Ship & validate before touching US2/3/4.
  - US2 (P1) is also P1 — failure-surface UX is co-priority with happy path. May ship in same PR as US1.
  - US3 (P2) builds on US1's preview card.
  - US4 (P3) is a single test, runnable any time after T004.
- **Polish (Phase 7)**: depends on all desired user stories being complete.

### Within Each User Story

- Tests MUST exist and FAIL before implementation (constitution-aligned discipline mirroring spec 010's pattern).
- US1's UI tasks are sequential within `page.tsx`; backend tasks (T010–T012) are sequential within `route.ts`.
- US2's route tasks (T021–T026) are sequential — they all touch `route.ts`.
- US3's UI tasks are sequential within `page.tsx`.

### File Conflicts to Note

| File | Tasks touching it | Sequential? |
|---|---|---|
| `src/app/api/scrape-url/route.ts` | T006, T010, T011, T012, T021, T022, T023, T024, T025, T026 | **Yes — all sequential** |
| `src/app/modes/short-video/page.tsx` | T013, T014, T015, T016, T027, T028, T031, T032, T033 | **Yes — all sequential** |
| `src/lib/url-scrape.ts` | T004 (creates), then read-only by tests | T004 alone; tests don't modify |
| `src/lib/ssrf.ts` | T005 (creates) | T005 alone |
| `tests/url-scrape.test.ts` | T007, T008, T030, T035 | Different test functions; can be developed in parallel as `[P]` |
| `tests/scrape-route.test.ts` | T009, T018, T019 | Different test functions; can be developed in parallel as `[P]` |
| `tests/ssrf.test.ts` | T020 | Single task; one file |

### Parallel Opportunities

- **Phase 1**: T002 + T003 parallel; T001 must complete first (deps install).
- **Phase 2**: T005 (`ssrf.ts`) parallel with T004 (`url-scrape.ts`). T006 sequential after both.
- **Phase 3 tests**: T007 + T008 + T009 all `[P]` — different test functions / different files.
- **Phase 3 implementation**: T010–T012 sequential (route.ts); T013–T016 sequential (page.tsx).
- **Phase 4 tests**: T018 + T019 + T020 all `[P]`.
- **Phase 4 implementation**: T021–T026 sequential (route.ts); T027–T028 sequential (page.tsx).
- **Phase 5 implementation**: T031–T033 sequential (page.tsx).
- **Phase 6**: single task T035 `[P]`.
- **Phase 7**: T036, T037, T038 all `[P]`; T039 sequential (depends on all preceding work being complete).

---

## Parallel Example: Phase 4 Tests

```bash
# Three test tasks can be developed in parallel (different files):
Task: "SE-3 through SE-15 integration tests in tests/scrape-route.test.ts"
Task: "SE-8 (robots) + SE-13 (rate limit) integration tests in tests/scrape-route.test.ts"  # different test functions in same file — also parallel
Task: "SP-1 through SP-26 SSRF refusal tests in tests/ssrf.test.ts"
```

---

## Implementation Strategy

### MVP First (US1 + US2 — both P1)

1. Complete Phase 1: Setup (T001, T002, T003).
2. Complete Phase 2: Foundational (T004, T005, T006). **CRITICAL — blocks all stories.**
3. Complete Phase 3: User Story 1 — happy path scraping (T007–T017).
4. Complete Phase 4: User Story 2 — failure surfacing (T018–T029). Both P1 stories shipped together.
5. **STOP and VALIDATE**: run [quickstart.md Parts 2 + 3 + 4 + 5](./quickstart.md). Confirm SC-001 (≥80%), SC-002 (100% failure surfacing), SC-006 (100% SSRF refusal), SC-007 (rate limit at 31st request).
6. Demo / merge as PR if ready.

### Incremental Delivery

1. Setup + Foundational → Foundation ready (~1 hour).
2. US1 happy path → ~2 hours (mostly the UI preview card).
3. US2 failure paths → ~2 hours (mostly route handler error mapping + UI error display). Co-shipped with US1.
4. US3 inline editing → ~30 min (small UI delta).
5. US4 schema test → ~5 min (one test).
6. Polish + constitution check → ~30 min.

**Total estimated time**: 6 hours single-developer, single-session. About half is the wizard's preview-card UX; the other half is the route handler + tests.

### Constitution Compliance Reminders

- **Do not edit anything under MoneyPrinterTurbo/** (Principle I + II — Layer 3 stays untouched). T039 verifies via `git diff --stat`.
- This feature touches Layer 1 only. The implementation PR's description should explicitly state "Layer 1 only; zero MPT-repo touches" so reviewers don't expect Mode references in the PR body.
- The 52 acceptance tests are a hard requirement — the PR MUST NOT merge without `pnpm vitest run` returning 0 (T037). MSW + jsdom + node 20 means tests run in <10 s on a laptop.

---

## Notes

- `[P]` tasks = different files, no dependencies — can run in parallel.
- `[Story]` label maps task to specific user story for traceability and independent delivery.
- US1 + US2 are both P1; co-shipping them in the same PR is the suggested cadence (failure-surface UX is a co-priority with happy-path scraping per the spec).
- The 52 acceptance tests are scheduled across:
  - Phase 3 (US1): T007 + T008 cover ES-1..ES-4 + ES-10..ES-11 + isUrlLike. T009 covers SE-1 + SE-2.
  - Phase 4 (US2): T018 covers SE-3 + SE-4..SE-7 + SE-11 + SE-12 + SE-14 + SE-15. T019 covers SE-8 + SE-13. T020 covers SP-1..SP-26.
  - Phase 5 (US3): T030 covers ES-5..ES-9.
  - Phase 6 (US4): T035 covers the schema forward-compat test.
- Commit after each task or logical group. The full feature is one PR per the SpecKit governance pattern; intra-feature commits are encouraged for review-ability.
- This feature is parallel-deliverable with specs 009 / 011 (009 unimplemented, 011 specced but not yet implemented). All four touch the wizard's `page.tsx` in different JSX subtrees — merge order is mechanical only.
