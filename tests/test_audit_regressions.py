"""Regressions for the release-blocking audit of 2026-08-07.

Ten findings were reported; seven reproduced exactly as described and are fixed here. Each
test names the finding it locks down. They live together rather than scattered through the
suite because the audit is a single event worth being able to re-run as a unit — and because
several of these bugs shared one root cause: **a check that accepted the shape of an answer
without checking its content**. Substring instead of flag, truthiness instead of boolean,
registry membership instead of role, absence instead of refusal.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from hawedit.boundary import Boundary, BoundaryInputs, fuse_boundary
from hawedit.captions import CaptionStyle, MissingRtlStack, assert_rtl_stack, build_ass
from hawedit.clip import Clip, ClipTranscript, DiscoveryPath, Editorial, Qc
from hawedit.corpus import Condition, CorpusItem, Dialect
from hawedit.registry import WrongRole
from hawedit.sentences import Sentence
from hawedit.transcripts import AsrProvenance, RawTranscript, TranscriptStore, Word


def a_boundary() -> Boundary:
    return fuse_boundary(
        BoundaryInputs(anchor_in_ms=1_000, anchor_out_ms=5_000, sentence_complete=True)
    )


def a_transcript() -> ClipTranscript:
    return ClipTranscript(
        raw_ckb="ئەمە",
        norm_ckb="ئەمە",
        en_aux=None,
        words=(),
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2"),
    )


# --- #4 the RTL check certified a build that explicitly disabled the libraries ----------


def test_disable_flags_are_not_read_as_enable_flags() -> None:
    """`--disable-libass` contains the substring "libass". The old check passed it."""
    with pytest.raises(MissingRtlStack):
        assert_rtl_stack("configuration: --disable-libass --disable-harfbuzz --disable-fribidi", "")


def test_a_partially_disabled_build_is_refused() -> None:
    with pytest.raises(MissingRtlStack, match="HarfBuzz"):
        assert_rtl_stack(
            "configuration: --enable-libass --enable-libfribidi --disable-libharfbuzz", ""
        )


def test_a_genuinely_enabled_build_still_passes() -> None:
    report = assert_rtl_stack(
        "configuration: --enable-libass --enable-libharfbuzz --enable-libfribidi", ""
    )
    assert report.libass and report.harfbuzz and report.fribidi


def test_linked_libraries_are_matched_as_library_names() -> None:
    report = assert_rtl_stack(
        "configuration: --enable-libass",
        "libharfbuzz.so.0 => /usr/lib/libharfbuzz.so.0\nlibfribidi.so.0 => /usr/lib/x.so",
    )
    assert report.harfbuzz_source == "linked libraries"


# --- #3 the render gate accepted absence as approval ------------------------------------


def test_a_clip_with_no_qc_record_is_refused() -> None:
    boundary = a_boundary()
    clip = Clip(
        clip_id="c",
        media_id="m",
        in_ms=boundary.final_in_ms,
        out_ms=boundary.final_out_ms,
        discovery_path=DiscoveryPath.VERBAL,
        boundary=boundary,
        transcript=a_transcript(),
        editorial=None,
        output=None,
        qc=None,
    )
    with pytest.raises(ValueError, match="no QC record"):
        clip.assert_renderable()


def test_a_string_false_does_not_deserialize_as_true() -> None:
    """`bool("false")` is True. A JSON document could disable the invariant by asserting it."""
    payload = a_boundary().to_dict()
    payload["sentence_complete"] = "false"
    with pytest.raises(ValueError, match="boolean"):
        Boundary.from_dict(payload)


def test_a_string_false_qc_flag_is_refused() -> None:
    with pytest.raises(ValueError, match="boolean"):
        Qc.from_dict({"auto_pass": "false", "flags": [], "human_reviewed": False})


def test_a_real_boolean_still_round_trips() -> None:
    boundary = a_boundary()
    assert Boundary.from_dict(json.loads(json.dumps(boundary.to_dict()))) == boundary


# --- #8 registry membership was mistaken for suitability --------------------------------


def test_a_scene_detector_cannot_be_an_asr_adapter() -> None:
    from hawedit.asr import validate_adapter

    class NotAnAsr:
        model_id = "PySceneDetect"

        def transcribe(self, path: Path, duration_s: float) -> None: ...

    with pytest.raises(WrongRole, match="ASR adapter"):
        validate_adapter(NotAnAsr())  # type: ignore[arg-type]


def test_a_scene_detector_cannot_be_transcript_provenance() -> None:
    with pytest.raises(WrongRole, match="canonical ASR"):
        AsrProvenance(canonical="PySceneDetect")


def test_a_scene_detector_cannot_be_the_editorial_judge() -> None:
    with pytest.raises(WrongRole, match="editorial judge"):
        Editorial(
            hook_score=0.5,
            self_contained=True,
            meaning_fidelity=0.5,
            misleading_edit_risk=0.0,
            cultural_landing=0.5,
            narrative_role="payoff",
            judge="PySceneDetect",
        )


def test_the_real_models_still_fill_their_own_roles() -> None:
    AsrProvenance(
        canonical="omniASR_LLM_7B_v2", validated_by="rzgar/qwen3-asr-sorani-kurdish-ckb-v1"
    )


# --- #9 media_id reached the filesystem unchecked ---------------------------------------


def test_a_media_id_cannot_escape_the_store(tmp_path: Path) -> None:
    store = TranscriptStore(tmp_path)
    with pytest.raises(ValueError, match="path separator"):
        store.raw_path("../../etc/evil")


def test_a_media_id_cannot_contain_a_separator(tmp_path: Path) -> None:
    store = TranscriptStore(tmp_path)
    with pytest.raises(ValueError, match="path separator"):
        store.raw_path("a/b")


def test_an_empty_media_id_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="empty"):
        TranscriptStore(tmp_path).raw_path("")


def test_write_once_is_atomic_not_check_then_write(tmp_path: Path) -> None:
    """`exists()` then `write` is a race two ingest workers can both win."""
    from hawedit.transcripts import RawTranscriptImmutable

    store = TranscriptStore(tmp_path)
    raw = RawTranscript(
        media_id="m1", text_ckb="ئەمە", words=(), asr=AsrProvenance(canonical="omniASR_LLM_7B_v2")
    )
    store.write_raw(raw)
    with pytest.raises(RawTranscriptImmutable):
        store.write_raw(raw)


# --- #6 alignment ground truth vanished on a round trip ---------------------------------


def test_reference_word_timings_survive_serialization() -> None:
    item = CorpusItem(
        item_id="i",
        audio_path="a.wav",
        reference_ckb="ئەمە",
        dialect=Dialect.HEWLER,
        conditions=frozenset({Condition.FORMAL_NEWS}),
        duration_s=10.0,
        reference_words=(Word(w="ئەمە", start_ms=0, end_ms=100, conf=0.9),),
    )
    restored = CorpusItem.from_dict(json.loads(json.dumps(item.to_dict())))
    assert restored.reference_words == item.reference_words
    assert restored == item


# --- #7 karaoke drifted by the length of every pause ------------------------------------


def test_karaoke_timings_cover_the_silence_between_words() -> None:
    """Word durations alone leave the highlight running ahead after each gap."""
    spoken = Sentence(
        words=(
            Word(w="یەک", start_ms=0, end_ms=500, conf=0.9),
            Word(w="دوو", start_ms=1_500, end_ms=2_000, conf=0.9),  # 1 s gap
        ),
        complete=True,
    )
    ass = build_ass((spoken,), style=CaptionStyle.WORD_HIGHLIGHT)
    events = ass.split("[Events]")[1]
    assert "{\\kf100}" in events, "the 1 s pause must be held by its own karaoke span"
    total = sum(int(n) for n in re.findall(r"\\kf(\d+)", events))
    assert total == 200, "karaoke spans must tile the full 2 s line, gaps included"
