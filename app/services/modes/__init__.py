"""Mode registry (spec 015 / Step 3 PR-A).

Constitution Principle V: every supported Agent Mode that produces a
Layer 3 render task MUST live as a module under ``app/services/modes/``
and be registered here. Adding a new mode = (1) new module satisfying
the :class:`Mode` Protocol, (2) one entry in ``_REGISTRY``, (3) widening
the ``VideoParams.mode`` literal in ``app/models/schema.py``.

``product_shoot`` (Mode 1) is intentionally NOT registered here — it
dispatches Layer 2 → Layer 2.5 only and never reaches Layer 3.
"""

from __future__ import annotations

from typing import Final

from . import faceless, long_form, short
from ._interface import Mode

_REGISTRY: Final[dict[str, Mode]] = {
    "short": short,         # Mode 2 — Short Marketing Video
    "faceless": faceless,   # Mode 5 — Faceless Channel Automation
    "long": long_form,      # Mode 3 — Long-Form Video (spec 016)
}


def pick(name: str) -> Mode:
    """Lookup a mode module by ``VideoParams.mode`` literal value.

    Raises:
        KeyError: when ``name`` isn't registered. Callers should map this to
            HTTP 422 ``unsupported_mode`` per the contract.
    """
    if name not in _REGISTRY:
        raise KeyError(
            f"unsupported_mode: {name!r}. Supported: {list(_REGISTRY.keys())}"
        )
    return _REGISTRY[name]


def supported() -> list[str]:
    """Return registered mode names (Step-4 introspection endpoint hooks here)."""
    return list(_REGISTRY.keys())


__all__ = ["Mode", "pick", "supported"]
