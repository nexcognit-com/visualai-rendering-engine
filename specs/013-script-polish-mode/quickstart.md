# Quickstart: Polish Mode for Script Editor

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Audience**: developers verifying the feature; operators reproducing SC-001..SC-007.

---

## Part 1 — Verify zero regression for legacy callers (SC-003)

Run a baseline render through the **existing** non-VisualAI API path with NO `script_mode` field. Behavior MUST be identical to today's pre-spec-013 pipeline.

```sh
# Terminal 1 — MPT backend on :8090
cd MoneyPrinterTurbo && python main.py

# Direct curl — NO script_mode field, empty video_script (legacy auto path)
curl -X POST http://localhost:8090/api/v1/videos \
  -H 'Content-Type: application/json' \
  -d '{
    "video_subject": "Diamond engagement ring",
    "video_script": "",
    "mode": "short",
    "video_aspect": "9:16",
    "video_count": 1
  }'

# Direct curl — NO script_mode field, non-empty video_script (legacy verbatim path)
curl -X POST http://localhost:8090/api/v1/videos \
  -H 'Content-Type: application/json' \
  -d '{
    "video_subject": "Diamond engagement ring",
    "video_script": "Pick the perfect ring. Visit our showroom today.",
    "mode": "short",
    "video_aspect": "9:16",
    "video_count": 1
  }'
```

**Pass criterion (SC-003)**: both renders produce voiceover identical to today's pipeline output. Legacy path 1 → LLM-written script. Legacy path 2 → exactly the typed words. No new `script_mode` or `script_brief` fields appear in either `task.json`. Confirms FR-008 + FR-010.

---

## Part 2 — Verify Polish mode end-to-end (SC-001, P1 acceptance)

Start the frontend + backend, open the wizard, paste a brief in Polish mode, ship it.

```sh
# Terminal 1 — MPT
cd MoneyPrinterTurbo && python main.py

# Terminal 2 — visualai-frontend
cd visualai-frontend && pnpm dev
```

In your browser at `http://localhost:3001`:

1. Click "Short Marketing Video".
2. **Step 1**: paste a real product URL (e.g., `https://example.com/products/widget`). Wait for the scrape preview. Click "Use this".
3. **Step 3**: in the new mode-pill row, click **Polish**. The textarea reveals.
4. Type a rough brief, e.g.:
   ```
   highlight the 32oz size, mention overnight steeping,
   focus on coffee enthusiasts who want cafe-quality at home
   ```
5. Pick a voice. Pick "None" or "Random" for music.
6. Click "Create video" and wait.

**Pass criteria**:

- The rendered MP4's voiceover is structurally a hook → body → CTA marketing script — NOT a verbatim reading of your bullet points.
- The voiceover MENTIONS specific facts from your brief (e.g., "32 oz", "overnight").
- The voiceover ALSO references real product context from the URL scrape (the enriched subject from spec 012). Brief and product context fuse.

To verify the LLM saw both inputs:

```sh
ls -t storage/tasks/ | head -1
TASK_ID=$(ls -t storage/tasks/ | head -1)
cat storage/tasks/$TASK_ID/script.json | jq '.params | {video_subject, video_script, script_mode, script_brief}'
```

You MUST see:
- `video_subject`: the URL-enriched text from Step 1
- `video_script`: the polished output (NOT your brief)
- `script_mode`: `"polish"`
- `script_brief`: your original brief, preserved verbatim

Score against SC-001's threshold: ≥ 50% of brief words rewritten/repositioned. Read the polished `video_script` next to your `script_brief` — they should be visibly different in structure, with the same key facts present.

---

## Part 3 — Verify Verbatim mode end-to-end (SC-002, US1 acceptance #2)

In the wizard:

1. Step 1 → type a plain subject (no URL): "Cold brew kit demo".
2. Step 3 → click **Verbatim** pill.
3. Type your exact final script: "Tired of weak cold brew? Try ours. Available now at acmebrew.com."
4. Submit.

**Pass criterion (SC-002)**: the rendered MP4's voiceover speaks your text WORD-FOR-WORD. No rewriting. Verify by listening + comparing to `script.json`'s `params.video_script` field.

```sh
TASK_ID=$(ls -t storage/tasks/ | head -1)
cat storage/tasks/$TASK_ID/script.json | jq '.params.video_script'
# MUST equal your typed text exactly
```

---

## Part 4 — Verify Auto mode end-to-end (US1 acceptance #3)

In the wizard:

1. Step 1 → type "Diamond engagement ring".
2. Step 3 → click **Auto** pill (default).
3. The textarea is HIDDEN. Helper text reads "Leave empty — the AI will write a script from your subject."
4. Submit.

**Pass criterion**: render proceeds; voiceover is LLM-generated from the subject (today's auto-path output). `script.json` shows:
- `script_mode`: `"auto"`
- `video_script`: the LLM-generated script
- `script_brief`: `null`

---

## Part 5 — Verify polish empty-brief refusal (FR-006, SC-006)

In the wizard:

1. Step 3 → click **Polish** pill.
2. Leave the textarea empty.
3. Click "Create video".

**Pass criterion (SC-006)**: an inline error appears within 100 ms: "Polish mode needs a brief — type some bullet points or a rough description, then try again." The render does NOT start. No task is created.

Defensive backend check: if you bypass the wizard via curl with `{"script_mode": "polish", "video_script": ""}`, the backend MUST mark the task `state="failed"` with `error="polish_brief_required"`.

```sh
curl -X POST http://localhost:8090/api/v1/videos \
  -H 'Content-Type: application/json' \
  -d '{
    "video_subject": "test",
    "video_script": "",
    "script_mode": "polish",
    "mode": "short"
  }'

# Wait a moment, then:
TASK_ID=$(ls -t storage/tasks/ | head -1)
cat storage/tasks/$TASK_ID/script.json | jq '{state, error}'
# MUST show: {"state": "failed", "error": "polish_brief_required"}
```

---

## Part 6 — Verify polish_failed surfacing (FR-007, SC-007)

Synthetic LLM-failure test. Easiest way: temporarily set `OPENAI_API_KEY` to an invalid value before running MPT, then attempt a Polish render.

```sh
# Stop MPT
lsof -tiTCP:8090 -sTCP:LISTEN | xargs kill

# Restart MPT with a bogus OpenAI key
cd MoneyPrinterTurbo
OPENAI_API_KEY="sk-bogus-key-for-testing" python main.py &

# In the wizard, submit a Polish-mode render with a valid brief
# (or via curl):
curl -X POST http://localhost:8090/api/v1/videos \
  -H 'Content-Type: application/json' \
  -d '{
    "video_subject": "test",
    "video_script": "highlight the 32oz size",
    "script_mode": "polish",
    "mode": "short"
  }'

sleep 5
TASK_ID=$(ls -t storage/tasks/ | head -1)
cat storage/tasks/$TASK_ID/script.json | jq '{state, error}'
# MUST show: {"state": "failed", "error": "polish_failed"}
```

**Pass criterion**: task fails closed with `polish_failed`. No silent fallback. The wizard's Step 4 displays the error + offers "Try Verbatim instead" / "Try again with Polish" buttons.

After this test, restore the real API key + restart MPT.

---

## Part 7 — Verify wizard mode persistence (FR-011)

In the wizard:

1. Step 3 → click **Polish** pill → type "test brief content".
2. Click "Back" to Step 2.
3. Click "Next" back to Step 3.

**Pass criterion**: Polish pill is still highlighted; "test brief content" is still in the textarea. State persisted across navigation.

Refresh the browser tab. After refresh: mode resets to Auto, textarea is empty. (Browser-state policy per spec assumption — no localStorage at v1.)

---

## Part 8 — Run the full test suite

```sh
# Backend tests
cd MoneyPrinterTurbo
.venv/bin/python -m pytest test/services/test_polish_script.py -v

# Frontend tests
cd ../visualai-frontend
pnpm vitest run tests/wizard-mode-selector.test.ts
```

**Expected**:

- Backend: ~17 tests pass (PL-1..PL-10 polish_script + WS-1..WS-10 wire-shape dispatch). Total wall clock < 5 s.
- Frontend: 11 tests pass (WMS-1..WMS-11). Total wall clock < 1 s.

If anything fails, the contract section it implements is violated. Fix the offending code, not the test.

---

## Part 9 — Verify cross-spec composition with URL scraping (Q1 clarification)

In the wizard:

1. Step 1 → paste `https://example.com/` (real, public, OG-rich).
2. Wait for scrape; click "Use this".
3. Step 3 → click **Polish**.
4. Type a brief that contradicts the scraped subject: "actually pretend this is a coffee shop, not a generic example domain".
5. Submit.

**Pass criterion (Q1 clarification)**: the polished script weaves brief + subject. The brief's "coffee shop" framing wins (per the prompt's Constraint #2: "If brief and context disagree, brief wins"), but real-domain facts from the scrape (if any) get woven in where relevant. Manual reading verifies.

---

## Part 10 — Verify Constitution Compliance (FR-011 implicit + plan §Re-evaluation)

```sh
cd MoneyPrinterTurbo
git diff --stat origin/main..HEAD -- 'app/services/material.py' 'app/services/voice.py' 'app/services/video.py'
```

**Pass criterion**: ZERO lines changed in any of those three files. Spec 013 only touches `app/services/llm.py`, `app/services/task.py`, `app/models/schema.py` — all already in the existing fork-surface debt set. `material.py` / `voice.py` / `video.py` stay rebase-clean per Principle II.

If any of those three files changed, the implementation is in violation of Principle II + must be reworked before merge.

---

## Operator runbook — interpreting `script_brief` in My Assets

**Status at v1**: My Assets does NOT yet display the `script_brief` field. v2 follow-up adds a "Polished from brief" badge on cards where `script_mode == "polish"`, with the brief shown on hover.

For ops debugging today:

```sh
# Find all polished renders + diff their briefs vs polished output
for task in $(ls storage/tasks/); do
  mode=$(cat storage/tasks/$task/script.json | jq -r '.params.script_mode // "null"')
  if [ "$mode" = "polish" ]; then
    echo "=== Task $task ==="
    echo "BRIEF:"
    cat storage/tasks/$task/script.json | jq -r '.params.script_brief'
    echo "POLISHED:"
    cat storage/tasks/$task/script.json | jq -r '.params.video_script'
    echo ""
  fi
done
```

This is the provenance contract from clarification Q2 — both are stored, both are inspectable.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Polish output reads exactly like the brief | LLM call returned the input verbatim (rare); OR prompt rendering is broken | Inspect the prompt actually sent to OpenAI via debug logs; verify Constraint #2 of the template is present |
| `script_brief` missing from `task.json` | Wizard didn't include it OR backend dropped it | Check the `/api/generate` proxy is forwarding the field; check `VideoParams` schema has the field declared |
| Polish renders fail with `polish_failed` consistently | OpenAI key invalid / quota exhausted | Check `config.toml`'s key; check OpenAI dashboard for quota |
| Auto mode produces verbatim-like output | `script_mode` was sent as `"auto"` but `video_script` was non-empty AND backend code didn't honor the explicit `"auto"` override | Verify dispatch matrix row A1: `"auto"` MUST ignore `video_script` |
| Wizard shows Polish pill highlighted but textarea hidden | State drift between mode and visibility | Component re-render bug; inspect React DevTools for `state.mode === "polish"` while textarea is hidden |
| Mode resets every time I switch wizard steps | Parent component is re-mounting (state lost) | Verify `state` is held in `ShortVideoWizard` parent, NOT in `StepScriptVoice` |

---

## Related contracts

- [contracts/polish-llm-contract.md](./contracts/polish-llm-contract.md) — Python `polish_script()` function shape
- [contracts/script-mode-wire-shape.md](./contracts/script-mode-wire-shape.md) — VideoParams field semantics + dispatch matrix
- [contracts/wizard-mode-selector-contract.md](./contracts/wizard-mode-selector-contract.md) — UI state machine + visual contract
