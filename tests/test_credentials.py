"""The credential store, tested around the three ways it can hurt you.

A key is the one piece of configuration that is actively dangerous to get slightly wrong, so
the tests that matter are refusals: writing a secret somewhere git tracks, storing a key that
does not work, and letting a key appear in output. Everything else here is plumbing.

Every test runs offline — the Gemini call goes through an injected transport. `AGENTS.md`
forbids committing secrets, and a test suite that needed a real key to pass would push people
toward putting one somewhere convenient.
"""

from __future__ import annotations

import getpass
import json
import os
import stat
import subprocess
from collections.abc import Mapping
from pathlib import Path

import pytest

from hawedit.credentials import (
    GEMINI_API_KEY,
    REPO_ROOT,
    CredentialError,
    KeyCheck,
    credential_status,
    mask,
    read_credential,
    validate_gemini_key,
    write_credential,
)

FAKE_KEY = "AIzaSy-not-a-real-key-0000-abcd"


def ok_transport(_url: str, _headers: Mapping[str, str]) -> tuple[int, str]:
    return 200, json.dumps(
        {"models": [{"name": "models/gemini-2.5-pro"}, {"name": "models/gemini-2.5-flash"}]}
    )


def rejecting_transport(_url: str, _headers: Mapping[str, str]) -> tuple[int, str]:
    return 400, json.dumps(
        {"error": {"code": 400, "message": "API key not valid. Please pass a valid API key."}}
    )


def offline_transport(_url: str, _headers: Mapping[str, str]) -> tuple[int, str]:
    return 0, "Name or service not known"


# --- refusal 1: never write a secret somewhere git tracks ---------------------------------


def test_writing_to_a_tracked_path_is_refused(tmp_path: Path) -> None:
    """The hard boundary in AGENTS.md — "never commit secrets" — as a check rather than a rule.

    A key in a commit outlives its own revocation: rotating it does not remove it from the
    history, and anyone who cloned in between has it.
    """
    # A path git does not ignore, chosen so that a *failure* here cannot destroy anything.
    #
    # This test used `Path(__file__)` — its own source — on the reasoning that the test file is
    # certainly committed. That made the guard under test the only thing standing between the
    # suite and its own source code, and on 2026-08-09 an audit that neutered
    # `assert_ignored_by_git` proved the point: this test wrote a credentials dump over
    # `tests/test_credentials.py`, replacing 262 lines with eleven `KEY=VALUE` fragments
    # scavenged from the module it had just overwritten. `git check-ignore` answers from
    # `.gitignore` patterns rather than from the filesystem, so a path that does not exist is
    # just as un-ignored — and if the guard ever fails open, the worst case is one stray file
    # instead of a deleted test. D-113.
    not_ignored = REPO_ROOT / "a-credential-must-never-be-written-here.env"
    assert not not_ignored.exists(), "the probe path must not exist before the call"

    with pytest.raises(CredentialError, match="not ignored by git"):
        write_credential(GEMINI_API_KEY, FAKE_KEY, env_file=not_ignored)

    assert not not_ignored.exists(), (
        "the refusal has to happen before the write, or a rejected credential is on disk anyway"
    )


def test_the_default_credential_file_is_outside_the_checkout() -> None:
    """An installed wheel must not write a secret into site-packages or require Git."""
    from hawedit.credentials import ENV_FILE, REPO_ROOT

    assert not ENV_FILE.is_relative_to(REPO_ROOT)
    assert ENV_FILE.name == "credentials.env"


def assert_owner_only(env_file: Path) -> None:
    """The stored key must not be readable by another local account — on either platform.

    Windows ignores every mode bit but read-only, so `S_IMODE == 0o600` is unsatisfiable
    there and asserting it would only ever have two outcomes: a red suite, or the check
    deleted. Neither tests the property. So the property is asserted in the terms each
    platform actually has, and read back from the OS rather than from the code that set it —
    `icacls` is the authority on a Windows ACL the way `stat` is on a POSIX mode.
    """
    if os.name != "nt":
        mode = stat.S_IMODE(env_file.stat().st_mode)
        assert mode == 0o600, f"{oct(mode)} — a credential file other users can read"
        return

    acl = subprocess.run(
        ["icacls", str(env_file)], capture_output=True, text=True, check=True
    ).stdout
    # `icacls` prints the path once, then one `PRINCIPAL:(perms)` per ACE, continuation lines
    # indented, then a summary line.
    granted = set()
    for line in acl.splitlines():
        ace = line.replace(str(env_file), "", 1).strip()
        if ace and not ace.startswith("Successfully"):
            granted.add(ace.split(":(")[0])
    assert len(granted) == 1 and granted.pop().endswith("\\" + getpass.getuser()), (
        f"{env_file} is readable by more than its owner — a credential file must not be.\n{acl}"
    )


def test_the_stored_file_is_not_world_readable(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    write_credential(GEMINI_API_KEY, FAKE_KEY, env_file=env_file, check_ignored=False)
    assert_owner_only(env_file)


def test_an_existing_permissive_file_is_tightened(tmp_path: Path) -> None:
    """An existing .env may predate this module, so it is narrowed on every write."""
    env_file = tmp_path / ".env"
    env_file.write_text("OTHER=1\n", encoding="utf-8")
    if os.name != "nt":
        env_file.chmod(0o644)
    write_credential(GEMINI_API_KEY, FAKE_KEY, env_file=env_file, check_ignored=False)
    assert_owner_only(env_file)


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


def test_key_validation_authenticates_by_header_never_by_url() -> None:
    seen: list[tuple[str, dict[str, str]]] = []

    def transport(url: str, headers: Mapping[str, str]) -> tuple[int, str]:
        seen.append((url, dict(headers)))
        return ok_transport(url, headers)

    assert validate_gemini_key(FAKE_KEY, transport=transport).valid
    assert FAKE_KEY not in seen[0][0] and "?key=" not in seen[0][0]
    assert seen[0][1].get("x-goog-api-key") == FAKE_KEY


def test_a_malformed_success_body_is_not_treated_as_valid() -> None:
    check = validate_gemini_key(FAKE_KEY, transport=lambda _u, _h: (200, "not json"))
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

    def explode(_url: str, _headers: Mapping[str, str]) -> tuple[int, str]:
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
