"""§4.1 conjunctive `و` separation — M1.7, the fifth collision KLPT does not cover.

§4.1's table says the conjunction `و` is "often joined to the previous word" and credits
AsoSoft with a separation algorithm. D-003 measured that KLPT covers the other four collisions
and not this one, and left it unimplemented rather than guessed: `وتو` could be one word or
two, and a wrong split writes a word that was never said into the artifact every index and
embedding reads.

What makes it implementable now is that the guess is not necessary. KLPT ships a Sorani
hunspell dictionary, and its `check_spelling` is morphology-aware — `کتێبەکان` (the inflected
plural) validates, `وکتێبەکان` does not. So the rule can be stated as a refusal rather than a
prediction:

    split `و` + R  only if  R is a valid Sorani word  and  `و`+R is not.

Both halves matter. Without the first, any `و`-initial token gets split. Without the second,
`وتار` — a real word meaning "article" — becomes "and tar". The rule is deliberately biased
toward under-splitting: leaving a joined `و` costs recall in the index, which character
3-grams (§2) partly absorb; splitting a real word writes a falsehood into the canonical
normalized transcript, which nothing absorbs.

The safety property is checked exhaustively rather than by example: **no entry in KLPT's
24,888-word dictionary is ever split**. That is the whole claim, tested over the whole lexicon.
"""

from __future__ import annotations

import json
from pathlib import Path

import klpt
import pytest

from hawedit.normalize import (
    WAW,
    is_sorani_word,
    normalize_sorani,
    separate_conjunctive_waw,
)


@pytest.fixture(scope="module")
def lexicon() -> tuple[str, ...]:
    """Every headword in KLPT's Sorani hunspell dictionary, normalized."""
    path = Path(klpt.__file__).parent / "data" / "ckb-Arab.dic"
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:  # line 0 is the count
        word = normalize_sorani(line.split("/")[0].split(" ")[0].strip())
        if word:
            entries.append(word)
    return tuple(entries)


# --- the rule ----------------------------------------------------------------------------


def test_a_joined_conjunction_is_separated() -> None:
    """`و` + an inflected noun. The remainder validates, the whole does not."""
    assert separate_conjunctive_waw("وکتێبەکان") == f"{WAW} کتێبەکان"


def test_separation_works_inside_a_sentence() -> None:
    assert separate_conjunctive_waw("ئەم کتێبە وژنان") == f"ئەم کتێبە {WAW} ژنان"


def test_a_real_word_that_merely_starts_with_waw_is_left_alone() -> None:
    """`وتار` is "article". Splitting it writes a word nobody said."""
    assert separate_conjunctive_waw("وتار") == "وتار"


def test_the_ambiguous_case_d003_named_is_still_refused() -> None:
    """D-003's example. `تو` does not validate on its own, so there is nothing to split to.

    This is the case that made the whole feature wait for a lexicon, and the lexicon's answer
    is "leave it": the rule declines rather than picking one of two readings.
    """
    assert separate_conjunctive_waw("وتو") == "وتو"


def test_a_bare_conjunction_is_untouched() -> None:
    assert separate_conjunctive_waw(f"من {WAW} تۆ") == f"من {WAW} تۆ"


def test_an_unknown_waw_initial_token_is_left_alone() -> None:
    """Neither the token nor its remainder is a word — there is no evidence to act on."""
    assert separate_conjunctive_waw("وپپپپ") == "وپپپپ"


def test_punctuation_is_preserved_around_a_split() -> None:
    assert separate_conjunctive_waw("«وکتێبەکان»") == f"«{WAW} کتێبەکان»"
    assert separate_conjunctive_waw("وکتێبەکان.") == f"{WAW} کتێبەکان."


def test_words_that_do_not_start_with_waw_are_never_touched(lexicon: tuple[str, ...]) -> None:
    for word in lexicon:
        if not word.startswith(WAW):
            assert separate_conjunctive_waw(word) == word


def test_separation_is_idempotent() -> None:
    once = separate_conjunctive_waw("وکتێبەکان وژنان")
    assert separate_conjunctive_waw(once) == once


def test_empty_and_latin_input_are_safe() -> None:
    assert separate_conjunctive_waw("") == ""
    assert separate_conjunctive_waw("hello world") == "hello world"


# --- the safety property, over the whole dictionary ---------------------------------------


def test_no_dictionary_word_is_ever_split(lexicon: tuple[str, ...]) -> None:
    """The claim, checked exhaustively rather than by example.

    A normalization that can destroy a known Sorani word is worse than one that does nothing:
    the damage lands in `transcript.norm.json`, which is what every index, embedding and model
    input reads (Kurdish invariant #3), and it is invisible on screen.
    """
    damaged = [w for w in lexicon if separate_conjunctive_waw(w) != w]
    assert not damaged, f"{len(damaged)} dictionary words were split, e.g. {damaged[:10]}"


def test_the_measured_residual_is_what_the_evidence_file_says() -> None:
    """The under-splitting is bounded and the bound is recorded, not hand-waved.

    A `و`-initial token that is *itself* a valid word can never be split, even when the
    conjunctive reading is the right one. That set is finite and enumerable, so it is
    enumerated — `evidence/waw-separation.md` carries the count and the list.
    """
    evidence = Path(__file__).resolve().parents[1] / "evidence" / "waw-separation.md"
    assert evidence.exists(), "the measurement backing D-026 is not recorded"
    assert "unsplittable" in evidence.read_text(encoding="utf-8")


def test_spell_check_agrees_with_the_dictionary_on_a_sample(lexicon: tuple[str, ...]) -> None:
    """`is_sorani_word` is the rule's only evidence source, so it gets its own check."""
    sample = lexicon[::500]
    accepted = sum(1 for w in sample if is_sorani_word(w))
    assert accepted / len(sample) > 0.9, f"only {accepted}/{len(sample)} dictionary words validate"
    assert not is_sorani_word("zzzqqq")
    assert not is_sorani_word("")


# --- wired into §4.1 normalization ---------------------------------------------------------


def test_normalize_sorani_now_separates_the_conjunction() -> None:
    """§4.1 lists this as one of its five collisions, so it belongs in normalization."""
    assert normalize_sorani("وکتێبەکان") == f"{WAW} کتێبەکان"


def test_normalization_runs_the_encoding_fixes_before_the_lexicon_lookup() -> None:
    """Order is load-bearing: `ه`+ZWNJ must become `ە` before any word is looked up.

    A lexicon lookup on unnormalized text fails for exactly the reason §4.1 exists — the
    dictionary is in one encoding and the input may be in another — so separation would
    silently never fire on precisely the text that most needs it.
    """
    typed_with_zwnj = "وکتێبه‌کان"
    assert normalize_sorani(typed_with_zwnj) == f"{WAW} کتێبەکان"


def test_normalization_is_still_idempotent_with_separation_on() -> None:
    text = "ئه‌مه‌ وکتێبەکان ساڵی ۲۰۲۵"
    once = normalize_sorani(text)
    assert normalize_sorani(once) == once


def test_the_index_can_now_match_a_joined_conjunction() -> None:
    """The point of the exercise, at the boundary that motivated it (§2).

    Before separation, `وکتێبەکان` and `کتێبەکان` were different terms and BM25 scored a query
    for one against a document containing the other at zero.
    """
    from hawedit.index import Bm25Index, Document

    joined = Document(
        doc_id="joined", text_norm=normalize_sorani("ئەمە وکتێبەکان بوو"), start_ms=0, end_ms=1
    )
    other = Document(
        doc_id="other", text_norm=normalize_sorani("ئەمە شتێکی تر بوو"), start_ms=1, end_ms=2
    )
    hits = Bm25Index([joined, other]).search("کتێبەکان")
    assert hits and hits[0].doc_id == "joined", f"joined conjunction still unreachable: {hits}"
    assert hits[0].word_score > 0, (
        "the word field still scores zero — separation did not reach the index, and only the "
        "n-gram field is carrying the match (which is the §2 failure mode, not the fix)"
    )


def test_the_evidence_file_records_real_counts() -> None:
    evidence = Path(__file__).resolve().parents[1] / "evidence" / "waw-separation.md"
    body = evidence.read_text(encoding="utf-8")
    numbers = json.loads(body.split("```json")[1].split("```")[0])
    assert numbers["lexicon_entries"] > 20_000
    assert numbers["dictionary_words_damaged"] == 0
    assert numbers["unsplittable_waw_initial_words"] == len(numbers["unsplittable_examples"])
