"""Every command-line entry point writes UTF-8, whatever the locale says.

Python takes the standard streams' encoding from the locale, and on Windows that is the ANSI
code page — cp1252 on hawapc01, §6's own machine, while this product's output is Sorani. The
failure is invisible from a console, where Python writes UTF-16 to the Windows terminal; it
appears when output is redirected, which is when someone is keeping it. Measured on the real
38-minute run, `--json` exited 1 having written **zero bytes**: the whole report of a completed
run, destroyed by the act of capturing it (D-115).

These tests drive the **declared** entry points — read out of `pyproject.toml`, so a sixth one
added without the fix fails here rather than in a client's terminal — under `PYTHONIOENCODING`
set to a non-UTF-8 codec. That is what makes them discriminate on a Linux runner, where the
locale is UTF-8 already and every one of them would otherwise pass without the fix.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Real Sorani, not a lone symbol: every character here is outside cp1252, which is the class
# that raises rather than the class that silently writes the wrong byte.
SENTINEL = "ڕۆژنامەوانی کوردی"

# `main(['--help'])` exits through argparse, so the driver swallows that and then writes the
# sentinel through whatever encoding `main` left on stdout. Both halves matter: the help text
# itself carries `§` in most of these, and the sentinel covers the ones whose help is ASCII.
DRIVER = (
    "import importlib, sys\n"
    "module = importlib.import_module(sys.argv[1])\n"
    "try:\n"
    "    module.main(['--help'])\n"
    "except SystemExit:\n"
    "    pass\n"
    "sys.stdout.write(sys.argv[2] + '\\n')\n"
    "sys.stderr.write(sys.argv[2] + '\\n')\n"
)


def console_script_modules() -> list[str]:
    """The module of every `[project.scripts]` entry, e.g. `hawedit.pipeline`."""
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = config["project"]["scripts"]
    assert scripts, "pyproject.toml declares no console scripts"
    return sorted({target.split(":")[0] for target in scripts.values()})


def run_entry_point(module: str, encoding: str) -> subprocess.CompletedProcess[bytes]:
    """`main(['--help'])` then a Sorani sentinel, with the locale's codec forced to `encoding`.

    The environment is inherited and only `PYTHONIOENCODING` overridden: `credentials.main`
    resolves the user's config directory, and an emptied environment fails there for a reason
    that has nothing to do with what this measures.
    """
    return subprocess.run(
        [sys.executable, "-c", DRIVER, module, SENTINEL],
        capture_output=True,
        cwd=ROOT,
        env={**os.environ, "PYTHONIOENCODING": encoding},
    )


@pytest.mark.parametrize("module", console_script_modules())
def test_an_entry_point_writes_utf8_under_a_cp1252_locale(module: str) -> None:
    """The artifact is the bytes on the redirected stream, not the call site.

    Asserting that each `main` *calls* `use_utf8_streams` would pass for a call placed after
    the first write, and would say nothing about an entry point added later. This runs the
    real entry point and decodes what came out.
    """
    done = run_entry_point(module, "cp1252")
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    assert SENTINEL in done.stdout.decode("utf-8")
    # stderr defaults to `backslashreplace`, so without the fix it does not raise — it mangles
    # `✗` into the literal `\u2717`. Nothing here may be escaped.
    assert SENTINEL in done.stderr.decode("utf-8")
    assert "\\u" not in done.stderr.decode("utf-8")


@pytest.mark.parametrize("module", console_script_modules())
def test_the_bytes_are_utf8_and_not_the_locales_codec(module: str) -> None:
    """The control for the other half of the defect: characters *inside* cp1252 do not raise.

    A run with no transcript wrote `0xB7` for `·` and `0xA7` for `§` and reported success, so a
    passing exit code proves nothing on its own — the bytes have to be checked.
    """
    stdout = run_entry_point(module, "cp1252").stdout
    assert SENTINEL.encode("utf-8") in stdout, stdout[-120:]
    # cp1252 has no encoding for these at all; UTF-8 is the only thing that produces them.
    stdout.decode("utf-8")


def test_the_helper_leaves_a_substituted_stream_alone() -> None:
    """A harness's replacement stream has no `reconfigure`, and that is not an error."""
    from hawedit.cli import use_utf8_streams

    class Substituted:
        pass

    original_out, original_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = Substituted(), Substituted()
    try:
        use_utf8_streams()
    finally:
        sys.stdout, sys.stderr = original_out, original_err
