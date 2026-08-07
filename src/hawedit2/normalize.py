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
measured, not assumed — see `DECISIONS.md` D-003. It covers four of §4.1's five collisions;
the fifth, conjunctive `و` separation, is handled here against KLPT's Sorani dictionary and
is documented on `separate_conjunctive_waw` (D-026).
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Final

from klpt.preprocess import Preprocess

__all__ = [
    "NUMERAL",
    "SCRIPT",
    "SORANI",
    "WAW",
    "is_sorani_word",
    "normalize_sorani",
    "separate_conjunctive_waw",
]

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
    # Order matters: the encoding fixes must land before any dictionary lookup, or separation
    # would fail on exactly the text §4.1 exists for — a word typed with `ه`+ZWNJ is not the
    # dictionary's spelling of it, so it would never be recognised and never be separated.
    return separate_conjunctive_waw(normalized)


# --- §4.1's fifth collision: conjunctive `و` ----------------------------------------------

WAW: Final = "و"

# A token as it sits in text: leading punctuation/quotes, the word, trailing punctuation.
# `\w` is Unicode-aware, so Kurdish letters are word characters and «», ., ، are not.
_TOKEN: Final = re.compile(r"(\w+)")


@lru_cache(maxsize=1)
def _speller() -> object:
    """KLPT's Stem, used only for `check_spelling`. Built once — construction reads the
    hunspell tables and costs ~0.2 s."""
    from klpt.stem import Stem

    return Stem(SORANI, SCRIPT)


@lru_cache(maxsize=100_000)
def is_sorani_word(token: str) -> bool:
    """Is `token` a valid Sorani word, inflections included?

    KLPT's spell check is morphology-aware — it accepts `کتێبەکان` (books-the), not just the
    citation form — which is what makes separation possible at all. A bare-lexicon lookup
    would only ever recognise the ~24k headwords and would leave every inflected form joined.

    Cached because normalization runs over whole transcripts and the same function words
    recur constantly.
    """
    if not token:
        return False
    checked: bool = _speller().check_spelling(token)  # type: ignore[attr-defined]
    return checked


def separate_conjunctive_waw(text: str) -> str:
    """Split a conjunctive `و` off the word it was typed onto (§4.1, D-026).

    §4.1: "Often joined to the previous word; AsoSoft applies a separation algorithm." The
    algorithm here is stated as a refusal rather than a prediction:

        split `و` + R  →  `و` R    only if   R is a valid Sorani word  AND  `و`+R is not.

    Both conditions carry weight. Drop the first and every `و`-initial token gets split. Drop
    the second and `وتار` — "article" — becomes "and tar", writing a word nobody said into the
    artifact that every index, embedding and model input reads (Kurdish invariant #3).

    The bias is deliberate and one-directional: **under-split, never mis-split.** A joined `و`
    left alone costs recall in the §2 index, and character 3-grams absorb part of that. A real
    word torn in half costs correctness, and nothing absorbs it. The residual is bounded and
    measured — see `evidence/waw-separation.md`: on KLPT's 24,888-entry dictionary, zero words
    are damaged and 10 `و`-initial words can never be separated because they are words in
    their own right.

    Returns:
        A new string. Never mutates `text`.
    """

    def split_token(match: re.Match[str]) -> str:
        token = match.group(1)
        if len(token) < 2 or not token.startswith(WAW):
            return token
        remainder = token[1:]
        if is_sorani_word(token) or not is_sorani_word(remainder):
            return token
        return f"{WAW} {remainder}"

    return _TOKEN.sub(split_token, text)
