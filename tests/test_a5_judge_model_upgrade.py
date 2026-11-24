"""Tests for A5 (D-339): upgrade Stage 4 judge away from deprecated gemini-2.5-pro."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_judge_and_shadow_constants_use_current_gemini_models() -> None:
    """Incumbent and shadow must not use deprecated 2.5-pro or 404 gemini-3.1-pro."""
    from hawedit.judge import JUDGE_SHADOW, KURDISH_EDITORIAL_JUDGE

    assert KURDISH_EDITORIAL_JUDGE in {"gemini-4-carbon", "gemini-4-argon"}
    assert JUDGE_SHADOW in {"gemini-4-argon", "gemini-3.1-pro-preview"}
    assert str(KURDISH_EDITORIAL_JUDGE) != str(JUDGE_SHADOW)


def test_no_hardcoded_deprecated_gemini_25_pro_in_runtime_paths() -> None:
    """Runtime modules must follow KURDISH_EDITORIAL_JUDGE rather than hardcoding 2.5-pro."""
    runtime_files = (
        ROOT / "src" / "hawedit" / "judge.py",
        ROOT / "src" / "hawedit" / "path_a.py",
        ROOT / "src" / "hawedit" / "pipeline.py",
        ROOT / "src" / "hawedit" / "credentials.py",
        ROOT / "src" / "hawedit" / "setup_panel.py",
        ROOT / "src" / "hawedit" / "smoke.py",
        ROOT / "src" / "hawedit" / "gemini.py",
    )
    for path in runtime_files:
        text = path.read_text(encoding="utf-8")
        assert '"gemini-2.5-pro"' not in text, f"hardcoded deprecated model in {path.name}"


def test_shadow_verdict_cannot_bypass_routing_guard() -> None:
    """Shadow model stays evaluated-only even after D-339 model upgrade."""
    from hawedit.gemini import GeminiJudge
    from hawedit.judge import JUDGE_SHADOW, KURDISH_EDITORIAL_JUDGE, NotRoutable, route
    from hawedit.registry import resolve

    assert resolve(KURDISH_EDITORIAL_JUDGE).routable
    assert not resolve(JUDGE_SHADOW).routable
    with pytest.raises(NotRoutable):
        GeminiJudge(api_key="test-key", model_id=JUDGE_SHADOW)

    class _ShadowFake:
        model_id = JUDGE_SHADOW

        def judge(self, request: object) -> object:
            raise AssertionError(f"shadow model should not be routed: {request!r}")

    with pytest.raises(NotRoutable):
        route(_ShadowFake())
