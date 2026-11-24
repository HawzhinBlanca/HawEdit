"""Unit and FFmpeg integration tests for HawEdit V8 Module 2 (src/hawedit/v8/director.py)."""

from __future__ import annotations

import base64
import json
import math
import struct
import subprocess
import wave
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from hawedit.captions import ffprobe_for, find_ffmpeg
from hawedit.transcripts import Word
from hawedit.v8.compiler import V8DirectorProtocol, apply_critique_patch
from hawedit.v8.director import (
    CRITIQUE_SYSTEM_PROMPT,
    DIRECTOR_SYSTEM_PROMPT,
    MAX_GEMINI_INLINE_BYTES,
    OMNI_URL_ENV,
    DirectorBrain,
    DirectorUnavailable,
    GeminiVideoDirector,
    LocalOmniDirector,
    OfflineRestrainedDirector,
    ProxyBuildError,
    build_critique_preview,
    build_director_proxy,
    create_director_brain,
    critique_rendered_clip,
)
from hawedit.v8.schema import (
    CameraMove,
    CaptionBeat,
    CritiqueVerdict,
    CutRegion,
    DirectorScript,
    compile_restrained_camera_filter,
    validate_director_script,
)


def _require_ffmpeg() -> Path:
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None and ffmpeg.is_file(), "FFmpeg must be available for proxy tests"
    return ffmpeg


def _make_synthetic_mp4(path: Path, *, duration_s: float = 3.0, height: int = 720) -> Path:
    ffmpeg = _require_ffmpeg()
    width = int(round(height * 16 / 9))
    width -= width % 2
    cmd = [
        str(ffmpeg),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=size={width}x{height}:rate=25:duration={duration_s:.2f}",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:sample_rate=48000:duration={duration_s:.2f}",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "96k",
        str(path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=60)
    assert res.returncode == 0, f"Failed to build synthetic MP4: {res.stderr}"
    return path


def _make_pcm_wav(
    path: Path,
    *,
    duration_ms: int,
    loud_spans_ms: tuple[tuple[int, int], ...] = (),
    sample_rate: int = 16_000,
) -> Path:
    total_samples = int(duration_ms * sample_rate / 1000)
    samples: list[int] = []
    for i in range(total_samples):
        t_ms = i * 1000.0 / sample_rate
        is_loud = any(s <= t_ms <= e for s, e in loud_spans_ms)
        amp = 22_000 if is_loud else 1_200
        val = int(amp * math.sin(2.0 * math.pi * 300.0 * i / sample_rate))
        samples.append(max(-32767, min(32767, val)))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return path


def _sample_kurdish_words() -> tuple[Word, ...]:
    """36 s Kurdish clip transcript containing known ASR garbles, pauses, and a filler."""
    entries = [
        ("ئەگەزانی", 200, 750),
        ("بەیانیەکەی", 800, 1450),
        ("مۆدەی", 1500, 2000),
        ("بڵاو", 2050, 2450),
        ("کرایەوە", 2500, 3100),
        ("لە", 3150, 3350),
        ("ناو", 3400, 3650),
        ("بازاڕ", 3700, 4200),
        ("یەعنی", 4500, 4900),  # isolated conversational filler (>120ms gap both sides)
        ("هەموو", 5200, 5700),
        ("کەسێک", 5750, 6400),
        ("باسی", 6450, 6900),
        ("ڕیستیک", 7000, 7600),
        ("دەکات", 7650, 8200),
        # Major 950 ms silence gap -> editorial jump-cut #1
        ("ئێستا", 9150, 9700),
        ("تەکنەلۆژیا", 9800, 10700),
        ("زۆر", 10800, 11200),
        ("خێرا", 11250, 11800),
        ("دەگۆڕێت", 11900, 12800),
        ("و", 12850, 13000),
        ("کارەکان", 13100, 14000),
        ("ئاسانتر", 14100, 15000),
        ("دەبن", 15100, 15700),
        # Major 1100 ms silence gap -> editorial jump-cut #2
        ("بەڵام", 16800, 17400),
        ("داهاتوو", 17500, 18400),
        ("دەستی", 18500, 19100),
        ("ئێمەدایە", 19200, 20200),
        ("بۆ", 20300, 20550),
        ("فێربوونی", 20600, 21500),
        ("ژیری", 21600, 22300),
        ("دەستکرد", 22400, 23400),
        ("پێویستە", 23500, 24500),
        ("هەوڵبدەین", 24600, 25800),
        ("سەرکەوتن", 26000, 27200),
        ("مسۆگەر", 27300, 28400),
        ("دەبێت", 28500, 29400),
        ("لە", 29500, 29700),
        ("کۆتاییدا", 29800, 31000),
        ("ئەنجامێکی", 31200, 32500),
        ("گەورە", 32600, 33600),
        ("دەبینین", 33700, 35000),
    ]
    return tuple(Word(w=text, start_ms=s, end_ms=e, conf=0.95) for text, s, e in entries)


def _valid_director_payload() -> dict[str, Any]:
    return {
        "hook_title_ckb": "مۆدێلە نوێیەکە هەموو شتێک دەگۆڕێت",
        "word_repairs": [
            {
                "word_index": 0,
                "original": "ئەگەزانی",
                "repaired": "ئەزانی",
                "reason": "audio confirms spoken Sorani ئەزانی",
            },
            {
                "word_index": 12,
                "original": "ڕیستیک",
                "repaired": "ڕیستریکت",
                "reason": "audio clearly says English loanword restrict",
            },
        ],
        "cuts": [
            {
                "start_ms": 8275,
                "end_ms": 9075,
                "kind": "silence",
                "reason": "remove 950 ms dead air",
            }
        ],
        "camera_moves": [
            {
                "start_ms": 9150,
                "end_ms": 11150,
                "kind": "punch_cut",
                "scale_start": 1.00,
                "scale_end": 1.12,
                "reason": "disguise jump cut",
            },
            {
                "start_ms": 23500,
                "end_ms": 27000,
                "kind": "slow_push",
                "scale_start": 1.00,
                "scale_end": 1.08,
                "reason": "earned payoff build-up",
            },
        ],
        "caption_beats": [
            {"word_indices": [0], "power_word_index": None, "accent_color": "#FFE500"},
            {"word_indices": [1], "power_word_index": 1, "accent_color": "#B8FF2E"},
            {"word_indices": [2, 3], "power_word_index": None, "accent_color": "#FFE500"},
        ],
        "visual_interrupts": [
            {
                "start_ms": 25000,
                "end_ms": 27400,
                "text_ckb": "سەرکەوتن مسۆگەرە",
                "position": "top",
            }
        ],
        "cold_open_span_ms": None,
    }


def _wrap_gemini_response(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": json.dumps(payload, ensure_ascii=False)}],
                    }
                }
            ]
        },
        ensure_ascii=False,
    )


def _wrap_openai_response(content: str) -> str:
    return json.dumps({"choices": [{"message": {"content": content}}]}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 1. Real FFmpeg Media Proxy & Critique Preview Tests
# ---------------------------------------------------------------------------


def test_build_director_proxy_and_critique_preview_real_ffmpeg(tmp_path: Path) -> None:
    ffmpeg = _require_ffmpeg()
    ffprobe = ffprobe_for(ffmpeg)
    source = _make_synthetic_mp4(tmp_path / "source.mp4", duration_s=3.5, height=720)

    proxy = build_director_proxy(
        source,
        500,
        3000,
        tmp_path / "out" / "director_proxy.mp4",
        fps=1.0,
        height=360,
        ffmpeg=ffmpeg,
    )
    assert proxy.is_file()
    assert 0 < proxy.stat().st_size < 500_000

    probe_proxy = subprocess.run(
        [
            str(ffprobe),
            "-v",
            "error",
            "-show_streams",
            "-print_format",
            "json",
            str(proxy),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    proxy_streams = json.loads(probe_proxy.stdout)["streams"]
    v_stream = next(s for s in proxy_streams if s["codec_type"] == "video")
    a_stream = next(s for s in proxy_streams if s["codec_type"] == "audio")
    assert int(v_stream["height"]) == 360
    assert v_stream["codec_name"] == "h264"
    assert int(a_stream["channels"]) == 1
    assert int(a_stream["sample_rate"]) == 16000

    preview = build_critique_preview(
        source,
        tmp_path / "out" / "critique_preview.mp4",
        fps=2.0,
        height=480,
        ffmpeg=ffmpeg,
    )
    assert preview.is_file()
    assert preview.stat().st_size > 0
    probe_prev = subprocess.run(
        [
            str(ffprobe),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=height",
            "-print_format",
            "json",
            str(preview),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert int(json.loads(probe_prev.stdout)["streams"][0]["height"]) == 480


def test_proxy_builders_fail_loud_on_bad_inputs(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.mp4"
    with pytest.raises(FileNotFoundError):
        build_director_proxy(missing, 0, 1000, tmp_path / "p.mp4")

    with pytest.raises(FileNotFoundError):
        build_critique_preview(missing, tmp_path / "c.mp4")

    fake = tmp_path / "fake.mp4"
    fake.write_bytes(b"not-a-valid-mp4")
    with pytest.raises(ValueError, match="clip_out_ms"):
        build_director_proxy(fake, 1000, 1000, tmp_path / "p.mp4")

    with pytest.raises(ProxyBuildError):
        build_director_proxy(
            fake,
            0,
            1000,
            tmp_path / "p.mp4",
            ffmpeg=tmp_path / "no_such_ffmpeg.exe",
        )


# ---------------------------------------------------------------------------
# 2. System Prompts Verification
# ---------------------------------------------------------------------------


def test_system_prompts_contain_mandatory_v8_directives() -> None:
    # Audio-grounded loanword repair examples
    assert "ما فەیبوو فایف" in DIRECTOR_SYSTEM_PROMPT
    assert "ڕیستیک" in DIRECTOR_SYSTEM_PROMPT
    assert "مۆدەی" in DIRECTOR_SYSTEM_PROMPT
    # Camera restraint & zero sway
    assert "1.00x" in DIRECTOR_SYSTEM_PROMPT
    assert "punch_cut" in DIRECTOR_SYSTEM_PROMPT
    assert "slow_push" in DIRECTOR_SYSTEM_PROMPT
    assert "ZERO wobble" in DIRECTOR_SYSTEM_PROMPT
    # Power words & trimming
    assert "power_word_index" in DIRECTOR_SYSTEM_PROMPT
    assert "14 characters" in DIRECTOR_SYSTEM_PROMPT
    # Watch-Before-Ship 5 explicit checks
    for keyword in (
        "UNNECESSARY CAMERA MOTION",
        "BROKEN KURDISH TEXT",
        "AWKWARD CUTS",
        "SUBTITLE READABILITY",
        "VIRAL HOOK STRENGTH",
    ):
        assert keyword in CRITIQUE_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# 3. GeminiVideoDirector Tests (Mocked HTTP, Strict Fail-Stop)
# ---------------------------------------------------------------------------


def test_gemini_video_director_sends_inline_mp4_and_validates_script(tmp_path: Path) -> None:
    words = _sample_kurdish_words()
    proxy = tmp_path / "proxy.mp4"
    proxy_bytes = b"\x00\x00\x00\x18ftypmp42synthetic-video-payload"
    proxy.write_bytes(proxy_bytes)

    captured: list[tuple[str, dict[str, Any], Mapping[str, str]]] = []

    def fake_transport(
        url: str,
        body: bytes | None,
        headers: Mapping[str, str],
    ) -> tuple[int, str]:
        assert body is not None
        captured.append((url, json.loads(body.decode("utf-8")), headers))
        return 200, _wrap_gemini_response(_valid_director_payload())

    director = GeminiVideoDirector(
        api_key="test-secret-key-9999",
        model_id="gemini-2.5-pro",
        timeout_s=180.0,
        transport=fake_transport,
    )
    script = director.direct_clip(
        source_mp4=proxy,
        clip_in_ms=0,
        clip_out_ms=36_000,
        clip_id="s86-87",
        words=words,
        shot_cuts_ms=(15_500,),
        jump_cuts_ms=((9_150, 950),),
        video_proxy=proxy,
    )

    assert len(captured) == 1
    url, req_json, headers = captured[0]
    assert url.endswith("/models/gemini-2.5-pro:generateContent")
    assert headers["x-goog-api-key"] == "test-secret-key-9999"
    assert req_json["generationConfig"]["responseMimeType"] == "application/json"
    assert "responseSchema" in req_json["generationConfig"]

    parts = req_json["contents"][0]["parts"]
    assert parts[0]["inlineData"]["mimeType"] == "video/mp4"
    assert base64.b64decode(parts[0]["inlineData"]["data"]) == proxy_bytes
    assert "[12] 7000..7600ms: ڕیستیک" in parts[1]["text"]

    assert script.clip_id == "s86-87"
    assert len(script.word_repairs) == 2
    assert script.word_repairs[1].repaired == "ڕیستریکت"
    validate_director_script(script, duration_ms=36_000, words=words)


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (429, '{"error": {"message": "Quota exceeded"}}'),
        (503, '{"error": {"message": "Service unavailable"}}'),
        (0, "Connection reset by peer"),
        (200, '{"candidates": [{"content": {"parts": [{"text": "{not valid json"}]}}]}'),
    ],
)
def test_gemini_video_director_fails_loud_zero_fallback(
    tmp_path: Path,
    status: int,
    body: str,
) -> None:
    proxy = tmp_path / "proxy.mp4"
    proxy.write_bytes(b"mp4bytes")
    words = _sample_kurdish_words()

    director = GeminiVideoDirector(
        api_key="test-key",
        transport=lambda _u, _b, _h: (status, body),
    )
    with pytest.raises(DirectorUnavailable):
        director.direct_clip(
            source_mp4=proxy,
            clip_in_ms=0,
            clip_out_ms=36_000,
            clip_id="s86-87",
            words=words,
            video_proxy=proxy,
        )


def test_gemini_video_director_rejects_excessive_camera_motion_from_model(tmp_path: Path) -> None:
    proxy = tmp_path / "proxy.mp4"
    proxy.write_bytes(b"mp4bytes")
    words = _sample_kurdish_words()
    bad_payload = _valid_director_payload()
    bad_payload["camera_moves"] = [
        {
            "start_ms": 0,
            "end_ms": 20_000,  # 55% moving > 25% hard cap!
            "kind": "slow_push",
            "scale_start": 1.00,
            "scale_end": 1.12,
            "reason": "too much motion",
        }
    ]
    director = GeminiVideoDirector(
        api_key="test-key",
        transport=lambda _u, _b, _h: (200, _wrap_gemini_response(bad_payload)),
    )
    with pytest.raises(DirectorUnavailable, match="strict validation"):
        director.direct_clip(
            source_mp4=proxy,
            clip_in_ms=0,
            clip_out_ms=36_000,
            clip_id="s86-87",
            words=words,
            video_proxy=proxy,
        )


def test_gemini_video_director_rejects_oversized_inline_proxy_and_missing_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    words = _sample_kurdish_words()
    small = tmp_path / "small.mp4"
    small.write_bytes(b"abc")

    # Missing credential fails loud before any HTTP request is attempted.
    monkeypatch.setattr("hawedit.v8.director.read_credential", lambda _name: None)
    called = False

    def fail_if_called(_u: str, _b: bytes | None, _h: Mapping[str, str]) -> tuple[int, str]:
        nonlocal called
        called = True
        return 200, ""

    no_key_director = GeminiVideoDirector(api_key=None, transport=fail_if_called)
    with pytest.raises(DirectorUnavailable, match="GEMINI_API_KEY"):
        no_key_director.direct_clip(
            source_mp4=small,
            clip_in_ms=0,
            clip_out_ms=36_000,
            clip_id="s86-87",
            words=words,
            video_proxy=small,
        )
    assert not called

    # Oversized inline video refuses upload instead of silently dropping video.
    huge = tmp_path / "huge.mp4"
    with huge.open("wb") as fh:
        fh.seek(MAX_GEMINI_INLINE_BYTES)
        fh.write(b"\x00")
    director = GeminiVideoDirector(api_key="test-key", transport=fail_if_called)
    with pytest.raises(DirectorUnavailable, match="exceeds inline limit"):
        director.direct_clip(
            source_mp4=huge,
            clip_in_ms=0,
            clip_out_ms=36_000,
            clip_id="s86-87",
            words=words,
            video_proxy=huge,
        )


def test_gemini_critique_rendered_clip_builds_preview_and_parses_patch(tmp_path: Path) -> None:
    ffmpeg = _require_ffmpeg()
    rendered = _make_synthetic_mp4(tmp_path / "rendered.mp4", duration_s=2.0, height=720)
    words = _sample_kurdish_words()[:6]
    script = DirectorScript(
        clip_id="s86-87",
        hook_title_ckb="مۆدێلە نوێیەکە",
    )

    verdict_payload = {
        "approved": False,
        "score": 0.72,
        "issues": ["broken_kurdish_text: word 0 still reads ئەگەزانی"],
        "patch": {
            "word_repairs": [
                {
                    "word_index": 0,
                    "original": "ئەگەزانی",
                    "repaired": "ئەزانی",
                    "reason": "fix spoken Sorani",
                }
            ]
        },
    }

    seen_calls = 0

    def fake_transport(
        _url: str,
        body: bytes | None,
        _headers: Mapping[str, str],
    ) -> tuple[int, str]:
        nonlocal seen_calls
        seen_calls += 1
        assert body is not None
        req = json.loads(body.decode("utf-8"))
        assert req["contents"][0]["parts"][0]["inlineData"]["mimeType"] == "video/mp4"
        return 200, _wrap_gemini_response(verdict_payload)

    brain = GeminiVideoDirector(api_key="test-key", ffmpeg=ffmpeg, transport=fake_transport)
    preview_out = tmp_path / "preview_480p.mp4"
    verdict = critique_rendered_clip(
        brain,
        rendered_mp4=rendered,
        script=script,
        words=words,
        preview_out_mp4=preview_out,
        ffmpeg=ffmpeg,
    )
    assert seen_calls == 1
    assert preview_out.is_file() and preview_out.stat().st_size > 0
    assert verdict.approved is False
    assert verdict.score == pytest.approx(0.72)
    assert len(verdict.issues) == 1
    assert verdict.patch is not None
    assert "word_repairs" in verdict.patch


# ---------------------------------------------------------------------------
# 4. LocalOmniDirector Tests (Real FFmpeg Keyframes+WAV + Mocked OpenAI HTTP)
# ---------------------------------------------------------------------------


def test_local_omni_director_extracts_keyframes_and_wav_and_resolves_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ffmpeg = _require_ffmpeg()
    source = _make_synthetic_mp4(tmp_path / "clip.mp4", duration_s=2.5, height=480)
    words = _sample_kurdish_words()
    monkeypatch.setenv(OMNI_URL_ENV, "http://127.0.0.1:8008/v1")

    seen_urls: list[str] = []
    chat_payloads: list[dict[str, Any]] = []

    def fake_transport(
        url: str,
        body: bytes | None,
        headers: Mapping[str, str],
    ) -> tuple[int, str]:
        seen_urls.append(url)
        if url.endswith("/models"):
            assert body is None
            return 200, json.dumps(
                {
                    "data": [
                        {"id": "text-embedding-nomic-embed-text-v1.5"},
                        {"id": "qwen2.5-omni-7b"},
                    ]
                }
            )
        assert body is not None
        req = json.loads(body.decode("utf-8"))
        chat_payloads.append(req)
        wrapped = (
            "<think>checking audio loanwords</think>\n"
            f"```json\n{json.dumps(_valid_director_payload(), ensure_ascii=False)}\n```"
        )
        return 200, _wrap_openai_response(wrapped)

    director = LocalOmniDirector(
        include_audio=True,
        keyframe_fps=1.0,
        max_keyframes=6,
        ffmpeg=ffmpeg,
        transport=fake_transport,
    )
    script = director.direct_clip(
        source_mp4=source,
        clip_in_ms=0,
        clip_out_ms=36_000,
        clip_id="s86-87",
        words=words,
        video_proxy=source,
    )

    assert seen_urls == [
        "http://127.0.0.1:8008/v1/models",
        "http://127.0.0.1:8008/v1/chat/completions",
    ]
    assert len(chat_payloads) == 1
    req = chat_payloads[0]
    assert req["model"] == "qwen2.5-omni-7b"
    assert req["response_format"]["type"] == "json_schema"
    assert req["response_format"]["json_schema"]["strict"] is True
    assert req["response_format"]["json_schema"]["schema"]["additionalProperties"] is False

    user_blocks = req["messages"][1]["content"]
    image_blocks = [b for b in user_blocks if b["type"] == "image_url"]
    audio_blocks = [b for b in user_blocks if b["type"] == "input_audio"]
    assert len(image_blocks) >= 2
    assert image_blocks[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert len(audio_blocks) == 1
    assert audio_blocks[0]["input_audio"]["format"] == "wav"
    assert base64.b64decode(audio_blocks[0]["input_audio"]["data"]).startswith(b"RIFF")
    assert script.word_repairs[1].repaired == "ڕیستریکت"


def test_local_omni_director_fails_loud_when_server_unreachable_or_no_chat_model(
    tmp_path: Path,
) -> None:
    ffmpeg = _require_ffmpeg()
    source = _make_synthetic_mp4(tmp_path / "clip.mp4", duration_s=1.5, height=360)
    words = _sample_kurdish_words()

    only_embed = LocalOmniDirector(
        base_url="http://127.0.0.1:1234/v1",
        ffmpeg=ffmpeg,
        transport=lambda _u, _b, _h: (200, '{"data": [{"id": "nomic-embed-text"}]}'),
    )
    with pytest.raises(DirectorUnavailable, match="No multimodal/chat model loaded"):
        only_embed.direct_clip(
            source_mp4=source,
            clip_in_ms=0,
            clip_out_ms=36_000,
            clip_id="s86-87",
            words=words,
            video_proxy=source,
        )

    down_server = LocalOmniDirector(
        base_url="http://127.0.0.1:1234/v1",
        model_id="qwen3-omni",
        ffmpeg=ffmpeg,
        transport=lambda _u, _b, _h: (0, "Connection refused"),
    )
    with pytest.raises(DirectorUnavailable, match="HTTP 0"):
        down_server.direct_clip(
            source_mp4=source,
            clip_in_ms=0,
            clip_out_ms=36_000,
            clip_id="s86-87",
            words=words,
            video_proxy=source,
        )


# ---------------------------------------------------------------------------
# 5. OfflineRestrainedDirector Tests (Restraint Law, ASR Repair, WAV Z-Score)
# ---------------------------------------------------------------------------


def test_offline_restrained_director_enforces_locked_tripod_and_earned_moves(
    tmp_path: Path,
) -> None:
    words = _sample_kurdish_words()
    duration_ms = 36_000
    # Make word 33 ("سەرکەوتن" @ 26000..27200) acoustically loudest for Z-score peak!
    wav = _make_pcm_wav(
        tmp_path / "clip.wav",
        duration_ms=duration_ms,
        loud_spans_ms=((25_900, 27_300), (17_400, 18_500)),
    )
    dummy_mp4 = tmp_path / "source.mp4"
    dummy_mp4.write_bytes(b"mp4")

    director = OfflineRestrainedDirector(audio_wav=wav)
    script = director.direct_clip(
        source_mp4=dummy_mp4,
        clip_in_ms=0,
        clip_out_ms=duration_ms,
        clip_id="s86-87",
        words=words,
    )

    # Validates cleanly against schema.py D-382, D-383, and E3 rules.
    validate_director_script(script, duration_ms=duration_ms, words=words)

    # 1. Deterministic Sorani ASR repairs detected accurately.
    repaired_map = {r.word_index: (r.original, r.repaired) for r in script.word_repairs}
    assert repaired_map[0] == ("ئەگەزانی", "ئەزانی")
    assert repaired_map[1] == ("بەیانیەکەی", "بەیانییەکەی")
    assert repaired_map[2] == ("مۆدەی", "مۆدێل")
    assert repaired_map[12] == ("ڕیستیک", "ڕیستریکت")

    # 2. Strict human camera restraint: >= 80% locked tripod, <= 3 moves, 0 sway!
    slow_pushes = [m for m in script.camera_moves if m.kind == "slow_push"]
    punch_cuts = [m for m in script.camera_moves if m.kind == "punch_cut"]
    assert len(slow_pushes) == 1
    assert slow_pushes[0].scale_start == pytest.approx(1.00)
    assert slow_pushes[0].scale_end == pytest.approx(1.08)
    assert slow_pushes[0].end_ms - slow_pushes[0].start_ms == 3_500
    assert 1 <= len(punch_cuts) <= 2
    assert len(script.camera_moves) <= 3

    moving_ms = sum(m.end_ms - m.start_ms for m in script.camera_moves if m.is_moving)
    assert moving_ms / duration_ms <= 0.20  # >= 80% locked!

    cam_filter, _ = compile_restrained_camera_filter(duration_ms, script.camera_moves)
    assert "sin(" not in cam_filter

    # 3. Acoustic Z-score peak word ("سەرکەوتن", index 33) selected as semantic power word.
    power_words = {
        b.power_word_index for b in script.caption_beats if b.power_word_index is not None
    }
    assert 33 in power_words

    # 4. Strict viral TikTok chunking (max 3 short <= 14 chars, never 4 words).
    for beat in script.caption_beats:
        assert 1 <= len(beat.word_indices) <= 3

    # 5. Earned visual interrupts emitted (1-2) on >= 28 s clip.
    assert 1 <= len(script.visual_interrupts) <= 2

    # 6. Silence & filler cuts emitted on exact word boundaries.
    cut_kinds = {c.kind for c in script.cuts}
    assert "silence" in cut_kinds
    assert "filler" in cut_kinds


def test_offline_director_zero_punch_cuts_without_major_jump_cuts_and_zero_interrupts_short(
    tmp_path: Path,
) -> None:
    # 20 s clip with NO >= 600 ms pauses -> MUST emit ZERO punch_cuts (no arbitrary timers!)
    # and ZERO visual interrupts (< 28 s).
    words = tuple(
        Word(w=f"وشە{i}", start_ms=i * 600 + 100, end_ms=i * 600 + 500, conf=0.95)
        for i in range(30)
    )
    dummy_mp4 = tmp_path / "short.mp4"
    dummy_mp4.write_bytes(b"mp4")

    director = OfflineRestrainedDirector()
    script = director.direct_clip(
        source_mp4=dummy_mp4,
        clip_in_ms=0,
        clip_out_ms=20_000,
        clip_id="short-clip",
        words=words,
        jump_cuts_ms=((6_000, 350),),  # < 600 ms removed -> must NOT trigger punch_cut!
    )
    assert all(m.kind != "punch_cut" for m in script.camera_moves)
    assert script.visual_interrupts == ()


def test_offline_critique_catches_all_defects_and_returns_patch(tmp_path: Path) -> None:
    preview = tmp_path / "rendered.mp4"
    preview.write_bytes(b"rendered-mp4-bytes")
    words = (
        Word(w="ئەگەزانی", start_ms=100, end_ms=600, conf=0.95),
        Word(w="ئەم", start_ms=650, end_ms=900, conf=0.95),
        Word(w="تەکنەلۆژیایە", start_ms=950, end_ms=1600, conf=0.95),
        Word(w="زۆر", start_ms=1650, end_ms=2000, conf=0.95),
        Word(w="بەهێزە", start_ms=2050, end_ms=2800, conf=0.95),
    )
    flawed = DirectorScript(
        clip_id="flawed",
        hook_title_ckb="کورت",  # < 2 words (weak hook)
        word_repairs=(),  # missing repair for ئەگەزانی -> ئەزانی
        cuts=(CutRegion(start_ms=300, end_ms=500, kind="filler", reason="bad mid-word cut"),),
        camera_moves=(
            CameraMove(
                start_ms=0,
                end_ms=2_000,  # > 25% of 2800 ms
                kind="slow_push",
                scale_start=1.00,
                scale_end=1.10,
                reason="excessive motion",
            ),
        ),
        caption_beats=(CaptionBeat(word_indices=(0, 1, 2, 3)),),  # 4-word beat violation
    )

    director = OfflineRestrainedDirector()
    verdict = director.critique_clip(rendered_mp4=preview, script=flawed, words=words)
    assert isinstance(verdict, CritiqueVerdict)
    assert verdict.approved is False
    issue_text = " | ".join(verdict.issues)
    assert "unnecessary_motion" in issue_text
    assert "broken_kurdish_text" in issue_text
    assert "awkward_cut" in issue_text
    assert "subtitle_readability" in issue_text
    assert "viral_hook_strength" in issue_text
    assert verdict.patch is not None
    assert verdict.patch["camera_moves"] == []
    assert len(verdict.patch["word_repairs"]) == 1
    assert verdict.patch["cuts"] == []
    assert "hook_title_ckb" in verdict.patch

    # Patched script integrates cleanly with compiler.apply_critique_patch!
    patched = apply_critique_patch(flawed, verdict.patch)
    assert patched.camera_moves == ()
    assert patched.cuts == ()
    assert len(patched.word_repairs) == 1
    assert patched.word_repairs[0].repaired == "ئەزانی"

    # An intentionally omitted empty hook title (when no bounded source clause qualifies)
    # must pass critique rather than looping against _source_quote_hook.
    omitted_hook = DirectorScript(
        clip_id="omitted-hook",
        hook_title_ckb="",
        word_repairs=(patched.word_repairs[0],),
        cuts=(),
        camera_moves=(),
        caption_beats=(CaptionBeat(word_indices=(0, 1)), CaptionBeat(word_indices=(2, 3))),
    )
    omitted_verdict = director.critique_clip(rendered_mp4=preview, script=omitted_hook, words=words)
    assert omitted_verdict.approved is True
    assert not any("viral_hook_strength" in issue for issue in omitted_verdict.issues)


def test_offline_director_respects_source_shot_cuts_and_never_stacks_punch_cut(
    tmp_path: Path,
) -> None:
    words = _sample_kurdish_words()
    dummy_mp4 = tmp_path / "source.mp4"
    dummy_mp4.write_bytes(b"mp4")

    director = OfflineRestrainedDirector()
    # Both major editorial jump-cuts coincide with real source camera shot cuts!
    script = director.direct_clip(
        source_mp4=dummy_mp4,
        clip_in_ms=0,
        clip_out_ms=36_000,
        clip_id="multicam",
        words=words,
        shot_cuts_ms=(8_275, 15_775),
        jump_cuts_ms=((8_275, 950), (15_775, 1_100)),
    )
    assert all(m.kind != "punch_cut" for m in script.camera_moves)
    validate_director_script(script, duration_ms=36_000, words=words)


def test_local_omni_critique_clip_sends_keyframes_and_audio_and_parses_verdict(
    tmp_path: Path,
) -> None:
    ffmpeg = _require_ffmpeg()
    rendered = _make_synthetic_mp4(tmp_path / "rendered.mp4", duration_s=2.0, height=480)
    words = _sample_kurdish_words()[:6]
    script = DirectorScript(clip_id="s86-87", hook_title_ckb="مۆدێلە نوێیەکە")

    verdict_json = json.dumps(
        {"approved": True, "score": 94.5, "issues": [], "patch": None},
        ensure_ascii=False,
    )
    director = LocalOmniDirector(
        base_url="http://127.0.0.1:1234/v1",
        model_id="qwen2.5-omni-7b",
        include_audio=True,
        ffmpeg=ffmpeg,
        transport=lambda _u, _b, _h: (200, _wrap_openai_response(verdict_json)),
    )
    verdict = director.critique_clip(
        rendered_mp4=rendered,
        script=script,
        words=words,
        preview_mp4=rendered,
    )
    assert verdict.approved is True
    assert verdict.score == pytest.approx(94.5)
    assert verdict.issues == ()
    assert verdict.patch is None


# ---------------------------------------------------------------------------
# 6. Factory & Protocol Compatibility Tests
# ---------------------------------------------------------------------------


def test_create_director_brain_explicit_backends_and_protocol_conformance() -> None:
    gemini = create_director_brain("gemini", api_key="k")
    omni = create_director_brain("local-omni", base_url="http://127.0.0.1:1234/v1")
    offline = create_director_brain("offline")

    assert isinstance(gemini, GeminiVideoDirector)
    assert isinstance(omni, LocalOmniDirector)
    assert isinstance(offline, OfflineRestrainedDirector)
    for brain in (gemini, omni, offline):
        assert isinstance(brain, DirectorBrain)

    # Static structural conformance to compiler.V8DirectorProtocol (verified by mypy --strict).
    compiler_brains: tuple[V8DirectorProtocol, ...] = (gemini, omni, offline)
    assert len(compiler_brains) == 3

    with pytest.raises(ValueError, match="Unsupported director backend"):
        create_director_brain("invalid")  # type: ignore[arg-type]
