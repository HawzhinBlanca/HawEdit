"""Routing provenance contracts using model doubles, not acoustic accuracy evidence."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

import test_pipeline as pipeline_fixtures
from hawedit.asr import (
    AsrProductionFailure,
    OmniAsrProducer,
    SegmentTranscript,
    _assemble_canonical_transcript,
    _validate_hard_segments,
    transcribe_prepared_segments,
)
from hawedit.asr_worker import run_request
from hawedit.captions import find_ffmpeg
from hawedit.escalation import scores_from_transcript, select_for_validation
from hawedit.transcripts import (
    AsrProvenance,
    RawTranscript,
    RawTranscriptImmutable,
    TranscriptStore,
    Word,
)
from test_asr_stop import RegionBackend, RegionValidator, prepared_regions, worker_request


def traced(
    root: Path, *, failure: str = "", no_route: bool = False
) -> tuple[RawTranscript, RegionBackend, RegionValidator]:
    class Backend(RegionBackend):
        def transcribe_segment(self, audio_path: Path, duration_s: float) -> SegmentTranscript:
            item = super().transcribe_segment(audio_path, duration_s)
            if no_route:
                item = replace(item, ctc_text=item.text_raw)
                self.results[-1] = item
            return item

    backend = Backend(fail_alignment=0 if failure == "alignment" else -1)
    validator = RegionValidator(fail_at=0 if failure == "transcription" else -1)
    initial, gaps = transcribe_prepared_segments(backend, prepared_regions(root))

    def factory() -> RegionValidator:
        if no_route:
            raise AssertionError("a non-routed batch loaded its validator")
        return validator

    results, validated_by, rejected, origins = _validate_hard_segments(initial, backend, factory)
    raw = _assemble_canonical_transcript(
        "episode",
        results,
        gaps,
        validated_by=validated_by,
        rejected_validator_corrections=rejected,
        segment_origins=origins,
    )
    return raw, backend, validator


def test_origin_retains_pre_correction_routing_inputs(tmp_path: Path) -> None:
    raw, backend, _ = traced(tmp_path)
    assert raw.segment_origins is not None
    for index, origin in enumerate(raw.segment_origins):
        original = backend.results[index]
        assert origin.draft.llm_text == original.text_raw
        assert origin.draft.ctc_text == original.ctc_text
        assert origin.draft.mean_logprob == -0.5
        assert origin.draft.start_ms == index * 1000
        assert origin.draft.end_ms == (index + 1) * 1000
        assert origin.selected.mean_logprob == -0.2
        assert origin.escalated is True
        assert "disagree materially" in origin.route_reason


def test_origin_records_actual_validator_selection(tmp_path: Path) -> None:
    raw, _, validator = traced(tmp_path)
    assert raw.segment_origins is not None
    assert len(validator.calls) == len(raw.segment_origins) == 3
    for index, origin in enumerate(raw.segment_origins):
        assert origin.outcome == "validator-selected"
        assert origin.validator == raw.asr.validated_by == validator.model_id
        assert origin.validator_text == origin.selected.llm_text
        assert origin.rejection_reason is None
        assert origin.selected_words[0].start_ms == index * 1000 + 10
    assert (
        tuple(word for origin in raw.segment_origins for word in origin.selected_words) == raw.words
    )


def test_origin_no_route_does_not_load_validator(tmp_path: Path) -> None:
    raw, backend, validator = traced(tmp_path, no_route=True)
    assert raw.segment_origins is not None
    assert validator.calls == backend.align_calls == []
    assert raw.asr.validated_by is None
    for origin in raw.segment_origins:
        assert origin.outcome == "not-routed"
        assert origin.escalated is False
        assert origin.draft == origin.selected
        assert origin.validator is origin.validator_text is origin.rejection_reason is None


@pytest.mark.parametrize("failure", ["transcription", "alignment"])
def test_origin_refused_correction_retains_draft(tmp_path: Path, failure: str) -> None:
    raw, backend, validator = traced(tmp_path, failure=failure)
    assert raw.segment_origins is not None
    origin = raw.segment_origins[0]
    assert origin.outcome == f"validator-{failure}-refused"
    assert origin.selected == origin.draft
    assert origin.selected_words == backend.results[0].words
    assert origin.validator == validator.model_id
    assert origin.rejection_reason == raw.rejected_validator_corrections[0].reason
    assert (origin.validator_text is None) == (failure == "transcription")


def test_origin_production_refusal_does_not_claim_selected_correction(tmp_path: Path) -> None:
    backend = RegionBackend()
    initial, _ = transcribe_prepared_segments(backend, prepared_regions(tmp_path))
    with pytest.raises(AsrProductionFailure) as caught:
        _validate_hard_segments(
            initial, backend, lambda: RegionValidator(fail_at=1), stop_on_failure=True
        )
    results = caught.value.diagnostic_results
    raw = _assemble_canonical_transcript("episode", results)
    assert raw.segment_origins is None
    assert raw.asr.validated_by is None
    assert raw.words[0] == backend.results[0].words[0]


def test_origin_native_and_worker_parity(tmp_path: Path) -> None:
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    native = OmniAsrProducer(RegionBackend(), RegionValidator()).transcribe(
        "episode",
        pipeline_fixtures.FIXTURE,
        tuple(SimpleNamespace(start_ms=i * 1000, end_ms=(i + 1) * 1000) for i in range(3)),
        tmp_path / "native",
        ffmpeg=ffmpeg,
    )
    worker_dir = tmp_path / "worker"
    worker_dir.mkdir()
    worker = run_request(
        worker_request(worker_dir), worker_dir / "output.json", RegionBackend(), RegionValidator()
    )
    assert native.segment_origins is not None
    assert native.segment_origins == worker.segment_origins
    assert (
        native
        == worker
        == RawTranscript.from_json((worker_dir / "output.json").read_text(encoding="utf-8"))
    )


def test_origin_roundtrip_and_immutable_storage(tmp_path: Path) -> None:
    raw, _, _ = traced(tmp_path)
    assert raw.segment_origins is not None
    assert RawTranscript.from_json(raw.to_json()) == raw
    with pytest.raises(FrozenInstanceError):
        cast(Any, raw.segment_origins[0]).outcome = "not-routed"
    store = TranscriptStore(tmp_path / "transcripts")
    path = store.write_raw(raw)
    before = path.read_bytes()
    assert store.read_raw(raw.media_id) == raw
    with pytest.raises(RawTranscriptImmutable):
        store.write_raw(raw)
    assert path.read_bytes() == before


def test_origin_legacy_serialization_hash_unchanged() -> None:
    raw = RawTranscript(
        "legacy",
        "draft",
        (Word("draft", 0, 500, 0.8),),
        AsrProvenance("omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
    )
    assert "segment_origins" not in json.loads(raw.to_json())
    assert raw.sha256() == "49c30482f7301daea5e1436e618933dc57b950ba51a1243390a4fa3672d1d3be"
    assert RawTranscript.from_json(raw.to_json()) == raw
    historical = replace(raw, asr=replace(raw.asr, validated_by=RegionValidator.model_id))
    assert RawTranscript.from_json(historical.to_json()).segment_origins is None
    assert "segment_origins" not in json.loads(historical.to_json())


@pytest.mark.parametrize(
    "damage",
    [
        "empty",
        "null",
        "duplicate",
        "reversed",
        "foreign",
        "boolean",
        "reason",
        "outcome",
        "response",
        "extra",
        "nan",
        "missing-validator",
        "outcome-type",
        "empty-words",
        "draft-boolean-confidence",
    ],
)
def test_origin_invalid_record_refuses(tmp_path: Path, damage: str) -> None:
    raw, _, _ = traced(tmp_path)
    data: dict[str, Any] = json.loads(raw.to_json())
    origins = data["segment_origins"]
    if damage == "empty":
        data["segment_origins"] = []
    elif damage == "null":
        data["segment_origins"] = None
    elif damage == "duplicate":
        origins.append(origins[0])
    elif damage == "reversed":
        origins.reverse()
    elif damage == "foreign":
        origins[0]["validator"] = "scene-detector"
    elif damage == "boolean":
        origins[0]["escalated"] = 1
    elif damage == "reason":
        origins[0]["route_reason"] = "invented routing"
    elif damage == "outcome":
        origins[0]["outcome"] = "not-routed"
    elif damage == "response":
        origins[0]["validator_text"] = None
    elif damage == "extra":
        origins[0]["unobserved_revision"] = "fake"
    elif damage == "nan":
        origins[0]["draft"]["mean_logprob"] = float("nan")
    elif damage == "missing-validator":
        origins[0]["validator"] = None
    elif damage == "outcome-type":
        origins[0]["outcome"] = []
    elif damage == "empty-words":
        origins[0]["selected_words"] = []
    elif damage == "draft-boolean-confidence":
        origins[0]["draft"]["mean_logprob"] = False
    with pytest.raises(ValueError):
        RawTranscript.from_json(json.dumps(data))


@pytest.mark.parametrize(
    "damage",
    ["text", "word", "confidence", "span", "missing", "global-validator", "rejection", "aggregate"],
)
def test_origin_selected_binding_refuses(tmp_path: Path, damage: str) -> None:
    raw, _, _ = traced(tmp_path)
    data: dict[str, Any] = json.loads(raw.to_json())
    origin = data["segment_origins"][0]
    if damage == "text":
        origin["selected"]["llm_text"] += " extra"
    elif damage == "word":
        origin["selected_words"][0]["end_ms"] += 1
    elif damage == "confidence":
        origin["selected"]["mean_logprob"] = -0.1
    elif damage == "span":
        origin["selected"]["end_ms"] += 1
    elif damage == "missing":
        data["segment_origins"].pop()
    elif damage == "global-validator":
        data["asr"]["validated_by"] = None
    elif damage == "rejection":
        origin["rejection_reason"] = "invented failure"
    elif damage == "aggregate":
        data["asr"]["mean_logprob"] = -0.1
    with pytest.raises(ValueError):
        RawTranscript.from_json(json.dumps(data))


def test_origin_policy_replay_uses_draft_inputs(tmp_path: Path) -> None:
    raw, _, _ = traced(tmp_path)
    scores = scores_from_transcript(raw)
    assert all(score.mean_logprob == -0.5 for score in scores)
    assert raw.segment_origins is not None
    for score, origin, decision in zip(
        scores, raw.segment_origins, select_for_validation(scores), strict=True
    ):
        assert score.llm_text == origin.draft.llm_text
        assert score.ctc_text == origin.draft.ctc_text
        assert decision.escalate == origin.escalated
        assert decision.reason == origin.route_reason


@pytest.mark.parametrize("response", [None, ""])
def test_origin_invalid_or_empty_validator_response_is_not_success(
    tmp_path: Path, response: str | None
) -> None:
    class Validator(RegionValidator):
        def transcribe_segment(self, audio_path: Path, duration_s: float) -> str:
            return cast(str, response)

    backend = RegionBackend()
    initial, gaps = transcribe_prepared_segments(backend, prepared_regions(tmp_path))
    results, validated_by, rejected, origins = _validate_hard_segments(initial, backend, Validator)
    raw = _assemble_canonical_transcript(
        "episode",
        results,
        gaps,
        validated_by=validated_by,
        rejected_validator_corrections=rejected,
        segment_origins=origins,
    )
    assert raw.asr.validated_by is None
    assert len(rejected) == len(origins) == 3
    assert raw == RawTranscript.from_json(raw.to_json())
    assert all(origin.selected == origin.draft for origin in origins)
    assert all(origin.validator_text == response for origin in origins)
    assert all(
        origin.outcome
        == (
            "validator-transcription-refused" if response is None else "validator-alignment-refused"
        )
        for origin in origins
    )


def test_origin_mixed_batch_keeps_non_routed_segments(tmp_path: Path) -> None:
    class Backend(RegionBackend):
        def transcribe_segment(self, audio_path: Path, duration_s: float) -> SegmentTranscript:
            result = super().transcribe_segment(audio_path, duration_s)
            return replace(result, ctc_text=result.text_raw, mean_logprob=-4.0 + len(self.calls))

    prepared = prepared_regions(tmp_path)
    batch = (*prepared, replace(prepared[-1], start_ms=3000, end_ms=4000))
    backend, validator = Backend(), RegionValidator()
    initial, gaps = transcribe_prepared_segments(backend, batch)
    results, validated_by, rejected, origins = _validate_hard_segments(
        initial, backend, lambda: validator
    )
    raw = _assemble_canonical_transcript(
        "episode",
        results,
        gaps,
        validated_by=validated_by,
        rejected_validator_corrections=rejected,
        segment_origins=origins,
    )
    assert len(validator.calls) == len(backend.align_calls) == 1
    assert [origin.outcome for origin in origins] == ["validator-selected", *("not-routed",) * 3]
    assert all(origin.validator is None for origin in origins[1:])
    assert RawTranscript.from_json(raw.to_json()) == raw
