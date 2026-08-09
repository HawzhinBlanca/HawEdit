"""Nothing this project downloads and executes is fetched from a moving target.

`fetch-ffmpeg.sh` unzips an archive, marks it executable and runs it, and its URL used to end
`/main/v8.0/linux.zip` — a branch path, so the bytes behind it could change under a name that
looked fixed. `README.md` and the CI step both called it "pinned"; `AUDIT_REPORT.md` correctly
called it unpinned, and the audit was right (D-121).

The 142 MB download is not repeated here. What is checked is the part a test can hold: the URL
carries a commit rather than a branch, a digest is recorded and compared *before* anything is
unzipped or executed, and `verify-sha256.sh` gives both answers on three bytes.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FETCH = ROOT / "scripts" / "fetch-ffmpeg.sh"
VERIFY = ROOT / "scripts" / "verify-sha256.sh"
BASH = shutil.which("bash")

needs_bash = pytest.mark.skipif(BASH is None, reason="needs bash")


def run_verify(path: Path, expected: str) -> subprocess.CompletedProcess[str]:
    assert BASH is not None
    return subprocess.run(
        # The resolved bash, and POSIX paths: `subprocess` finds WSL's bash.exe on Windows, which
        # cannot open a `C:/…` path at all, and bash eats the backslashes (D-120).
        [BASH, VERIFY.as_posix(), path.as_posix(), expected],
        capture_output=True,
        text=True,
        errors="replace",
        cwd=ROOT,
    )


def test_the_ffmpeg_archive_is_fetched_from_a_commit_not_a_branch() -> None:
    """A branch path is a mutable name for bytes this script executes."""
    body = FETCH.read_text(encoding="utf-8")
    url = re.search(r'^\s*url="(?P<url>https://media\.githubusercontent\.com[^"]+)"', body, re.M)
    assert url is not None, "no ffmpeg archive URL found in fetch-ffmpeg.sh"
    assert "${ref}" in url.group("url"), url.group("url")
    ref = re.search(r'^\s*ref="(?P<ref>[0-9a-f]{40})"', body, re.M)
    assert ref is not None, "the ref is not a full 40-character commit SHA"


def test_the_archive_digest_is_recorded_and_checked_before_anything_runs() -> None:
    """Order is the whole point: a digest compared after `chmod +x` guards nothing.

    Asserting only that a digest exists would pass for a check placed after the unzip, which is
    where a well-meaning refactor puts it.
    """
    lines = FETCH.read_text(encoding="utf-8").splitlines()

    def line_of(needle: str) -> int:
        """The first *code* line containing `needle`.

        Comments are skipped because the script explains this ordering in prose right above it
        — "Before unzip, before chmod +x" — and the first version of this test matched that
        comment and reported the order backwards.
        """
        return next(
            i for i, line in enumerate(lines) if needle in line and not line.strip().startswith("#")
        )

    digest = re.search(r'^\s*sha256="(?P<d>[0-9a-f]{64})"', "\n".join(lines), re.M)
    assert digest is not None, "no lowercase 64-hex archive digest recorded"
    verified = line_of("verify-sha256.sh")
    assert verified < line_of("unzip -oq"), "the digest is checked after the archive is unpacked"
    assert verified < line_of("chmod +x"), "the digest is checked after the file is made runnable"
    assert verified > line_of("curl -sSL"), "the digest is checked before the download finishes"


def test_the_download_fails_loudly_on_an_http_error() -> None:
    """Without `--fail`, curl writes the error page into linux.zip and the failure arrives as a
    confusing unzip error about a file that was never an archive.

    Read off the curl invocation, not the file: the script explains `--fail` in a comment, and the
    first version of this matched that comment — the mutation audit reported dropping the flag as
    SURVIVED, which is exactly what a test that greps prose is worth.
    """
    curls = [
        line
        for line in FETCH.read_text(encoding="utf-8").splitlines()
        if "curl " in line and not line.strip().startswith("#")
    ]
    assert curls, "no curl invocation found in fetch-ffmpeg.sh"
    for line in curls:
        assert "--fail" in line, line.strip()


@needs_bash
def test_a_matching_digest_is_accepted(tmp_path: Path) -> None:
    """The control. A guard that refuses everything would satisfy the test below and stop every
    fetch, including the honest one."""
    probe = tmp_path / "probe.bin"
    probe.write_bytes(b"abc")
    done = run_verify(probe, hashlib.sha256(b"abc").hexdigest())
    assert done.returncode == 0, done.stdout + done.stderr
    assert "sha256 OK" in done.stdout


@needs_bash
def test_a_mismatching_digest_is_refused_and_says_both_values(tmp_path: Path) -> None:
    probe = tmp_path / "probe.bin"
    probe.write_bytes(b"abc")
    done = run_verify(probe, "0" * 64)
    assert done.returncode == 1, done.stdout + done.stderr
    assert "does not match the recorded digest" in done.stderr
    assert hashlib.sha256(b"abc").hexdigest() in done.stderr, "the actual digest is not reported"


@needs_bash
def test_an_upper_case_or_short_digest_is_refused_rather_than_compared(tmp_path: Path) -> None:
    """The second control: an upper-case digest compares unequal against every real file, so a
    typo would read as tampering forever and the recorded value would look like the problem."""
    probe = tmp_path / "probe.bin"
    probe.write_bytes(b"abc")
    for bad in (hashlib.sha256(b"abc").hexdigest().upper(), "abc123", ""):
        done = run_verify(probe, bad)
        assert done.returncode == 2, f"{bad!r}: {done.stdout + done.stderr}"
        assert "not a lowercase hex SHA-256" in done.stderr


@needs_bash
def test_a_missing_file_is_refused_rather_than_reported_verified(tmp_path: Path) -> None:
    done = run_verify(tmp_path / "absent.bin", "0" * 64)
    assert done.returncode == 2
    assert "does not exist" in done.stderr
