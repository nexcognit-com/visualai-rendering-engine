"""Spec 015 — modes registry dispatcher (T017)."""

from __future__ import annotations

import pytest

from app.models.schema import VideoAspect
from app.services import modes
from app.services.modes._interface import Mode


def test_reg1_pick_short_returns_short_module() -> None:
    m = modes.pick("short")
    assert m.name == "short"


def test_reg2_pick_faceless_returns_faceless_module() -> None:
    m = modes.pick("faceless")
    assert m.name == "faceless"


def test_reg3_pick_unknown_raises_keyerror() -> None:
    with pytest.raises(KeyError, match="unsupported_mode"):
        modes.pick("nonexistent_mode_xyz")


def test_reg4_pick_product_shoot_raises() -> None:
    """Mode 1 is intentionally NOT registered in Layer 3 (lives in Layer 2)."""
    with pytest.raises(KeyError, match="unsupported_mode"):
        modes.pick("product_shoot")


def test_reg5_supported_returns_all_registered_modes() -> None:
    s = modes.supported()
    assert set(s) == {"short", "faceless", "long"}


def test_reg6_each_module_satisfies_mode_protocol() -> None:
    """Runtime Protocol check — each registered mode has the required surface."""
    for name in modes.supported():
        m = modes.pick(name)
        assert isinstance(m, Mode), f"{name!r} doesn't satisfy Mode Protocol"


def test_reg7_each_modules_name_matches_registry_key() -> None:
    for name in modes.supported():
        m = modes.pick(name)
        assert m.name == name


def test_default_aspect_ratio_per_mode() -> None:
    """Mode 2 + Mode 5 are vertical (9:16); Mode 3 is horizontal (16:9)."""
    expected = {
        "short": VideoAspect.portrait,
        "faceless": VideoAspect.portrait,
        "long": VideoAspect.landscape,
    }
    for name in modes.supported():
        m = modes.pick(name)
        assert m.default_aspect_ratio == expected[name], (
            f"{name!r} default_aspect_ratio={m.default_aspect_ratio}, "
            f"expected {expected[name]}"
        )
