"""CLI entry point for HawEdit V8/V9 Lean Multimodal Director (``python -m hawedit.v8``)."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from hawedit.delivery import DeliveryError
from hawedit.render import RenderError
from hawedit.sentences import segment_sentences
from hawedit.v8.compiler import (
    CachedDirectorScriptBrain,
    DirectorBackend,
    SubtitleEngine,
    V8ActiveSpeakerTrackerProtocol,
    V8ClipRendererProtocol,
    V8CompileConfig,
    V8CompileError,
    V8DirectorProtocol,
    V8SubtitleRendererProtocol,
    compile_v8_clip,
    load_transcript_words,
    parse_sentence_indices,
    select_clip_span_from_sentences,
)
from hawedit.v8.delivery_pack import (
    DeliveryPackError,
    write_client_delivery_pack,
    write_client_review_html,
)
from hawedit.v8.director import LocalDirectorModality
from hawedit.v8.doctor import format_doctor_report, run_v8_doctor
from hawedit.v8.episode import V8EpisodeConfig, V8EpisodeError, compile_v8_episode
from hawedit.v8.localization import translate_sidecar
from hawedit.v8.schema import DirectorScriptError
from hawedit.v8.story_editor import StoryEditorError
from hawedit.v8.styles import CLIENT_STYLE_PRESETS
from hawedit.v8.youtube import resolve_youtube_source

__all__ = ["build_doctor_parser", "build_episode_parser", "build_parser", "main"]

_STYLE_CHOICES = tuple(CLIENT_STYLE_PRESETS.keys())


def _add_shared_v9_style_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--style-preset",
        choices=_STYLE_CHOICES,
        default="viral_gold",
        help="Client subtitle/brand preset (D-388).",
    )
    p.add_argument(
        "--brand-accent-hex",
        type=str,
        default=None,
        help="Optional #RRGGBB brand accent override.",
    )
    p.add_argument(
        "--speaker-name",
        type=str,
        default=None,
        help="Optional Kurdish speaker lower-third name (e.g. 'هاوژین').",
    )
    p.add_argument(
        "--speaker-role",
        type=str,
        default=None,
        help="Optional Kurdish speaker lower-third role (e.g. 'پێشکەشکار').",
    )
    p.add_argument(
        "--end-card-title",
        type=str,
        default=None,
        help="Optional Kurdish outro CTA end-card title (final 2.0 s).",
    )
    p.add_argument(
        "--end-card-subtitle",
        type=str,
        default=None,
        help="Optional Kurdish outro CTA end-card subtitle.",
    )
    p.add_argument(
        "--end-card-handle",
        type=str,
        default=None,
        help="Optional social handle pill on the outro end card (e.g. '@hawedit').",
    )
    p.add_argument(
        "--local-modality",
        choices=("omni", "vision", "text"),
        default=None,
        help="Explicit modality for --director local-omni (D-391).",
    )
    p.add_argument(
        "--keep-overlay",
        action="store_true",
        help="Keep bulky intermediate .v8.overlay.mov after successful encode & grill.",
    )


def build_parser() -> argparse.ArgumentParser:
    """Construct the single-clip ``python -m hawedit.v8`` argument parser."""
    p = argparse.ArgumentParser(
        prog="python -m hawedit.v8",
        description="HawEdit V8/V9 Lean Multimodal Director clip compiler.",
    )
    p.add_argument("source", type=Path, help="Source video path.")
    p.add_argument("--transcript", type=Path, required=True, help="Aligned transcript JSON.")
    p.add_argument("--sentences", type=str, required=True, help="Sentence range, e.g. '86-87'.")
    p.add_argument("--out-dir", type=Path, required=True, help="Output directory.")
    p.add_argument("--director", choices=("gemini", "local-omni", "offline"), default="offline")
    p.add_argument(
        "--director-script",
        type=Path,
        default=None,
        help="Replay a saved DirectorScript JSON deterministically (zero LLM call).",
    )
    p.add_argument("--sub-engine", choices=("skia", "libass"), default="skia")
    p.add_argument("--clip-id", type=str, default=None)
    p.add_argument("--fps", type=float, default=25.0)
    p.add_argument("--encoder", type=str, default="h264_nvenc")
    p.add_argument("--condense", action="store_true", help="Condense long stories to 30-48s.")
    p.add_argument("--cold-open", action="store_true", help="Prepend a 1.8-3.4s payoff hook.")
    p.add_argument("--silence-threshold-ms", type=int, default=420)
    p.add_argument("--silence-target-gap-ms", type=int, default=140)
    p.add_argument("--no-excise-fillers", action="store_true")
    p.add_argument("--no-progress-bar", action="store_true")
    p.add_argument("--asd-onnx", type=Path, default=None, help="Optional Light-ASD ONNX model.")
    p.add_argument("--director-model", type=str, default=None)
    p.add_argument("--omni-url", type=str, default=None)
    p.add_argument("--no-critique", action="store_true")
    p.add_argument("--no-asd", action="store_true")
    p.add_argument("--no-cinema-grade", action="store_true")
    p.add_argument(
        "--client-pack",
        action="store_true",
        help="Emit full ClientDeliveryPack (.srt, .edl, .otio, .cover.png, client-review.html).",
    )
    _add_shared_v9_style_flags(p)
    return p


def build_episode_parser() -> argparse.ArgumentParser:
    """Construct the ``python -m hawedit.v8 episode`` full-episode batch parser (D-389)."""
    p = argparse.ArgumentParser(
        prog="python -m hawedit.v8 episode",
        description="HawEdit V9 full-episode multi-reel compiler & client delivery pack.",
    )
    p.add_argument("source", help="Full source episode file or YouTube video URL.")
    p.add_argument(
        "--source-library", type=Path, help="Directory for cached YouTube source videos."
    )
    p.add_argument("--out-dir", type=Path, required=True, help="Output directory.")
    p.add_argument("--transcript", type=Path, default=None, help="Aligned transcript JSON.")
    p.add_argument(
        "--use-omni-asr",
        action="store_true",
        help="Run Stage 0/1 WSL OmniASR automatically when --transcript is omitted.",
    )
    p.add_argument("--subtitles", choices=("ar", "en"), action="append", default=[])
    p.add_argument("--dub", choices=("ar", "en"), action="append", default=[])
    p.add_argument("--translation-model", help="Model ID on the local subtitle server")
    p.add_argument("--max-clips", type=int, default=3)
    p.add_argument("--min-duration-ms", type=int, default=28_000)
    p.add_argument("--max-duration-ms", type=int, default=68_000)
    p.add_argument("--min-separation-ms", type=int, default=30_000)
    p.add_argument(
        "--sentences",
        type=str,
        action="append",
        default=None,
        help="Optional explicit sentence range override (repeatable, e.g. --sentences 86-87).",
    )
    p.add_argument(
        "--audio-wav", type=Path, default=None, help="Optional pre-extracted 16 kHz WAV."
    )
    p.add_argument("--director", choices=("gemini", "local-omni", "offline"), default="offline")
    p.add_argument("--sub-engine", choices=("skia", "libass"), default="skia")
    p.add_argument("--fps", type=float, default=25.0)
    p.add_argument("--encoder", type=str, default="h264_nvenc")
    p.add_argument("--condense", action="store_true", help="Condense long stories to 30-48s.")
    p.add_argument("--cold-open", action="store_true", help="Prepend a 1.8-3.4s payoff hook.")
    p.add_argument("--silence-threshold-ms", type=int, default=420)
    p.add_argument("--silence-target-gap-ms", type=int, default=140)
    p.add_argument("--no-excise-fillers", action="store_true")
    p.add_argument("--no-progress-bar", action="store_true")
    p.add_argument("--asd-onnx", type=Path, default=None)
    p.add_argument("--director-model", type=str, default=None)
    p.add_argument("--omni-url", type=str, default=None)
    p.add_argument("--no-critique", action="store_true")
    p.add_argument("--no-asd", action="store_true")
    p.add_argument("--no-cinema-grade", action="store_true")
    p.add_argument(
        "--story-mode",
        choices=("auto", "semantic-multicut", "legacy"),
        default="auto",
        help="V10.2 story selection mode (semantic-multicut default for gemini/local-omni).",
    )
    p.add_argument(
        "--broll-dir",
        type=Path,
        default=None,
        help="Optional local commercial B-roll folder for content-aware visual cutaways.",
    )
    p.add_argument(
        "--allow-web-stock",
        action="store_true",
        help="Allow stock-media searches for this episode.",
    )
    p.add_argument(
        "--no-broll",
        action="store_true",
        help="Disable content-aware B-roll cutaways & Top-PiP overlays.",
    )
    p.add_argument(
        "--no-banter-split",
        action="store_true",
        help="Disable automatic 50/50 split-screen on dual-speaker banter wide shots.",
    )
    p.add_argument(
        "--music-mood",
        choices=("none", "curious", "cinematic", "energetic"),
        default="curious",
        help="Optional subtle CC0 procedural voice-ducked ambient music bed (D-395).",
    )
    p.add_argument(
        "--no-overgenerate",
        action="store_true",
        help="Disable candidate over-generation and quarantine promotion.",
    )
    p.add_argument(
        "--no-local-vlm",
        action="store_true",
        help="Disable local §7 VideoChat3-4B / TimeLens2-4B visual grounding.",
    )
    _add_shared_v9_style_flags(p)
    return p


def build_doctor_parser() -> argparse.ArgumentParser:
    """Construct the ``python -m hawedit.v8 doctor`` preflight diagnostic parser (D-391)."""
    p = argparse.ArgumentParser(
        prog="python -m hawedit.v8 doctor",
        description="HawEdit V8/V9 team preflight diagnostic doctor.",
    )
    p.add_argument("--json", action="store_true", help="Emit structured JSON report.")
    p.add_argument("--work-dir", type=Path, default=None, help="Drive/path for disk space check.")
    p.add_argument("--omni-url", type=str, default=None, help="Local OpenAI-compatible server URL.")
    return p


def _run_doctor_cli(argv: Sequence[str]) -> int:
    args = build_doctor_parser().parse_args(list(argv))
    report = run_v8_doctor(work_dir=args.work_dir, omni_url=args.omni_url)
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_doctor_report(report))
    return 0 if report.ready_for_production else 2


def _run_episode_cli(argv: Sequence[str]) -> int:
    args = build_episode_parser().parse_args(list(argv))
    director_backend: DirectorBackend = args.director
    sub_engine: SubtitleEngine = args.sub_engine
    local_modality: LocalDirectorModality | None = args.local_modality

    try:
        source = (
            resolve_youtube_source(args.source, args.source_library or args.out_dir / ".sources")
            if "://" in args.source
            else Path(args.source)
        )
        sentence_ranges: tuple[tuple[int, ...], ...] | None = None
        if args.sentences:
            sentence_ranges = tuple(parse_sentence_indices(spec) for spec in args.sentences)
        cfg = V8EpisodeConfig(
            director=director_backend,
            sub_engine=sub_engine,
            max_clips=args.max_clips,
            min_duration_ms=args.min_duration_ms,
            max_duration_ms=args.max_duration_ms,
            min_separation_ms=args.min_separation_ms,
            condense=args.condense,
            cold_open=args.cold_open,
            fps=args.fps,
            encoder=args.encoder,
            cinema_grade=not args.no_cinema_grade,
            enable_critique=not args.no_critique,
            enable_asd=not args.no_asd,
            silence_threshold_ms=args.silence_threshold_ms,
            silence_target_gap_ms=args.silence_target_gap_ms,
            excise_fillers=not args.no_excise_fillers,
            progress_bar=not args.no_progress_bar,
            keep_overlay=args.keep_overlay,
            style_preset=args.style_preset,
            brand_accent_hex=args.brand_accent_hex,
            speaker_name_ckb=args.speaker_name,
            speaker_role_ckb=args.speaker_role,
            end_card_title_ckb=args.end_card_title,
            end_card_subtitle_ckb=args.end_card_subtitle,
            end_card_handle=args.end_card_handle,
            director_model=args.director_model,
            omni_url=args.omni_url,
            local_modality=local_modality,
            asd_onnx_path=args.asd_onnx,
            story_mode=args.story_mode,
            subtitle_languages=tuple(args.subtitles),
            dub_languages=tuple(args.dub),
            translation_model=args.translation_model,
            allow_web_stock=args.allow_web_stock,
            enable_broll=not args.no_broll,
            broll_dir=args.broll_dir,
            enable_banter_split=not args.no_banter_split,
            music_mood=args.music_mood,
            overgenerate_candidates=not args.no_overgenerate,
            enable_local_vlm=not args.no_local_vlm,
        )
        result = compile_v8_episode(
            source=source,
            out_dir=args.out_dir,
            transcript_path=args.transcript,
            use_omni_asr=args.use_omni_asr,
            config=cfg,
            sentence_ranges=sentence_ranges,
            audio_wav_path=args.audio_wav,
        )
    except (
        OSError,
        ValueError,
        DirectorScriptError,
        V8EpisodeError,
        V8CompileError,
        DeliveryPackError,
        RenderError,
    ) as exc:
        print(f"hawedit.v8 episode error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result.to_dict(), ensure_ascii=False))
    return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    director: V8DirectorProtocol | None = None,
    subtitle_renderer: V8SubtitleRendererProtocol | None = None,
    speaker_tracker: V8ActiveSpeakerTrackerProtocol | None = None,
    clip_renderer: V8ClipRendererProtocol | None = None,
) -> int:
    """Run the V8/V9 CLI and return a POSIX exit status (0 = ok, 2 = strict fail-stop)."""
    argv_list = list(argv) if argv is not None else sys.argv[1:]
    if argv_list and argv_list[0] == "publish-instagram":
        from hawedit.v8.instagram import instagram_cli

        return instagram_cli(argv_list[1:])
    if argv_list and argv_list[0] == "dub":
        from hawedit.v8.dubbing import dub_cli

        return dub_cli(argv_list[1:])
    if argv_list and argv_list[0] == "team":
        from hawedit.v8.team_review import team_cli

        return team_cli(argv_list[1:])
    if argv_list and argv_list[0] == "localize":
        parser = argparse.ArgumentParser(prog="hawedit.v8 localize")
        parser.add_argument("srt", type=Path, help="Finished Sorani reel SRT")
        parser.add_argument("--language", choices=("ar", "en"), action="append", required=True)
        parser.add_argument("--model", help="Model served by the local director")
        options = parser.parse_args(argv_list[1:])
        try:
            for language in dict.fromkeys(options.language):
                print(translate_sidecar(options.srt, language, options.model))
        except (OSError, ValueError, StoryEditorError, DeliveryError) as exc:
            print(f"Subtitle translation failed: {exc}", file=sys.stderr)
            return 2
        return 0
    if argv_list and argv_list[0] == "doctor":
        return _run_doctor_cli(argv_list[1:])
    if argv_list and argv_list[0] == "episode":
        return _run_episode_cli(argv_list[1:])

    args = build_parser().parse_args(argv_list)
    director_backend: DirectorBackend = args.director
    sub_engine: SubtitleEngine = args.sub_engine
    local_modality: LocalDirectorModality | None = args.local_modality

    try:
        words = load_transcript_words(args.transcript)
        sentence_indices = parse_sentence_indices(args.sentences)
        clip_in_ms, clip_out_ms, clip_words = select_clip_span_from_sentences(
            words, sentence_indices
        )
        all_sentences = segment_sentences(words)
        selected_sentences = tuple(all_sentences[idx] for idx in sorted(sentence_indices))
        clip_id = (
            args.clip_id or f"{args.source.stem}-s{sentence_indices[0]}-{sentence_indices[-1]}"
        )
        effective_director = (
            director
            if director is not None
            else (
                CachedDirectorScriptBrain(args.director_script)
                if args.director_script is not None
                else None
            )
        )
        result = compile_v8_clip(
            source_mp4=args.source,
            clip_id=clip_id,
            clip_in_ms=clip_in_ms,
            clip_out_ms=clip_out_ms,
            words=clip_words,
            out_dir=args.out_dir,
            config=V8CompileConfig(
                director_backend=director_backend,
                sub_engine=sub_engine,
                fps=args.fps,
                cinema_grade=not args.no_cinema_grade,
                enable_critique=not args.no_critique,
                enable_asd=not args.no_asd,
                encoder=args.encoder,
                condense=args.condense,
                cold_open=args.cold_open,
                silence_threshold_ms=args.silence_threshold_ms,
                silence_target_gap_ms=args.silence_target_gap_ms,
                excise_fillers=not args.no_excise_fillers,
                progress_bar=not args.no_progress_bar,
                asd_onnx_path=args.asd_onnx,
                director_model=args.director_model,
                omni_url=args.omni_url,
                local_modality=local_modality,
                style_preset=args.style_preset,
                brand_accent_hex=args.brand_accent_hex,
                speaker_name_ckb=args.speaker_name,
                speaker_role_ckb=args.speaker_role,
                end_card_title_ckb=args.end_card_title,
                end_card_subtitle_ckb=args.end_card_subtitle,
                end_card_handle=args.end_card_handle,
                # If --client-pack will build the pack, let it reclaim & log overlay bytes.
                keep_overlay=True if args.client_pack else args.keep_overlay,
            ),
            director=effective_director,
            subtitle_renderer=subtitle_renderer,
            speaker_tracker=speaker_tracker,
            clip_renderer=clip_renderer,
            source_sentences=selected_sentences,
        )
        pack_dict: dict[str, Any] | None = None
        review_html: Path | None = None
        if args.client_pack:
            pack = write_client_delivery_pack(
                result,
                source_mp4=args.source,
                clip_in_ms=clip_in_ms,
                clip_out_ms=clip_out_ms,
                fps=args.fps,
                media_id=args.source.stem,
                hook_title_ckb=result.script.hook_title_ckb,
                post_cta=(args.end_card_title, args.end_card_subtitle, args.end_card_handle),
                retained_intervals_ms=result.retained_intervals_ms,
                keep_overlay=args.keep_overlay,
            )
            review_html = write_client_review_html(
                [pack],
                args.out_dir / "client-review.html",
                episode_title=f"HawEdit V9 — {clip_id}",
                source_name=args.source.name,
                director_backend=result.director_backend,
                style_preset=args.style_preset,
            )
            pack_dict = pack.to_dict()
    except (DirectorScriptError, V8CompileError, DeliveryPackError, RenderError) as exc:
        print(f"hawedit.v8 error: {exc}", file=sys.stderr)
        return 2

    payload: dict[str, Any] = {
        "clip_id": result.clip_id,
        "output_mp4": str(result.output_mp4),
        "script_path": str(result.script_path),
        "director_backend": result.director_backend,
        "sub_engine": result.sub_engine,
        "style_preset": args.style_preset,
        "camera_moves": len(result.script.camera_moves),
        "word_repairs": len(result.script.word_repairs),
        "subtitle_chunks": result.subtitles.chunk_count,
        "locked_crops": len(result.locked_crops),
        "critique_revisions": result.critique_revisions,
        "critique_approved": result.critique.approved if result.critique else None,
        "grill_passed": result.grill_report.passed if result.grill_report else None,
    }
    if pack_dict is not None:
        payload["delivery_pack"] = pack_dict
        payload["review_html"] = str(review_html)
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
