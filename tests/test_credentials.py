"""The credential store, tested around the three ways it can hurt you.

A key is the one piece of configuration that is actively dangerous to get slightly wrong, so
the tests that matter are refusals: writing a secret somewhere git tracks, storing a key that
does not work, and letting a key appear in output. Everything else here is plumbing.

Every test runs offline — the Gemini call goes through an injected transport. `AGENTS.md`
forbids committing secrets, and a test suite that needed a real key to pass would push people
toward putting one somewhere convenient.
"""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from hawedit.credentials import (
    GEMINI_API_KEY,
    CredentialError,
    KeyCheck,
    assert_ignored_by_git,
    credential_status,
    mask,
    read_credential,
    validate_gemini_key,
    write_credential,
)

FAKE_KEY = "AIzaSy-not-a-real-key-0000-abcd"


def ok_transport(_url: str) -> tuple[int, str]:
    return 200, json.dumps(
        {"models": [{"name": "models/gemini-2.5-pro"}, {"name": "models/gemini-2.5-flash"}]}
    )


def rejecting_transport(_url: str) -> tuple[int, str]:
    return 400, json.dumps(
        {"error": {"code": 400, "message": "API key not valid. Please pass a valid API key."}}
    )


def offline_transport(_url: str) -> tuple[int, str]:
    return 0, "Name or service not known"


# --- refusal 1: never write a secret somewhere git tracks ---------------------------------


def test_writing_to_a_tracked_path_is_refused(tmp_path: Path) -> None:
    """The hard boundary in AGENTS.md — "never commit secrets" — as a check rather than a rule.

    A key in a commit outlives its own revocation: rotating it does not remove it from the
    history, and anyone who cloned in between has it.
    """
    tracked = Path(__file__).resolve()  # this test file is committed
    with pytest.raises(CredentialError, match="not ignored by git"):
        write_credential(GEMINI_API_KEY, FAKE_KEY, env_file=tracked)


def test_the_projects_own_env_file_is_ignored() -> None:
    """The check is only worth having if the real target passes it."""
    from hawedit.credentials import ENV_FILE

    assert_ignored_by_git(ENV_FILE)  # must not raise


def test_the_stored_file_is_not_world_readable(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    write_credential(GEMINI_API_KEY, FAKE_KEY, env_file=env_file, check_ignored=False)
    mode = stat.S_IMODE(env_file.stat().st_mode)
    assert mode == 0o600, f"{oct(mode)} — a credential file other users can read"


def test_an_existing_permissive_file_is_tightened(tmp_path: Path) -> None:
    """An existing .env may predate this module, so the mode is set on every write."""
    env_file = tmp_path / ".env"
    env_file.write_text("OTHER=1\n", encoding="utf-8")
    env_file.chmod(0o644)
    write_credential(GEMINI_API_KEY, FAKE_KEY, env_file=env_file, check_ignored=False)
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600


# --- refusal 2: never store a key that has not been verified ------------------------------


def test_a_rejected_key_is_reported_with_the_apis_own_message() -> None:
    check = validate_gemini_key("wrong", transport=rejecting_transport)
    assert not check.valid
    assert "API key not valid" in check.detail
    assert check.models == ()


def test_an_unreachable_api_is_not_reported_as_an_invalid_key() -> None:
    """A network failure and a bad key are different problems with different fixes."""
    check = validate_gemini_key(FAKE_KEY, transport=offline_transport)
    assert not check.valid
    assert "could not reach" in check.detail


def test_a_working_key_reports_the_models_it_can_see() -> None:
    check = validate_gemini_key(FAKE_KEY, transport=ok_transport)
    assert check.valid
    assert "gemini-2.5-pro" in check.models, "§7 pins this model; its absence is worth knowing"


def test_a_malformed_success_body_is_not_treated_as_valid() -> None:
    check = validate_gemini_key(FAKE_KEY, transport=lambda _u: (200, "not json"))
    assert not check.valid


def test_an_empty_key_is_refused_before_anything_is_written(tmp_path: Path) -> None:
    with pytest.raises(CredentialError, match="typo"):
        write_credential(GEMINI_API_KEY, "   ", env_file=tmp_path / ".env", check_ignored=False)
    assert not (tmp_path / ".env").exists()


# --- refusal 3: never print the key --------------------------------------------------------


def test_masking_shows_enough_to_tell_two_keys_apart_and_no_more() -> None:
    assert mask("AIzaSyABCD1234") == "…1234"
    assert "AIzaSy" not in mask("AIzaSyABCD1234")
    assert mask("") == "(unset)"
    assert mask("ab") == "…", "a short secret must not be shown in full"


def test_the_rejection_message_does_not_contain_the_key() -> None:
    """An error carrying a credential is how secrets reach log aggregators."""
    check = validate_gemini_key(FAKE_KEY, transport=rejecting_transport)
    assert FAKE_KEY not in check.detail


def test_an_unreachable_api_message_does_not_contain_the_key() -> None:
    check = validate_gemini_key(FAKE_KEY, transport=offline_transport)
    assert FAKE_KEY not in check.detail


# --- reading: environment first, then .env -------------------------------------------------


def test_the_environment_beats_the_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """So CI can inject a secret with no file, and an export can override a stale .env."""
    env_file = tmp_path / ".env"
    write_credential(GEMINI_API_KEY, "from-file", env_file=env_file, check_ignored=False)
    monkeypatch.setenv(GEMINI_API_KEY, "from-environment")
    assert read_credential(GEMINI_API_KEY, env_file) == "from-environment"


def test_the_file_is_used_when_the_environment_is_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(GEMINI_API_KEY, raising=False)
    env_file = tmp_path / ".env"
    write_credential(GEMINI_API_KEY, "from-file", env_file=env_file, check_ignored=False)
    assert read_credential(GEMINI_API_KEY, env_file) == "from-file"


def test_an_absent_credential_is_none_not_empty_string(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty string reads as "configured, to nothing" — the two are different states."""
    monkeypatch.delenv(GEMINI_API_KEY, raising=False)
    assert read_credential(GEMINI_API_KEY, tmp_path / "absent") is None


def test_an_empty_value_in_the_file_reads_as_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(GEMINI_API_KEY, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(f"{GEMINI_API_KEY}=\n", encoding="utf-8")
    assert read_credential(GEMINI_API_KEY, env_file) is None


def test_writing_one_credential_leaves_the_others_alone(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("OTHER_TOKEN=keep-me\n", encoding="utf-8")
    write_credential(GEMINI_API_KEY, FAKE_KEY, env_file=env_file, check_ignored=False)
    body = env_file.read_text(encoding="utf-8")
    assert "OTHER_TOKEN=keep-me" in body
    assert f"{GEMINI_API_KEY}={FAKE_KEY}" in body


def test_quoted_and_exported_lines_are_understood(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """People write .env by hand, and `export KEY="value"` is what a shell user types."""
    monkeypatch.delenv(GEMINI_API_KEY, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(f'# a comment\nexport {GEMINI_API_KEY}="quoted-value"\n', encoding="utf-8")
    assert read_credential(GEMINI_API_KEY, env_file) == "quoted-value"


def test_status_reports_absence_without_calling_the_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(GEMINI_API_KEY, raising=False)

    def explode(_url: str) -> tuple[int, str]:
        raise AssertionError("the API must not be called when no key is configured")

    key, check = credential_status(GEMINI_API_KEY, tmp_path / "absent", transport=explode)
    assert key is None and check is None


def test_status_validates_a_configured_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(GEMINI_API_KEY, FAKE_KEY)
    key, check = credential_status(GEMINI_API_KEY, tmp_path / "absent", transport=ok_transport)
    assert key == FAKE_KEY
    assert check == KeyCheck(
        True, "key accepted; 2 model(s) visible", ("gemini-2.5-pro", "gemini-2.5-flash")
    )
