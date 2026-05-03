"""Mode registry interface (spec 015).

Every active mode under ``app/services/modes/`` MUST satisfy the ``Mode``
Protocol below. Constitution Principle V mandates this directory as the
single home for mode dispatch logic.
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from app.models.schema import VideoAspect, VideoParams


VisualsStrategy = Literal["auto", "user_uploaded", "hybrid"]


@runtime_checkable
class Mode(Protocol):
    """Structural-typed contract for mode modules.

    Module-level functions only — modes are stateless. Worker-thread safe by
    construction. Adding a mode = a new module satisfying this Protocol +
    one entry in ``_REGISTRY`` in ``__init__.py``.
    """

    name: str
    default_aspect_ratio: VideoAspect

    def generate_script(self, params: VideoParams) -> str: ...

    def generate_terms(
        self, params: VideoParams, video_script: str
    ) -> list[str]: ...

    def select_visuals_strategy(self, params: VideoParams) -> VisualsStrategy: ...
