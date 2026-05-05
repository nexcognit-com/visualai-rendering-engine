"""Mode 4 — UGC Avatar Generator (spec 018).

Lip-synced talking-head video. The wizard provides a 5-15 second selfie
"speaker reference" (FR-001) plus a script (auto/verbatim/polish via the
existing spec-013 contract). Layer 2 generates the script via
``marketing_script.py`` (research.md R4 — same Hook→Body→CTA shape as
Mode 2, no Mode-4-specific prompt drift) and forwards a
``script_mode="verbatim"`` payload to L3. L3 dispatches via this module's
``generate_script`` only when L2's orchestrator was bypassed (e.g. legacy
direct-to-L3 callers, smoke tests).

The actual lip-sync inference lives in :mod:`app.services.lip_sync` and is
called from :mod:`app.services.task` AFTER TTS audio synth and BEFORE
subtitle burn-in (see [contracts/l3-payload.md](specs/018-ugc-avatar-musetalk/contracts/l3-payload.md#pipeline---taskpy-dispatch-path)).

Mode 4 has NO per-segment B-roll — the speaker's face IS the visual
throughout the render. ``segment_count_range`` is intentionally None to
signal this to any code that walks the registry looking for stock-footage-
based modes.
"""

from __future__ import annotations

from typing import Final

from app.models.schema import VideoAspect, VideoParams
from app.services import llm
from app.services.voice import infer_language_from_voice

from ._interface import VisualsStrategy

name: str = "ugc_avatar"
default_aspect_ratio: VideoAspect = VideoAspect.portrait

# Duration band: 15s minimum (any shorter is a confused single-clip ad)
# up to 300s (5 min, Q1=C resolution — Mode 3 long-form parity).
duration_min_seconds: Final[int] = 15
duration_max_seconds: Final[int] = 300
default_duration_seconds: Final[int] = 30

# 9:16 portrait, 1080×1920. Lower-third subtitle band (matches Mode 2's
# bottom-of-frame placement; Mode 3's mid-frame band is for 16:9 only).
target_resolution: Final[tuple[int, int]] = (1080, 1920)
subtitle_band_y_pct: Final[float] = 0.80
subtitle_band_color: Final[str] = "#000000"
subtitle_band_opacity: Final[float] = 0.60

# No per-segment B-roll — face IS the visual. Explicitly None so callers
# walking the registry can branch on this signal (e.g. Mode 3's segment
# resolver vs. Mode 4's lip-sync pipeline).
segment_count_range: Final[tuple[int, int] | None] = None

# Same Hook→Body→CTA template as Mode 2.
script_template: Final[str] = "HOOK_BODY_CTA"


def generate_script(params: VideoParams) -> str:
    """Mode 4 fallback script generation.

    Layer 2's orchestrator normally produces the script via
    :func:`app.services.marketing_script.generate_marketing_script`
    BEFORE dispatching to Layer 3, then sets ``script_mode="verbatim"`` on
    the dispatched VideoParams so L3 doesn't regenerate. This function
    only runs when L2 didn't run the orchestrator (legacy direct-to-L3
    callers, smoke tests, or fallthrough on orchestrator failure).

    Reuses :func:`llm.generate_marketing_script` per [research.md R4](specs/018-ugc-avatar-musetalk/research.md#r4--script-generator-reuse-mode-2s-helper-or-write-a-mode-4-specific-one).
    Voice-locale fallback applies (i18n spec) so an Arabic voice produces
    an Arabic script.
    """
    duration = (params.video_clip_duration or 5) * (params.video_count or 1)
    duration = max(duration_min_seconds, min(duration_max_seconds, duration))
    language = (
        params.video_language
        or infer_language_from_voice(params.voice_name)
        or "en"
    )
    return llm.generate_marketing_script(
        product_info=params.video_subject or "",
        duration_seconds=duration,
        language=language,
    )


def generate_terms(params: VideoParams, video_script: str) -> list[str]:
    """Mode 4 has no stock-footage terms — face IS the visual."""
    return []


def select_visuals_strategy(params: VideoParams) -> VisualsStrategy:
    """Mode 4 always uses the user-uploaded selfie.

    Returns ``"user_uploaded"`` so existing visuals-mode plumbing routes
    correctly — though Mode 4's ``task.py`` dispatch branch consumes
    ``params.speaker_reference_path`` directly rather than walking the
    generic uploaded_*_paths surface that Mode 1's hybrid path uses.
    """
    return "user_uploaded"
