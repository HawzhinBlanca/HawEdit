"""Tests for A2 (D-336): one command produces verified multi-clip reels in plain WSL."""

from __future__ import annotations

import hashlib
import json
import subprocess
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from hawedit.clip import DiscoveryPath
from hawedit.discovery import Candidate
from hawedit.judge import KURDISH_EDITORIAL_JUDGE, JudgeRequest, JudgeVerdict
from hawedit.transcripts import AsrProvenance, RawTranscript, Word

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "kurdish-speech-3cuts.mp4"


def _two_clip_transcript(media_id: str) -> RawTranscript:
    words = (
        Word(w="ڕۆژنامەوانی", start_ms=100, end_ms=800, conf=0.95),
        Word(w="کوردی.", start_ms=800, end_ms=1_500, conf=0.94),
        Word(w="لە", start_ms=2_000, end_ms=2_400, conf=0.93),
        Word(w="هەولێر.", start_ms=2_400, end_ms=4_100, conf=0.92),
    )
    return RawTranscript(
        media_id=media_id,
        text_ckb="ڕۆژنامەوانی کوردی. لە هەولێر.",
        words=words,
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
        media_sha256=hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
    )


class _StubJudge:
    model_id = KURDISH_EDITORIAL_JUDGE

    def judge(self, request: JudgeRequest) -> JudgeVerdict:
        mid = (request.clip_in_ms + request.clip_out_ms) // 2
        return JudgeVerdict(
            candidate_id=request.candidate_id,
            hook_score=0.88,
            self_contained=True,
            payoff_at_ms=mid,
            meaning_fidelity=0.95,
            misleading_edit_risk=0.04,
            cultural_landing=0.90,
            narrative_role="payoff",
            title_ckb="تایتڵی کوردی",
            description_ckb="وەسفی تەواوی کوردی بۆ تاقیکردنەوە.",
            hashtags_ckb=("#کوردی",),
            judge=self.model_id,
            clip_in_ms=request.clip_in_ms,
            clip_out_ms=request.clip_out_ms,
        )


def _write_pcm_wav(path: Path, *, duration_ms: int = 1_500) -> None:
    sample_rate = 16_000
    frames = max(1, int(sample_rate * duration_ms / 1_000))
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(b"\x00\x00" * frames)


def test_default_wsl_runtime_resolves_without_ready_receipt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Default A2 WSL ASR producer resolves plain WSL Python & runs with validator off."""
    from hawedit.asr import (
        DEFAULT_CHAMPION_CHECKPOINT_PATHS,
        WslOmniAsrProducer,
        create_omni_asr_producer,
    )

    assert DEFAULT_CHAMPION_CHECKPOINT_PATHS
    monkeypatch.delenv("HAWEDIT_STRICT_RUNTIME", raising=False)
    monkeypatch.delenv("HAWEDIT_WSL_PYTHON", raising=False)
    monkeypatch.setattr("hawedit.asr._discover_plain_wsl_python", lambda **_kw: "/wsl/venv/python")
    monkeypatch.setattr(
        "hawedit.asr.load_wsl_runtime_receipt",
        lambda **_kw: (_ for _ in ()).throw(AssertionError("receipt gate must not run by default")),
    )

    producer = create_omni_asr_producer("wsl", validate_hard_segments=False)
    assert isinstance(producer, WslOmniAsrProducer)
    monkeypatch.setattr(producer, "_wsl_path", lambda p: f"/mnt/{Path(p).name}")
    interp, src = producer._runtime()
    assert interp == "/wsl/venv/python"
    assert src == "/mnt/src"

    stage1 = tmp_path / "stage1"
    wav = tmp_path / "audio.wav"
    _write_pcm_wav(wav)

    seen_requests: list[dict[str, object]] = []

    def fake_run(cmd: list[str], **_kw: object) -> subprocess.CompletedProcess[bytes]:
        if "-ss" in cmd:
            _write_pcm_wav(Path(cmd[-1]), duration_ms=1_500)
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        if "hawedit.asr_worker" in cmd:
            req = json.loads((stage1 / "omni-asr-request.json").read_text(encoding="utf-8"))
            seen_requests.append(req)
            out = _two_clip_transcript("ep")
            (stage1 / "omni-asr-worker-output.json").write_text(out.to_json(), encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr("hawedit.asr.subprocess.run", fake_run)
    monkeypatch.setattr(
        "hawedit.asr.ModelStore",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("validator ModelStore must not be resolved when validator is off")
        ),
    )

    result = producer.transcribe(
        "ep", wav, (SimpleNamespace(start_ms=0, end_ms=1_500),), stage1, ffmpeg=Path("ffmpeg")
    )
    assert result.media_id == "ep"
    assert seen_requests[0]["validate_hard_segments"] is False


def test_strict_runtime_still_enforces_wsl_receipt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """--strict-runtime flag is parsed and restores full WSL receipt enforcement."""
    from hawedit.asr import WslOmniAsrProducer, create_omni_asr_producer
    from hawedit.pipeline import build_parser

    args = build_parser().parse_args(["ep.mp4", "--strict-runtime"])
    assert args.strict_runtime is True

    monkeypatch.setattr("hawedit.asr.configured_wsl_runtime", lambda: tmp_path / "missing")
    strict_producer = create_omni_asr_producer("wsl", strict_runtime=args.strict_runtime)
    assert isinstance(strict_producer, WslOmniAsrProducer)
    with pytest.raises(RuntimeError, match="runtime receipt is invalid"):
        strict_producer._runtime()


def test_stage0_proxy_threads_and_shot_parity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """ingest(..., threads=0) passes -threads 0 for proxy while keeping shot/speech parity."""
    from hawedit.ingest import detect_shots, extract_proxy, ingest

    seen_proxy_cmds: list[list[str]] = []

    def fake_ingest_run(command: list[str]) -> subprocess.CompletedProcess[bytes]:
        seen_proxy_cmds.append(command)
        Path(command[-1]).write_bytes(b"\x00" * 64)
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr("hawedit.ingest._run", fake_ingest_run)
    monkeypatch.setattr("hawedit.ingest._assert_audio_format", lambda _p: None)
    monkeypatch.setattr("hawedit.ingest.probe_duration_ms", lambda *_a, **_k: 4_162)
    monkeypatch.setattr("hawedit.ingest.detect_speech", lambda *_a, **_k: ())
    monkeypatch.setattr("hawedit.ingest.detect_shots", lambda *_a, **_k: (1_000,))

    ingest(FIXTURE, tmp_path / "s0", threads=0)
    proxy_cmd = next(cmd for cmd in seen_proxy_cmds if "libx264" in cmd)
    assert proxy_cmd[proxy_cmd.index("-threads") + 1] == "0"

    seen_proxy_cmds.clear()
    extract_proxy(FIXTURE, tmp_path / "direct.mp4")
    direct_cmd = seen_proxy_cmds[0]
    assert direct_cmd[direct_cmd.index("-threads") + 1] == "1"

    assert isinstance(detect_shots(FIXTURE), tuple)


def test_cli_default_profile_builds_end_to_end_multi_clip_kwargs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`pipeline EPISODE.mp4 --work-dir work --reels/--output-dir` enables multi-clip defaults."""
    from hawedit.asr import WslOmniAsrProducer
    from hawedit.pipeline import _build_and_run, build_parser

    captured: dict[str, object] = {}

    def spy_run_pipeline(*args: object, **kwargs: object) -> object:
        captured["args"] = args
        captured["kwargs"] = kwargs
        raise RuntimeError("stop-after-capture")

    monkeypatch.setattr("hawedit.pipeline.run_pipeline", spy_run_pipeline)
    monkeypatch.setattr("hawedit.asr.discover_default_champion_checkpoint", lambda: None)
    monkeypatch.setattr("hawedit.asr.resolve_champion_adapter", lambda: tmp_path / "champ")
    monkeypatch.setattr("hawedit.asr.adapter_fingerprint", lambda _p: "a" * 64)

    args = build_parser().parse_args([str(FIXTURE), "--work-dir", str(tmp_path / "w"), "--reels"])
    with pytest.raises(RuntimeError, match="stop-after-capture"):
        _build_and_run(args)

    kw = captured["kwargs"]
    assert isinstance(kw, dict)
    assert kw["asr"] is not None
    if isinstance(kw["asr"], WslOmniAsrProducer):
        assert kw["asr"].strict_runtime is False
        assert kw["asr"].validate_hard_segments is False
    assert kw["discover"] is not None
    assert kw["judge"] is not None
    assert kw["auto_select"] is True
    assert kw["max_clips"] == 10
    assert kw["ingest_threads"] == 0

    captured.clear()
    out_dir = tmp_path / "reels"
    out_args = build_parser().parse_args(
        [str(FIXTURE), "--work-dir", str(tmp_path / "w_out"), "--output-dir", str(out_dir)]
    )
    with pytest.raises(RuntimeError, match="stop-after-capture"):
        _build_and_run(out_args)
    kw_out = captured["kwargs"]
    assert isinstance(kw_out, dict)
    assert kw_out["auto_select"] is True and kw_out["max_clips"] == 10
    assert kw_out["output_dir"] == out_dir

    captured.clear()
    bare_args = build_parser().parse_args([str(FIXTURE), "--work-dir", str(tmp_path / "w2")])
    with pytest.raises(RuntimeError, match="stop-after-capture"):
        _build_and_run(bare_args)
    kw2 = captured["kwargs"]
    assert isinstance(kw2, dict)
    assert kw2["asr"] is None
    assert kw2["discover"] is None
    assert kw2["judge"] is None


def test_episode_delivery_exports_reels_with_measured_sidecars_and_stage_timings(
    tmp_path: Path,
) -> None:
    """Multi-clip delivery exports .mp4 + .measured.json into output_dir and logs stage timings."""
    from hawedit.pipeline import cli_json_report, run_pipeline

    work = tmp_path / "work"
    reels_dir = tmp_path / "reels"
    transcript = _two_clip_transcript("fixture")
    candidates = [
        Candidate("c1", "fixture", 100, 1_500, DiscoveryPath.VERBAL, rank=1, score=0.92),
        Candidate("c2", "fixture", 2_000, 4_100, DiscoveryPath.VERBAL, rank=2, score=0.89),
    ]
    run = run_pipeline(
        FIXTURE,
        work,
        media_id="fixture",
        transcript=transcript,
        discover=lambda _n: candidates,
        judge=_StubJudge(),
        auto_select=True,
        judge_top_n=2,
        min_clip_ms=1_000,
        max_clips=2,
        min_separation_ms=100,
        output_dir=reels_dir,
    )

    assert run.episode_manifest is not None
    assert run.episode_manifest.clips_count == 2
    exported_mp4s = sorted(reels_dir.glob("*.mp4"))
    assert len(exported_mp4s) == 2
    for mp4 in exported_mp4s:
        assert mp4.stat().st_size > 0
        sidecar = Path(f"{mp4}.measured.json")
        assert sidecar.is_file(), f"missing sidecar {sidecar}"

    timings = dict(run.stage_timings_s)
    assert timings["ingest"] >= 0.0
    assert timings["total"] >= timings["ingest"]
    report_dict = cli_json_report(run)
    assert "stage_timings_s" in report_dict
    assert report_dict["stage_timings_s"]["total"] == timings["total"]
