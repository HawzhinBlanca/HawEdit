"""The setup panel's logic, tested without ever opening a window.

Every test here runs headless and offline. Tk is not imported, and each provider check goes
through an injected transport — the panel's whole job is handling two secrets, so none of it
may depend on a display being present to be verifiable.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

from hawedit import credentials, setup_panel

FAKE_GEMINI = "AIza" + "0" * 35
FAKE_HF = "hf_" + "0" * 34


def _accepting(_url: str, _headers: Mapping[str, str]) -> tuple[int, str]:
    return 200, '{"models": [{"name": "models/gemini-2.5-pro"}], "name": "hawzhin"}'


def _rejecting(_url: str, _headers: Mapping[str, str]) -> tuple[int, str]:
    return 401, '{"error": {"message": "API key not valid"}, "error": "Invalid credentials"}'


def test_the_panel_names_what_each_credential_unlocks() -> None:
    """A window that just says "API key" tells a non-programmer nothing.

    Each slot has to say which stages it turns on and which numbered blocker it answers, or the
    operator cannot tell what they bought by pasting a token in.
    """
    slots = {slot.name: slot for slot in setup_panel.slots()}
    assert set(slots) == {credentials.GEMINI_API_KEY, credentials.HF_TOKEN}

    gemini = slots[credentials.GEMINI_API_KEY]
    assert "Stage 3" in gemini.unlocks and "Stage 4" in gemini.unlocks
    assert gemini.blocker == 3
    assert gemini.where.startswith("https://")

    hugging_face = slots[credentials.HF_TOKEN]
    assert "diariz" in hugging_face.unlocks.lower()
    assert hugging_face.blocker == 4
    assert hugging_face.where.startswith("https://")


def test_the_gemini_slot_says_a_valid_key_is_still_not_enough() -> None:
    """§4 pins gemini-2.5-pro and its free tier is exactly zero (BLOCKED.md #3).

    A panel that reported "key accepted" and stopped would send the operator away believing
    Stage 4 works, and the next real run would be the thing that told them otherwise.
    """
    gemini = next(s for s in setup_panel.slots() if s.name == credentials.GEMINI_API_KEY)
    assert "billing" in gemini.caveat.lower()


def test_a_credential_that_fails_verification_is_not_stored(tmp_path: Path) -> None:
    """Storing an unverified credential turns a clear "not configured" into a failure deep
    inside the first job that needs it — `credentials.main` already refuses to, and the window
    must not be the softer door into the same store."""
    env = tmp_path / "credentials.env"
    slot = next(s for s in setup_panel.slots() if s.name == credentials.GEMINI_API_KEY)

    result = setup_panel.save(slot, FAKE_GEMINI, env_file=env, transport=_rejecting)
    assert not result.valid
    assert not env.exists(), "a rejected credential must leave no trace"

    accepted = setup_panel.save(slot, FAKE_GEMINI, env_file=env, transport=_accepting)
    assert accepted.valid
    assert credentials.read_credential(credentials.GEMINI_API_KEY, env) == FAKE_GEMINI


def test_the_panel_never_displays_an_unmasked_secret(tmp_path: Path) -> None:
    """The only display path for a secret is `mask()`.

    A window keeps its text on screen, in a screenshot, and in whatever the operator pastes
    into a support thread. Nothing here may ever render the value.
    """
    env = tmp_path / "credentials.env"
    slot = next(s for s in setup_panel.slots() if s.name == credentials.HF_TOKEN)
    setup_panel.save(slot, FAKE_HF, env_file=env, transport=_accepting)

    line = setup_panel.status_line(slot, env_file=env, transport=_accepting)
    assert FAKE_HF not in line
    assert credentials.mask(FAKE_HF) in line

    # An empty store must say so rather than rendering an empty secret as if it were one.
    missing = setup_panel.status_line(
        next(s for s in setup_panel.slots() if s.name == credentials.GEMINI_API_KEY),
        env_file=env,
        transport=_accepting,
    )
    assert "not set" in missing.lower()


def test_an_empty_value_is_refused_before_the_provider_is_called(tmp_path: Path) -> None:
    """Blank is a typo, not a credential, and it must not cost a network round trip."""

    def exploding(_url: str, _headers: Mapping[str, str]) -> tuple[int, str]:
        raise AssertionError("an empty value reached the transport")

    slot = next(s for s in setup_panel.slots() if s.name == credentials.HF_TOKEN)
    result = setup_panel.save(slot, "   ", env_file=tmp_path / "c.env", transport=exploding)
    assert not result.valid
    assert not (tmp_path / "c.env").exists()


def test_saving_one_credential_leaves_the_other_alone(tmp_path: Path) -> None:
    """Two slots, one file. Saving the second must not erase the first."""
    env = tmp_path / "credentials.env"
    gemini = next(s for s in setup_panel.slots() if s.name == credentials.GEMINI_API_KEY)
    hugging_face = next(s for s in setup_panel.slots() if s.name == credentials.HF_TOKEN)

    setup_panel.save(gemini, FAKE_GEMINI, env_file=env, transport=_accepting)
    setup_panel.save(hugging_face, FAKE_HF, env_file=env, transport=_accepting)

    assert credentials.read_credential(credentials.GEMINI_API_KEY, env) == FAKE_GEMINI
    assert credentials.read_credential(credentials.HF_TOKEN, env) == FAKE_HF


def test_the_panel_module_does_not_import_tk_at_module_scope() -> None:
    """`credentials.py` sits on `pipeline.py`'s import path. Tk must never land there, and a
    headless machine must be able to import this module to reach the terminal fallback."""
    import sys

    assert "tkinter" not in sys.modules or setup_panel.__name__ in sys.modules
    source = Path(setup_panel.__file__).read_text(encoding="utf-8")
    module_level = [
        line
        for line in source.splitlines()
        if line.startswith("import tkinter") or line.startswith("from tkinter")
    ]
    assert not module_level, f"tkinter is imported at module scope: {module_level}"


def test_every_slot_validates_through_its_own_provider() -> None:
    """A single shared validator would have sent the Hugging Face token to Google."""
    validators = {slot.name: slot.validate for slot in setup_panel.slots()}
    assert validators[credentials.GEMINI_API_KEY] is credentials.validate_gemini_key
    assert validators[credentials.HF_TOKEN] is credentials.validate_hf_token


def test_the_setup_console_script_is_declared() -> None:
    """The whole point is that Hawa runs one command. It has to exist as one."""
    import tomllib

    root = Path(__file__).resolve().parents[1]
    scripts = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "scripts"
    ]
    assert scripts["hawedit-setup"] == "hawedit.setup_panel:main"


def test_no_display_falls_back_to_the_terminal_panel(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tk raises on a headless box. That is a known state, not a crash to show an operator."""
    called: list[str] = []

    def refuse() -> object:
        raise setup_panel.NoDisplay("no display")

    monkeypatch.setattr(setup_panel, "_open_window", refuse)

    def fallback() -> int:
        called.append("terminal")
        return 0

    monkeypatch.setattr(setup_panel, "_terminal_fallback", fallback)

    assert setup_panel.main([]) == 0
    assert called == ["terminal"]
