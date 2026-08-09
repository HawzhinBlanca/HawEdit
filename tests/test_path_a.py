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
from typing import Any

import pytest

from hawedit.clip import DiscoveryPath
from hawedit.discovery import merge_candidates
from hawedit.gemini import GeminiUnavailable, Governance, JudgeUnusable
from hawedit.judge import InputMode, RequestTooLarge
from hawedit.path_a import CANDIDATE_SCHEMA, PathADiscovery, discover_verbal
from hawedit.transcripts import AsrProvenance, RawTranscript, Word, normalize_transcript

KEY = "test-key-not-real"

TEXT = "ڕۆژنامەوانی کوردی لە هەولێر. ئەمە زۆر گرنگە بۆ ئێمە. با باسی بکەین."


def a_transcript(media_id: str = "ep01") -> Any:
    raw = RawTranscript(
        media_id=media_id,
        text_ckb=TEXT,
        words=(
            Word(w="ڕۆژنامەوانی", start_ms=0, end_ms=900, conf=0.95),
            Word(w="کوردی", start_ms=900, end_ms=1_800, conf=0.94),
            Word(w="ئەمە", start_ms=2_000, end_ms=2_500, conf=0.93),
            Word(w="گرنگە", start_ms=2_500, end_ms=4_000, conf=0.92),
            Word(w="بکەین.", start_ms=4_200, end_ms=6_000, conf=0.91),
        ),
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
    )
    return normalize_transcript(raw)


def candidates(*spans: tuple[int, int, float]) -> list[dict[str, Any]]:
    return [
        {"in_ms": in_ms, "out_ms": out_ms, "score": score, "reason_ckb": "گرنگە"}
        for in_ms, out_ms, score in spans
    ]


class Api:
    """A recording transport answering countTokens and generateContent."""

    def __init__(self, tokens: int = 5_000, payload: list[dict[str, Any]] | None = None) -> None:
        self.tokens = tokens
        self.payload = payload if payload is not None else candidates((0, 1_800, 0.9))
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
    """§3: "the full normalized Sorani transcript […] Not a filtered subset."

    Sending a sample, or only what a local heuristic liked, is the failure the dual path was
    designed to prevent — and it would be invisible, because the candidates that came back
    would still look perfectly reasonable.

    Asserted on the WHOLE `text_ckb`, not on sampled fragments. The three fragments this test
    used to check — ڕۆژنامەوانی, گرنگە, بکەین — are all entries in the fixture's `words` tuple, so
    `_timing_table` renders every one of them above the transcript and `fragment in api.prompt`
    was satisfied by the timing table alone. Measured: deleting the transcript text from the
    prompt entirely left `tests/test_path_a.py` at 21 passed and the full suite at `exit=0,
    0 FAILED`. The test could not see the thing it was written to protect. D-095.
    """
    transcript = a_transcript()
    api = Api()
    a_path_a(api).discover(transcript)

    assert transcript.text_ckb in api.prompt, (
        "the normalized transcript was not sent verbatim. §3 requires the full text, and a "
        "subset would be invisible in the output because the candidates still look reasonable."
    )
    # The fragments that discriminate: present in `text_ckb` and absent from `words`, so only
    # the transcript itself can put them in the prompt.
    words = {word.w.strip(".،") for word in transcript.words}
    discriminating = [
        fragment
        for fragment in transcript.text_ckb.replace(".", " ").split()
        if fragment.strip(".،") not in words
    ]
    assert discriminating, "the fixture no longer has text outside `words`; this test is blind"
    for fragment in discriminating:
        assert fragment in api.prompt, f"{fragment!r} was withheld from the judge"

    # The control: the timing table must still be there. Otherwise a prompt that dropped
    # timings and kept the text would pass everything above.
    assert "0-900" in api.prompt, "the timing table vanished"


def test_a_verbal_only_moment_is_discoverable_because_nothing_pre_filtered() -> None:
    """The whole point: a talking head with no motion is invisible to every local component."""
    api = Api(payload=candidates((2_000, 4_000, 0.95)))
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
    found = a_path_a(Api(payload=candidates((0, 900, 0.8), (2_000, 4_000, 0.7)))).discover(
        a_transcript("ep-42")
    )
    assert {c.media_id for c in found} == {"ep-42"}
    assert {c.path for c in found} == {DiscoveryPath.VERBAL}


def test_path_a_output_feeds_the_union_directly() -> None:
    """The seam `discovery.py` was built for, closed."""
    found = a_path_a(Api(payload=candidates((0, 1_800, 0.9)))).discover(a_transcript())
    merged = merge_candidates(list(found), [])
    assert len(merged) == 1
    assert merged[0].discovery_path is DiscoveryPath.VERBAL
    assert merged[0].verbal_score == 0.9


# --- what a model gets wrong about time ----------------------------------------------------


def test_a_candidate_past_the_end_of_the_transcript_is_refused() -> None:
    """A model asked for millisecond spans will occasionally invent one past the media."""
    with pytest.raises(JudgeUnusable, match="outside the transcript"):
        a_path_a(Api(payload=candidates((0, 999_000, 0.9)))).discover(a_transcript())


def test_a_candidate_before_the_start_is_refused() -> None:
    with pytest.raises(JudgeUnusable, match="outside the transcript"):
        a_path_a(Api(payload=candidates((-500, 1_000, 0.9)))).discover(a_transcript())


def test_a_zero_length_candidate_is_refused() -> None:
    with pytest.raises(JudgeUnusable, match="length"):
        a_path_a(Api(payload=candidates((1_000, 1_000, 0.9)))).discover(a_transcript())


def test_an_inverted_candidate_is_refused() -> None:
    with pytest.raises(JudgeUnusable, match="length"):
        a_path_a(Api(payload=candidates((4_000, 1_000, 0.9)))).discover(a_transcript())


def test_a_score_outside_the_unit_range_is_refused() -> None:
    with pytest.raises(JudgeUnusable, match="score"):
        a_path_a(Api(payload=candidates((0, 900, 4.2)))).discover(a_transcript())


# --- ranks, because §8.2 counts them -------------------------------------------------------


def test_ranks_are_dense_and_ordered_by_score() -> None:
    """§8.2 counts Recall@K by rank. A gap or a duplicate makes every K mean something else."""
    found = a_path_a(
        Api(payload=candidates((0, 900, 0.4), (2_000, 4_000, 0.9), (4_200, 6_000, 0.6)))
    ).discover(a_transcript())
    assert [c.rank for c in found] == [1, 2, 3]
    assert [c.score for c in found] == [0.9, 0.6, 0.4]


def test_candidate_ids_are_unique_and_name_their_path() -> None:
    found = a_path_a(Api(payload=candidates((0, 900, 0.4), (2_000, 4_000, 0.9)))).discover(
        a_transcript()
    )
    ids = [c.candidate_id for c in found]
    assert len(set(ids)) == len(ids)
    assert all("verbal" in cid for cid in ids), ids


def test_an_empty_result_is_an_empty_tuple_not_a_failure() -> None:
    """A transcript with nothing worth clipping is a real answer, and §8.2 records it."""
    assert a_path_a(Api(payload=[])).discover(a_transcript()) == ()


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
        a_path_a(Api(), model_id="gemini-3.1-pro")


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


def test_the_convenience_function_matches_the_class() -> None:
    api = Api()
    found = discover_verbal(a_transcript(), api_key=KEY, transport=api, sleep=lambda _s: None)
    assert len(found) == 1
