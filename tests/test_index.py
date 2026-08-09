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

import pytest

from hawedit.index import (
    DEFAULT_NGRAM_WEIGHT,
    Bm25Index,
    Document,
    character_ngrams,
    index_tokens,
)
from hawedit.transcripts import AsrProvenance, NormalizedTranscript, RawTranscript

BOOK = "کتێب"  # book
MY_BOOK = "کتێبەکەم"  # my book — the same stem with clitics attached


def doc(doc_id: str, text: str, start_ms: int = 0, end_ms: int = 1000) -> Document:
    return Document(doc_id=doc_id, text_norm=text, start_ms=start_ms, end_ms=end_ms)


def norm(media_id: str = "m1", text: str = "ئەمە زۆر باشە") -> NormalizedTranscript:
    return NormalizedTranscript(media_id=media_id, text_ckb=text, source_sha256="abc")


# --- tokenization ----------------------------------------------------------------------


def test_tokens_are_split_on_whitespace_and_stripped_of_punctuation() -> None:
    assert index_tokens("ئەمە زۆر باشە.") == ("ئەمە", "زۆر", "باشە")


def test_tokenizing_normalizes_first() -> None:
    """A query typed on an Arabic keyboard must produce the same tokens as a Kurdish one."""
    assert index_tokens("كوردي") == index_tokens("کوردی")


def test_character_ngrams_pad_word_boundaries() -> None:
    grams = character_ngrams("ab", size=3)
    assert grams == ("\x02ab", "ab\x03")


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
    index = Bm25Index.from_sentences(segment_sentences(words), norm("m1"))
    hit = index.search("کوردستان")[0]
    assert (hit.start_ms, hit.end_ms) == (0, 900)
    assert hit.doc_id.startswith("m1")


def test_sentences_are_normalized_on_the_way_into_the_index() -> None:
    """Sentence.text is raw surface forms; the index must hold the derived normalized form."""
    from hawedit.sentences import Sentence
    from hawedit.transcripts import Word

    sentence = Sentence(words=(Word(w="كوردي.", start_ms=0, end_ms=500, conf=0.9),), complete=True)
    index = Bm25Index.from_sentences((sentence,), norm("m1"))
    assert index.documents[0].text_norm == "کوردی."
    assert index.search("کوردی")


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


def test_from_sentences_refuses_a_raw_transcript() -> None:
    from hawedit.sentences import Sentence
    from hawedit.transcripts import Word

    raw = RawTranscript(
        media_id="m",
        text_ckb="ئەمە",
        words=(),
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2"),
    )
    sentence = Sentence(words=(Word(w="ئەمە.", start_ms=0, end_ms=500, conf=0.9),), complete=True)
    with pytest.raises(TypeError, match="raw"):
        Bm25Index.from_sentences((sentence,), raw)  # type: ignore[arg-type]


def test_nonpositive_search_limits_are_refused_at_the_exact_boundary() -> None:
    index = Bm25Index([doc(f"d{position}", "کوردستان") for position in range(10)])
    for limit in (0, -1, -10):
        with pytest.raises(ValueError, match="cannot return a document"):
            index.search("کوردستان", limit=limit)
    assert len(index.search("کوردستان", limit=1)) == 1
