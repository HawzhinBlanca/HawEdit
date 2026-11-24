"""Validator off-default and paired WER/RTF ablation contracts (`specs/b6-validator-ablation`)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hawedit.escalation import SegmentScore, select_for_validation
from hawedit.pipeline import PipelineRun, _print_report
from hawedit.transcripts import (
    AsrProvenance,
    RawTranscript,
    SegmentConfidence,
    SegmentOrigin,
    Word,
)


def _disabled_origins() -> tuple[RawTranscript, tuple[SegmentOrigin, ...]]:
    confidences = (
        SegmentConfidence(0, 1000, -0.5, "کوردی.", "جیاواز."),
        SegmentConfidence(1000, 2000, -0.4, "سڵاو.", "سڵاو."),
        SegmentConfidence(2000, 3000, -0.3, "باشە.", "باشە."),
        SegmentConfidence(3000, 4000, -0.8, "دوایی.", "دوایی."),
    )
    scores = tuple(
        SegmentScore(
            segment_id=f"{c.start_ms}-{c.end_ms}",
            mean_logprob=c.mean_logprob,
            llm_text=c.llm_text,
            ctc_text=c.ctc_text,
            duration_s=(c.end_ms - c.start_ms) / 1000.0,
        )
        for c in confidences
    )
    decisions = select_for_validation(scores)
    assert any(d.escalate for d in decisions)

    words_by_seg = (
        (Word("کوردی.", 0, 500, 0.8),),
        (Word("سڵاو.", 1000, 1500, 0.8),),
        (Word("باشە.", 2000, 2500, 0.8),),
        (Word("دوایی.", 3000, 3500, 0.8),),
    )
    origins = tuple(
        SegmentOrigin(
            draft=c,
            selected=c,
            selected_words=w,
            escalated=False,
            route_reason=d.reason,
            outcome="validator-disabled",
        )
        for c, w, d in zip(confidences, words_by_seg, decisions, strict=True)
    )
    raw = RawTranscript(
        media_id="ablation-ep",
        text_ckb="\n".join(c.llm_text for c in confidences),
        words=tuple(word for group in words_by_seg for word in group),
        asr=AsrProvenance(
            "omniASR_LLM_7B_v2",
            aligner="ctc_viterbi",
            validated_by=None,
            mean_logprob=sum(c.mean_logprob for c in confidences) / len(confidences),
        ),
        segment_confidence=confidences,
        segment_origins=origins,
    )
    return raw, origins


def test_segment_origins_record_validator_disabled_uniformly_and_refuse_mixed_batches() -> None:
    raw, origins = _disabled_origins()
    assert raw.asr.validated_by is None
    assert all(o.outcome == "validator-disabled" and not o.escalated for o in origins)
    assert RawTranscript.from_json(raw.to_json()) == raw

    mixed = (
        origins[0],
        SegmentOrigin(
            draft=origins[1].draft,
            selected=origins[1].selected,
            selected_words=origins[1].selected_words,
            escalated=False,
            route_reason=origins[1].route_reason,
            outcome="not-routed",
        ),
        origins[2],
        origins[3],
    )
    with pytest.raises(ValueError, match="mix|validator-disabled"):
        RawTranscript(
            media_id=raw.media_id,
            text_ckb=raw.text_ckb,
            words=raw.words,
            asr=raw.asr,
            segment_confidence=raw.segment_confidence,
            segment_origins=mixed,
        )


def test_pipeline_report_never_claims_escalations_when_validator_disabled(
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw, _ = _disabled_origins()
    run = PipelineRun("ablation-ep", "not-media", "not-work", raw_diagnostics=raw)
    payload = json.loads(json.dumps(run.to_dict(), allow_nan=False))
    assert payload["asr_routing_status"] == "validator-disabled"
    assert payload["escalation"]["validator_enabled"] is False
    assert payload["escalation"]["scored_segments"] == 4
    assert payload["escalation"]["escalated"] == 0
    assert payload["escalation"]["would_escalate"] == 2
    assert payload["escalation"]["segments"] == []
    assert payload["escalation_diagnostics"] is None

    _print_report(run)
    out = capsys.readouterr().out
    stage1_line = next(line for line in out.splitlines() if line.startswith("stage 1"))
    assert "validator disabled" in stage1_line
    assert "0/4" in stage1_line


def test_cli_defaults_validator_off_and_opts_in_with_validate_asr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hawedit.asr as asr_mod
    from hawedit.pipeline import _build_and_run, build_parser

    seen_flags: list[bool] = []
    stub_raw, _ = _disabled_origins()

    class StubProducer:
        admission_policy = "stub"

        def transcribe(self, *args: object, **kwargs: object) -> RawTranscript:
            raise RuntimeError("stop after producer construction")

    def fake_factory(
        *args: object, validate_hard_segments: bool = False, **kwargs: object
    ) -> StubProducer:
        seen_flags.append(validate_hard_segments)
        return StubProducer()

    monkeypatch.setattr(asr_mod, "create_omni_asr_producer", fake_factory)

    from test_pipeline import FIXTURE

    for suffix, extra in (
        ("default", []),
        ("explicit_off", ["--no-validate-asr"]),
        ("explicit_on", ["--validate-asr"]),
    ):
        args = build_parser().parse_args(
            [str(FIXTURE), "--work-dir", str(tmp_path / suffix), "--omni-asr", *extra]
        )
        _build_and_run(args)
    assert seen_flags == [False, False, True]


def test_native_and_wsl_producers_skip_validator_weights_when_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import contextlib
    import subprocess
    from collections.abc import Iterator
    from dataclasses import replace

    import hawedit.asr as asr_mod
    from hawedit.asr import OmniAsrProducer, WslOmniAsrProducer, create_omni_asr_producer
    from hawedit.captions import find_ffmpeg
    from hawedit.models import ModelStore
    from test_asr_context import regions, source_pcm
    from test_asr_stop import RegionBackend

    default_local = create_omni_asr_producer("local")
    default_wsl = create_omni_asr_producer("wsl")
    assert isinstance(default_local, OmniAsrProducer)
    assert isinstance(default_wsl, WslOmniAsrProducer)
    assert default_local.validate_hard_segments is False
    assert default_wsl.validate_hard_segments is False
    assert default_local.admission_policy == default_wsl.admission_policy
    assert default_local.admission_policy is not None
    assert default_local.admission_policy.endswith("+validator-off")

    audio = tmp_path / "source.wav"
    source_pcm(audio)
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None

    def fail_store(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("ModelStore validator resolution must not run when validator is off")

    monkeypatch.setattr(ModelStore, "assert_available", fail_store)
    monkeypatch.setattr(ModelStore, "path_for", fail_store)

    @contextlib.contextmanager
    def fail_lease(*_args: object, **_kwargs: object) -> Iterator[Path]:
        raise AssertionError("verified_checkpoint_access must not run when validator is off")
        yield tmp_path  # pragma: no cover

    monkeypatch.setattr(asr_mod, "verified_checkpoint_access", fail_lease)

    backend = RegionBackend()
    native = OmniAsrProducer(
        backend, context_grouping=True, validate_hard_segments=False
    ).transcribe("ablation-ep", audio, regions((0, 500), (600, 1100)), tmp_path / "native", ffmpeg)
    assert len(backend.calls) == 1
    assert backend.align_calls == []
    assert native.asr.validated_by is None
    assert native.segment_origins is not None
    assert all(
        o.outcome == "validator-disabled" and not o.escalated for o in native.segment_origins
    )

    disabled_raw, _ = _disabled_origins()
    disabled_raw = replace(disabled_raw, media_id="ablation-ep")
    stage1 = tmp_path / "wsl_stage1"
    real_run = subprocess.run
    seen_requests: list[dict[str, object]] = []

    class TransportProducer(WslOmniAsrProducer):
        def _runtime(self) -> tuple[str, str]:
            return "/test/python", "/test/source"

        def _prefix(self) -> list[str]:
            return ["owned-wsl-off"]

        def _wsl_path(self, path: Path) -> str:
            return str(path)

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        if args[0] != "owned-wsl-off":
            return real_run(args, **kwargs)  # type: ignore[call-overload,no-any-return]
        req = json.loads((stage1 / "omni-asr-request.json").read_text(encoding="utf-8"))
        seen_requests.append(req)
        (stage1 / "omni-asr-worker-output.json").write_text(
            disabled_raw.to_json(), encoding="utf-8"
        )
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    wsl_out = TransportProducer(
        interpreter="/test/python", context_grouping=True, validate_hard_segments=False
    ).transcribe("ablation-ep", audio, regions((0, 500), (600, 1100)), stage1, ffmpeg)
    assert wsl_out == disabled_raw
    assert seen_requests[0]["validate_hard_segments"] is False
    assert "validator_model_dir" not in seen_requests[0]


def test_worker_and_journal_run_without_qwen_asr_or_validator_dir_when_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib.metadata
    from types import SimpleNamespace

    import hawedit.asr_resume as resume_mod
    from hawedit.asr_resume import worker_journal
    from hawedit.asr_worker import run_request
    from test_asr_resume import private
    from test_asr_stop import RegionBackend, RegionValidator, prepared_regions

    segs_dir = tmp_path / "segs"
    segs_dir.mkdir()
    prepared = prepared_regions(segs_dir)
    req = segs_dir / "req.json"
    req.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "media_id": "ep",
                "validate_hard_segments": False,
                "segments": [
                    {"path": seg.path.name, "start_ms": seg.start_ms, "end_ms": seg.end_ms}
                    for seg in prepared
                ],
            }
        ),
        encoding="utf-8",
    )

    backend = RegionBackend()

    def forbidden_validator(*_args: object, **_kwargs: object) -> RegionValidator:
        raise AssertionError("validator should not be constructed when disabled")

    out = tmp_path / "out.json"
    monkeypatch.setattr("hawedit.asr_worker.QwenSoraniValidator", forbidden_validator)
    raw = run_request(req, out, backend)
    assert len(backend.calls) == 3
    assert backend.align_calls == []
    assert raw.asr.validated_by is None
    assert raw.segment_origins is not None
    assert all(o.outcome == "validator-disabled" and not o.escalated for o in raw.segment_origins)

    # worker_journal with validator_path=None skips qwen-asr metadata and ModelStore verification
    monkeypatch.setattr(resume_mod, "freeze_fairseq2_asset_overrides", lambda: None)
    monkeypatch.setattr(resume_mod, "assert_omni_card_integrity", lambda: req)
    monkeypatch.setattr(resume_mod, "assert_omni_asset_integrity", lambda: ())
    monkeypatch.setattr(resume_mod, "_file_digest", lambda _p: "a" * 64)
    monkeypatch.setattr(
        importlib.metadata,
        "distribution",
        lambda _name: SimpleNamespace(locate_file=lambda _p: req),
    )

    def no_qwen_version(name: str) -> str:
        if name == "qwen-asr":
            raise importlib.metadata.PackageNotFoundError(name)
        return "0.0.0"

    monkeypatch.setattr(importlib.metadata, "version", no_qwen_version)
    with worker_journal(private(tmp_path), req, prepared, None, None) as journal:
        binding = json.loads((journal.directory.path / "binding.json").read_text(encoding="utf-8"))[
            "inputs"
        ]
    assert binding["validator"] is None
    assert binding["validator_completion_policy"] is None
    assert binding["validator_mode"] == "off"
    assert "qwen-asr" not in binding["runtime"]


def test_validator_on_preserves_strict_request_journal_and_origin_contracts(
    tmp_path: Path,
) -> None:
    from hawedit.asr import OmniAsrProducer, WslOmniAsrProducer, create_omni_asr_producer
    from hawedit.asr_worker import run_request
    from test_asr_stop import RegionBackend, prepared_regions

    on_producer = create_omni_asr_producer("wsl", validate_hard_segments=True)
    assert isinstance(on_producer, WslOmniAsrProducer)
    assert on_producer.validate_hard_segments is True
    assert on_producer.admission_policy is not None
    assert "+validator-off" not in on_producer.admission_policy

    # Request with validate_hard_segments=True (default legacy) still requires validator_model_dir
    strict_dir = tmp_path / "strict_segs"
    strict_dir.mkdir()
    prepared = prepared_regions(strict_dir)
    missing_dir_req = strict_dir / "req.json"
    missing_dir_req.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "media_id": "ep",
                "validate_hard_segments": True,
                "segments": [
                    {"path": seg.path.name, "start_ms": seg.start_ms, "end_ms": seg.end_ms}
                    for seg in prepared
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="validator_model_dir"):
        run_request(missing_dir_req, tmp_path / "strict_out.json", RegionBackend())

    with pytest.raises(ValueError, match="cannot pass a validator"):
        OmniAsrProducer(RegionBackend(), validator_model_dir=tmp_path, validate_hard_segments=False)


def test_transcript_store_separates_validator_on_and_off_caches(tmp_path: Path) -> None:
    from hawedit.asr import WslOmniAsrProducer, create_omni_asr_producer
    from hawedit.transcripts import RawTranscriptImmutable, TranscriptStore
    from test_transcripts import MEDIA_SHA256, a_raw

    off_p = create_omni_asr_producer("wsl")
    on_p = create_omni_asr_producer("wsl", validate_hard_segments=True)
    assert isinstance(off_p, WslOmniAsrProducer)
    assert isinstance(on_p, WslOmniAsrProducer)
    assert off_p.admission_policy != on_p.admission_policy

    store = TranscriptStore(tmp_path)
    raw = a_raw()
    store.write_raw(
        raw, audio_sha256="audio", producer="prod", admission_policy=off_p.admission_policy
    )
    with pytest.raises(RawTranscriptImmutable, match="admission"):
        store.reusable_raw(
            raw.media_id, "audio", "prod", MEDIA_SHA256, admission_policy=on_p.admission_policy
        )


def test_paired_ablation_scorer_computes_exact_wer_cer_and_speedup_deltas() -> None:
    from hawedit.asr import Hardware
    from hawedit.bench import AblationClipPair, score_validator_ablation
    from hawedit.metrics import normalized_wer

    assert normalized_wer("سڵاو کوردستان", "سڵاو کوردستان") == 0.0
    assert normalized_wer("سڵاو کوردستان", "سڵاو") == 0.5

    report = score_validator_ablation(
        (
            AblationClipPair(
                clip_id="clip-01",
                reference_ckb="سڵاو کوردستان",
                audio_duration_s=10.0,
                without_validator_text="سڵاو کوردستان",
                with_validator_text="سڵاو هەولێر",
                without_validator_wall_s=4.0,
                with_validator_wall_s=8.0,
                validator_passes=1,
                rejected_corrections=0,
            ),
            AblationClipPair(
                clip_id="clip-02",
                reference_ckb="ئەمڕۆ باشە",
                audio_duration_s=10.0,
                without_validator_text="ئەمڕۆ خراپە",
                with_validator_text="ئەمڕۆ باشە",
                without_validator_wall_s=6.0,
                with_validator_wall_s=12.0,
                validator_passes=2,
                rejected_corrections=1,
            ),
        ),
        hardware=Hardware("HawaPC01", "RTX 3090 Ti"),
    )
    # Total reference words = 4: off has 1 error (0.25), on has 1 error (0.25) -> delta 0.0
    assert report.clip_count == 2
    assert report.wer_off == pytest.approx(0.25)
    assert report.wer_on == pytest.approx(0.25)
    assert report.wer_delta == pytest.approx(0.0)
    assert report.rtf_off == pytest.approx(10.0 / 20.0)
    assert report.rtf_on == pytest.approx(20.0 / 20.0)
    assert report.speedup == pytest.approx(2.0)
    assert report.total_validator_passes == 3
    assert report.total_rejected_corrections == 1
    payload = report.to_dict()
    hardware = payload["hardware"]
    clips = payload["clips"]
    assert isinstance(hardware, dict) and hardware["host"] == "HawaPC01"
    assert isinstance(clips, list) and len(clips) == 2
