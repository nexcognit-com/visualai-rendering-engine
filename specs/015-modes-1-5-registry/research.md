# Research: Modes 1 + 5 + Mode Registry + Layer 2.5 Image Routing (Step 3)

**Date**: 2026-05-03
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

Six technical decisions blocked detailed planning. Each is resolved here so [data-model.md](data-model.md) and [contracts/](contracts/) can proceed without unknowns.

---

## R1 — Constitution v1.1.0 amendment

**Decision**: Amend `.specify/memory/constitution.md` to v1.1.0 (MINOR bump) in the same PR as Step 3's first slice.

**Rationale**:
- Step 1's constitution v1.0.2 lists `app/services/material.py`, `app/services/llm.py`, `app/services/voice.py`, `app/models/schema.py`, and `app/controllers/v1/` as the five permitted fork-surface files (Principle II). Step 3 adds `app/services/modes/` as a sixth.
- Principle V already requires modes to live there ("Each mode's prompt templates ... MUST be declared in a single `app/services/modes/` registry"), so the addition is a wording-cleanup more than a structural change.
- The amendment also adds Mode 1 + Mode 5 to the actively-implemented column. The constitution already names all 5 modes by id; this is just documenting which ship in Step 3.
- Per the constitution's amendment rules, this is a **MINOR** bump (new mode set entries + one section addition; no principle redefined).

**Exact diff** (will land in the Step-3 PR):

```diff
 ### II. Surgical Fork Discipline
 
 Modifications to the upstream MoneyPrinterTurbo codebase MUST be confined to
-the five surfaces called out in §5 of the Master Spec:
-`app/services/material.py`, `app/services/llm.py`, `app/services/voice.py`,
-`app/models/schema.py`, and the video controllers under `app/controllers/`.
+the six surfaces listed below:
+- `app/services/material.py`
+- `app/services/llm.py`
+- `app/services/voice.py`
+- `app/services/modes/` (Mode registry, formalized in v1.1.0)
+- `app/models/schema.py`
+- the video controllers under `app/controllers/`
 ...

# Sync Impact Report header gains:
+Version: 1.1.0 (MINOR — 2026-05-03)
+  - Added `app/services/modes/` to the documented fork-surface set.
+  - Documented Mode 1 (Product Shoot Generator) and Mode 5 (Faceless Channel
+    Automation) as actively implemented as of Step 3.
+  - No principle redefined or removed.
```

**Alternatives considered**:
- **Skip the amendment, ship the directory anyway**: rejected — that's a Principle II violation that would generate a NEW DEBT, defeating the point of Step 3 being a debt-burndown step.
- **MAJOR bump**: rejected — no principle is redefined or removed, and the Agent Mode set isn't changing; we're just marking which are live.

**Spec impact**: FR-031 codifies this. PR-A lands the constitution amendment + the empty `app/services/modes/` package; subsequent commits add per-mode modules.

---

## R2 — Image-generation provider for Mode 1

**Decision**: **NanoBanana Pro via FAL.ai** as the primary provider for Step 3, with the Layer 2.5 router architected for provider swap.

**Rationale**:
- Master Spec §3 names NanoBanana Pro explicitly. The product team has already been using it informally for ad-hoc product photos.
- FAL.ai hosts NanoBanana Pro at `fal.run/fal-ai/nano-banana-pro/edit/multi` with a stable HTTP API: input image (URL or base64) + prompt → response with one image URL or array of image URLs.
- Pricing: ~$0.04 per image at NanoBanana Pro's quality tier. 6-image batch = $0.24/generation. Acceptable for Step 3 single-user demo; Step 4 credit gating handles scale.
- FAL.ai API contract: returns ONE image per request. To get 6, Layer 2.5 either (a) calls the API 6 times in parallel with different prompt variations, or (b) calls once with `num_images: 6` if the API supports it. Per FAL docs, NanoBanana Pro's edit/multi endpoint supports `num_images` up to 6 — option (b) is the chosen path.
- Provider abstraction: `app/router/_provider_nanobanana.py` is one file; swapping to OpenAI's `gpt-image-1` or Google's `imagen-4` later is a new sibling file + an env-var change.

**Provider abstraction shape**:

```python
# app/router/image.py
async def generate_studio_photos(
    input_image_url: str,
    description: str = "",
    count: int = 6,
) -> list[str]:
    """Provider-agnostic. Returns 6 image URLs."""
    provider = os.environ.get("LAYER25_IMAGE_PROVIDER", "nanobanana").lower()
    if provider == "nanobanana":
        from . import _provider_nanobanana as p
    elif provider == "openai_gpt_image":
        from . import _provider_openai_gpt_image as p  # future
    else:
        raise ValueError(f"unknown LAYER25_IMAGE_PROVIDER: {provider}")
    return await p.generate(input_image_url, description, count)
```

**Alternatives considered**:
- **OpenAI gpt-image-1**: similar quality, ~$0.04/image. Lacks the "studio product photography" tuning NanoBanana has out of the box. Reserved as fallback if NanoBanana rate-limits.
- **Google Imagen 4**: comparable cost. Slightly weaker on physical product photography per public benchmarks. Reserved as second fallback.
- **Self-hosted Stable Diffusion XL with fine-tunes**: rejected for Step 3 (GPU infrastructure isn't built yet; constitution says we use API providers, not self-hosted models, until Step 5+).

**Cost / latency budget**:
- Per-generation: $0.24 (6 × $0.04) at NanoBanana Pro's "Pro" quality tier.
- Latency: ~25-35s for the 6-image batch (typical NanoBanana Pro response time).
- Step-3 demo limit: log-only, no enforcement. Step 4 enforces a credit-balance check.

**Spec impact**: FR-007..FR-015 are honored as written. FR-028's `LAYER25_NANOBANANA_API_KEY` env var is the FAL.ai API key.

---

## R3 — Mode interface (registry contract)

**Decision**: A `typing.Protocol` defining the interface every mode module exports + a `pick(name)` dispatcher in `app/services/modes/__init__.py`.

```python
# app/services/modes/_interface.py
from typing import Protocol
from app.models.schema import VideoParams, VideoAspect

class Mode(Protocol):
    """The interface every active mode in the registry MUST export."""
    name: str                       # "short", "faceless"; matches VideoParams.mode literal
    default_aspect_ratio: VideoAspect

    def generate_script(self, params: VideoParams) -> str:
        """Mode-specific script generation. Called by task.generate_script."""
        ...

    def generate_terms(self, params: VideoParams, video_script: str) -> list[str]:
        """Mode-specific search-term generation. Called by task.generate_terms."""
        ...

    def select_visuals_strategy(self, params: VideoParams) -> str:
        """Returns "auto" | "user_uploaded" | "hybrid" — what visuals_mode to apply.
        Mode 5 (faceless) always returns "auto"; Mode 2 (short) returns
        params.visuals_mode (preserves user's wizard choice)."""
        ...
```

```python
# app/services/modes/__init__.py
from typing import Final
from . import short, faceless
from ._interface import Mode

_REGISTRY: Final[dict[str, Mode]] = {
    "short": short,         # Mode 2
    "faceless": faceless,   # Mode 5
    # "product_shoot": NOT registered — Mode 1 doesn't dispatch through Layer 3
}

def pick(name: str) -> Mode:
    """Lookup a mode module by VideoParams.mode literal. Raises KeyError on unknown."""
    if name not in _REGISTRY:
        raise KeyError(f"unknown_mode: {name!r}")
    return _REGISTRY[name]

def supported() -> list[str]:
    return list(_REGISTRY.keys())
```

**Rationale**:
- `typing.Protocol` (PEP 544) gives structural typing without forcing inheritance. Each mode module is just a Python module exporting the right top-level functions; mypy / pyright validates the contract structurally.
- Module-level functions (not classes) match the existing `llm.py` / `material.py` style and avoid stateful instances. Worker-thread safe by construction.
- Step-3 explicitly does NOT register `product_shoot` — Mode 1 doesn't dispatch through Layer 3's render pipeline at all. The registry only contains modes that produce videos.

**Refactor mapping** — what moves where:

| Current location | New location |
|---|---|
| `llm.py:generate_script(... mode="short")` short branch (Mode 2 marketing-script logic) | `modes/short.py:generate_script` |
| `llm.py:generate_terms(... mode="short")` short branch (product-centric terms) | `modes/short.py:generate_terms` |
| `llm.py:generate_marketing_script` (Mode 2 hook-body-CTA prompt) | `modes/short.py:_marketing_prompt` (private) + called from `generate_script` |
| `llm.py:extract_setting_tag` + `expand_setting_to_queries` + `generate_setting_terms` (Mode 2 hybrid) | `modes/short.py` — these stay accessible as utility functions exported by the mode |
| `task.py:generate_script` script_mode dispatch (auto/verbatim/polish) | UNCHANGED — script_mode is orthogonal to Mode and stays in `task.py` |
| `task.py:generate_terms` faceless-default fall-through | calls `modes.pick(params.mode).generate_terms(...)` |
| `material.py:download_videos` Pexels/Pixabay call | calls `modes.pick(params.mode).select_visuals_strategy(...)` to gate; auto + hybrid go through pre-signed URL flow when not faceless |

**Alternatives considered**:
- **Class-based Mode with an ABC**: rejected — heavier than needed; encourages stateful instances; doesn't compose well with Python's import system.
- **Keep dispatch inline in `llm.py` / `task.py`**: rejected — that's exactly debt #4 + #5. Whole point of Step 3 is to retire those.
- **External plugin discovery (entry points)**: rejected — overkill for 5 modes total; YAGNI until we have third-party modes.

**Spec impact**: FR-016..FR-021 honored. The Protocol-based interface is one specific implementation; could swap to ABC if mypy strictness becomes an issue.

---

## R4 — Pre-signed URL handshake (Layer 2 → Layer 3)

**Decision**: HMAC-SHA256 signed URLs with 15-minute TTL, served from Layer 2 at `/_signed/<sig>/<tenant_id>/<uuid>.<ext>?expires=<unix>`.

**Format**:

```
GET http://layer2:8088/_signed/<sig>/<tenant_id>/<uuid>.<ext>?expires=1714867200
```

Where:
- `<sig>` = `hmac_sha256(LAYER2_SIGNING_KEY, f"{tenant_id}/{uuid}.{ext}|{expires}")[:32]` (truncated to 32 hex chars for URL aesthetics; full 64 chars is overkill given 15-min TTL).
- `<tenant_id>` = the demo tenant in Step 3 (`demo-tenant-001`); per-real-tenant in Step 4.
- `<uuid>.<ext>` = the file under `storage/uploads/<tenant_id>/`.
- `expires` = Unix timestamp; URL is rejected after this.

**Verification at Layer 2's static-file mount**:

```python
@app.get("/_signed/{sig}/{tenant_id}/{filename}")
async def serve_signed(sig: str, tenant_id: str, filename: str, expires: int):
    if expires <= int(time.time()):
        raise HTTPException(410, {"error_code": "url_expired"})
    expected = hmac.new(
        os.environ["LAYER2_SIGNING_KEY"].encode(),
        f"{tenant_id}/{filename}|{expires}".encode(),
        "sha256",
    ).hexdigest()[:32]
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(403, {"error_code": "url_invalid_signature"})
    file_path = os.path.join("storage/uploads", tenant_id, filename)
    if not os.path.exists(file_path):
        raise HTTPException(404, {"error_code": "url_target_missing"})
    return FileResponse(file_path)
```

**Rationale**:
- Step 3 doesn't introduce a real CDN signed-URL store (that's Step 4 with cloud storage). The static-file mount is a working stand-in: signing works, expiry works, tenant scoping works.
- Layer 3 receives the URLs in the `visuals.json` sidecar from Layer 2 (writes the sidecar pre-dispatch as it does today). Layer 3 reads via standard `requests.get` — no special client needed.
- The signature scheme is the same shape Step 4's CDN signed URLs will use (typically AWS S3 / CloudFront sigv4). Step-4 migration is a URL format change inside Layer 2's signer + verifier; Layer 3's read code stays unchanged.
- 15-minute TTL matches the JWT TTL (Step 2 FR-004). Both expire at the same scale, simplifying the operations story.

**Where the URLs flow**:

1. User uploads a product photo via Layer 1 → Layer 2 stores at `storage/uploads/<tenant_id>/<uuid>.<ext>`. Layer 2 returns the path to Layer 1.
2. User clicks Generate (Mode 2 with `user_uploaded` or `hybrid`). Layer 1 → Layer 2 with the upload path.
3. Layer 2 mints a fresh JWT + writes `visuals.json` to Layer 3's task dir BEFORE dispatch. The sidecar contains `pre_signed_clip_urls: [...]` (per-clip URLs OR `null` if Mode 5 / Pexels-only).
4. Layer 3's `material.download_videos` reads the sidecar; if `pre_signed_clip_urls` is non-null, downloads from those URLs (just `requests.get`); else (Mode 5 only) calls Pexels direct.

**Alternatives considered**:
- **Symmetric path with no signing**: rejected — leaks files across tenants when multi-tenant lands in Step 4.
- **Real S3 / CloudFront signed URLs in Step 3**: rejected — adds AWS dep + bucket setup + IAM config to a single-user demo; the static-file stand-in keeps the architecture forward-compatible without the cloud overhead.
- **Pre-signing at the Layer 2 ↔ Layer 3 boundary via mTLS**: rejected — heavy; inappropriate when both services are on the same host.

**Spec impact**: FR-022 + FR-024 honored. Layer 2 file mount + signer is a new ~50-line module.

---

## R5 — Contact-sheet slicing for Mode 1

**Decision**: Use Pillow to detect whether NanoBanana returned 6 individual images OR a 3×2 contact sheet, and slice when needed.

**Rationale**:
- NanoBanana Pro's response shape varies by tier / API version. Some endpoints return `images: [{url}, {url}, ...]` (6 separate); some return a single composite `image: {url}` containing the contact sheet.
- Layer 2.5's job is to normalize: regardless of provider response, output is always 6 individual image URLs.
- Detection heuristic: if response has 6+ images → use directly. If response has 1 image → load via Pillow, check dimensions: if width/height ≈ 3:2 (contact sheet) AND total pixel count > 4× single-image pixel count → slice 3×2.
- Slicing code (~15 lines):

```python
from PIL import Image

def slice_contact_sheet(sheet_path: str, output_dir: str) -> list[str]:
    """Slice a 3-column × 2-row contact sheet into 6 individual images."""
    img = Image.open(sheet_path)
    w, h = img.size
    cell_w, cell_h = w // 3, h // 2
    out_paths = []
    for row in range(2):
        for col in range(3):
            box = (col * cell_w, row * cell_h, (col + 1) * cell_w, (row + 1) * cell_h)
            cell = img.crop(box)
            out_path = os.path.join(output_dir, f"shot-{row * 3 + col + 1}.jpg")
            cell.save(out_path, "JPEG", quality=92)
            out_paths.append(out_path)
    return out_paths
```

**Alternatives considered**:
- **Always assume 6 individual images**: rejected — NanoBanana's actual response in some configs is a sheet; we'd ship broken on first generation.
- **Always assume contact sheet**: rejected — symmetric problem.
- **Provider-specific shape baked into adapter**: this IS the chosen approach; the detection lives in `app/router/image.py` (provider-agnostic) and the adapter (`_provider_nanobanana.py`) just reports what it got.

**Spec impact**: FR-011 honored. Both response shapes normalize to 6 image URLs at the Layer 2.5 boundary.

---

## R6 — Faceless Channel dispatch shape (separate route vs `mode` field on existing)

**Decision**: Reuse the existing `POST /api/v1/videos` endpoint with `mode = "faceless"` in the body. NO new endpoint for Mode 5.

**Rationale**:
- The frontend wizard dispatches to `/api/generate` regardless of mode; that proxy already forwards to Layer 2's `/api/v1/videos`. Adding a separate `/api/v1/faceless` endpoint duplicates plumbing without benefit.
- `VideoParams.mode` is the dispatch field. The request body shape is identical; only the wizard's collected fields differ (Mode 5 wizard collects topic + voice + music; no Visuals selector, no script editor).
- Layer 2.5 doesn't touch Mode 5 — the request flows through the existing `videos.py` forwarder, lands at Layer 3's `create_video`, hits `task.py:generate_script` which dispatches via `modes.pick(params.mode).generate_script`.

**Mode 1 IS different — gets its own endpoint** (`POST /api/v1/product-shoots`):
- Different output shape (image URLs, not a render task with progress polling).
- Different upstream (Layer 2.5, not Layer 3).
- Different timing (sync response in ~30s, not async render in ~90s).
- Different result type (6 images, not 1 video).

The asymmetry is justified: Mode 5 is a video-rendering mode that uses the existing pipeline; Mode 1 is a fundamentally different output type that needs its own contract.

**Alternatives considered**:
- **Separate endpoints for both Mode 1 and Mode 5**: rejected for Mode 5 — duplicates the videos endpoint without payoff.
- **Combine into one mega-endpoint with output-type discriminator**: rejected — Mode 1's response shape (6 image URLs sync) vs Mode 2/5's (task_id async) is a fundamental enough difference that one endpoint shape would be confusing.

**Spec impact**: FR-001..FR-006 (Mode 5) reuse existing endpoint with `mode="faceless"`. FR-009 (Mode 1) gets `/api/v1/product-shoots` as a new endpoint.

---

## Decisions consolidated

| ID | Decision | Spec FRs touched | Files affected |
|---|---|---|---|
| R1 | Constitution v1.1.0 amendment lands in PR-A | FR-031 | `.specify/memory/constitution.md` |
| R2 | NanoBanana Pro via FAL.ai; provider-agnostic adapter | FR-010, FR-028 | `visualai-orchestration/app/router/_provider_nanobanana.py` |
| R3 | `typing.Protocol` Mode interface; module-per-mode in `app/services/modes/` | FR-016..FR-021 | Layer 3 `app/services/modes/`, `task.py`, `llm.py` |
| R4 | HMAC-signed URLs at `/_signed/<sig>/<tenant>/<uuid>.<ext>?expires=<unix>` | FR-022, FR-024 | Layer 2 `app/auth/pre_signer.py` + `app/routes/pre_signed.py` |
| R5 | Pillow contact-sheet detection + slicing in Layer 2.5 | FR-011 | `visualai-orchestration/app/router/image.py` |
| R6 | Mode 5 reuses `POST /api/v1/videos` with `mode="faceless"`; Mode 1 gets `/api/v1/product-shoots` | FR-001..FR-006, FR-009 | Layer 2 `app/routes/videos.py` (extend), `app/routes/product_shoots.py` (new) |

All six `NEEDS CLARIFICATION` candidates resolved. Phase 1 design unblocked.

## PR slicing recommendation

**PR-A** (lands first, on `015-modes-1-5-registry`):
- Constitution v1.1.0 amendment.
- `app/services/modes/` package + `_interface.py` + `short.py` + `faceless.py`.
- `app/services/llm.py` shrink — Mode 2 prompts move to `modes/short.py`.
- `app/services/task.py` simplification — registry dispatch.
- `app/services/material.py` rewrite — pre-signed URL flow + Mode-5-only Pexels gate.
- Layer 2 — `pre_signed.py` route + `pre_signer.py` HMAC signer.
- Frontend — Mode 5 dashboard card activation + `/modes/faceless-channel/page.tsx`.
- STEP1_DEBT.md — strike rows #4, #5; partial-strike row #3.

PR-A target: ~2000 lines, 4 hours of work, exclusively backend pipeline + Mode 5 UI. Test target: 20+ new pytest cases, 5+ new Vitest cases.

**PR-B** (lands second, rebased on top of PR-A):
- Layer 2 — `app/routes/product_shoots.py` + `app/router/image.py` + `_provider_nanobanana.py`.
- Layer 2 — `storage/tasks/<task_id>/` mount for Mode 1 outputs.
- Frontend — Mode 1 dashboard card activation + `/modes/product-shoot/page.tsx` + `/api/product-shoot/route.ts`.
- My Assets page extension — list Mode 1 image generations alongside videos.
- Constitution check re-confirms — no further amendments.

PR-B target: ~1500 lines, 3 hours of work, mostly Layer 2 + Layer 1. Test target: 15+ new pytest cases (with NanoBanana mocked via respx), 5+ new Vitest cases.

**Total Step 3**: ~3500 lines across two PRs, ~7 hours of work, ~50 new tests. Achievable in one focused work session if no surprises; realistic estimate is ~10-12 hours including manual smoke + PR review iteration.
