"""Where secrets live, and the panel that puts them there.

    python -m hawedit.credentials

§3 Stage 4 routes through `gemini-2.5-pro` and needs an API key. A key is the one kind of
configuration that is actively dangerous to get slightly wrong, so this module is written
around three refusals rather than around convenience:

**It refuses to write a key to a file git would track.** Before writing anything it asks git
whether the target is ignored, and stops if it is not. `AGENTS.md`'s hard boundary — "never
commit secrets" — is a rule someone has to remember; this is the same rule as a check. A key
in a commit is a key that has to be revoked, and the commit outlives the revocation.

**It refuses to store a key it has not verified.** Google's endpoint answers a bad key with a
clear 400, so there is no reason to accept one on trust and discover it inside a client job.
Validation is a live call, not a regex: a well-formed key that has been revoked looks exactly
like a working one.

**It never prints the key.** Not on success, not in an exception, not in the status line. The
panel shows the last four characters so you can tell two keys apart, and nothing else — an
error message containing a credential is how secrets reach log aggregators.

Reading is layered so CI and a laptop can differ without either being a special case: the
process environment wins, then the owner-only user config file. Nothing here reads a key from
a command-line argument, because arguments are visible in `ps` to every user on the machine.
"""

from __future__ import annotations

import errno
import getpass
import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from hawedit.cli import program_name, use_utf8_streams

__all__ = [
    "ENV_FILE",
    "GEMINI_API_KEY",
    "CredentialError",
    "KeyCheck",
    "credential_status",
    "main",
    "mask",
    "read_credential",
    "restrict_to_owner",
    "validate_gemini_key",
    "write_credential",
]

GEMINI_API_KEY: Final = "GEMINI_API_KEY"
REPO_ROOT: Final = Path(__file__).resolve().parents[2]


def _user_config_file() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "hawedit" / "credentials.env"


ENV_FILE: Final = _user_config_file()

_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")

# `O_NOFOLLOW` is POSIX-only, and hawapc01 — the box §6 names, and the one that will hold the
# real key — is Windows. `getattr(os, "O_NOFOLLOW", 0)` alone would make the flag vanish
# there: the code still reads as protected and the protection is gone, which is the worst of
# the three states. So where the kernel cannot give the guarantee, `write_credential`
# reconstructs it in two halves — see the comment at its `os.open` call.
_O_NOFOLLOW: Final = getattr(os, "O_NOFOLLOW", 0)


def restrict_to_owner(path: Path) -> None:
    """Narrow `path` so no other local account can read it.

    On POSIX that is `chmod 0600`, and the `0o600` handed to `os.open` already did most of
    it. On Windows every mode bit but read-only is ignored: measured on hawapc01, the file
    lands at `0o666` and inherits whatever the directory grants, so the mode argument is
    decoration and `chmod` corrects nothing. hawapc01 is Windows and is the machine that will
    hold the real key, so the guarantee is rebuilt with the tool Windows has — `icacls`
    dropping inheritance and granting the owner alone — rather than left as a POSIX-only
    promise the docstring still made.

    Raises:
        CredentialError: the file could not be narrowed. A key sitting at inherited
            permissions is not something to warn about and continue past.
    """
    if os.name != "nt":
        path.chmod(0o600)
        return

    user = getpass.getuser()
    result = subprocess.run(
        ["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:(R,W)"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise CredentialError(
            f"could not restrict {path} to {user} alone (icacls exited "
            f"{result.returncode}): {result.stderr.strip() or result.stdout.strip()}. "
            f"Refusing to leave a credential at inherited permissions."
        )


class CredentialError(RuntimeError):
    """Raised when a credential cannot be stored or verified safely."""


def mask(secret: str) -> str:
    """A credential rendered so two keys can be told apart and neither can be used."""
    if not secret:
        return "(unset)"
    return f"…{secret[-4:]}" if len(secret) > 4 else "…"


def _parse_env(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = _LINE.match(line)
        if match:
            value = match.group(2)
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values[match.group(1)] = value
    return values


def read_credential(name: str = GEMINI_API_KEY, env_file: Path = ENV_FILE) -> str | None:
    """The credential, from the environment first and `.env` second.

    Environment wins so CI can inject a secret without a file, and a shell export can override
    a stale `.env` without editing it. `None` means genuinely absent — never an empty string,
    which would read as "configured, to nothing".
    """
    from_env = os.environ.get(name)
    if from_env and from_env.strip():
        return from_env.strip()
    if env_file.exists():
        value = _parse_env(env_file.read_text(encoding="utf-8")).get(name, "").strip()
        return value or None
    return None


def assert_ignored_by_git(path: Path) -> None:
    """Refuse to treat a git-tracked path as somewhere secrets may go.

    Raises:
        CredentialError: git does not ignore `path`, or git cannot say.
    """
    try:
        result = subprocess.run(
            ["git", "check-ignore", "-q", str(path)],
            cwd=path.parent if path.parent.exists() else REPO_ROOT,
            capture_output=True,
            check=False,
        )
    except OSError as exc:  # pragma: no cover - git missing is not a normal state here
        raise CredentialError(f"cannot ask git whether {path} is ignored: {exc}") from exc
    if result.returncode != 0:
        raise CredentialError(
            f"{path} is not ignored by git. Storing a credential there risks committing it, "
            f"and a key in a commit outlives its revocation. Add it to .gitignore first."
        )


def write_credential(
    name: str,
    value: str,
    env_file: Path = ENV_FILE,
    check_ignored: bool | None = None,
) -> Path:
    """Store one credential in `.env`, leaving any others in place.

    The file is narrowed to its owner on every write, because an existing `.env` may predate
    this function — `chmod 0600` on POSIX, an `icacls` ACL rewrite on Windows, where the mode
    argument carries nothing but the read-only bit. See `restrict_to_owner`.

    Raises:
        CredentialError: the value is empty, or the file is not git-ignored.
    """
    if not value.strip():
        raise CredentialError(f"{name} is empty — that is not a credential, it is a typo")
    # The default lives outside the checkout and cannot be committed. Any caller-selected
    # path keeps the original fail-closed Git check unless it opts out explicitly (tests use
    # that only for isolated temporary files).
    if check_ignored is None:
        check_ignored = env_file != ENV_FILE
    if check_ignored:
        assert_ignored_by_git(env_file)

    existing = _parse_env(env_file.read_text(encoding="utf-8")) if env_file.exists() else {}
    existing[name] = value.strip()

    env_file.parent.mkdir(parents=True, exist_ok=True)
    body = "# hawedit credentials. Git-ignored. Never commit this file.\n" + "".join(
        f"{key}={val}\n" for key, val in sorted(existing.items())
    )

    # Two defects the independent review found here, fixed by one syscall.
    #
    # O_NOFOLLOW: `git check-ignore` answers about the *pathname*, never the symlink target, so
    # `.env -> README.md` passed the ignore check and `Path.write_text` followed the link and
    # put the plaintext key into a tracked file — one `git add -A` from being committed
    # forever. `TranscriptStore.write_raw` already used O_EXCL for exactly this reason; the one
    # module actually handling a secret did not.
    #
    # mode=0o600 at creation: `write_text` then `chmod` created the file at the process umask
    # (0644 typically) and only narrowed it afterwards, leaving a window in which any other
    # local user — or a backup, indexer or AV scan — could read the key. A file cannot be
    # created wider than the mode passed here, so there is no window to lose.
    # Where the kernel has no O_NOFOLLOW (Windows), the guarantee is rebuilt from two halves,
    # and both are needed. Refusing a symlink before the open is the check; proving after the
    # open that the handle is the *same file* that was checked is what closes the TOCTOU window
    # the pre-check opens. A window here is the original symlink bug back again, just narrower.
    checked: os.stat_result | None = None
    if not _O_NOFOLLOW:
        if env_file.is_symlink():
            raise CredentialError(
                f"{env_file} is a symbolic link. git reports whether the *name* is ignored, "
                f"not where the link points, so writing through it could put the key into a "
                f"tracked file. Remove the link and try again."
            )
        try:
            checked = os.lstat(env_file)
        except FileNotFoundError:
            checked = None  # nothing to race against; O_CREAT is about to make it

    try:
        # Deliberately NO O_TRUNC. It empties the file at open time — before any check could
        # run — so a hardlink guard placed after the open would fire only once the tracked file
        # it protects had already been destroyed. Truncation happens below, after identity.
        handle = os.open(env_file, os.O_WRONLY | os.O_CREAT | _O_NOFOLLOW, 0o600)
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.EMLINK):
            raise CredentialError(
                f"{env_file} is a symbolic link. git reports whether the *name* is ignored, "
                f"not where the link points, so writing through it could put the key into a "
                f"tracked file. Remove the link and try again."
            ) from exc
        raise CredentialError(f"cannot write {env_file}: {exc}") from exc

    # Second half of the O_NOFOLLOW reconstruction: the file that was opened must be the file
    # that was checked. Windows reports real, comparable st_dev/st_ino from both fstat and
    # lstat, so this is an identity test, not an approximation of one.
    if checked is not None:
        opened = os.fstat(handle)
        if (opened.st_dev, opened.st_ino) != (checked.st_dev, checked.st_ino):
            os.close(handle)
            raise CredentialError(
                f"{env_file} was replaced between the symlink check and the open. Refusing to "
                f"write a key into a file whose identity changed underneath the check."
            )

    # O_NOFOLLOW rejects a *symlinked* .env. It says nothing about a hardlink, which is an
    # ordinary regular file sharing an inode with — say — a tracked file. O_TRUNC would then
    # rewrite that file's content with the key. The round-1 fix validated the path's NAME; this
    # validates the file's IDENTITY, which is what the symlink bug was really about. Found by
    # the second independent review, in the code written to fix the first one.
    links = os.fstat(handle).st_nlink
    if links > 1:
        os.close(handle)
        raise CredentialError(
            f"{env_file} has {links} hard links — writing to it would also rewrite whatever "
            f"else shares that inode, which may be a tracked file. Remove the extra link and "
            f"try again."
        )

    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        os.ftruncate(stream.fileno(), 0)  # safe now: this inode is ours alone
        stream.write(body)
    # An existing file keeps its old mode through O_CREAT, so narrow it explicitly too.
    restrict_to_owner(env_file)
    return env_file


@dataclass(frozen=True, slots=True)
class KeyCheck:
    """What a live validation call concluded. `models` is empty unless the key worked."""

    valid: bool
    detail: str
    models: tuple[str, ...] = ()


Transport = Callable[[str, Mapping[str, str]], tuple[int, str]]


def _https_get(url: str, headers: Mapping[str, str] | None = None) -> tuple[int, str]:
    import urllib.error
    import urllib.request

    request = urllib.request.Request(url, headers=dict(headers or {}))
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except OSError as exc:
        return 0, str(exc)


def validate_gemini_key(key: str, transport: Transport = _https_get) -> KeyCheck:
    """Ask Google whether this key works, rather than whether it looks like a key.

    A revoked key and a working key are the same string shape. The only check worth having is
    the one the service performs, and it is cheap: listing models bills nothing.

    Authentication uses Google's API-key header so the credential cannot leak through URL
    logging in clients, proxies, exception traces, or access logs.
    """
    import json

    status, body = transport(
        "https://generativelanguage.googleapis.com/v1beta/models", {"x-goog-api-key": key}
    )
    if status == 0:
        return KeyCheck(False, f"could not reach the Gemini API: {body}")
    if status != 200:
        try:
            message = json.loads(body)["error"]["message"]
        except (ValueError, KeyError, TypeError):
            message = body[:200]
        return KeyCheck(False, f"the API rejected this key (HTTP {status}): {message}")

    try:
        names = tuple(
            str(model["name"]).removeprefix("models/") for model in json.loads(body)["models"]
        )
    except (ValueError, KeyError, TypeError) as exc:
        return KeyCheck(False, f"unreadable response from the API: {exc}")
    return KeyCheck(True, f"key accepted; {len(names)} model(s) visible", names)


def credential_status(
    name: str = GEMINI_API_KEY,
    env_file: Path = ENV_FILE,
    transport: Transport = _https_get,
) -> tuple[str | None, KeyCheck | None]:
    """The stored credential (masked by the caller) and what a live check says about it."""
    key = read_credential(name, env_file)
    if key is None:
        return None, None
    return key, validate_gemini_key(key, transport)


# --- the panel ----------------------------------------------------------------------------

_PINNED_JUDGE = "gemini-2.5-pro"


def main(argv: list[str] | None = None) -> int:
    """Interactive panel: show the current key, take a new one, verify it, store it.

    Input is read with `getpass`, so the key is never echoed to the terminal and never lands
    in shell history. There is deliberately no `--key` flag: command-line arguments are
    visible in `ps` to every user on the machine.
    """
    use_utf8_streams()
    import argparse
    from getpass import getpass

    parser = argparse.ArgumentParser(
        prog=program_name("hawedit.credentials"),
        description="Store and verify the Gemini API key §3 Stage 4 routes through.",
    )
    parser.add_argument("--check", action="store_true", help="report status and exit")
    args = parser.parse_args(argv)

    print("hawedit credentials — §3 Stage 4 judge access")
    # "0600" was printed unconditionally, and on Windows it is not what the file gets — the mode
    # argument carries only the read-only bit there and `restrict_to_owner` rewrites the ACL
    # instead. A status line that names the wrong mechanism is a small lie in the one panel whose
    # job is telling you where your secret is and how it is protected.
    protection = "chmod 0600" if os.name != "nt" else "ACL: owner only"
    print(f"store: {ENV_FILE}  (user config, {protection})\n")

    key, check = credential_status()
    if key is None:
        print(f"{GEMINI_API_KEY}: not set")
    else:
        source = "environment" if os.environ.get(GEMINI_API_KEY) else "user config"
        print(f"{GEMINI_API_KEY}: {mask(key)}  (from {source})")
        if check is not None:
            print(f"  {'✓' if check.valid else '✗'} {check.detail}")
            if check.valid:
                pinned = _PINNED_JUDGE in check.models
                state = "available" if pinned else "NOT visible to this key — §7 pins it"
                print(f"  {'✓' if pinned else '✗'} {_PINNED_JUDGE} {state}")

    if args.check:
        return 0 if (check is not None and check.valid) else 1

    print(
        "\nPaste a key from https://aistudio.google.com/apikey — input is hidden, and blank "
        "keeps the current one."
    )
    try:
        entered = getpass("GEMINI_API_KEY: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nno change")
        return 1
    if not entered:
        print("no change")
        return 0 if (check is not None and check.valid) else 1

    print("verifying with Google…")
    verified = validate_gemini_key(entered)
    if not verified.valid:
        # Not stored. A key that does not work is worse than no key: it turns a clear "not
        # configured" into a failure inside the first client job.
        print(f"✗ {verified.detail}\nnothing was written.", file=sys.stderr)
        return 1

    try:
        path = write_credential(GEMINI_API_KEY, entered)
    except CredentialError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 2

    print(f"✓ {verified.detail}")
    print(f"✓ stored {mask(entered)} in {path}")
    if _PINNED_JUDGE not in verified.models:
        print(
            f"⚠ {_PINNED_JUDGE} is not visible to this key. §7 pins it and the registry will "
            f"refuse anything else — check the key's project has the model enabled."
        )
    print(
        "\n§3 Stage 4 can now route. Still required before the first client job: the §3 "
        "governance answer on zero-data-retention (BLOCKED.md #3) — full-transcript discovery "
        "sends 100% of every transcript to Google."
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    raise SystemExit(main())
