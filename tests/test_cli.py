"""Every command-line entry point writes UTF-8, whatever the locale says.

Python takes the standard streams' encoding from the locale, and on Windows that is the ANSI
code page — cp1252 on hawapc01, §6's own machine, while this product's output is Sorani. The
failure is invisible from a console, where Python writes UTF-16 to the Windows terminal; it
appears when output is redirected, which is when someone is keeping it. Measured on the real
38-minute run, `--json` exited 1 having written **zero bytes**: the whole report of a completed
run, destroyed by the act of capturing it (D-152).

These tests drive the **declared** entry points — read out of `pyproject.toml`, so a sixth one
added without the fix fails here rather than in a client's terminal — under `PYTHONIOENCODING`
set to a non-UTF-8 codec. That is what makes them discriminate on a Linux runner, where the
locale is UTF-8 already and every one of them would otherwise pass without the fix.
"""

from __future__ import annotations

import json
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


def _console_script_for(module: str) -> str:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    matches = [
        str(name)
        for name, target in config["project"]["scripts"].items()
        if str(target).split(":", 1)[0] == module
    ]
    assert len(matches) == 1, f"expected one console script for {module}, got {matches}"
    return matches[0]


def _usage_line(module: str, argv0: str) -> str:
    import importlib
    import io
    from contextlib import redirect_stdout

    imported = importlib.import_module(module)
    captured = io.StringIO()
    saved = sys.argv
    sys.argv = [argv0, "--help"]
    try:
        with redirect_stdout(captured), pytest.raises(SystemExit) as exit_info:
            imported.main(["--help"])
    finally:
        sys.argv = saved
    assert exit_info.value.code == 0
    first = captured.getvalue().splitlines()[0]
    assert first.startswith("usage: "), first
    return first.removeprefix("usage: ")


@pytest.mark.parametrize("module", console_script_modules())
@pytest.mark.parametrize("suffix", ("", ".exe"), ids=("posix-launcher", "windows-launcher"))
def test_console_script_help_names_the_command_a_user_ran(module: str, suffix: str) -> None:
    script = _console_script_for(module)
    argv0 = str(Path("opt") / "hawedit-venv" / "bin" / f"{script}{suffix}")

    assert _usage_line(module, argv0).split()[0] == script


@pytest.mark.parametrize("module", console_script_modules())
def test_python_dash_m_help_names_the_pasteable_module_command(module: str) -> None:
    argv0 = str(ROOT / "src" / module.replace(".", "/")) + ".py"

    assert _usage_line(module, argv0).startswith(f"python -m {module} ")


def test_program_name_falls_back_to_the_module_when_argv0_is_empty() -> None:
    from hawedit.cli import program_name

    saved = sys.argv
    sys.argv = [""]
    try:
        assert program_name("hawedit.pipeline") == "python -m hawedit.pipeline"
    finally:
        sys.argv = saved


# =========================================================================================
# D-119 — a document on stdout, and a library that prints to it
# =========================================================================================

# `transformers/utils/auto_docstring.py:1602` is a bare `print`, not a logger, so no verbosity
# setting reaches it. Loading VideoChat3's remote code fires it twice, and on the real 38-minute
# run that put 580 bytes of `🚨 …` ahead of the report: `json.loads` on the captured file raised
# at character 0. The driver below stands in for that with one line, because what is being
# checked is who owns the stream, not which dependency was noisy.
NOISY_DRIVER = (
    "import sys\n"
    "from hawedit import pipeline\n"
    "real = pipeline.run_pipeline\n"
    "def noisy(*args, **kwargs):\n"
    "    print('\\U0001f6a8 a dependency wrote to stdout')\n"
    "    return real(*args, **kwargs)\n"
    "pipeline.run_pipeline = noisy\n"
    "raise SystemExit(pipeline.main(sys.argv[1:]))\n"
)

FIXTURE = ROOT / "tests" / "fixtures" / "kurdish-speech-3cuts.mp4"


def run_cli(tmp_path: Path, *flags: str) -> subprocess.CompletedProcess[bytes]:
    """The real `main`, in a subprocess, with a dependency printing to stdout mid-run."""
    return subprocess.run(
        [sys.executable, "-c", NOISY_DRIVER, str(FIXTURE), "--work-dir", str(tmp_path), *flags],
        capture_output=True,
        cwd=ROOT,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )


needs_fixture = pytest.mark.skipif(not FIXTURE.exists(), reason="no media fixture")


@needs_fixture
def test_the_json_report_is_the_only_thing_on_stdout(tmp_path: Path) -> None:
    """The artifact is what a caller redirects to a file, and it must parse.

    Asserting the report *contains* the right keys would pass with 580 bytes of foreign text in
    front of it, which is exactly what shipped.
    """
    done = run_cli(tmp_path / "work", "--json")
    payload = json.loads(done.stdout.decode("utf-8"))
    assert payload["media_id"]
    assert "\U0001f6a8" not in done.stdout.decode("utf-8")
    # The noise is not lost — it goes where a human reads it and no parser looks.
    assert "\U0001f6a8" in done.stderr.decode("utf-8")


@needs_fixture
def test_the_human_report_still_goes_to_stdout(tmp_path: Path) -> None:
    """The control. Redirecting stdout unconditionally would silence the readable report, which
    is the mode anyone runs by hand."""
    done = run_cli(tmp_path / "work")
    assert "media   kurdish-speech-3cuts" in done.stdout.decode("utf-8")


@needs_fixture
def test_the_exit_code_still_reports_an_incomplete_run(tmp_path: Path) -> None:
    """The second control: holding stdout must not swallow the return value. A bare run is
    incomplete — Stage 1 has no producer — and automation reads that as 1, not 0."""
    assert run_cli(tmp_path / "work", "--json").returncode == 1


def test_no_document_is_printed_to_a_shared_stdout() -> None:
    """Every machine-readable document in `src/hawedit` names the stream it goes to.

    The pipeline's own channel is checked on the artifact above. `editorial_bench`'s cannot be:
    reaching its document needs a valid manifest of real reviewed comparisons against real media
    (`BLOCKED.md` #1, M7.2), so a source-level invariant stands in — and it covers the site added
    next year as well as the two that exist, which an artifact test for one command would not.
    """
    offenders: list[str] = []
    for module in sorted((ROOT / "src" / "hawedit").glob("*.py")):
        for number, line in enumerate(module.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if not stripped.startswith("print("):
                continue
            if "json.dumps" not in stripped and "payload" not in stripped:
                continue
            if "file=" in stripped:
                continue
            offenders.append(f"{module.name}:{number}: {stripped}")
    assert not offenders, (
        "a JSON document printed to the shared stdout: "
        + "; ".join(offenders)
        + ". Hold the stream with `machine_readable_stdout()` and pass `file=`, or a library "
        "that prints — `transformers/utils/auto_docstring.py` does — corrupts the document."
    )
