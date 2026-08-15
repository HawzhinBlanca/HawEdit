"""The credential store, tested around the three ways it can hurt you.

A key is the one piece of configuration that is actively dangerous to get slightly wrong, so
the tests that matter are refusals: writing a secret somewhere git tracks, storing a key that
does not work, and letting a key appear in output. Everything else here is plumbing.

Every test runs offline — the Gemini call goes through an injected transport. `AGENTS.md`
forbids committing secrets, and a test suite that needed a real key to pass would push people
toward putting one somewhere convenient.
"""

from __future__ import annotations

import errno
import getpass
import io
import json
import os
import stat
import subprocess
import urllib.error
import urllib.request
from collections.abc import Mapping
from email.message import Message
from pathlib import Path

import pytest

from hawedit import credentials
from hawedit.credentials import (
    _PINNED_JUDGE,
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
from hawedit.credentials import main as credentials_main

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
    # Cleaned up in `finally`, because D-113 stopped one failure from deleting a test and left it
    # able to poison every later run instead: the pre-existence assertion below fails for any
    # subsequent invocation once the file is on disk, so a single fail-open turned into an
    # indefinitely red suite that only a manual `rm` of a real-looking credential file could
    # clear. Measured 2026-08-10 while auditing this very guard — the stray file made 16 of 20
    # mutations report RED for the wrong reason. The check is unchanged; it now heals. D-137.
    not_ignored = REPO_ROOT / "a-credential-must-never-be-written-here.env"
    assert not not_ignored.exists(), (
        f"the probe path must not exist before the call. If it does, an earlier run of this test "
        f"wrote a credential there and the guard failed open — inspect and delete {not_ignored}"
    )

    try:
        with pytest.raises(CredentialError, match="not ignored by git"):
            write_credential(GEMINI_API_KEY, FAKE_KEY, env_file=not_ignored)

        assert not not_ignored.exists(), (
            "the refusal has to happen before the write, or a rejected credential is on disk anyway"
        )
    finally:
        not_ignored.unlink(missing_ok=True)


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


def test_the_opened_env_must_be_the_file_the_symlink_check_looked_at(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Found SURVIVED by adversarial pass #20, on the platform where it is load-bearing.

    Where the kernel has no `O_NOFOLLOW` — `_O_NOFOLLOW` is measured at **0** on this Windows
    host — the guarantee is rebuilt from two halves: refuse a symlink *before* the open, then
    prove *after* the open that the handle is the same file that was checked. The second half is
    what closes the window the first half opens, and deleting it left the whole suite green: the
    symlink test covers the pre-check, and nothing covered the identity test.

    The race is forced rather than waited for. `os.lstat` is made to answer about a *different*
    file, which is exactly what an attacker replacing `.env` between the two calls achieves, and
    the write must refuse rather than put a key into whatever now sits at that path.

    `_O_NOFOLLOW` is patched to 0 rather than the test being skipped where the kernel has the
    flag. The first version skipped on POSIX, and the gate refused the commit: *"only 1372 tests
    passed against a floor of 1373 … a skip condition is creeping."* It was right — a guard that
    only Windows exercises is a guard CI never checks. Patching the constant is how the branch is
    reached anywhere, and it is the same condition the branch itself tests.
    """
    monkeypatch.setattr("hawedit.credentials._O_NOFOLLOW", 0)

    env_file = tmp_path / ".env"
    env_file.write_text("OTHER=1\n", encoding="utf-8")
    decoy = tmp_path / "decoy"
    decoy.write_text("decoy\n", encoding="utf-8")
    real_lstat = os.lstat

    def lstat_of_another_file(path: object, *args: object, **kwargs: object) -> os.stat_result:
        if str(path) == str(env_file):
            return real_lstat(decoy)  # the identity the check will remember
        return real_lstat(path)  # type: ignore[arg-type]

    monkeypatch.setattr("hawedit.credentials.os.lstat", lstat_of_another_file)

    with pytest.raises(CredentialError, match="identity changed"):
        write_credential(GEMINI_API_KEY, FAKE_KEY, env_file=env_file, check_ignored=False)

    assert env_file.read_text(encoding="utf-8") == "OTHER=1\n", (
        "the key was written into a file whose identity had changed under the check"
    )
    # The control: with `os.lstat` telling the truth the same call succeeds, so this measures the
    # identity test and not merely that some patched syscall breaks the write.
    monkeypatch.setattr("hawedit.credentials.os.lstat", real_lstat)
    write_credential(GEMINI_API_KEY, FAKE_KEY, env_file=env_file, check_ignored=False)
    assert GEMINI_API_KEY in env_file.read_text(encoding="utf-8")


def test_a_hard_linked_env_file_is_refused_before_the_key_is_written(tmp_path: Path) -> None:
    """The sibling of the symlink refusal, and the one no test held.

    Measured by neutralising each refusal in a shadow copy of src/hawedit and running this file
    with tests/test_claims.py: this one could be deleted with both green.

    Its own comment says where it came from — "found by the second independent review, in the
    code written to fix the first one". O_NOFOLLOW rejects a *symlinked* `.env` and says nothing
    about a hardlink, which is an ordinary regular file sharing an inode with, say, a tracked
    file. O_TRUNC would then rewrite that file's content with the key. The first fix validated
    the path's name; this validates the file's identity.
    """
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("a file git knows about\n", encoding="utf-8")
    env_file = tmp_path / ".env"
    try:
        os.link(tracked, env_file)
    except (OSError, NotImplementedError) as exc:  # pragma: no cover - filesystem dependent
        pytest.fail(f"could not create a hard link to exercise the guard: {exc}")

    with pytest.raises(CredentialError, match="hard links"):
        write_credential(GEMINI_API_KEY, FAKE_KEY, env_file=env_file, check_ignored=False)

    assert tracked.read_text(encoding="utf-8") == "a file git knows about\n", (
        "the key was written through a hard link into the file sharing that inode"
    )
    assert FAKE_KEY not in env_file.read_text(encoding="utf-8")

    # The control: the same call against a file with one link succeeds, so this measures the
    # link count and not something else about writing into tmp_path.
    alone = tmp_path / "alone.env"
    write_credential(GEMINI_API_KEY, FAKE_KEY, env_file=alone, check_ignored=False)
    assert GEMINI_API_KEY in alone.read_text(encoding="utf-8")


def test_the_key_never_reaches_the_disk_when_the_narrowing_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusal used to name a state it had already created.

    `restrict_to_owner` ran *after* the body was written, so when it failed the plaintext key
    was on disk at inherited permissions and the panel printed "Refusing to leave a credential
    at inherited permissions". Measured on hawapc01 against a real `icacls` failure — an
    unresolvable principal, exit 1332 — in a directory granting `Everyone:(OI)(CI)F`: 95 bytes
    containing the key, readable by Everyone, and `main()` returning 2 as though nothing had
    been stored.

    So the narrowing moved above the write, and this asserts the file rather than the exception.
    """
    env_file = tmp_path / ".env"
    env_file.write_text("GEMINI_API_KEY=sk-the-one-already-stored\n", encoding="utf-8")
    real_restrict = credentials.restrict_to_owner

    def cannot_narrow(_path: Path) -> None:
        raise CredentialError("could not restrict … refusing to leave it at inherited permissions")

    monkeypatch.setattr("hawedit.credentials.restrict_to_owner", cannot_narrow)

    with pytest.raises(CredentialError, match="inherited permissions"):
        write_credential(
            GEMINI_API_KEY, "sk-MUST-NOT-REACH-DISK", env_file=env_file, check_ignored=False
        )

    body = env_file.read_text(encoding="utf-8")
    assert "sk-MUST-NOT-REACH-DISK" not in body, (
        "the key is on disk at permissions the code just refused to accept"
    )
    # The narrowing is also above `ftruncate`, so refusing does not destroy what was stored
    # before it — a failed rotation must not leave the operator with neither key.
    assert "sk-the-one-already-stored" in body, "the previous key was destroyed on the way out"

    # The control. With the narrowing working, the same call writes — otherwise this test would
    # pass just as well against a `write_credential` that never writes anything.
    monkeypatch.setattr("hawedit.credentials.restrict_to_owner", real_restrict)
    write_credential(
        GEMINI_API_KEY, "sk-MUST-NOT-REACH-DISK", env_file=env_file, check_ignored=False
    )
    assert "sk-MUST-NOT-REACH-DISK" in env_file.read_text(encoding="utf-8")


def test_a_narrowing_that_could_not_be_applied_is_refused_not_warned_about(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`icacls` exiting nonzero is the only signal Windows gives that the ACL was not rewritten.

    Deleting this check left the entire suite green — the sweep that found it deleted every
    `raise` in the module one at a time — because the branch is Windows-only and the assertion
    that would catch it lives on the success path. `_IS_WINDOWS` is patched rather than the test
    being skipped on POSIX, for the reason spelled out above: a guard only one platform executes
    is a guard the runner never checks.
    """
    monkeypatch.setattr("hawedit.credentials._IS_WINDOWS", True)
    target = tmp_path / ".env"
    target.write_text("x\n", encoding="utf-8")
    seen: list[list[str]] = []

    def icacls(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.append(argv)
        # 1332 is what the real tool returns for a principal it cannot map to a SID, measured.
        return subprocess.CompletedProcess(argv, 1332, "", "No mapping between account names")

    monkeypatch.setattr("hawedit.credentials.subprocess.run", icacls)
    with pytest.raises(CredentialError, match="inherited permissions"):
        credentials.restrict_to_owner(target)
    assert seen and seen[0][0] == "icacls" and "/inheritance:r" in seen[0], seen

    # The control: the same code path with the tool succeeding must return, so this measures the
    # exit status and not merely that the call was intercepted.
    monkeypatch.setattr(
        "hawedit.credentials.subprocess.run",
        lambda argv, **_k: subprocess.CompletedProcess(argv, 0, "", ""),
    )
    credentials.restrict_to_owner(target)


@pytest.mark.parametrize(
    ("code", "message"),
    [(errno.ELOOP, "symbolic link"), (errno.EACCES, "cannot write")],
)
def test_the_kernels_own_answer_about_a_symlink_is_a_refusal_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: int, message: str
) -> None:
    """Where `O_NOFOLLOW` exists, the kernel refuses the symlink and the code reads `ELOOP`.

    That branch is unreachable on this Windows host — `_O_NOFOLLOW` is 0, so the pre-open check
    answers first — and the sweep duly found both arms of the `OSError` handler deletable with
    the suite green here. On the POSIX runner they are the live path. The kernel's answer is
    supplied rather than waited for, which is what the symlink test one file over already does
    with the privilege it cannot get on Windows.
    """
    env_file = tmp_path / ".env"
    real_open = os.open

    def refusing_open(path: object, flags: int, mode: int = 0o777) -> int:
        if str(path) == str(env_file):
            raise OSError(code, os.strerror(code))
        return real_open(path, flags, mode)  # type: ignore[arg-type]

    monkeypatch.setattr("hawedit.credentials.os.open", refusing_open)
    with pytest.raises(CredentialError, match=message):
        write_credential(GEMINI_API_KEY, FAKE_KEY, env_file=env_file, check_ignored=False)
    assert not env_file.exists(), "a refused open still left a credential file behind"


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


@pytest.mark.parametrize(
    "unsafe_key",
    [
        "",
        "contains a space",
        "contains\ta-tab",
        "header\r\nInjected: value",
        "unicode-کلیل",
        "A" * 513,
    ],
)
def test_header_unsafe_keys_are_refused_before_transport(unsafe_key: str) -> None:
    calls = 0

    def transport(_url: str, _headers: Mapping[str, str]) -> tuple[int, str]:
        nonlocal calls
        calls += 1
        raise AssertionError("a header-unsafe key reached the transport")

    check = validate_gemini_key(unsafe_key, transport=transport)
    assert not check.valid
    assert calls == 0
    assert "header-safe" in check.detail
    if unsafe_key:
        assert unsafe_key not in check.detail


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


def test_key_validation_bounds_and_redacts_an_untrusted_provider_error() -> None:
    hostile = f"provider echoed {FAKE_KEY}\x00\n" + ("X" * 1_000_000) + " secret-tail"
    check = validate_gemini_key(
        FAKE_KEY,
        transport=lambda _url, _headers: (
            400,
            json.dumps({"error": {"message": hostile}}),
        ),
    )

    assert not check.valid
    assert FAKE_KEY not in check.detail
    assert "\x00" not in check.detail and "\n" not in check.detail
    assert len(check.detail) <= credentials._MAX_KEY_CHECK_DETAIL_CHARS
    assert "secret-tail" not in check.detail


def test_key_validation_bounds_an_untrusted_network_error() -> None:
    check = validate_gemini_key(
        FAKE_KEY,
        transport=lambda _url, _headers: (0, "offline\x00\n" + ("N" * 1_000_000)),
    )

    assert not check.valid
    assert "\x00" not in check.detail and "\n" not in check.detail
    assert len(check.detail) <= credentials._MAX_KEY_CHECK_DETAIL_CHARS


def test_the_live_key_probe_refuses_an_oversized_response_without_reading_it_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested: list[int] = []

    class OversizedResponse:
        status = 200

        def __enter__(self) -> OversizedResponse:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, size: int = -1) -> bytes:
            requested.append(size)
            assert size == credentials._MAX_KEY_CHECK_RESPONSE_BYTES + 1
            return b"x" * size

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda _request, timeout: OversizedResponse(),
    )

    check = validate_gemini_key(FAKE_KEY)
    assert not check.valid
    assert "exceeded" in check.detail
    assert requested == [credentials._MAX_KEY_CHECK_RESPONSE_BYTES + 1]


def test_the_live_key_probe_bounds_an_oversized_http_error_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested: list[int] = []

    class OversizedErrorBody(io.BytesIO):
        def __init__(self) -> None:
            super().__init__(b"e" * (credentials._MAX_KEY_CHECK_RESPONSE_BYTES + 1))

        def read(self, size: int | None = -1) -> bytes:
            requested.append(-1 if size is None else size)
            return super().read(size)

    def reject(_request: object, timeout: int) -> object:
        assert timeout == 30
        raise urllib.error.HTTPError(
            "https://generativelanguage.googleapis.com/v1beta/models",
            429,
            "too many requests",
            Message(),
            OversizedErrorBody(),
        )

    monkeypatch.setattr(urllib.request, "urlopen", reject)

    check = validate_gemini_key(FAKE_KEY)
    assert not check.valid
    assert "exceeded" in check.detail
    assert requested == [credentials._MAX_KEY_CHECK_RESPONSE_BYTES + 1]


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


# --- D-137: the panel's own ordering, which no test drove -----------------------------------
#
# M2.8 leads with "`python -m hawedit.credentials` verifies a key against Google before storing
# it". That decision lives entirely in `main()`, and adversarial pass #20 found **no test drove
# `main()` at all**: storing a rejected key, and storing before validating, both survived.


def _drive_main(
    monkeypatch: pytest.MonkeyPatch,
    entered: str,
    check: KeyCheck,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, list[str], list[tuple[str, str]], str]:
    """Run the panel with the network and the writer replaced, recording the order of both.

    `write_credential` is stubbed rather than pointed at a temporary file: its default
    `env_file` is bound at definition time, so a test that redirected `ENV_FILE` would still
    write to the real user config. The claim under test is the *decision and its order*, and
    that is what is recorded.
    """
    order: list[str] = []
    written: list[tuple[str, str]] = []

    def fake_validate(key: str, transport: object = None) -> KeyCheck:
        order.append("validate")
        return check

    def fake_write(name: str, value: str, *args: object, **kwargs: object) -> Path:
        order.append("write")
        written.append((name, value))
        return Path("/tmp/does-not-matter.env")

    monkeypatch.setattr("hawedit.credentials.validate_gemini_key", fake_validate)
    monkeypatch.setattr("hawedit.credentials.write_credential", fake_write)
    monkeypatch.setattr("hawedit.credentials.getpass", lambda _prompt: entered, raising=False)
    monkeypatch.setattr("getpass.getpass", lambda _prompt="": entered)
    monkeypatch.delenv(GEMINI_API_KEY, raising=False)
    monkeypatch.setattr("hawedit.credentials.read_credential", lambda *a, **k: None)

    code = credentials_main([])
    captured = capsys.readouterr()
    return code, order, written, captured.out + captured.err


def test_a_key_google_rejects_is_never_written(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A key that does not work is worse than no key: it turns a clear "not configured" into a
    failure inside the first client job — and the module says so in that branch's comment.

    Survived pass #20: deleting the `if not verified.valid` guard left the whole suite green.
    """
    code, order, written, output = _drive_main(
        monkeypatch, FAKE_KEY, KeyCheck(False, "the API rejected this key (HTTP 400)"), capsys
    )

    assert written == [], f"a rejected key was stored: {written}"
    assert order == ["validate"], order
    assert code == 1
    assert "nothing was written" in output


def test_the_key_is_validated_before_it_is_stored(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The ordering, not just the outcome. Also survived pass #20: moving the write above the
    validation left every test green, because the accepted path stores either way.

    The control is the assertion on `order` — asserting only that the key *was* stored is
    satisfied by a panel that stores first and validates afterwards, which is the defect.
    """
    code, order, written, _ = _drive_main(
        monkeypatch, FAKE_KEY, KeyCheck(True, "key works", (_PINNED_JUDGE,)), capsys
    )

    assert written == [(GEMINI_API_KEY, FAKE_KEY)]
    assert order == ["validate", "write"], f"stored before verifying: {order}"
    assert code == 0


def test_the_panel_prints_the_mask_and_never_the_key(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """ "never prints it" covers the success path too, where the key has just been accepted and
    is the most tempting thing to echo back as confirmation."""
    _, _, _, accepted = _drive_main(
        monkeypatch, FAKE_KEY, KeyCheck(True, "key works", (_PINNED_JUDGE,)), capsys
    )
    assert FAKE_KEY not in accepted
    assert mask(FAKE_KEY) in accepted

    _, _, _, rejected = _drive_main(monkeypatch, FAKE_KEY, KeyCheck(False, "no"), capsys)
    assert FAKE_KEY not in rejected


def test_the_panel_refuses_a_header_unsafe_key_without_printing_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    unsafe_key = "AIzaSy-THIS-MUST-NOT-PRINT\nInjected: value"

    monkeypatch.delenv(GEMINI_API_KEY, raising=False)
    monkeypatch.setattr("hawedit.credentials.read_credential", lambda *a, **k: None)
    monkeypatch.setattr("getpass.getpass", lambda _prompt="": unsafe_key)

    def no_network(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("the panel constructed a request for a header-unsafe key")

    def no_write(*_args: object, **_kwargs: object) -> Path:
        raise AssertionError("the panel stored a header-unsafe key")

    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    monkeypatch.setattr("hawedit.credentials.write_credential", no_write)

    code = credentials_main([])
    output = capsys.readouterr()
    combined = output.out + output.err
    assert code == 1
    assert "THIS-MUST-NOT-PRINT" not in combined
    assert "Injected" not in combined
    assert "Traceback" not in combined
    assert "nothing was written" in combined


def test_a_blank_entry_changes_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The control for both tests above: with nothing entered the panel must neither validate a
    new key nor write one, so "no key was stored" cannot be reached by a panel that simply never
    stores anything."""
    code, order, written, output = _drive_main(
        monkeypatch, "   ", KeyCheck(True, "key works"), capsys
    )

    assert written == []
    assert order == [], f"a blank entry reached the API or the writer: {order}"
    assert "no change" in output
    assert code == 1  # no working key is configured


# --- D-176: the status readout for a key that is already stored -----------------------------


def _drive_status(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    check: KeyCheck,
) -> tuple[int, str]:
    """Run the panel with a key **already stored**, and nothing entered.

    `_drive_main` above stubs the validator and the writer but not `credential_status`, so on a
    machine with no key configured `main` takes the `key is None` branch and the readout for a
    stored key never executes. That is the branch every user with a key hits on every run, and
    it is where the key is most tempting to print. D-176.
    """
    monkeypatch.setattr("hawedit.credentials.credential_status", lambda *a, **k: (FAKE_KEY, check))
    monkeypatch.setattr("getpass.getpass", lambda _prompt="": "")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    code = credentials_main(argv)
    return code, capsys.readouterr().out


def test_the_status_readout_for_a_stored_key_never_prints_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """M2.8's claim is that the panel "never prints it", and the readout was uncovered.

    Measured before this: replacing `mask(key)` with `key` on that line left the whole suite
    green, including `test_the_panel_prints_the_mask_and_never_the_key` — which drives the
    *entry* path, where the key comes from `getpass`, not the *status* path, where it comes from
    the store. A key printed there reaches terminal scrollback and any log capturing stdout.
    """
    _, out = _drive_status(monkeypatch, capsys, [], KeyCheck(True, "key works", (_PINNED_JUDGE,)))
    assert FAKE_KEY not in out, "the panel printed the stored key"
    # The control: without this the assertion above passes for a panel that prints nothing at
    # all, which would also satisfy "never prints it" and would be useless.
    assert mask(FAKE_KEY) in out, f"the readout did not identify the stored key: {out!r}"


def test_check_reports_a_stored_key_without_printing_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--check` is the scriptable path, so it is the one most likely to be piped into a log.

    Driven by no test at all before this. Both directions of the exit code are asserted, since
    "reports status" is only true if a bad key and a good key differ.
    """
    good, out = _drive_status(
        monkeypatch, capsys, ["--check"], KeyCheck(True, "key works", (_PINNED_JUDGE,))
    )
    assert FAKE_KEY not in out, "--check printed the stored key"
    assert mask(FAKE_KEY) in out, f"--check did not identify the stored key: {out!r}"
    assert good == 0

    bad, rejected = _drive_status(
        monkeypatch, capsys, ["--check"], KeyCheck(False, "the API rejected this key")
    )
    assert FAKE_KEY not in rejected, "--check printed a rejected key"
    assert bad == 1, "--check reported success for a key the API rejected"
