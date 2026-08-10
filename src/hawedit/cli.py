"""What every HawEdit command-line entry point does before it writes anything.

Python takes the standard streams' encoding from the locale. On Windows that is the ANSI code
page — **cp1252** on hawapc01, which is §6's own machine — and this product's output is Sorani.
None of that shows on a console, where Python writes UTF-16 to the Windows terminal directly. It
appears the moment output is redirected, which is the moment someone is keeping it.

Measured on hawapc01 with stdout redirected to a file (D-115):

* Every character **outside** cp1252 raises `UnicodeEncodeError`, and that is all Kurdish plus
  `✓ ✗ →`. `--json` after a 38-minute Stage 0 and ten minutes of GPU work exited 1 having
  written **zero bytes**: the whole report of a completed run, destroyed by capturing it.
* Every character **inside** cp1252 is written as a cp1252 byte, so the captured file is not
  UTF-8 at all. A run with no transcript wrote 9 high bytes — `0xB7` for `·`, `0xA7` for `§` —
  and fails to decode as UTF-8 at the first one. No error, wrong bytes.
* stderr defaults to `errors="backslashreplace"`, so it does not raise; it mangles. `✗` reaches
  the operator as the literal seven characters `\\u2717`.

One function, called first in every `main()`, and a test that drives each declared entry point
under a non-UTF-8 locale rather than checking that the call is present.
"""

from __future__ import annotations

import contextlib
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import TextIO

__all__ = ["machine_readable_stdout", "program_name", "use_utf8_streams"]


def program_name(module: str) -> str:
    """What `--help` should call this program, from how it was actually started.

    Every entry point here has **two** ways in — an installed console script and `python -m` —
    and a fixed `prog=` is wrong in one of them. Measured across all five on 2026-08-10, from
    the real wheel and from `-m`:

    ```
    console script            python -m
      hawedit.pipeline  ✗       hawedit.pipeline
      hawedit-asr-bench         bench.py  ✗
      hawedit-asr-setup         wsl_setup.py  ✗
      hawedit.credentials  ✗    hawedit.credentials
      hawedit-editorial-bench   editorial_bench.py  ✗
    ```

    Two named a module path the shell cannot run; the other three fell back to argparse's
    default, `basename(sys.argv[0])`, which under `-m` is a bare source filename — also not a
    command. So each of the five printed something untypeable in one mode. D-142.

    The rule needs no guessing. Python sets `sys.argv[0]` to the module's *file* under `-m` and
    to the script itself otherwise, so a `.py` suffix distinguishes them, and each branch returns
    something a reader can paste:

    * `python -m hawedit.pipeline` — the form this repo's own documentation uses;
    * `hawedit` — the console script's own name, without the `.exe` Windows adds.
    """
    argv0 = Path(sys.argv[0] or "")
    if argv0.suffix.lower() == ".py":
        return f"python -m {module}"
    return argv0.stem or f"python -m {module}"


def use_utf8_streams() -> None:
    """Pin stdout and stderr to UTF-8. The first statement of every `main()`.

    Only the encoding is changed. The error handlers are left as the interpreter set them —
    UTF-8 encodes every character this product produces, so `surrogateescape` and
    `backslashreplace` stop being reachable for text and remain in place for the one thing they
    are for, a path that came out of the filesystem with lone surrogates in it.

    A stream a test harness has substituted has no `reconfigure`, and that is not an error: it
    is already whatever the harness decided, and the streams this exists for are the real
    interpreter's.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


@contextlib.contextmanager
def machine_readable_stdout() -> Iterator[TextIO]:
    """Hold stdout for one document, and send everything else to stderr.

    A command that promises JSON on stdout shares that stream with every library it loads, and
    a library that prints is not a hypothetical. `transformers/utils/auto_docstring.py:1602` is
    a bare `print` — not a logger, so no verbosity setting reaches it — and loading VideoChat3's
    remote code fires it twice. Measured on the real 38-minute run: **580 bytes** of
    `🚨 \\`image_grid_thw\\` is part of …` ahead of the report, and `json.loads` on the captured
    file raises at character 0 (D-119).

    Yields the real stdout, so the caller writes its one document there while the pipeline's own
    output — and anything a dependency prints — lands on stderr, which is where a human reads it
    and where no parser is looking.
    """
    real = sys.stdout
    with contextlib.redirect_stdout(sys.stderr):
        yield real
