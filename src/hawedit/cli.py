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

import sys

__all__ = ["use_utf8_streams"]


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
