"""End-to-end integration tests for HawEdit V8 wired pipeline & Skia overlay rendering."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from hawedit.captions import find_ffmpeg
from hawedit.render import RenderError, render_clip
from hawedit.transcripts import Word
from hawedit.v8.__main__ import main
from hawedit.v8.compiler import V8CompileConfig, compile_v8_clip
from hawedit.v8.tiktok_subs import chunk_viral_kurdish_words


def _make_synthetic_source_mp4(path: Path, *, duration_s: float = 4.0) -> Path:
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    proc = subprocess.run(
        [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c=#1b2432:s=640x360:r=25:d={duration_s}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:sample_rate=48000:duration={duration_s}",
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
            "-y",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30.0,
    )
    assert proc.returncode == 0, proc.stderr
    return path


def _kurdish_sample_words() -> tuple[Word, ...]:
    return (
        Word("ئەگەزانی", 200, 700, 0.99),
        Word("مۆدەی", 760, 1200, 0.98),
        Word("بڵاو", 1260, 1650, 0.98),
        Word("کوردییەکەیان", 1720, 2350, 0.99),
        Word("لە", 2400, 2600, 0.99),
        Word("ڕەستۆرانتەکە", 2660, 3300, 0.97),
        Word("باشە.", 3360, 3800, 0.99),
    )


def test_v8_end_to_end_skia_and_libass_default_wiring(tmp_path: Path) -> None:
    """Real FFmpeg end-to-end V8 compile using default director, Skia/libass, ASD, and render."""
    source = _make_synthetic_source_mp4(tmp_path / "episode.mp4", duration_s=4.0)
    words = _kurdish_sample_words()

    # 1. Skia HarfBuzz RGBA overlay path (default sub_engine="skia").
    res_skia = compile_v8_clip(
        source_mp4=source,
        clip_id="e2e-skia",
        clip_in_ms=0,
        clip_out_ms=4_000,
        words=words,
        out_dir=tmp_path / "out_skia",
        config=V8CompileConfig(
            director_backend="offline",
            sub_engine="skia",
            fps=25.0,
            encoder="libx264",
            silence_threshold_ms=0,
            deliverable=False,
            progress_bar=True,
            keep_overlay=True,
        ),
    )
    assert res_skia.output_mp4.is_file() and res_skia.output_mp4.stat().st_size > 1_000
    assert res_skia.subtitles.engine == "skia"
    assert res_skia.subtitles.overlay_path is not None and res_skia.subtitles.overlay_path.is_file()
    assert res_skia.subtitles.ass_path is not None and res_skia.subtitles.ass_path.is_file()
    assert "sin(" not in res_skia.camera_filter
    assert res_skia.critique is not None and res_skia.critique.approved is True
    # Verify Sorani ASR orthography repairs were applied cleanly 1:1.
    repaired_tokens = [w.w for w in res_skia.repaired_words]
    assert "ئەزانی" in repaired_tokens
    assert "مۆدێل" in repaired_tokens
    assert "ڕێستۆرانتەکە" in repaired_tokens
    # Verify viral chunk law (<= 3 words, 3 only if <= 14 chars).
    chunks = chunk_viral_kurdish_words(res_skia.repaired_words)
    assert all(len(c.words) <= 3 for c in chunks)
    assert all(len(" ".join(w.text for w in c.words)) <= 14 for c in chunks if len(c.words) == 3)

    # 2. Pure libass viral fallback via CLI `python -m hawedit.v8`.
    transcript_json = tmp_path / "transcript.json"
    transcript_json.write_text(
        json.dumps(
            {
                "words": [
                    {"w": w.w, "start_ms": w.start_ms, "end_ms": w.end_ms, "conf": w.conf}
                    for w in words
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    rc = main(
        [
            str(source),
            "--transcript",
            str(transcript_json),
            "--sentences",
            "0-0",
            "--out-dir",
            str(tmp_path / "out_cli"),
            "--director",
            "offline",
            "--sub-engine",
            "libass",
            "--encoder",
            "libx264",
            "--silence-threshold-ms",
            "0",
        ]
    )
    assert rc == 0
    assert (tmp_path / "out_cli" / "episode-s0-0.v8.mp4").is_file()


def test_render_clip_rejects_missing_subtitle_overlay_path(tmp_path: Path) -> None:
    """Strict fail-stop: render_clip rejects a missing subtitle_overlay_path loudly."""
    from hawedit.boundary import Boundary
    from hawedit.clip import Clip, ClipTranscript, DiscoveryPath, Editorial, Output, Provenance, Qc
    from hawedit.render import Encoder
    from hawedit.transcripts import AsrProvenance
    from hawedit.v8.tiktok_subs import build_viral_tiktok_ass

    source = _make_synthetic_source_mp4(tmp_path / "src.mp4", duration_s=2.0)
    words = (Word("سڵاو", 200, 800, 0.99), Word("کوردستان.", 900, 1600, 0.99))
    ass_path = tmp_path / "subs.ass"
    ass_path.write_text(
        build_viral_tiktok_ass(chunk_viral_kurdish_words(words), clip_duration_ms=2_000),
        encoding="utf-8",
    )
    fonts_dir = Path(__file__).resolve().parents[1] / "assets" / "fonts"
    clip = Clip(
        clip_id="ov-missing",
        media_id="src",
        media_sha256="a" * 64,
        in_ms=0,
        out_ms=2_000,
        discovery_path=DiscoveryPath.VERBAL,
        boundary=Boundary(0, 2_000, 0, 2_000, None, None, True, 1.0),
        transcript=ClipTranscript(
            raw_ckb="سڵاو کوردستان.",
            norm_ckb="سڵاو کوردستان.",
            en_aux=None,
            words=words,
            asr=AsrProvenance(canonical="omniASR_LLM_7B_v2"),
        ),
        editorial=Editorial(0.85, True, 1.0, 0.0, 0.85, "test", "gemini-4-carbon"),
        output=Output("سڵاو", "سڵاو", "centre", "tiktok_skia", (2_000,)),
        qc=Qc(auto_pass=True),
        provenance=Provenance.current(),
    )

    with pytest.raises(RenderError, match="subtitle overlay file not found"):
        render_clip(
            clip,
            source,
            ass_path,
            fonts_dir,
            tmp_path / "out.mp4",
            640,
            360,
            encoder=Encoder.X264,
            for_review=True,
            subtitle_overlay_path=tmp_path / "does-not-exist.mov",
        )


def test_v9_style_camera_restraint_and_overlay_cleanup_and_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """V9 integration: preset camera caps, keep_overlay=False cleanup, and CLI subcommands."""
    from hawedit.v8.compiler import CachedDirectorScriptBrain
    from hawedit.v8.schema import CameraMove, DirectorScript

    source = _make_synthetic_source_mp4(tmp_path / "v9_src.mp4", duration_s=4.0)
    words = _kurdish_sample_words()
    saved_script = DirectorScript(
        clip_id="v9-cached",
        hook_title_ckb="مۆدێل و کوردی",
        camera_moves=(
            CameraMove(
                start_ms=1_500,
                end_ms=2_300,
                kind="punch_cut",
                scale_start=1.14,
                scale_end=1.14,
                reason="emphasis",
            ),
        ),
    )
    script_json = tmp_path / "saved.director.json"
    script_json.write_text(saved_script.to_json(indent=2), encoding="utf-8")

    # 1. broadcast_news locks 100% 1.00x AND default keep_overlay=False cleans .overlay.mov.
    res_news = compile_v8_clip(
        source_mp4=source,
        clip_id="v9-news",
        clip_in_ms=0,
        clip_out_ms=4_000,
        words=words,
        out_dir=tmp_path / "out_news",
        config=V8CompileConfig(
            director_backend="offline",
            sub_engine="skia",
            fps=25.0,
            encoder="libx264",
            silence_threshold_ms=0,
            deliverable=False,
            style_preset="broadcast_news",
        ),
        director=CachedDirectorScriptBrain(script_json),
    )
    assert res_news.script.camera_moves == ()
    assert res_news.subtitles.overlay_path is not None
    assert not res_news.subtitles.overlay_path.exists()
    assert res_news.grill_report is not None and res_news.grill_report.passed

    # 2. luxury_minimal clamps camera scale to <= 1.08 + renders speaker bio & end card cleanly.
    res_lux = compile_v8_clip(
        source_mp4=source,
        clip_id="v9-lux",
        clip_in_ms=0,
        clip_out_ms=4_000,
        words=words,
        out_dir=tmp_path / "out_lux",
        config=V8CompileConfig(
            director_backend="offline",
            sub_engine="skia",
            fps=25.0,
            encoder="libx264",
            silence_threshold_ms=0,
            deliverable=False,
            style_preset="luxury_minimal",
            speaker_name_ckb="هاوژین",
            speaker_role_ckb="پێشکەشکار",
            end_card_title_ckb="فۆڵۆومان بکەن",
            end_card_handle="@hawedit",
        ),
        director=CachedDirectorScriptBrain(script_json),
    )
    assert len(res_lux.script.camera_moves) == 1
    assert res_lux.script.camera_moves[0].scale_start <= 1.08
    assert res_lux.script.camera_moves[0].scale_end <= 1.08
    assert res_lux.subtitles.overlay_path is not None
    assert not res_lux.subtitles.overlay_path.exists()

    # 3. CLI: `doctor --json` + single-clip `--client-pack` emit verified artifacts & zero .mov.
    rc_doc = main(["doctor", "--json", "--work-dir", str(tmp_path)])
    assert rc_doc in (0, 2)
    doc_payload = json.loads(capsys.readouterr().out)
    assert "ready_for_production" in doc_payload and "checks_by_name" in doc_payload

    transcript_json = tmp_path / "transcript.json"
    transcript_json.write_text(
        json.dumps(
            {
                "words": [
                    {"w": w.w, "start_ms": w.start_ms, "end_ms": w.end_ms, "conf": w.conf}
                    for w in words
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    pack_dir = tmp_path / "out_pack"
    rc_pack = main(
        [
            str(source),
            "--transcript",
            str(transcript_json),
            "--sentences",
            "0-0",
            "--out-dir",
            str(pack_dir),
            "--director-script",
            str(script_json),
            "--style-preset",
            "crimson_punch",
            "--sub-engine",
            "skia",
            "--encoder",
            "libx264",
            "--silence-threshold-ms",
            "0",
            "--client-pack",
        ]
    )
    assert rc_pack == 0
    pack_out = json.loads(capsys.readouterr().out)
    assert pack_out["style_preset"] == "crimson_punch"
    assert pack_out["delivery_pack"]["overlay_cleaned"] is True
    assert pack_out["delivery_pack"]["overlay_bytes_reclaimed"] > 0
    assert (pack_dir / "client-review.html").is_file()
    assert list(pack_dir.glob("*.overlay.mov")) == []
