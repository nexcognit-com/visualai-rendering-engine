# Contract — Layer 1 wizard for `/modes/long-form/`

**Layer**: Frontend (Layer 1 — `visualai-frontend` repo)
**Created**: 2026-05-03

## Wizard structure — 3 steps

### Step 1 — Input (one of three input modes)

Three pill-style sub-modes; user picks one:

| Pill | UX |
|---|---|
| **Topic prompt** | Single multi-line `<textarea>`, ≤ 500 chars, char counter. Placeholder: "What's your video about? e.g., How AI is changing logistics in 2026". |
| **Source URL** | Single-line `<input type="url">`. Inline validation on URL regex. On focus-out, optionally previews the scraped page title (calls `/api/scrape-url` from spec 012). |
| **Pre-written script** | Multi-line `<textarea>`, word counter (≤ 1500). Submit button disabled if empty or > 1500 words. |

Pill selection drives which payload field becomes `source_type` + `source_text`.

### Step 2 — Configuration

| Control | Values | Default |
|---|---|---|
| Target duration | `2 min`, `3 min`, `4 min`, `5 min` (radio group) | `3 min` |
| Voice | shared voice picker (from Mode 2's library) | `en-US-AvaMultilingualNeural` |
| Background music | bundled BGM list + "None" + "Upload custom" (spec 010) | "None" |

Wizard surfaces an estimated cost (≤ $0.50) and an estimated wait (~3–5 min) under the duration radios.

### Step 3 — Generation + result

- Progress bar polling `GET /api/long-form-videos/{id}` if the POST-await pattern from Mode 1 is too slow for UI feedback. Stage labels parsed from a future SSE/WS upgrade; v1 ships fixed-stage animation: "Generating script" → "Synthesizing voice" → "Fetching visuals" → "Assembling video".
- On completion: inline `<video controls src={output_video_url} />` at full width, 16:9 aspect; Download button uses HTML5 `download` with filename `long-form-{topic-slug}-{YYYYMMDD-HHMMSS}.mp4`.
- On failure: render the `error_code` against a copy table; offer a Retry button.

## API proxy — `src/app/api/long-form-videos/route.ts`

Mirrors `src/app/api/product-shoots/route.ts` from spec 015:

- `POST /api/long-form-videos` → forwards JSON body to Layer 2 `POST /api/v1/long-form-videos` with the demo bearer header injected from server-side env.
- `GET /api/long-form-videos` → forwards to Layer 2 `GET /api/v1/long-form-videos`.
- `GET /api/long-form-videos/[id]` → forwards to Layer 2 single-record route.

Error handling: any non-2xx from Layer 2 is forwarded as-is (status + body) so the wizard can switch on `error_code`.

## Dashboard card

The Long-Form Video card appears as the third card in the dashboard grid (after Mode 1 Product Shoot, Mode 2 Short Marketing Video). Card metadata:

- Title: "Long-Form Video"
- Subtitle: "16:9 explainer for YouTube · 2-5 min"
- Icon: lucide `monitor-play`
- Badge: none (Mode 3 ships in this spec — no "Coming soon")
- Click target: `/modes/long-form/`

## My Assets surfacing

`src/app/assets/page.tsx` already fetches:

- `/api/history` (Mode 2/5 short videos)
- `/api/product-shoots` (Mode 1 stills)

This spec adds:

- `/api/long-form-videos` (Mode 3 long videos)

A new card variant `LongFormCard` renders a 16:9 thumbnail (the `output_video_url`'s first frame via the same `<video preload="metadata">` trick used elsewhere). Heterogeneous grid stays sorted by `created_at DESC` across all sources. Records without a viewable `output_video_url` are filtered out at fetch time (the Layer 2 list endpoint already does this — Layer 1 just renders what it gets).

## Routing + navigation

- Sidebar nav unchanged.
- Breadcrumb on the wizard: `Dashboard › Long-Form Video`.
- After successful generation, "View in My Assets" link navigates to `/assets`.

## Out of scope (Layer 1 v1)

- Live progress streaming (deferred — fixed-stage animation for v1).
- Per-segment thumbnail strip in the result view (Mode 3 produces one continuous video, not 4 stills like Mode 1).
- Multi-user history filters (Step 4 — multi-tenant lands with spec 014).
- Direct YouTube upload button (Step 5).
