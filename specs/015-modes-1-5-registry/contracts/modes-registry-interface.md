# Contract: Modes Registry Interface (Layer 3)

**Date**: 2026-05-03
**Owner**: Layer 3 (`MoneyPrinterTurbo` fork)
**Touches**: `app/services/modes/_interface.py`, `app/services/modes/__init__.py`, every per-mode module under `app/services/modes/`

This contract defines what every active mode in the registry MUST export and how `task.py` invokes it. Adding a new mode (Step 4 brings Mode 3 + Mode 4) means writing one new module that satisfies this Protocol — no `task.py` changes required after Step 3.

---

## 1. The Mode Protocol

```python
# app/services/modes/_interface.py
from __future__ import annotations
from typing import Literal, Protocol
from app.models.schema import VideoAspect, VideoParams


class Mode(Protocol):
    """Every active mode module in app/services/modes/ MUST satisfy this."""

    name: str
    """Stable identifier matching VideoParams.mode literal: 'short', 'faceless'."""

    default_aspect_ratio: VideoAspect
    """Default vertical/horizontal preset. Mode 2 + Mode 5: VideoAspect.portrait."""

    def generate_script(self, params: VideoParams) -> str:
        """Mode-specific LLM script generation.

        Honors params.script_mode (orthogonal: auto/verbatim/polish/draft) — script_mode
        dispatch stays in task.py; this method only owns the mode-specific prompt + LLM call
        when script_mode == 'auto'.
        """

    def generate_terms(self, params: VideoParams, video_script: str) -> list[str]:
        """Mode-specific search-term generation.

        Mode 2 returns product-centric terms (or extracts setting tag for hybrid).
        Mode 5 returns generic faceless / topic-driven terms.
        """

    def select_visuals_strategy(self, params: VideoParams) -> Literal["auto", "user_uploaded", "hybrid"]:
        """Returns the visuals_mode material.py should apply.

        Mode 5: always 'auto' (user has no Visuals selector).
        Mode 2: returns params.visuals_mode (preserves user's wizard choice).
        """
```

---

## 2. Registry dispatcher

```python
# app/services/modes/__init__.py
from __future__ import annotations
from typing import Final
from . import faceless, short
from ._interface import Mode

_REGISTRY: Final[dict[str, Mode]] = {
    "short": short,
    "faceless": faceless,
}


def pick(name: str) -> Mode:
    """Lookup a mode by VideoParams.mode literal.

    Raises:
        KeyError: when name is not a registered mode (caller should map to 422 unsupported_mode).
    """
    if name not in _REGISTRY:
        raise KeyError(f"unsupported_mode: {name!r}. Supported: {list(_REGISTRY.keys())}")
    return _REGISTRY[name]


def supported() -> list[str]:
    """Return registered mode names. Used by /api/v1/modes (Step 4 introspection)."""
    return list(_REGISTRY.keys())
```

---

## 3. Per-mode module shape

Every module under `app/services/modes/` (except `_interface.py` and `__init__.py`) MUST export the three top-level callables + two top-level attributes from the Protocol. **Module-level functions, not classes** — modes are stateless.

### 3.1 `app/services/modes/short.py` (Mode 2)

```python
# app/services/modes/short.py
"""Mode 2 — Short Marketing Video.

Migrated from inline constants in app/services/llm.py per debt #4 + #5 burndown.
Preserves byte-for-byte behaviour with pre-Step-3 Mode 2 outputs.
"""
from __future__ import annotations
from typing import Literal
from app.models.schema import VideoAspect, VideoParams

name: str = "short"
default_aspect_ratio: VideoAspect = VideoAspect.portrait

# --- public methods --------------------------------------------------------

def generate_script(params: VideoParams) -> str:
    """Mode 2's hook-body-CTA marketing prompt. Calls _g(...) helper from llm.py."""
    ...  # body lifted from llm.generate_marketing_script

def generate_terms(params: VideoParams, video_script: str) -> list[str]:
    """Product-centric terms for visuals_mode='auto', or setting-tag extraction for hybrid."""
    if params.visuals_mode == "hybrid":
        setting_tag = _extract_setting_tag(video_script)
        return _expand_setting_to_queries(setting_tag, params.video_subject)
    return _generate_product_centric_terms(params, video_script)

def select_visuals_strategy(params: VideoParams) -> Literal["auto", "user_uploaded", "hybrid"]:
    """Pass through user's wizard choice."""
    return params.visuals_mode  # already validated by Pydantic

# --- private helpers (formerly in llm.py) ---------------------------------

def _generate_product_centric_terms(...): ...
def _extract_setting_tag(script: str) -> str: ...
def _expand_setting_to_queries(setting_tag: str, subject: str) -> list[str]: ...
```

### 3.2 `app/services/modes/faceless.py` (Mode 5 — NEW)

```python
# app/services/modes/faceless.py
"""Mode 5 — Faceless Channel Automation.

Generic-stock-footage flow: topic + voice + music in, B-roll auto-fetched
from Pexels (constitution-permitted Principle IV exception for this mode only).
"""
from __future__ import annotations
from typing import Literal
from app.models.schema import VideoAspect, VideoParams

name: str = "faceless"
default_aspect_ratio: VideoAspect = VideoAspect.portrait

def generate_script(params: VideoParams) -> str:
    """Topic-driven faceless template. Reuses upstream MPT's existing generate_script logic."""
    ...

def generate_terms(params: VideoParams, video_script: str) -> list[str]:
    """Generic Pexels-friendly terms drawn from the topic + script."""
    ...

def select_visuals_strategy(params: VideoParams) -> Literal["auto", "user_uploaded", "hybrid"]:
    """Mode 5 is auto-only; user_uploaded + hybrid don't apply."""
    return "auto"
```

---

## 4. Caller — how `task.py` uses the registry

**Pre-Step-3** (`task.py`, debt #5):
```python
def generate_script(task_id, params):
    if params.mode == "short":
        return llm.generate_marketing_script(...)  # inline branch
    return llm.generate_script(...)  # default fallthrough
```

**Post-Step-3** (`task.py`, debt #5 retired):
```python
from app.services import modes

def generate_script(task_id, params):
    if params.script_mode == "verbatim":
        return params.video_script  # spec 013 — orthogonal
    if params.script_mode == "polish":
        return llm.polish_script(params.video_script, ...)  # spec 013
    # script_mode == 'auto' — delegate to the mode
    try:
        mode = modes.pick(params.mode)
    except KeyError as e:
        raise HTTPException(422, {"error_code": "unsupported_mode", "detail": str(e)})
    return mode.generate_script(params)
```

`generate_terms` follows the same shape: `modes.pick(params.mode).generate_terms(params, video_script)`.

`download_videos` in `material.py` calls `modes.pick(params.mode).select_visuals_strategy(params)` to gate Pexels-direct (Mode 5 only) vs pre-signed URLs (Mode 2 always).

---

## 5. Test contract

Every mode module ships with one test file matching its name. Required test cases:

### 5.1 `test/services/modes/test_registry.py`

| Test ID | Scenario | Expected |
|---|---|---|
| REG-1 | `modes.pick("short")` | Returns the `short` module |
| REG-2 | `modes.pick("faceless")` | Returns the `faceless` module |
| REG-3 | `modes.pick("nonexistent")` | Raises `KeyError` |
| REG-4 | `modes.pick("product_shoot")` | Raises `KeyError` (Mode 1 not registered in Layer 3) |
| REG-5 | `modes.supported()` | Returns `["short", "faceless"]` (order-independent set membership check) |
| REG-6 | Each registered module satisfies `Mode` Protocol via `isinstance(module, Mode)` runtime check | True |
| REG-7 | Each registered module has `name` attribute equal to its registry key | True |

### 5.2 `test/services/modes/test_short.py`

| Test ID | Scenario | Expected |
|---|---|---|
| SHORT-1 | `short.generate_script(params)` for product subject | Returns hook-body-CTA template (substring match) |
| SHORT-2 | `short.generate_terms(params, script)` with `visuals_mode='auto'` | Returns product-centric terms |
| SHORT-3 | `short.generate_terms(params, script)` with `visuals_mode='hybrid'` | Returns setting-tag-derived terms |
| SHORT-4 | `short.select_visuals_strategy(params)` for each visuals_mode | Returns the input `params.visuals_mode` |
| SHORT-5 | Snapshot test — generate_script output for fixed seed matches a pinned baseline | byte-equal to fixture |

### 5.3 `test/services/modes/test_faceless.py`

| Test ID | Scenario | Expected |
|---|---|---|
| FACE-1 | `faceless.generate_script(params)` for "Mediterranean diet" topic | Non-empty string > 200 chars |
| FACE-2 | `faceless.generate_terms(params, script)` for fitness topic | List of 3-7 generic Pexels-friendly terms |
| FACE-3 | `faceless.select_visuals_strategy(params)` regardless of params.visuals_mode | Returns `"auto"` always |
| FACE-4 | `faceless.default_aspect_ratio` | `VideoAspect.portrait` |

---

## 6. Versioning + extensibility

**Adding Mode 3 (Long-Form 16:9) in Step 4**:
1. Create `app/services/modes/long.py` with `name = "long"`, `default_aspect_ratio = VideoAspect.landscape`, the three methods.
2. Add `from . import long` and `"long": long` to `_REGISTRY` in `__init__.py`.
3. Widen `VideoParams.mode` literal to include `"long"`.
4. Constitution amendment v1.2.0 (MINOR — adds Mode 3 to actively-implemented column).

**No `task.py` changes required.** That's the contract — the registry abstracts mode-add to a 3-file mechanical edit.

**Adding Mode 1 (`product_shoot`)** is intentionally NOT in this registry. Mode 1's generation pipeline is Layer 2 + Layer 2.5 only. If a future requirement makes Mode 1 produce a video (e.g. "animate the 6 product shots into a 15-second reel"), THAT video-render path becomes a new mode in Layer 3's registry, distinct from the Mode 1 image-gen pipeline.

---

## 7. Forbidden patterns

The registry is the contract. The following are violations:

- ❌ Adding mode dispatch in `task.py` (e.g. `if params.mode == "long": ...`) — must be a registry call
- ❌ Cross-importing one mode module from another (e.g. `faceless.py` doesn't `from . import short`) — modes are siblings, not a hierarchy
- ❌ Stateful module-level globals in mode modules (e.g. caches, counters) — modes are pure
- ❌ Mode modules calling external HTTP APIs directly — that's Layer 2.5 / Layer 2's job
- ❌ Inheriting from a Mode ABC — we use Protocol, not ABC; no inheritance
