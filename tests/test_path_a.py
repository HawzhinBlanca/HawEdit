"""§3 Stage 3 Path A — the Kurdish judge reads the whole transcript.

    Send the **full normalized Sorani transcript** to the Kurdish judge in one pass. Not a
    filtered subset. […] If the visual stage filters first, the best clip in the episode is
    gone before anything that understands Kurdish ever reads it.

`discovery.py` built the union and had no producers. This is the first one. Everything here
runs offline through an injected transport — a suite that needed a live key would push people
toward committing one.

Four properties are tested harder than the rest, because each has an implementation that looks
correct and quietly destroys the reason Path A exists:

* **The whole transcript goes, unfiltered.** Sampling it, or sending only the parts some local
  heuristic liked, is the exact failure §3 built the dual path to prevent — and it would be
  invisible, because the candidates that came back would still look reasonable.
* **It reads `norm`, never `raw`.** Kurdish invariant #3. The judge is a model input.
* **Candidates land inside the transcript.** A model asked for millisecond spans will
  occasionally invent one past the end, and a candidate that runs past the media is a clip
  that cannot be cut.
* **Ranks are dense and ordered.** §8.2 counts Recall@K by rank; duplicated or gapped ranks
  make every K mean something slightly different.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from hawedit.clip import (
    MAX_CANDIDATE_SPAN_MS,
    MIN_CANDIDATE_SPAN_MS,
    DiscoveryPath,
)
from hawedit.discovery import merge_candidates
from hawedit.gemini import GeminiUnavailable, Governance, JudgeUnusable
from hawedit.judge import JUDGE_SHADOW, KURDISH_EDITORIAL_JUDGE, InputMode, RequestTooLarge
from hawedit.normalize import normalize_sorani
from hawedit.path_a import CANDIDATE_SCHEMA, PathADiscovery, discover_verbal
from hawedit.sentences import Sentence, segment_sentences
from hawedit.transcripts import AsrProvenance, RawTranscript, Word, normalize_transcript

KEY = "test-key-not-real"

TEXT = "ڕۆژنامەوانی کوردی لە هەولێر. ئەمە زۆر گرنگە بۆ ئێمە. با باسی بکەین."


def a_transcript(media_id: str = "ep01") -> Any:
    raw = RawTranscript(
        media_id=media_id,
        text_ckb=TEXT,
        words=(
            Word(w="ڕۆژنامەوانی", start_ms=0, end_ms=450, conf=0.95),
            Word(w="کوردی", start_ms=450, end_ms=900, conf=0.95),
            Word(w="لە", start_ms=900, end_ms=1_350, conf=0.94),
            Word(w="هەولێر.", start_ms=1_350, end_ms=1_800, conf=0.94),
            Word(w="ئەمە", start_ms=2_000, end_ms=2_400, conf=0.93),
            Word(w="زۆر", start_ms=2_400, end_ms=2_800, conf=0.93),
            Word(w="گرنگە", start_ms=2_800, end_ms=3_200, conf=0.92),
            Word(w="بۆ", start_ms=3_200, end_ms=3_600, conf=0.92),
            Word(w="ئێمە.", start_ms=3_600, end_ms=4_000, conf=0.92),
            Word(w="با", start_ms=4_200, end_ms=4_800, conf=0.91),
            Word(w="باسی", start_ms=4_800, end_ms=5_400, conf=0.91),
            Word(w="بکەین.", start_ms=5_400, end_ms=6_000, conf=0.91),
        ),
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
    )
    return normalize_transcript(raw)


def candidates(*spans: tuple[int, int, float]) -> list[dict[str, Any]]:
    return [
        {
            "start_sentence": start_sentence,
            "end_sentence": end_sentence,
            "score": score,
            "reason_ckb": "گرنگە",
        }
        for start_sentence, end_sentence, score in spans
    ]


class Api:
    """A recording transport answering countTokens and generateContent."""

    def __init__(self, tokens: int = 5_000, payload: list[dict[str, Any]] | None = None) -> None:
        self.tokens = tokens
        self.payload = payload if payload is not None else candidates((0, 0, 0.9))
        self.calls: list[str] = []
        self.bodies: list[dict[str, Any]] = []

    def __call__(
        self, url: str, body: bytes | None, _headers: Mapping[str, str]
    ) -> tuple[int, str]:
        self.calls.append(url.split("?")[0].rsplit("/", 1)[-1])
        if body:
            self.bodies.append(json.loads(body))
        if "countTokens" in url:
            return 200, json.dumps({"totalTokens": self.tokens})
        return 200, json.dumps(
            {
                "candidates": [
                    {"content": {"parts": [{"text": json.dumps({"candidates": self.payload})}]}}
                ]
            }
        )

    @property
    def prompt(self) -> str:
        return str(self.bodies[-1]["contents"][0]["parts"][0]["text"])


def a_path_a(api: Api, **kwargs: Any) -> PathADiscovery:
    kwargs.setdefault("sleep", lambda _s: None)
    return PathADiscovery(api_key=KEY, transport=api, **kwargs)


# --- the reason Path A exists --------------------------------------------------------------


def test_the_whole_transcript_is_sent_unfiltered() -> None:
    """§3 / D-344: every normalized sentence is sent as 0-based numbered lines with no ms dump."""
    transcript = a_transcript()
    api = Api()
    a_path_a(api).discover(transcript)

    sentences = segment_sentences(transcript.words)
    for idx, sent in enumerate(sentences):
        line = f"[{idx}] {normalize_sorani(sent.text)}"
        assert line in api.prompt, f"numbered sentence {line!r} was withheld from the judge"

    for word in transcript.text_ckb.replace(".", " ").split():
        assert word in api.prompt, f"{word!r} was withheld from the judge"

    assert "0-900" not in api.prompt, "legacy millisecond timing table must be removed"
    assert not hasattr(__import__("hawedit.path_a", fromlist=["path_a"]), "_timing_table"), (
        "_timing_table(limit=4000) must be removed"
    )


def _long_transcript(sentence_count: int = 900, words_per_sentence: int = 5) -> Any:
    words: list[Word] = []
    parts: list[str] = []
    t = 0
    for s_idx in range(sentence_count):
        sent_tokens: list[str] = []
        for w_idx in range(words_per_sentence):
            base = f"وشە{s_idx}_{w_idx}" if w_idx == 0 else "كوردی"
            token = f"{base}." if w_idx == words_per_sentence - 1 else base
            words.append(Word(w=token, start_ms=t, end_ms=t + 300, conf=0.95))
            sent_tokens.append(token)
            t += 350
        t += 600
        parts.append(" ".join(sent_tokens))
    raw = RawTranscript(
        media_id="ep-long",
        text_ckb=" ".join(parts),
        words=tuple(words),
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
    )
    return normalize_transcript(raw)


def test_prompt_sends_all_numbered_sentences_past_4000_words() -> None:
    """AC1: transcripts >4,000 words render every [i] sentence without truncation."""
    transcript = _long_transcript(sentence_count=900, words_per_sentence=5)  # 4,500 words
    api = Api(tokens=18_000, payload=candidates((895, 899, 0.92)))
    path_a = a_path_a(api, k=1)
    path_a.discover(transcript)
    assert path_a.model_id == KURDISH_EDITORIAL_JUDGE
    assert "[0] " in api.prompt
    assert "[899] " in api.prompt
    assert "وشە899_0" in api.prompt
    assert "omitted from this timing table" not in api.prompt


def test_candidate_schema_uses_sentence_numbers_not_milliseconds() -> None:
    """AC3: structured schema uses start_sentence and end_sentence, never in_ms/out_ms."""
    item_props = CANDIDATE_SCHEMA["properties"]["candidates"]["items"]["properties"]
    required = set(CANDIDATE_SCHEMA["properties"]["candidates"]["items"]["required"])
    assert set(item_props.keys()) == {"start_sentence", "end_sentence", "score", "reason_ckb"}
    assert item_props["start_sentence"]["type"] == "integer"
    assert item_props["end_sentence"]["type"] == "integer"
    assert required == {"start_sentence", "end_sentence", "score", "reason_ckb"}


def test_sentence_indices_map_to_exact_ctc_word_boundaries() -> None:
    """AC4: inclusive [start_sentence..end_sentence] snap deterministically to CTC Sentence ms."""
    api = Api(payload=candidates((1, 2, 0.88)))
    found = a_path_a(api, k=1).discover(a_transcript())
    assert len(found) == 1
    assert found[0].in_ms == 2_000
    assert found[0].out_ms == 6_000
    assert found[0].span == (2_000, 6_000)


def test_discovery_finds_moments_past_4000_words() -> None:
    """AC6: candidates selected in sentences past word 4,000 resolve exact CTC timestamps."""
    transcript = _long_transcript(sentence_count=900, words_per_sentence=5)
    sents = segment_sentences(transcript.words)
    assert len(transcript.words) == 4_500
    assert len(sents) == 900
    api = Api(tokens=18_000, payload=candidates((890, 895, 0.95)))
    found = a_path_a(api, k=1).discover(transcript, sentences=sents)
    assert len(found) == 1
    assert found[0].span == (sents[890].start_ms, sents[895].end_ms)


def test_a_verbal_only_moment_is_discoverable_because_nothing_pre_filtered() -> None:
    """The whole point: a talking head with no motion is invisible to every local component."""
    api = Api(payload=candidates((1, 1, 0.95)))
    found = a_path_a(api).discover(a_transcript())
    assert len(found) == 1
    assert found[0].path is DiscoveryPath.VERBAL
    assert found[0].span == (2_000, 4_000)


def test_the_judge_reads_the_normalized_transcript_never_the_raw_one() -> None:
    """Kurdish invariant #3 — the judge is a model input."""
    raw = RawTranscript(
        media_id="ep01",
        text_ckb=TEXT,
        words=(Word(w="ئەمە", start_ms=0, end_ms=500, conf=0.9),),
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
    )
    with pytest.raises(TypeError, match="norm"):
        a_path_a(Api()).discover(raw)  # type: ignore[arg-type]


def test_candidates_are_verbal_and_carry_the_media_id() -> None:
    found = a_path_a(Api(payload=candidates((0, 0, 0.8), (1, 1, 0.7)))).discover(
        a_transcript("ep-42")
    )
    assert {c.media_id for c in found} == {"ep-42"}
    assert {c.path for c in found} == {DiscoveryPath.VERBAL}


def test_path_a_output_feeds_the_union_directly() -> None:
    """The seam `discovery.py` was built for, closed."""
    found = a_path_a(Api(payload=candidates((0, 0, 0.9)))).discover(a_transcript())
    merged = merge_candidates(list(found), [])
    assert len(merged) == 1
    assert merged[0].discovery_path is DiscoveryPath.VERBAL
    assert merged[0].verbal_score == 0.9


# --- invalid sentence indices & incomplete-sentence boundary refusals ----------------------


def test_a_candidate_past_the_end_of_the_transcript_is_refused() -> None:
    with pytest.raises(JudgeUnusable, match="sentence range"):
        a_path_a(Api(payload=candidates((0, 999, 0.9)))).discover(a_transcript())


def test_a_candidate_before_the_start_is_refused() -> None:
    with pytest.raises(JudgeUnusable, match="sentence range"):
        a_path_a(Api(payload=candidates((-1, 1, 0.9)))).discover(a_transcript())


def test_an_inverted_candidate_is_refused() -> None:
    with pytest.raises(JudgeUnusable, match="inverted"):
        a_path_a(Api(payload=candidates((2, 0, 0.9)))).discover(a_transcript())


def test_invalid_or_incomplete_sentence_indices_raise_judge_unusable() -> None:
    """AC5: out-of-range, inverted, non-int, and incomplete fragment sentences fail-stop."""
    incomplete_raw = RawTranscript(
        media_id="ep-frag",
        text_ckb="ئەمە تەواوە. ئەمە ناتەواوە",
        words=(
            Word(w="ئەمە", start_ms=0, end_ms=400, conf=0.9),
            Word(w="تەواوە.", start_ms=400, end_ms=900, conf=0.9),
            Word(w="ئەمە", start_ms=1_500, end_ms=2_000, conf=0.9),
            Word(w="ناتەواوە", start_ms=2_000, end_ms=2_600, conf=0.9),
        ),
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
    )
    norm_frag = normalize_transcript(incomplete_raw)
    # Selecting ending fragment (index 1, complete=False) must raise JudgeUnusable
    with pytest.raises(JudgeUnusable, match="incomplete"):
        a_path_a(Api(payload=candidates((0, 1, 0.9))), k=1).discover(norm_frag)
    # Explicit sentence sequence with dangling start fragment must also refuse
    dangling = (
        Sentence(words=(Word(w="چونکە", start_ms=0, end_ms=400, conf=0.9),), complete=False),
        Sentence(words=(Word(w="تەواوە.", start_ms=1_000, end_ms=2_000, conf=0.9),), complete=True),
    )
    with pytest.raises(JudgeUnusable, match="incomplete"):
        a_path_a(Api(payload=candidates((0, 1, 0.9))), k=1).discover(norm_frag, sentences=dangling)
    # Bad bounds / inverted also fail
    with pytest.raises(JudgeUnusable):
        a_path_a(Api(payload=candidates((3, 3, 0.9))), k=1).discover(a_transcript())
    with pytest.raises(JudgeUnusable):
        a_path_a(Api(payload=candidates((2, 1, 0.9))), k=1).discover(a_transcript())


def test_a_score_outside_the_unit_range_is_refused() -> None:
    with pytest.raises(JudgeUnusable, match="score"):
        a_path_a(Api(payload=candidates((0, 0, 4.2)))).discover(a_transcript())


@pytest.mark.parametrize(
    "candidate",
    (
        {"start_sentence": False, "end_sentence": 1, "score": 0.9, "reason_ckb": "گرنگە"},
        {"start_sentence": 0, "end_sentence": True, "score": 0.9, "reason_ckb": "گرنگە"},
        {"start_sentence": 0, "end_sentence": 1, "score": True, "reason_ckb": "گرنگە"},
        {"start_sentence": "0", "end_sentence": 1, "score": 0.9, "reason_ckb": "گرنگە"},
        {"start_sentence": 0, "end_sentence": 1, "score": float("nan"), "reason_ckb": "گرنگە"},
        {"start_sentence": 0, "end_sentence": 1, "score": 10**1_000, "reason_ckb": "گرنگە"},
        {"start_sentence": 0, "end_sentence": 1, "score": 0.9, "reason_ckb": {"گرنگ": True}},
    ),
)
def test_schema_invalid_candidate_numbers_are_refused(candidate: dict[str, Any]) -> None:
    with pytest.raises(JudgeUnusable, match="malformed|outside|range"):
        a_path_a(Api(payload=[candidate])).discover(a_transcript())


# --- ranks, because §8.2 counts them -------------------------------------------------------


def test_ranks_are_dense_and_ordered_by_score() -> None:
    """§8.2 counts Recall@K by rank. A gap or a duplicate makes every K mean something else."""
    found = a_path_a(Api(payload=candidates((0, 0, 0.4), (1, 1, 0.9), (2, 2, 0.6)))).discover(
        a_transcript()
    )
    assert [c.rank for c in found] == [1, 2, 3]
    assert [c.score for c in found] == [0.9, 0.6, 0.4]
    assert [c.span for c in found] == [(2_000, 4_000), (4_200, 6_000), (0, 1_800)]


def test_candidate_ids_are_unique_and_name_their_path() -> None:
    found = a_path_a(Api(payload=candidates((0, 0, 0.4), (1, 1, 0.9)))).discover(a_transcript())
    ids = [c.candidate_id for c in found]
    assert len(set(ids)) == len(ids)
    assert all("verbal" in cid for cid in ids), ids


def test_an_empty_result_is_an_empty_tuple_not_a_failure() -> None:
    """A transcript with nothing worth clipping is a real answer, and §8.2 records it."""
    assert a_path_a(Api(payload=[])).discover(a_transcript()) == ()


@pytest.mark.parametrize("payload", (None, 1, {"start_sentence": 0}))
def test_candidate_container_must_be_a_json_array(payload: object) -> None:
    api = Api()
    api.payload = payload  # type: ignore[assignment]
    with pytest.raises(JudgeUnusable, match="JSON array"):
        a_path_a(api).discover(a_transcript())


def test_every_candidate_must_be_a_json_object() -> None:
    api = Api(payload=[True])  # type: ignore[list-item]
    with pytest.raises(JudgeUnusable, match="JSON object"):
        a_path_a(api).discover(a_transcript())


# --- cost, which §3 is specific about ------------------------------------------------------


def test_the_request_is_path_a_discovery_mode() -> None:
    api = Api()
    request = a_path_a(api).build_request(a_transcript())
    assert request.mode is InputMode.PATH_A_DISCOVERY


def test_tokens_are_counted_before_the_billed_call() -> None:
    api = Api()
    a_path_a(api).discover(a_transcript())
    assert api.calls[0].endswith("countTokens")


def test_a_transcript_too_long_for_one_pass_is_refused_with_the_arithmetic() -> None:
    """§3's own figures put the ceiling at roughly ten source hours.

    §3 says one pass and not a filtered subset, so silently splitting would be this module
    choosing which parts of a ten-hour transcript the Kurdish judge gets to read — the
    decision §3 spends a paragraph forbidding. Refusing names the limit instead.
    """
    api = Api(tokens=250_000)
    with pytest.raises(RequestTooLarge, match="200"):
        a_path_a(api).discover(a_transcript())
    assert "generateContent" not in api.calls


def test_the_estimated_cost_matches_section_3s_figure() -> None:
    """§3: a one-hour transcript is roughly 20K tokens, about $0.04."""
    request = a_path_a(Api(tokens=20_000)).build_request(a_transcript(), tokens=20_000)
    assert request.estimated_cost_usd == pytest.approx(0.04, abs=0.005)


# --- §7, governance, and the schema --------------------------------------------------------


def test_the_shadow_cannot_run_path_a() -> None:
    from hawedit.judge import NotRoutable

    with pytest.raises(NotRoutable):
        a_path_a(Api(), model_id=JUDGE_SHADOW)


def test_confidential_material_without_zero_data_retention_is_refused() -> None:
    """§3's governance box applies hardest here: Path A sends 100% of the transcript."""
    api = Api()
    path_a = a_path_a(api, governance=Governance(confidential=True))
    with pytest.raises(GeminiUnavailable, match="mandatory, not advisory"):
        path_a.discover(a_transcript())
    assert api.calls == [], "nothing may leave the network before the check"


def test_the_schema_is_sent_rather_than_asked_for_in_prose() -> None:
    api = Api()
    a_path_a(api).discover(a_transcript())
    generation = api.bodies[-1]["generationConfig"]
    assert generation["responseSchema"] == CANDIDATE_SCHEMA
    assert generation["temperature"] == 0.0


def test_the_discovery_prompt_states_the_target_duration() -> None:
    """Path A was asked for clips and told nothing about how long a clip is.

    The prompt said "every moment that could stand alone as a short social clip" and the schema
    required only `out_ms > in_ms`, so Gemini answered with 1.1-second spans and D-253's gate
    then refused them as fragments — the system refusing what it asked for. Measured on the real
    75-minute episode: judged spans of 6.3, 22.9, 5.3, 13.9 and 1.1 seconds, and the two
    shortest carried the two highest misleading-edit risks (0.85, 0.90). D-254.

    Asserted against the constants rather than against the words, so the prompt cannot say one
    number while `_span_compliance` measures another.
    """
    api = Api()
    a_path_a(api).discover(a_transcript())

    assert str(MIN_CANDIDATE_SPAN_MS // 1_000) in api.prompt, (
        "the judge was never told the minimum it is being measured against"
    )
    assert str(MAX_CANDIDATE_SPAN_MS // 1_000) in api.prompt, "the judge was never told the maximum"
    assert "second" in api.prompt, "a bare number is not a duration"


def test_the_convenience_function_matches_the_class() -> None:
    api = Api()
    found = discover_verbal(a_transcript(), api_key=KEY, transport=api, sleep=lambda _s: None)
    assert len(found) == 1


def test_path_a_k5_voting_records_all_billed_calls() -> None:
    """B6 & Reality Check Item 8: Billing line count equals K calls, nothing hidden."""
    api = Api(payload=candidates((0, 0, 0.9)))
    path_a = a_path_a(api, k=5)
    candidates_found = path_a.discover(a_transcript())
    assert len(candidates_found) == 1
    # Exactly 5 billed calls were recorded (one for each of the K passes)
    assert len(path_a.billed_calls) == 5
    assert all(c.stage == "discovery" for c in path_a.billed_calls)


def test_path_a_caches_by_transcript_hash(tmp_path: Path) -> None:
    """B6 & Reality Check Item 8: Candidates are cached by transcript sha256."""
    api = Api(payload=candidates((0, 0, 0.9)))
    path_a = a_path_a(api, k=3, cache_dir=tmp_path)
    t = a_transcript()
    found1 = path_a.discover(t)
    assert len(found1) == 1
    assert len(path_a.billed_calls) == 3

    # Second call with new client instance pointing to same cache directory
    api2 = Api(payload=candidates((0, 0, 0.9)))
    path_a2 = a_path_a(api2, k=3, cache_dir=tmp_path)
    found2 = path_a2.discover(t)
    assert len(found2) == 1
    # Zero API calls made because cache hit
    assert len(path_a2.billed_calls) == 0
    assert found1[0].span == found2[0].span


def test_cache_key_binds_sentence_boundaries(tmp_path: Path) -> None:
    """AC7: Changing sentence boundaries invalidates the Path A cache even for equal text."""
    t = a_transcript()
    sents_orig = segment_sentences(t.words)
    api1 = Api(payload=candidates((0, 0, 0.9)))
    found1 = a_path_a(api1, k=2, cache_dir=tmp_path).discover(t, sentences=sents_orig)
    assert len(found1) == 1

    # Shift sentence 0 boundary cleanly while leaving transcript.text_ckb identical
    shifted_words = (
        Word(w="ڕۆژنامەوانی", start_ms=100, end_ms=500, conf=0.95),
        Word(w="کوردی", start_ms=500, end_ms=950, conf=0.95),
        Word(w="لە", start_ms=950, end_ms=1_400, conf=0.94),
        Word(w="هەولێر.", start_ms=1_400, end_ms=1_900, conf=0.94),
    )
    sents_shifted = (Sentence(words=shifted_words, complete=True), *sents_orig[1:])
    api2 = Api(payload=candidates((0, 0, 0.9)))
    path_a2 = a_path_a(api2, k=2, cache_dir=tmp_path)
    found2 = path_a2.discover(t, sentences=sents_shifted)
    assert len(path_a2.billed_calls) == 2
    assert found2[0].span == (100, 1_900)


def test_prompt_marks_incomplete_sentences_and_durations() -> None:
    """Real unpunctuated ASR transcripts must disclose duration and [incomplete] boundaries."""
    t = a_transcript()
    sents = segment_sentences(t.words)
    mixed = (sents[0], Sentence(words=sents[1].words, complete=False), sents[2])
    api = Api(payload=candidates((0, 0, 0.9)))
    a_path_a(api, k=1).discover(t, sentences=mixed)
    assert f"[0] {normalize_sorani(mixed[0].text)} (1.8s)" in api.prompt
    assert f"[1] {normalize_sorani(mixed[1].text)} (2.0s) [incomplete]" in api.prompt
    assert "[0] " in api.prompt and "[1] " in api.prompt
    assert "[incomplete]" in api.prompt


@pytest.mark.parametrize("changed", ["media", "source", "words", "votes", "iou"])
def test_path_a_cache_binds_all_discovery_inputs(tmp_path: Path, changed: str) -> None:
    from dataclasses import replace

    original = a_transcript()
    a_path_a(Api(), k=3, cache_dir=tmp_path).discover(original)
    transcript = original
    options: dict[str, Any] = {"k": 3, "cache_dir": tmp_path}
    if changed == "media":
        transcript = replace(original, media_id="other-media")
    elif changed == "source":
        transcript = replace(original, source_sha256="f" * 64)
    elif changed == "words":
        words = list(original.words)
        words[1] = replace(words[1], end_ms=words[1].end_ms - 10)
        transcript = replace(original, words=tuple(words))
    elif changed == "votes":
        options["min_votes"] = 3
    else:
        options["iou_threshold"] = 0.8
    api = Api()
    found = a_path_a(api, **options).discover(transcript)
    assert len(api.calls) > 0
    assert found[0].media_id == transcript.media_id


@pytest.mark.parametrize(
    "field,value",
    [
        ("media_id", "other-media"),
        ("in_ms", -500),
        ("out_ms", 500),
        ("rank", True),
        ("score", True),
        ("score", float("nan")),
        ("path", "visual"),
    ],
)
def test_path_a_cache_rejects_wrong_media_and_unaligned_spans(
    tmp_path: Path, field: str, value: Any
) -> None:
    transcript = a_transcript()
    a_path_a(Api(), k=3, cache_dir=tmp_path).discover(transcript)
    cache = next(tmp_path.glob("path_a_*.json"))
    records = json.loads(cache.read_text(encoding="utf-8"))
    records[0][field] = value
    cache.write_text(json.dumps(records), encoding="utf-8")
    api = Api()
    with pytest.raises(JudgeUnusable, match="cache refused"):
        a_path_a(api, k=3, cache_dir=tmp_path).discover(transcript)
    assert api.calls == []  # Corruption must not silently incur fresh paid calls.


def test_numbered_discovery_keeps_moments_beyond_word_four_thousand() -> None:
    from hawedit.transcripts import NormalizedTranscript

    words = tuple(Word("دەق.", i * 1000, i * 1000 + 800, 0.99) for i in range(4100))
    transcript = NormalizedTranscript("long-media", " ".join(w.w for w in words), "a" * 64, words)
    sentences = tuple(Sentence((word,), complete=True) for word in words)
    api = Api(payload=candidates((4099, 4099, 0.9)))
    discovery = a_path_a(api, k=1)
    found = discovery.discover(transcript, sentences=sentences)
    assert "[4099]" in api.prompt
    assert len(found) == 1
    assert found[0].span == (words[4099].start_ms, words[4099].end_ms)


def test_path_a_cache_changes_when_the_prompt_protocol_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hawedit.path_a as module

    transcript = a_transcript()
    a_path_a(Api(), k=3, cache_dir=tmp_path).discover(transcript)
    monkeypatch.setattr(
        module, "_PROMPT", module._PROMPT + "\nExplicit updated discovery instructions."
    )
    api = Api()
    a_path_a(api, k=3, cache_dir=tmp_path).discover(transcript)
    assert len(api.calls) > 0
