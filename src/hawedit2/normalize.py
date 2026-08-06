"""§4.1 Sorani normalization — mandatory, and the first of the three things §0 says decide
whether this system works at all.

Kurdish Arabic script has multiple valid Unicode encodings for the same visible grapheme.
Unnormalized, two identical-looking sentences are different strings: BM25 scores them as
unrelated, embeddings place them apart, and nothing in the failure is visible on screen.

**Direction of travel is one-way.** `transcript.raw.json` is canonical and ships to the
client; `transcript.norm.json` is derived from it. Indexes, embeddings and model inputs read
the normalized artifact (Kurdish invariant #3) — never the raw one, and never the reverse.
This module only ever returns a new string; it has no in-place mode by design.

Tooling is KLPT's `preprocess` module, per §4.1. What it does and does not cover was
measured, not assumed — see `DECISIONS.md` D-003. The one gap (conjunctive `و` separation)
is asserted in `tests/test_normalize.py` so it cannot be silently carried forward.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Final

from klpt.preprocess import Preprocess

__all__ = ["NUMERAL", "SCRIPT", "SORANI", "normalize_sorani"]

SORANI: Final = "Sorani"
SCRIPT: Final = "Arabic"

# Numerals must land in ONE system or the index splits on digits the way it would split on
# ه/ە. §4.1 lists Farsi, Eastern Arabic and Western forms as all occurring in real text.
# Latin is the target because it is also what timestamps, IDs and the §5 JSON contract use,
# so a normalized transcript carries no second numeral convention.
NUMERAL: Final = "Latin"


@lru_cache(maxsize=1)
def _preprocessor() -> Preprocess:
    """KLPT's Preprocess loads rule tables; build it once per process."""
    return Preprocess(SORANI, SCRIPT, numeral=NUMERAL)


def normalize_sorani(text: str) -> str:
    """Return the normalized form of Sorani `text`, leaving `text` untouched.

    Resolves the §4.1 collisions: `ه`+ZWNJ to `ە`, Arabic `ي`/`ك` to the Farsi forms Kurdish
    uses, and Farsi/Eastern-Arabic numerals to Latin. Leading and trailing whitespace is
    stripped; internal runs are left as they are. That residual is one reason §8.1 keeps a
    spacing-free CER alongside the normalized one, and why word alignment (§4.2) keys off
    raw tokens rather than this string.

    Idempotent: `normalize_sorani(normalize_sorani(t)) == normalize_sorani(t)`.
    """
    normalized: str = _preprocessor().normalize(text)
    return normalized
