# Implementation Plan: Mode 4 — UGC Avatar Generator (MuseTalk lip-sync)

**Branch**: `018-ugc-avatar-musetalk` | **Date**: 2026-05-05 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/018-ugc-avatar-musetalk/spec.md`

## Summary

Add Mode 4 — UGC Avatar Generator — as the fourth concrete entry in the Layer 3 mode registry. The wizard accepts a 5-15s selfie speaker reference (uploaded or recorded), generates an LLM-driven script (Auto/Verbatim/Polish — same contract as Mode 2), synthesizes TTS audio in the chosen voice's locale (multilingual catalog already shipped), then runs lip-sync inference over the face reference + audio to produce a 9:16 vertical MP4 of the speaker apparently delivering the script. Output up to 5 minutes (Mode 3 long-form parity per Q1=C). Selfie persistence is hybrid last-3 (filesystem only, no schema additions per Q2=C). Audio overflow loops the speaker reference seamlessly to match audio length (per Q3=B).

The architectural shape mirrors Mode 2's spec-017 backport: L1 wizard → L2 orchestrator → L3 renderer. L2 owns the script-gen + TTS-prep + dispatch coordination; L3 runs the lip-sync inference + final MP4 encode. Lip-sync engine choice (MuseTalk vs Wav2Lip vs SadTalker, self-hosted vs hosted) is the most planning-impactful unknown and is resolved in research.md.

## Technical Context

**Language/Version**: Python 3.11/3.12 (Layer 3 + Layer 2); TypeScript / React (Next.js 16 + React 19) on Layer 1.

**Primary Dependencies**:
- **L3 (rendering)**: existing MoviePy + FFmpeg + ImageMagick (constitutionally pinned). NEW: lip-sync runtime [NEEDS CLARIFICATION: see research.md R1] + face detection [NEEDS CLARIFICATION: see research.md R2]. NEW: video-loop helper for seam-smoothed reference loop (FR-015) — pure FFmpeg, no new dep.
- **L2 (orchestration)**: existing FastAPI + httpx + pydantic + loguru. No new runtime dep — Mode 4 reuses the same orchestrator pattern as Mode 2.
- **L1 (frontend)**: existing Next.js 16 + React 19 + lucide-react + native `<input type="file" accept="video/*">`. NEW: optional `<video>` recording via `MediaRecorder` API for in-browser selfie capture (no new dep, browser-native).

**Storage**:
- L3: existing `storage/tasks/<task_id>/` for render artifacts; NEW `storage/uploads/<tenant>/avatars/<slot>/<uuid>.mp4` for the hybrid last-3 selfie retention.
- L2: existing pre-signed URL signer (spec 015) signs the avatar paths so L3 can fetch them.
- No database schema changes (Q2=C resolved this — filesystem-only retention with slot-based eviction).

**Testing**: pytest (existing, per constitution). New tests under `test/services/modes/test_ugc_avatar.py` + `test/services/test_lip_sync.py`. Smoke test with a synthetic 5s reference + a 10s TTS audio fixture, asserting output MP4 properties (9:16, duration±0.2s, ≥1MB, valid mp4 header).

**Target Platform**: Linux server (production: GPU-capable host per Constitution §Technology Constraints). Local dev on macOS/Apple Silicon for the wizard + L2 path; lip-sync inference path needs special handling on Apple Silicon [NEEDS CLARIFICATION: see research.md R3].

**Project Type**: Three-tier web app (matches existing VisualAI shape) — web frontend (L1) + orchestration API (L2) + rendering API (L3). Each in its own git repo.

**Performance Goals**:
- 90% of 30-second renders complete < 180s end-to-end (SC-001).
- 90% of 5-minute renders complete < 8min end-to-end.
- Render time scales near-linearly with output duration.

**Constraints**:
- 5-minute cap on output duration (Q1=C resolved).
- Audio sync ±0.2s (FR-007).
- Lip-sync indistinguishability ≥4/5 panel rating (SC-002).
- 100% locale match for Auto-mode script-gen (SC-004).
- $1 per render budget ceiling [NEEDS CLARIFICATION: see research.md R1 — depends on engine + hosting choice].

**Scale/Scope**: Single-user demo + multi-tenant production. v1 expects modest concurrent renders (≤10 parallel). Scaling to 100+ parallel waits for Step 4's GPU-cluster deployment.

## Constitution Check

Project Constitution v1.1.0 (Layer 3 only). Five principles + Technology Constraints. Per-principle assessment:

### I. Layer 3 Scope — Rendering Only ✅

Mode 4's lip-sync inference IS rendering: it consumes audio + a face reference and produces an MP4. Same conceptual category as MoviePy's video.assemble. No user-management, auth, credits, or billing logic introduced.

### II. Surgical Fork Discipline ⚠️ (justified)

Mode 4 lives in `app/services/modes/ugc_avatar.py` — within the approved `app/services/modes/` surface. Schema extension lands in `app/models/schema.py` (approved surface — `Mode` literal gains `"ugc_avatar"`).

**Out-of-fork-surface additions** (require justification — see Complexity Tracking):
- New file `app/services/lip_sync.py` for the lip-sync inference wrapper. Justified: lip-sync is a distinct concern from video assembly and warrants a focused module. Logically equivalent to `app/services/voice.py` (TTS wrapper). Documented in PR body per the constitution's escape clause.
- Selfie validation lives in `app/controllers/v1/uploads.py` (or similar) — file-upload endpoint. The constitution's approved fork surface includes "video controllers under `app/controllers/`", so this is within bounds.

### III. Multi-Tenant Context Propagation ✅

Mode 4 inherits the existing `VideoParams` JWT validation pattern from Mode 2. Speaker-reference uploads are tenant-scoped at the path layer (`storage/uploads/<tenant>/avatars/...`). Render-job logs include `tenant_id`, `user_id`, `generation_id` per existing pattern.

### IV. External Asset Acceptance Over Direct API Calls ⚠️ (clarification surfaced)

The constitution forbids L3 from calling NanoBanana/Veo/ElevenLabs/Kling/Runway/etc. directly. MuseTalk-style lip-sync is **a different category**:
- **Self-hosted** (locally loaded PyTorch model in L3 process): NOT a generation API call — just local inference. Equivalent to MoviePy. Constitutionally clean.
- **Hosted** (Replicate / Fal.ai / etc.): IS an external generation API call. Constitutionally must live in L2 / L2.5, NOT L3.

Research.md R1 picks the engine + hosting model. If hosted is chosen, the lip-sync orchestration moves to L2.5 — same pattern as spec 015's NanoBanana router. If self-hosted, it stays in L3.

The Pexels exception (Mode 5 only) is unaffected.

### V. Mode-Aware Rendering Contract ⚠️ (constitution amendment required)

Mode 4 transitions from "reserved" (current v1.1.0 status) to "actively implemented". Per the v1.1.0 amendment that promoted Modes 1 + 5, this transition requires a constitution **MINOR version bump to v1.2.0** with a Sync Impact Report entry. The amendment is a 1-line wording change in §I + §V; lands as a separate `chore: constitution v1.2.0` commit before the Mode 4 implementation PR merges.

The mode registry entry in `app/services/modes/ugc_avatar.py` declares: aspect ratio (9:16), default duration band (15-300s), subtitle position (lower-third, matching Mode 2), script_template ("HOOK_BODY_CTA" — same as Mode 2), segment_count_range (irrelevant — no per-segment B-roll; explicitly null), pacing rules.

### Technology Constraints ✅

- Python 3.11/3.12 ✓ (existing).
- GPU host for production ✓ (constitution already mandates).
- FFmpeg + ImageMagick ✓ (existing).
- No tenant/credit/user schema in L3 ✓ (selfie metadata is filesystem-only).
- Loguru structured logging ✓ (mandatory).
- Secrets in env ✓ (lip-sync model API key if hosted, decided in R1).

### Constitution Check verdict

**Conditional pass.** Two items require explicit acknowledgment:
1. Constitution amendment v1.1.0 → v1.2.0 (Mode 4 active) — pre-PR work, not a blocker.
2. R1's engine choice determines whether lip-sync code lives in L3 (self-hosted) or L2.5 (hosted). Either is constitutionally aligned; R1 will make the call.

## Project Structure

### Documentation (this feature)

```text
specs/018-ugc-avatar-musetalk/
├── plan.md                  # This file (/speckit.plan output)
├── spec.md                  # /speckit.specify output (already authored)
├── research.md              # Phase 0 output (engine + face-detect + Apple-Silicon investigation)
├── data-model.md            # Phase 1 output (Speaker Reference + Avatar Render + Avatar Asset entities)
├── quickstart.md            # Phase 1 output (curl smoke + browser smoke)
├── contracts/               # Phase 1 output
│   ├── l2-route.md          # L2 POST /api/v1/avatars + GET /api/v1/avatars/{id}
│   ├── l3-payload.md        # Extended VideoParams shape for Mode 4
│   └── selfie-upload.md     # POST /api/v1/uploads/selfie endpoint contract
├── checklists/
│   └── requirements.md      # /speckit.specify quality checklist (already passing)
└── tasks.md                 # Phase 2 output (/speckit.tasks command — NOT created here)
```

### Source Code (across 3 repos)

This is a three-tier web app feature. Repository layout:

```text
# Layer 3 — Rendering Engine (this repo: MoneyPrinterTurbo)
app/
├── services/
│   ├── lip_sync.py                  # NEW — lip-sync inference wrapper (engine TBD R1)
│   ├── modes/
│   │   └── ugc_avatar.py            # NEW — Mode 4 registry entry
│   ├── voice.py                     # (existing — multilingual TTS)
│   ├── video.py                     # (existing — final MP4 assembly + Arabic font swap)
│   └── subtitle.py                  # (existing — subtitle generation)
├── controllers/v1/
│   ├── video.py                     # (existing — extended dispatch handles mode="ugc_avatar")
│   └── uploads.py                   # MAYBE NEW — selfie-upload endpoint (or extend existing)
└── models/
    └── schema.py                    # EXTENDED — Mode literal + speaker_reference_path field

storage/
├── tasks/<task_id>/                 # (existing — render artifacts)
└── uploads/<tenant>/avatars/        # NEW — hybrid last-3 selfie retention
    ├── slot1/<uuid>.mp4
    ├── slot2/<uuid>.mp4
    └── slot3/<uuid>.mp4

test/services/
├── modes/test_ugc_avatar.py         # NEW
└── test_lip_sync.py                  # NEW

# Layer 2 — Orchestration API (sibling repo: visualai-orchestration)
app/
├── routes/
│   ├── videos.py                    # (existing — orchestrator branch added for mode=ugc_avatar)
│   └── uploads.py                   # MAYBE NEW — proxy selfie upload to L3
├── services/
│   └── ugc_avatar_script.py         # MAYBE NEW — same pattern as marketing_script.py;
│                                    # Mode 4 may not need its own script gen if it just
│                                    # reuses marketing_script (decided in R4)

# Layer 1 — Frontend (sibling repo: visualai-frontend)
src/
├── app/modes/ugc-avatar/
│   └── page.tsx                     # NEW — wizard for Mode 4
├── lib/
│   ├── voices.ts                    # (existing — already covers multilingual)
│   ├── selfie-upload.ts             # NEW — upload + last-3 picker logic
│   └── ugc-avatar.ts                # NEW — wizard state + API binding
└── components/
    └── selfie-recorder.tsx          # NEW — MediaRecorder-based in-browser capture
```

**Structure Decision**: Three-repo layout, mirroring the VisualAI architectural shape (Step 1's L1 + Step 2's L2 + the L3 fork). Mode 4 adds new files in each repo without restructuring; reuses voice catalog, script-mode contract, Arabic font auto-swap, and asset-history surface from prior specs.

## Complexity Tracking

> Filled because Constitution Check raised two items requiring acknowledgment.

| Violation / Gap | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| New file `app/services/lip_sync.py` outside the 6 named fork-surfaces | Lip-sync is a distinct concern from video assembly + voice synthesis; warrants a focused module that can be tested + replaced independently of MoviePy/FFmpeg code. | Inlining into `app/services/video.py` would mix concerns and make the lip-sync engine swap (likely between v1 and v2) much more invasive. The constitution's intent is to discourage sprawling forks of upstream files, not to prevent net-new modules in `app/services/`. |
| Constitution amendment v1.1.0 → v1.2.0 required (Mode 4 active) | Principle V is explicit that activating a reserved mode requires a MINOR bump. | Would silently mark Mode 4 active without governance — violates the constitution's amendment process. |

No other complexity. Lip-sync engine choice (R1) and Apple-Silicon dev story (R3) are routine research items, not constitutional gaps.

## Post-design Constitution Re-evaluation

After Phase 0 + Phase 1 (research.md, data-model.md, contracts/, quickstart.md authored), re-evaluating the Constitution Check:

| Principle | Status | Rationale |
|---|---|---|
| **I. Layer 3 Scope** | ✅ Pass | All Mode 4 work is rendering — selfie validation, lip-sync inference, subtitle burn-in, MP4 encode. No user/credit/billing logic introduced. |
| **II. Surgical Fork** | ⚠️ Justified | `app/services/lip_sync.py` is a net-new module (NOT a modification of upstream). Documented in Complexity Tracking. Mode 4's mode-registry entry lives in the approved `app/services/modes/` surface. |
| **III. Multi-Tenant Context** | ✅ Pass | `tenant_id` + `user_id` flow through VideoParams (existing JWT pattern); selfie storage paths are tenant-scoped (`storage/uploads/<tenant>/avatars/...`). |
| **IV. External Asset Acceptance** | ✅ Pass | Resolved via R1: self-hosted MuseTalk = local PyTorch inference, NOT an external API call. Same constitutional category as MoviePy. |
| **V. Mode-Aware Contract** | ⚠️ Amendment required | Mode 4 transitions from "reserved" → "active". Triggers MINOR bump v1.1.0 → v1.2.0 with a Sync Impact Report entry. Lands as a separate `chore: constitution v1.2.0` commit before Mode 4 implementation merges. |
| **Technology Constraints** | ✅ Pass | Python 3.11/3.12, FFmpeg/ImageMagick, GPU-host production target, no DB schema, loguru structured logging, secrets in env — all met. New deps `mediapipe>=0.10` + MuseTalk (pinned to a SHA) added via `pyproject.toml` per the `uv` workflow rule. |

**Verdict**: same conditional pass as pre-design. The two acknowledged items (constitution amendment, new lip_sync.py module) remain the only gaps; both have explicit justification paths.

## Phase 2 Output

This plan command stops here. Phase 2 (`/speckit.tasks`) is invoked separately by the user and produces `tasks.md` from these artifacts.

Generated artifacts under `specs/018-ugc-avatar-musetalk/`:
- ✅ [spec.md](./spec.md) — feature specification (clarifications resolved)
- ✅ [plan.md](./plan.md) — this file
- ✅ [research.md](./research.md) — Phase 0: 7 decisions (R1–R7)
- ✅ [data-model.md](./data-model.md) — Phase 1: 3 entities, no DB schema
- ✅ [contracts/selfie-upload.md](./contracts/selfie-upload.md) — Phase 1
- ✅ [contracts/l2-route.md](./contracts/l2-route.md) — Phase 1
- ✅ [contracts/l3-payload.md](./contracts/l3-payload.md) — Phase 1
- ✅ [quickstart.md](./quickstart.md) — Phase 1: 6 smoke tests + wizard smoke
- ✅ [checklists/requirements.md](./checklists/requirements.md) — from /speckit.specify, all items passing
