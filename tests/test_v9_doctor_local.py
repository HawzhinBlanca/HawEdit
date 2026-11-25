"""Unit and live-smoke tests for V9 Module C: doctor.py & hardened LocalOmniDirector (D-391)."""

from __future__ import annotations

import json
import shutil
import time
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from hawedit.captions import FontCoverageError
from hawedit.transcripts import Word
from hawedit.v8 import doctor as doctor_mod
from hawedit.v8.director import (
    DEFAULT_OMNI_TIMEOUT_S,
    OMNI_MODALITY_ENV,
    DirectorUnavailable,
    LocalOmniDirector,
    _strip_json_wrappers,
    create_director_brain,
)
from hawedit.v8.doctor import (
    DoctorCheck,
    DoctorReport,
    format_doctor_report,
    run_v8_doctor,
)
from hawedit.v8.schema import DirectorScript

_GIB = 1024**3


def _sample_words() -> tuple[Word, ...]:
    return (
        Word(w="ئەگەزانی", start_ms=200, end_ms=700, conf=0.95),
        Word(w="مۆدێلە", start_ms=800, end_ms=1400, conf=0.95),
        Word(w="نوێیەکە", start_ms=1500, end_ms=2200, conf=0.95),
        Word(w="زۆر", start_ms=2300, end_ms=2700, conf=0.95),
        Word(w="خێرایە", start_ms=2800, end_ms=3600, conf=0.95),
    )


def _valid_script_payload() -> dict[str, Any]:
    return {
        "hook_title_ckb": "مۆدێلە نوێیەکە زۆر خێرایە",
        "word_repairs": [
            {
                "word_index": 0,
                "original": "ئەگەزانی",
                "repaired": "ئەزانی",
                "reason": "spoken Sorani orthography",
            }
        ],
        "cuts": [],
        "camera_moves": [],
        "caption_beats": [{"word_indices": [1], "power_word_index": 1, "accent_color": "#B8FF2E"}],
        "visual_interrupts": [],
        "cold_open_span_ms": None,
    }


def _wrap_openai(content: str) -> str:
    return json.dumps({"choices": [{"message": {"content": content}}]}, ensure_ascii=False)


def _patch_all_doctor_ok(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    fake_ffmpeg = tmp_path / "ffmpeg.exe"
    fake_ffmpeg.write_bytes(b"fake-ffmpeg")
    fonts_dir = tmp_path / "fonts"
    fonts_dir.mkdir()
    fake_font = fonts_dir / "Vazirmatn-ExtraBold.ttf"
    fake_font.write_bytes(b"fake-ttf")

    monkeypatch.setattr(doctor_mod, "find_ffmpeg", lambda: fake_ffmpeg)
    monkeypatch.setattr(
        doctor_mod,
        "_query_nvidia_smi",
        lambda timeout_s=2.0: (
            True,
            [
                {
                    "index": 0,
                    "name": "NVIDIA GeForce RTX 3090 Ti",
                    "memory_total_mib": 24564,
                    "memory_free_mib": 12000,
                }
            ],
            None,
        ),
    )
    monkeypatch.setattr(doctor_mod, "encoder_available", lambda _enc, _ff: True)
    monkeypatch.setattr(
        doctor_mod,
        "_run_ffmpeg_buildconf",
        lambda _ff, timeout_s=2.0: (
            True,
            "--enable-libass --enable-libharfbuzz --enable-libfribidi",
            "",
        ),
    )
    monkeypatch.setattr(
        doctor_mod,
        "_import_module",
        lambda name: SimpleNamespace(__version__="1.0.0", _name=name),
    )
    monkeypatch.setattr(doctor_mod, "assert_font_covers_kurdish", lambda _p: None)
    monkeypatch.setattr(
        doctor_mod, "read_credential", lambda _k: "super-secret-api-key-DO-NOT-LEAK"
    )
    monkeypatch.setattr(
        shutil,
        "disk_usage",
        lambda _p: shutil._ntuple_diskusage(total=500 * _GIB, used=200 * _GIB, free=300 * _GIB),
    )

    def _fake_http(url: str, *, timeout_s: float) -> tuple[int, dict[str, Any] | None, str | None]:
        _ = timeout_s
        if url.endswith("/health"):
            return (
                200,
                {"status": "healthy", "model": "kurdish-omniasr-7b", "device": "cuda:0"},
                None,
            )
        if url.endswith("/models"):
            return (
                200,
                {
                    "data": [
                        {"id": "qwen3.8-27b-obliterated"},
                        {"id": "text-embedding-nomic-embed-text-v1.5"},
                    ]
                },
                None,
            )
        return 404, None, "HTTP 404"

    monkeypatch.setattr(doctor_mod, "_probe_http_json", _fake_http)
    return fonts_dir


# ---------------------------------------------------------------------------
# 1. DoctorReport & All 7 Subsystem Probes (ok / warn / fail)
# ---------------------------------------------------------------------------


def test_doctor_all_ok_redacts_secret_and_formats_checklist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fonts_dir = _patch_all_doctor_ok(monkeypatch, tmp_path)
    report = run_v8_doctor(work_dir=tmp_path, fonts_dir=fonts_dir)

    assert isinstance(report, DoctorReport)
    assert report.ready_for_production is True
    assert len(report.checks) == 7
    payload = report.to_dict()
    assert payload["ready_for_production"] is True
    assert payload["counts"] == {"ok": 7, "warn": 0, "fail": 0}
    assert set(payload["checks_by_name"]) == {
        "gpu_nvenc",
        "ffmpeg_rtl",
        "skia_harfbuzz",
        "wsl_asr",
        "gemini_director",
        "local_omni_director",
        "disk_space",
    }
    assert payload["checks_by_name"]["local_omni_director"]["details"]["models"] == [
        "qwen3.8-27b-obliterated"
    ]
    assert (
        payload["checks_by_name"]["local_omni_director"]["details"]["embedding_models_filtered"]
        == 1
    )

    # Secret MUST NEVER appear anywhere in JSON or formatted CLI output.
    serialized = json.dumps(payload, ensure_ascii=False)
    formatted = format_doctor_report(report)
    assert "super-secret-api-key-DO-NOT-LEAK" not in serialized
    assert "super-secret-api-key-DO-NOT-LEAK" not in formatted
    assert "READY FOR PRODUCTION" in formatted
    assert "[OK]" in formatted


def test_doctor_gpu_nvenc_warn_cpu_note_still_ready_for_production(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fonts_dir = _patch_all_doctor_ok(monkeypatch, tmp_path)
    monkeypatch.setattr(
        doctor_mod, "_query_nvidia_smi", lambda timeout_s=2.0: (False, [], "not found")
    )
    monkeypatch.setattr(doctor_mod, "encoder_available", lambda _enc, _ff: False)

    report = run_v8_doctor(work_dir=tmp_path, fonts_dir=fonts_dir)
    gpu = report.get("gpu_nvenc")
    assert gpu is not None
    assert gpu.status == "warn"
    assert "libx264" in gpu.summary
    assert "libx264" in report.gpu_note
    # Core render stack (ffmpeg_rtl, skia_harfbuzz, disk_space) is still ok!
    assert report.ready_for_production is True


def test_doctor_gpu_detected_but_nvenc_unavailable_warns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fonts_dir = _patch_all_doctor_ok(monkeypatch, tmp_path)
    monkeypatch.setattr(doctor_mod, "encoder_available", lambda _enc, _ff: False)

    report = run_v8_doctor(work_dir=tmp_path, fonts_dir=fonts_dir)
    gpu = report.get("gpu_nvenc")
    assert gpu is not None
    assert gpu.status == "warn"
    assert gpu.details["nvenc_available"] is False
    assert len(gpu.details["gpus"]) == 1
    assert report.ready_for_production is True


def test_doctor_ffmpeg_rtl_fail_blocks_production(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fonts_dir = _patch_all_doctor_ok(monkeypatch, tmp_path)

    # Case A: Missing FFmpeg binary.
    monkeypatch.setattr(doctor_mod, "find_ffmpeg", lambda: None)
    rep_missing = run_v8_doctor(work_dir=tmp_path, fonts_dir=fonts_dir)
    ff_check = rep_missing.get("ffmpeg_rtl")
    assert ff_check is not None and ff_check.status == "fail"
    assert rep_missing.ready_for_production is False

    # Case B: FFmpeg exists but lacks HarfBuzz/FriBidi.
    fake_ff = tmp_path / "ffmpeg.exe"
    monkeypatch.setattr(doctor_mod, "find_ffmpeg", lambda: fake_ff)
    monkeypatch.setattr(
        doctor_mod,
        "_run_ffmpeg_buildconf",
        lambda _ff, timeout_s=2.0: (True, "--enable-libass --disable-libharfbuzz", ""),
    )
    rep_no_rtl = run_v8_doctor(work_dir=tmp_path, fonts_dir=fonts_dir)
    ff_no_rtl = rep_no_rtl.get("ffmpeg_rtl")
    assert ff_no_rtl is not None and ff_no_rtl.status == "fail"
    assert "RTL" in ff_no_rtl.summary
    assert rep_no_rtl.ready_for_production is False


def test_doctor_skia_harfbuzz_fail_states(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fonts_dir = _patch_all_doctor_ok(monkeypatch, tmp_path)

    # Missing skia import.
    def _fail_skia(name: str) -> Any:
        if name == "skia":
            raise ImportError("No module named 'skia'")
        return SimpleNamespace(__version__="0.56.0")

    monkeypatch.setattr(doctor_mod, "_import_module", _fail_skia)
    rep = run_v8_doctor(work_dir=tmp_path, fonts_dir=fonts_dir)
    chk = rep.get("skia_harfbuzz")
    assert chk is not None and chk.status == "fail"
    assert rep.ready_for_production is False

    # Missing font file.
    monkeypatch.setattr(doctor_mod, "_import_module", lambda _n: SimpleNamespace(__version__="1.0"))
    empty_fonts = tmp_path / "empty_fonts"
    empty_fonts.mkdir()
    rep_missing_font = run_v8_doctor(work_dir=tmp_path, fonts_dir=empty_fonts)
    chk_font = rep_missing_font.get("skia_harfbuzz")
    assert chk_font is not None and chk_font.status == "fail"
    assert rep_missing_font.ready_for_production is False

    # Kurdish glyph coverage failure.
    def _bad_cov(_p: Path) -> None:
        raise FontCoverageError("missing Sorani glyph ڕ")

    monkeypatch.setattr(doctor_mod, "assert_font_covers_kurdish", _bad_cov)
    rep_bad_cov = run_v8_doctor(work_dir=tmp_path, fonts_dir=fonts_dir)
    chk_cov = rep_bad_cov.get("skia_harfbuzz")
    assert chk_cov is not None and chk_cov.status == "fail"
    assert rep_bad_cov.ready_for_production is False


def test_doctor_optional_services_warn_without_blocking_core_render(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fonts_dir = _patch_all_doctor_ok(monkeypatch, tmp_path)

    # Partial WSL ASR (8000 up, 8001 down), missing Gemini key, LM Studio only embed models.
    def _mixed_http(url: str, *, timeout_s: float) -> tuple[int, dict[str, Any] | None, str | None]:
        _ = timeout_s
        if ":8000/" in url:
            return 200, {"status": "healthy", "model": "kurdish-omniasr-7b"}, None
        if ":8001/" in url:
            return 0, None, "Connection refused"
        if url.endswith("/models"):
            return 200, {"data": [{"id": "nomic-embed-text"}]}, None
        return 0, None, "unreachable"

    monkeypatch.setattr(doctor_mod, "_probe_http_json", _mixed_http)
    monkeypatch.setattr(doctor_mod, "read_credential", lambda _k: None)

    report = run_v8_doctor(work_dir=tmp_path, fonts_dir=fonts_dir)
    assert report.ready_for_production is True
    for name in ("wsl_asr", "gemini_director", "local_omni_director"):
        chk = report.get(name)
        assert chk is not None and chk.status == "warn"

    # All endpoints completely unreachable.
    monkeypatch.setattr(doctor_mod, "_probe_http_json", lambda _u, *, timeout_s: (0, None, "down"))
    rep_down = run_v8_doctor(work_dir=tmp_path, fonts_dir=fonts_dir)
    assert rep_down.ready_for_production is True
    for name in ("wsl_asr", "local_omni_director"):
        chk = rep_down.get(name)
        assert chk is not None and chk.status == "warn"


def test_doctor_disk_space_warn_and_fail_block_production(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fonts_dir = _patch_all_doctor_ok(monkeypatch, tmp_path)

    # Low disk (< 10 GB) -> warn -> ready_for_production False.
    monkeypatch.setattr(
        shutil,
        "disk_usage",
        lambda _p: shutil._ntuple_diskusage(total=100 * _GIB, used=95 * _GIB, free=5 * _GIB),
    )
    rep_low = run_v8_doctor(work_dir=tmp_path, fonts_dir=fonts_dir)
    disk_low = rep_low.get("disk_space")
    assert disk_low is not None and disk_low.status == "warn"
    assert rep_low.ready_for_production is False
    assert "NOT READY FOR PRODUCTION" in format_doctor_report(rep_low)

    # Unreadable disk -> fail -> ready_for_production False.
    def _disk_err(_p: Path) -> Any:
        raise OSError("device disconnected")

    monkeypatch.setattr(shutil, "disk_usage", _disk_err)
    rep_err = run_v8_doctor(work_dir=tmp_path, fonts_dir=fonts_dir)
    disk_err = rep_err.get("disk_space")
    assert disk_err is not None and disk_err.status == "fail"
    assert rep_err.ready_for_production is False


def test_doctor_validation_and_live_smoke_under_3s() -> None:
    with pytest.raises(ValueError, match="min_disk_gb"):
        run_v8_doctor(min_disk_gb=0.0)
    with pytest.raises(ValueError, match="http_timeout_s"):
        run_v8_doctor(http_timeout_s=-1.0)
    with pytest.raises(ValueError, match="DoctorCheck.name"):
        DoctorCheck(name="", status="ok", summary="bad")

    t0 = time.perf_counter()
    live = run_v8_doctor()
    wall_s = time.perf_counter() - t0
    assert wall_s < 3.0, f"run_v8_doctor took {wall_s:.2f}s (must be < 3 s)"
    assert len(live.checks) == 7
    assert isinstance(json.dumps(live.to_dict()), str)
    assert "HawEdit V8/V9 Preflight Doctor" in format_doctor_report(live)


# ---------------------------------------------------------------------------
# 2. Hardened LocalOmniDirector Tests (Modality, <think> Stripping, Fail-Loud)
# ---------------------------------------------------------------------------


def test_default_omni_timeout_is_240s_and_modality_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert DEFAULT_OMNI_TIMEOUT_S == 240.0
    default_dir = LocalOmniDirector(base_url="http://127.0.0.1:1234/v1")
    assert default_dir.timeout_s == 240.0
    assert default_dir.modality == "omni"
    assert default_dir.supports_vision is True
    assert default_dir.supports_audio is True

    text_dir = create_director_brain(
        "local-omni",
        base_url="http://127.0.0.1:1234/v1",
        modality="text",
    )
    assert isinstance(text_dir, LocalOmniDirector)
    assert text_dir.modality == "text"
    assert text_dir.supports_vision is False
    assert text_dir.supports_audio is False
    assert text_dir.timeout_s == 240.0

    monkeypatch.setenv(OMNI_MODALITY_ENV, "vision")
    env_dir = LocalOmniDirector(base_url="http://127.0.0.1:1234/v1")
    assert env_dir.modality == "vision"
    assert env_dir.supports_vision is True
    assert env_dir.supports_audio is False

    with pytest.raises(ValueError, match="Unsupported local director modality"):
        LocalOmniDirector(
            base_url="http://127.0.0.1:1234/v1",
            modality="audio-only",  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "wrapper",
    [
        lambda js: f"<think>Step 1: check Kurdish loanwords.</think>\n{js}",
        lambda js: (
            f"<think>first thought</think>\n<thinking>second thought</thinking>\n```json\n{js}\n```"
        ),
        lambda js: f"LM Studio prompt-injected opening think...\n</think>\n```json\n{js}\n```",
        lambda js: f"Here is your JSON:\n```\n{js}\n```\nDone.",
    ],
)
def test_strip_json_wrappers_handles_qwen_deepseek_think_and_fences(
    wrapper: Any,
) -> None:
    raw_response = wrapper(json.dumps(_valid_script_payload(), ensure_ascii=False))
    cleaned = _strip_json_wrappers(raw_response)
    parsed = json.loads(cleaned)
    assert parsed["hook_title_ckb"] == "مۆدێلە نوێیەکە زۆر خێرایە"


def test_local_omni_text_modality_skips_media_and_sends_plain_string(tmp_path: Path) -> None:
    # Even with a dummy file (no FFmpeg media extraction in text mode), text modality succeeds!
    dummy_mp4 = tmp_path / "dummy.mp4"
    dummy_mp4.write_bytes(b"not-an-mp4")
    words = _sample_words()
    sent_payloads: list[dict[str, Any]] = []

    def _transport(url: str, body: bytes | None, headers: Mapping[str, str]) -> tuple[int, str]:
        _ = (url, headers)
        assert body is not None
        req = json.loads(body.decode("utf-8"))
        sent_payloads.append(req)
        wrapped = (
            "<think>Evaluating Sorani transcript in text mode...</think>\n"
            f"```json\n{json.dumps(_valid_script_payload(), ensure_ascii=False)}\n```"
        )
        return 200, _wrap_openai(wrapped)

    director = LocalOmniDirector(
        base_url="http://127.0.0.1:1234/v1",
        model_id="qwen3.8-27b-obliterated",
        modality="text",
        transport=_transport,
    )
    script = director.direct_clip(
        source_mp4=dummy_mp4,
        clip_in_ms=0,
        clip_out_ms=4_000,
        clip_id="text-only-01",
        words=words,
    )
    assert script.clip_id == "text-only-01"
    assert len(sent_payloads) == 1
    user_msg = sent_payloads[0]["messages"][1]["content"]
    assert isinstance(user_msg, str)
    assert "input_audio" not in user_msg
    assert "image_url" not in user_msg
    assert director.last_modality_used == "text"
    assert director.last_diagnostics["configured_modality"] == "text"
    assert director.last_diagnostics["effective_modality"] == "text"
    assert director.last_diagnostics["modality_rejections"] == []

    # Critique also works cleanly in explicit text modality.
    verdict_director = LocalOmniDirector(
        base_url="http://127.0.0.1:1234/v1",
        model_id="huihui-deepseek-v4-flash-0731-abliterated",
        modality="text",
        transport=lambda _u, _b, _h: (
            200,
            _wrap_openai(
                "<think>Checking script...</think>\n"
                '{"approved": true, "score": 92.0, "issues": [], "patch": null}'
            ),
        ),
    )
    verdict = verdict_director.critique_clip(
        rendered_mp4=dummy_mp4,
        script=DirectorScript(clip_id="text-only-01", hook_title_ckb="مۆدێلە نوێیەکە"),
        words=words,
    )
    assert verdict.approved is True
    assert verdict_director.last_modality_used == "text"

    # Non-loopback http:// with Bearer api_key is refused; https:// and loopback http:// allowed
    with pytest.raises(ValueError, match="https://"):
        LocalOmniDirector(base_url="http://10.0.0.5:1234/v1", api_key="secret-token")
    https_dir = LocalOmniDirector(base_url="https://llm.example.com/v1", api_key="secret-token")
    assert https_dir.base_url == "https://llm.example.com/v1"


def test_local_omni_records_diagnostics_on_http_400_input_audio_and_image_rejection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dummy_mp4 = tmp_path / "clip.mp4"
    dummy_mp4.write_bytes(b"mp4")
    words = _sample_words()
    monkeypatch.setattr(
        "hawedit.v8.director._extract_omni_media",
        lambda *_a, **_kw: ((b"\xff\xd8\xff\xe0jpeg",), b"RIFF0000WAVEfmt "),
    )

    seen_user_contents: list[Any] = []

    def _lm_studio_text_only_server(
        url: str, body: bytes | None, headers: Mapping[str, str]
    ) -> tuple[int, str]:
        _ = (url, headers)
        assert body is not None
        req = json.loads(body.decode("utf-8"))
        content = req["messages"][1]["content"]
        seen_user_contents.append(content)
        if isinstance(content, list):
            types = {block.get("type") for block in content}
            if "input_audio" in types:
                return 400, '{"error": "Unsupported content part type: input_audio"}'
            if "image_url" in types:
                return (
                    400,
                    '{"error": "Model qwen3.8-27b-obliterated is not a vision model '
                    '(image_url unsupported)"}',
                )
        return 200, _wrap_openai(
            f"<think>reasoning</think>\n{json.dumps(_valid_script_payload(), ensure_ascii=False)}"
        )

    director = LocalOmniDirector(
        base_url="http://127.0.0.1:1234/v1",
        model_id="qwen3.8-27b-obliterated",
        modality="omni",
        transport=_lm_studio_text_only_server,
    )
    script = director.direct_clip(
        source_mp4=dummy_mp4,
        clip_in_ms=0,
        clip_out_ms=4_000,
        clip_id="lmstudio-step",
        words=words,
        video_proxy=dummy_mp4,
    )
    assert script.clip_id == "lmstudio-step"
    assert len(seen_user_contents) == 3  # omni -> 400 -> vision -> 400 -> text -> 200
    assert director.last_modality_used == "text"
    diag = director.last_diagnostics
    assert diag["configured_modality"] == "omni"
    assert diag["effective_modality"] == "text"
    assert len(diag["modality_rejections"]) == 2
    assert diag["modality_rejections"][0]["rejected_modality"] == "omni"
    assert "input_audio" in diag["modality_rejections"][0]["reason"]
    assert diag["modality_rejections"][1]["rejected_modality"] == "vision"


def test_local_omni_fails_loud_on_non_modality_400_500_and_truncated_think(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dummy_mp4 = tmp_path / "clip.mp4"
    dummy_mp4.write_bytes(b"mp4")
    words = _sample_words()
    monkeypatch.setattr(
        "hawedit.v8.director._extract_omni_media",
        lambda *_a, **_kw: ((b"\xff\xd8\xff\xe0jpeg",), b"RIFF0000WAVEfmt "),
    )

    # Non-modality HTTP 400 MUST fail immediately (1 call, zero silent retry or offline fallback).
    calls = 0

    def _ctx_overflow(_u: str, _b: bytes | None, _h: Mapping[str, str]) -> tuple[int, str]:
        nonlocal calls
        calls += 1
        return 400, '{"error": "Context length exceeded: 32768 tokens"}'

    director_400 = LocalOmniDirector(
        base_url="http://127.0.0.1:1234/v1",
        model_id="qwen3.8-27b-obliterated",
        modality="omni",
        transport=_ctx_overflow,
    )
    with pytest.raises(DirectorUnavailable, match="HTTP 400"):
        director_400.direct_clip(
            source_mp4=dummy_mp4,
            clip_in_ms=0,
            clip_out_ms=4_000,
            clip_id="fail-400",
            words=words,
            video_proxy=dummy_mp4,
        )
    assert calls == 1
    assert director_400.last_modality_used is None
    assert "HTTP 400" in str(director_400.last_diagnostics["error"])

    # Truncated <think> block without JSON MUST fail loud.
    director_trunc = LocalOmniDirector(
        base_url="http://127.0.0.1:1234/v1",
        model_id="qwen3.8-27b-obliterated",
        modality="text",
        transport=lambda _u, _b, _h: (
            200,
            _wrap_openai("<think>still reasoning and hit max tokens"),
        ),
    )
    with pytest.raises(DirectorUnavailable, match="malformed JSON"):
        director_trunc.direct_clip(
            source_mp4=dummy_mp4,
            clip_in_ms=0,
            clip_out_ms=4_000,
            clip_id="fail-trunc",
            words=words,
        )

    # HTTP 500 MUST fail loud.
    director_500 = LocalOmniDirector(
        base_url="http://127.0.0.1:1234/v1",
        model_id="qwen3.8-27b-obliterated",
        modality="text",
        transport=lambda _u, _b, _h: (500, '{"error": "CUDA OOM"}'),
    )
    with pytest.raises(DirectorUnavailable, match="HTTP 500"):
        director_500.direct_clip(
            source_mp4=dummy_mp4,
            clip_in_ms=0,
            clip_out_ms=4_000,
            clip_id="fail-500",
            words=words,
        )
