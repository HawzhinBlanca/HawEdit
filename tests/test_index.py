"""M2.1 — §2's text index: BM25 + character 3-grams over the normalized transcript.

§2: "BM25 + character 3-grams over the normalized transcript. Character n-grams matter more
than usual — Sorani is morphologically rich with heavy clitic attachment, so word-level
matching misses variants a human reads as identical."

The n-gram half is therefore not a refinement, it is the point. `test_the_failure_section_2_
describes` is the test this module exists to pass: a query whose word never appears as a
standalone token — only swallowed inside a clitic-attached form — scores zero on BM25 alone
and is still found. Without that, the index silently returns nothing for queries a Kurdish
speaker considers obvious matches.

Kurdish invariant #3 also lands here: an index reads `transcript.norm.json`, never raw.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from hawedit.index import (
    DEFAULT_NGRAM_SIZE,
    DEFAULT_NGRAM_WEIGHT,
    Bm25Index,
    Document,
    character_ngrams,
    index_tokens,
)
from hawedit.sentences import Sentence
from hawedit.transcripts import (
    AsrProvenance,
    NormalizedTranscript,
    RawTranscript,
)

BOOK = "کتێب"  # book


MY_BOOK = "کتێبەکەم"  # my book — the same stem with clitics attached


ROOT = Path(__file__).resolve().parents[1]


def _norm(media_id: str = "m1", text: str = "ئەمە زۆر باشە") -> NormalizedTranscript:
    """A normalized transcript to hang a sentence index off — `from_sentences` takes the
    transcript rather than a bare id so invariant #3's type guard is on that path (D-134)."""
    return NormalizedTranscript(media_id=media_id, text_ckb=text, source_sha256="abc")


def doc(doc_id: str, text: str, start_ms: int = 0, end_ms: int = 1000) -> Document:
    return Document(doc_id=doc_id, text_norm=text, start_ms=start_ms, end_ms=end_ms)


# --- tokenization ----------------------------------------------------------------------


def test_tokens_are_split_on_whitespace_and_stripped_of_punctuation() -> None:
    assert index_tokens("ئەمە زۆر باشە.") == ("ئەمە", "زۆر", "باشە")


def test_tokenizing_normalizes_first() -> None:
    """A query typed on an Arabic keyboard must produce the same tokens as a Kurdish one."""
    assert index_tokens("كوردي") == index_tokens("کوردی")


def test_character_ngrams_pad_word_boundaries() -> None:
    grams = character_ngrams("ab", size=3)
    assert grams == ("\x02ab", "ab\x03")


@pytest.mark.parametrize("size", [0, -1])
def test_a_character_ngram_size_below_one_is_refused(size: int) -> None:
    """The only refusal in this module no test held — measured by neutralising each in a shadow
    copy of src/hawedit and running this file.

    A size of 0 does not fail: `padded[i:i + 0]` is the empty string and the range still runs,
    so the function returns one empty gram per character position. Those enter the index as real
    postings that match every word, which turns §4.1's morphological near-match scoring into
    noise rather than into an error anyone would see.
    """
    with pytest.raises(ValueError, match="at least 1"):
        character_ngrams("کتێب", size=size)


def test_character_ngrams_of_a_longer_word_slide() -> None:
    assert "کتێ" in character_ngrams(BOOK, size=3)


def test_a_clitic_form_shares_ngrams_with_its_stem() -> None:
    shared = set(character_ngrams(BOOK, size=3)) & set(character_ngrams(MY_BOOK, size=3))
    assert len(shared) >= 2, "the stem's interior trigrams must survive clitic attachment"


# --- the failure §2 describes ----------------------------------------------------------


def test_the_failure_section_2_describes() -> None:
    """A query word that only ever appears clitic-attached. Word BM25 alone finds nothing.

    This is the whole reason §2 mandates character n-grams, and the reason they are not an
    optional refinement of this index.
    """
    index = Bm25Index(
        [
            doc("d1", f"من {MY_BOOK} خوێندەوە"),
            doc("d2", "ئەمە هیچ پەیوەندی نییە"),
        ]
    )
    hits = index.search(BOOK)
    assert hits, "the clitic-attached form must be findable"
    assert hits[0].doc_id == "d1"
    assert hits[0].word_score == 0.0, "word-level BM25 genuinely misses it"
    assert hits[0].ngram_score > 0.0, "character n-grams are what found it"


def test_word_matches_still_outrank_mere_ngram_overlap() -> None:
    """N-grams must widen recall without drowning an exact match in fuzzy noise."""
    index = Bm25Index([doc("exact", f"من {BOOK} خوێندەوە"), doc("clitic", f"من {MY_BOOK} خ")])
    hits = index.search(BOOK)
    assert hits[0].doc_id == "exact"


# --- invariant #3 ----------------------------------------------------------------------


def test_an_index_refuses_a_raw_transcript() -> None:
    raw = RawTranscript(
        media_id="m",
        text_ckb="ئەمە",
        words=(),
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2"),
    )
    with pytest.raises(TypeError, match="raw"):
        Bm25Index.from_transcript(raw)  # type: ignore[arg-type]


def test_an_index_accepts_a_normalized_transcript() -> None:
    norm = NormalizedTranscript(media_id="m", text_ckb="ئەمە زۆر باشە", source_sha256="abc")
    index = Bm25Index.from_transcript(norm)
    assert index.search("باشە")


# --- BM25 behaviour --------------------------------------------------------------------


def test_a_rare_term_outweighs_a_common_one() -> None:
    """IDF: a word in every document discriminates nothing."""
    common = "ئەمە"
    rare = "کوردستان"
    index = Bm25Index(
        [
            doc("d1", f"{common} {rare}"),
            doc("d2", common),
            doc("d3", common),
            doc("d4", common),
        ]
    )
    hits = index.search(f"{common} {rare}")
    assert hits[0].doc_id == "d1"


def test_term_frequency_saturates() -> None:
    """BM25's k1: the tenth occurrence must add far less than the second."""
    word = "کوردستان"
    index = Bm25Index([doc("twice", f"{word} {word}"), doc("ten", " ".join([word] * 10))])
    scores = {h.doc_id: h.word_score for h in index.search(word)}
    assert scores["ten"] > scores["twice"]
    assert scores["ten"] < 5 * scores["twice"], "score must not scale linearly with count"


def test_length_normalization_prefers_the_focused_document() -> None:
    """BM25's b: one hit in a short sentence beats one hit buried in a long one."""
    word = "کوردستان"
    padding = " ".join(["ئەمە"] * 40)
    index = Bm25Index([doc("short", f"{word} جوانە"), doc("long", f"{word} {padding}")])
    hits = index.search(word)
    assert hits[0].doc_id == "short"


def test_encoding_differences_do_not_prevent_a_match() -> None:
    """§4.1's failure mode, at the layer §0 says it actually bites: the index."""
    index = Bm25Index([doc("d1", "ئەمە کوردی یە")])
    assert index.search("كوردي"), "an Arabic-keyboard query must match Kurdish-keyboard text"


# --- results -----------------------------------------------------------------------------


def test_hits_are_ranked_by_descending_score() -> None:
    index = Bm25Index([doc("d1", "کوردستان کوردستان"), doc("d2", "کوردستان ئەمە زۆر باشە")])
    hits = index.search("کوردستان")
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)


def test_hits_carry_both_component_scores_for_tuning() -> None:
    index = Bm25Index([doc("d1", "کوردستان جوانە")])
    hit = index.search("کوردستان")[0]
    assert hit.word_score > 0
    assert hit.score == pytest.approx(hit.word_score + DEFAULT_NGRAM_WEIGHT * hit.ngram_score)


def test_hits_carry_timings_so_a_match_maps_back_to_a_clip_window() -> None:
    """M2 needs the index to hand Stage 5 a time range, not just a document id."""
    index = Bm25Index([doc("d1", "کوردستان", start_ms=84200, end_ms=112700)])
    hit = index.search("کوردستان")[0]
    assert (hit.start_ms, hit.end_ms) == (84200, 112700)


def test_the_limit_is_respected() -> None:
    index = Bm25Index([doc(f"d{i}", "کوردستان") for i in range(10)])
    assert len(index.search("کوردستان", limit=3)) == 3


def test_a_query_matching_nothing_returns_no_hits() -> None:
    index = Bm25Index([doc("d1", "ئەمە زۆر باشە")])
    assert index.search("zzzz") == ()


def test_an_empty_index_returns_no_hits() -> None:
    assert Bm25Index([]).search("کوردستان") == ()


def test_an_empty_query_is_refused() -> None:
    with pytest.raises(ValueError, match="query"):
        Bm25Index([doc("d1", "ئەمە")]).search("   ")


def test_duplicate_document_ids_are_refused() -> None:
    """Two documents sharing an id makes every hit ambiguous."""
    with pytest.raises(ValueError, match="duplicate"):
        Bm25Index([doc("d1", "ئەمە"), doc("d1", "باشە")])


def test_a_document_with_no_indexable_text_is_refused() -> None:
    with pytest.raises(ValueError, match="no indexable"):
        Bm25Index([doc("d1", "   ")])


def test_ranking_is_stable_for_tied_scores() -> None:
    """Ties broken by document id, so a re-run never reshuffles a candidate list."""
    index = Bm25Index([doc("b", "کوردستان"), doc("a", "کوردستان")])
    assert [h.doc_id for h in index.search("کوردستان")] == ["a", "b"]


# --- building from sentences ------------------------------------------------------------


def test_an_index_can_be_built_from_segmented_sentences() -> None:
    from hawedit.sentences import segment_sentences
    from hawedit.transcripts import Word

    words = (
        Word(w="کوردستان", start_ms=0, end_ms=500, conf=0.9),
        Word(w="جوانە.", start_ms=500, end_ms=900, conf=0.9),
        Word(w="ئەمە", start_ms=2000, end_ms=2400, conf=0.9),
        Word(w="باشە.", start_ms=2400, end_ms=2800, conf=0.9),
    )
    index = Bm25Index.from_sentences(segment_sentences(words), _norm("m1"))
    hit = index.search("کوردستان")[0]
    assert (hit.start_ms, hit.end_ms) == (0, 900)
    assert hit.doc_id.startswith("m1")


def test_sentences_are_normalized_on_the_way_into_the_index() -> None:
    """Sentence.text is raw surface forms; the index must hold the derived normalized form."""
    from hawedit.sentences import Sentence
    from hawedit.transcripts import Word

    sentence = Sentence(words=(Word(w="كوردي.", start_ms=0, end_ms=500, conf=0.9),), complete=True)
    index = Bm25Index.from_sentences((sentence,), _norm("m1"))
    assert index.documents[0].text_norm == "کوردی."
    assert index.search("کوردی")


# --- §2, D-134: the shape the runner builds, and what a single document can do -------------


def _sentences_of(*specs: tuple[str, int, int]) -> tuple[Sentence, ...]:
    from hawedit.sentences import segment_sentences
    from hawedit.transcripts import Word

    return segment_sentences(tuple(Word(w=w, start_ms=s, end_ms=e, conf=0.9) for w, s, e in specs))


SPECS = (
    ("کوردستان", 0, 500),
    ("جوانە.", 500, 900),
    ("هەولێر", 2000, 2400),
    ("جوانە.", 2400, 2800),
    ("سلێمانی", 4000, 4400),
    ("گەورەیە.", 4400, 4800),
)


def test_a_single_document_index_has_one_idf_and_cannot_rank() -> None:
    """The arithmetic behind D-134, stated as arithmetic.

    BM25's idf is `log(1 + (N - df + 0.5) / (df + 0.5))`. At N=1 every term has df=1, so every
    term's idf is `log(1 + 0.5/1.5)` — one value for the whole vocabulary. Measured on the real
    38-minute transcript: 2,784 distinct terms, **1** distinct idf, and the single hit's window
    was 322..2,313,729 ms. This pins it on a fixture so the property is checked every run.
    """
    single = Bm25Index.from_transcript(
        _norm("whole", "کوردستان جوانە هەولێر جوانە سلێمانی گەورەیە")
    )
    assert len(single.documents) == 1
    idfs = {
        round(math.log(1.0 + (1 - len(posting) + 0.5) / (len(posting) + 0.5)), 9)
        for posting in single._words.postings.values()
    }
    assert idfs == {round(math.log(1.0 + 0.5 / 1.5), 9)}, idfs
    # Whatever is asked, the same one document comes back — there is no ordering to produce, and
    # its window is the whole media rather than a passage. (Term *frequency* still varies within
    # that document, which is why this asserts what a single document cannot do rather than
    # claiming its scores are all equal — the first version of this test claimed that and the
    # control caught it.)
    for query in ("کوردستان", "جوانە", "سلێمانی"):
        hits = single.search(query)
        assert len(hits) == 1
        assert hits[0].doc_id == "whole"


def test_the_sentence_index_ranks_and_the_whole_transcript_one_does_not() -> None:
    """The control, and the reason D-134 is a fix rather than a preference.

    Same text, two shapes. Ranking means ordering *documents* for one query, so that is what is
    compared: the per-sentence index answers different queries with different best documents and
    real per-sentence windows; the single-document index answers every query with the same one.

    The idf spread is the mechanism §2's paragraph depends on — a term in one sentence must
    outweigh a term in two — and it exists only when there is more than one document.
    """
    sentences = _sentences_of(*SPECS)
    per_sentence = Bm25Index.from_sentences(sentences, _norm("m1"))
    whole = Bm25Index.from_transcript(_norm("m1", " ".join(w for w, _, _ in SPECS)))

    rare = per_sentence.search("کوردستان")[0].word_score  # in 1 of 3 sentences
    common = per_sentence.search("جوانە")[0].word_score  # in 2 of 3
    assert rare > common, f"rare {rare} should outrank common {common}"

    best_per_query = {q: per_sentence.search(q)[0].doc_id for q in ("کوردستان", "سلێمانی")}
    assert len(set(best_per_query.values())) == 2, best_per_query
    whole_per_query = {q: whole.search(q)[0].doc_id for q in ("کوردستان", "سلێمانی")}
    assert len(set(whole_per_query.values())) == 1, (
        "the single-document index returned two different documents, so this control measures "
        "nothing"
    )


def test_a_sentence_hit_carries_its_own_window_not_the_whole_media() -> None:
    """§3 Stage 5 consumes a window. A hit spanning the whole episode is not one.

    Asserted on the hit: the window must be the matching sentence's, and must not be the media's
    full span — the plausible wrong answer, which is exactly what the runner used to produce.
    """
    sentences = _sentences_of(*SPECS)
    index = Bm25Index.from_sentences(sentences, _norm("m1"))
    hit = index.search("سلێمانی")[0]
    assert (hit.start_ms, hit.end_ms) == (4000, 4800)
    media_span = (SPECS[0][1], SPECS[-1][2])
    assert (hit.start_ms, hit.end_ms) != media_span, "the hit spans the whole media"


def test_the_runner_indexes_sentences_and_the_report_shows_more_than_one_document() -> None:
    """The wiring, which is what actually shipped wrong — the factory was right and unused.

    Asserted on `pipeline.py`'s source because the claim is *which* factory the runner calls;
    `test_the_run_report_serializes_to_json` asserts the consequence on the emitted JSON.
    """
    pipeline_py = ROOT / "src" / "hawedit" / "pipeline.py"
    source = pipeline_py.read_text(encoding="utf-8")
    assert "Bm25Index.from_sentences(sentences, normalized)" in source, (
        "the runner no longer builds the sentence index; a one-document index cannot rank and "
        "its only hit spans the whole media"
    )
    assert "Bm25Index.from_transcript(" not in source, (
        "the runner is back on the single-document shape"
    )


def test_from_sentences_refuses_a_raw_transcript() -> None:
    """Invariant #3 moved with the runner. `from_transcript` held the type guard and the runner
    left it; a bare `media_id` string cannot be refused, a `RawTranscript` can."""
    raw = RawTranscript(
        media_id="m",
        text_ckb="ئەمە",
        words=(),
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2"),
    )
    with pytest.raises(TypeError, match="raw"):
        Bm25Index.from_sentences(_sentences_of(*SPECS), raw)  # type: ignore[arg-type]


def test_a_limit_that_cannot_return_a_document_is_refused() -> None:
    """D-090 fixed `scored[:k]` in `visual_index.retrieve` and this sibling kept the defect.

    Measured on a 10-document index before the guard: `limit=-1` returned **9** hits and
    `limit=-10` returned **0**, because a negative slice drops the tail rather than keeping a
    head — the caller gets the best documents minus some and cannot tell.
    """
    index = Bm25Index([doc(f"d{i}", "کوردستان") for i in range(10)])
    for limit in (0, -1, -5, -10):
        with pytest.raises(ValueError, match="cannot return a document"):
            index.search("کوردستان", limit=limit)
    # The control: limit=1 is the tight boundary and must still work, so this is not measuring
    # "any limit is refused". D-090's over-strict direction is the one only a control catches.
    assert len(index.search("کوردستان", limit=1)) == 1
    assert len(index.search("کوردستان", limit=10)) == 10


# --- D-173: §2's n-gram size, stated in the frozen blueprint and held by nothing -------------


def test_the_ngram_size_is_the_one_the_blueprint_states() -> None:
    """§2/§3: *"BM25 + character 3-grams over the normalized transcript."*

    Adversarial pass 28 measured this one drifting silently: `DEFAULT_NGRAM_SIZE` 3 → 4 left the
    whole suite green. Nothing pinned it to the blueprint and nothing pinned it behaviourally
    either, though the document singles the choice out — *"Character n-grams matter more than
    usual — Sorani is morphologically rich"* — which is why it is a stated number and not a
    tuning knob.

    Read from the document rather than restated beside the constant, for the reason D-172
    records one module over.
    """
    import re
    from pathlib import Path as _Path

    blueprint = (_Path(__file__).resolve().parents[1] / "BLUEPRINT.md").read_text(encoding="utf-8")
    stated = re.findall(r"character (\d+)-grams", blueprint)
    assert stated, "§2 no longer states the character n-gram size; the scan is broken"
    assert len(set(stated)) == 1, f"the blueprint states two different n-gram sizes: {stated}"
    assert int(stated[0]) == DEFAULT_NGRAM_SIZE, (
        f"§2 states character {stated[0]}-grams and DEFAULT_NGRAM_SIZE is {DEFAULT_NGRAM_SIZE}"
    )


def test_the_ngram_size_is_the_one_the_index_actually_uses() -> None:
    """The control: the constant could be right while nothing consulted it.

    Binding a constant to a document proves the *number* is the blueprint's, not that the index
    uses it — so this asserts on the artifact, the emitted n-grams of a word long enough to
    distinguish 3 from 4.
    """
    emitted = character_ngrams("کوردستان")
    assert emitted, "no n-grams emitted for a word long enough to produce them"
    assert {len(gram) for gram in emitted} == {DEFAULT_NGRAM_SIZE}, (
        f"character_ngrams emitted lengths {sorted({len(g) for g in emitted})}, and "
        f"DEFAULT_NGRAM_SIZE is {DEFAULT_NGRAM_SIZE}"
    )


def norm(media_id: str = "m1", text: str = "ئەمە زۆر باشە") -> NormalizedTranscript:
    return NormalizedTranscript(media_id=media_id, text_ckb=text, source_sha256="abc")


# --- tokenization ----------------------------------------------------------------------


def test_sentence_documents_rank_distinct_queries_into_distinct_windows() -> None:
    from hawedit.sentences import segment_sentences
    from hawedit.transcripts import Word

    words = (
        Word(w="کوردستان", start_ms=0, end_ms=500, conf=0.9),
        Word(w="جوانە.", start_ms=500, end_ms=900, conf=0.9),
        Word(w="هەولێر", start_ms=2000, end_ms=2400, conf=0.9),
        Word(w="باشە.", start_ms=2400, end_ms=2800, conf=0.9),
        Word(w="سلێمانی", start_ms=4000, end_ms=4400, conf=0.9),
        Word(w="گەورەیە.", start_ms=4400, end_ms=4800, conf=0.9),
    )
    index = Bm25Index.from_sentences(segment_sentences(words), norm())

    first = index.search("کوردستان")[0]
    last = index.search("سلێمانی")[0]
    assert first.doc_id != last.doc_id
    assert (first.start_ms, first.end_ms) == (0, 900)
    assert (last.start_ms, last.end_ms) == (4000, 4800)


def test_single_document_shape_cannot_return_a_passage() -> None:
    index = Bm25Index.from_transcript(norm("whole", "کوردستان هەولێر سلێمانی"))
    assert {index.search(query)[0].doc_id for query in ("کوردستان", "سلێمانی")} == {"whole"}


def test_nonpositive_search_limits_are_refused_at_the_exact_boundary() -> None:
    index = Bm25Index([doc(f"d{position}", "کوردستان") for position in range(10)])
    for limit in (0, -1, -10):
        with pytest.raises(ValueError, match="cannot return a document"):
            index.search("کوردستان", limit=limit)
    assert len(index.search("کوردستان", limit=1)) == 1
