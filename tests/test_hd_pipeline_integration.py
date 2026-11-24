"""Integration tests for Lane 4 (`hd-integrate`, D-363, T8): end-to-end wiring of
human-grade-director-v2 audio mastering, content-aware push-ins, edge-guard camera
stabilization, face-aware 2-line hook card, zero-orphan captions, and excited karaoke pop.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from hawedit.audio_signals import SentenceAudioMetrics
from hawedit.boundary import Boundary
from hawedit.captions import (
    DEFAULT_CAPTION_FONT,
    VIRAL_FONT_SIZE,
    VIRAL_THEME,
    CaptionStyle,
    build_ass,
    find_ffmpeg,
)
from hawedit.clip import DiscoveryPath
from hawedit.content_type import resolve_effective_configuration
from hawedit.discovery import Candidate
from hawedit.judge import KURDISH_EDITORIAL_JUDGE, JudgeRequest, JudgeVerdict
from hawedit.pipeline import (
    StageSkipped,
    _build_clip_punch_ins,
    _excited_caption_intervals_ms,
    _trim_trailing_flash_cut,
    run_pipeline,
)
from hawedit.reframe import FocusPoint
from hawedit.render import Encoder, vertical_crop_size
from hawedit.sentences import Sentence
from hawedit.silence import plan_silence_tightening, tighten_sentences
from hawedit.transcripts import (
    AsrProvenance,
    NormalizedTranscript,
    RawTranscript,
    TranscriptStore,
    Word,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "kurdish-speech-3cuts.mp4"
FONTS_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
_EXCITED_POP_SNIPPET = r"\1c&H002EFFB8&"
_LONG_HOOK_TITLE = "ئایا ژیری دەستکرد جێگەی مرۆڤ دەگرێتەوە لە داهاتوودا؟"


def _make_verdict(
    candidate_id: str, clip_in_ms: int, clip_out_ms: int, payoff_at_ms: int
) -> JudgeVerdict:
    payoff = max(clip_in_ms, min(clip_out_ms, payoff_at_ms))
    return JudgeVerdict(
        candidate_id=candidate_id,
        hook_score=0.91,
        self_contained=True,
        payoff_at_ms=payoff,
        meaning_fidelity=0.96,
        misleading_edit_risk=0.04,
        cultural_landing=0.92,
        narrative_role="payoff",
        title_ckb=_LONG_HOOK_TITLE,
        description_ckb="وەسفی تەواوی کوردی بۆ تاقیکردنەوەی دایرێکتەر.",
        hashtags_ckb=("#کوردی",),
        judge=KURDISH_EDITORIAL_JUDGE,
        clip_in_ms=clip_in_ms,
        clip_out_ms=clip_out_ms,
    )


class _StubDirectorJudge:
    model_id = KURDISH_EDITORIAL_JUDGE

    def __init__(self, payoff_at_ms: int) -> None:
        self._payoff_at_ms = payoff_at_ms

    def judge(self, request: JudgeRequest) -> JudgeVerdict:
        return _make_verdict(
            request.candidate_id,
            request.clip_in_ms,
            request.clip_out_ms,
            self._payoff_at_ms,
        )


class _LeaningForeheadFaceTracker:
    """Stub tracker emitting upper-frame face geometry (`f_top < 420`) with a mid-clip lean."""

    last_intra_shot_switches_ms: tuple[int, ...] = ()

    def track(
        self,
        source: Path,
        in_ms: int,
        out_ms: int,
        shot_cuts_ms: Sequence[int] = (),
    ) -> tuple[FocusPoint, ...]:
        step = 200
        pts: list[FocusPoint] = []
        mid = (in_ms + out_ms) // 2
        t = in_ms
        while t < out_ms:
            # Lean sharply past dead_zone_px & edge_guard_px in the second half.
            cx = 310 if t < mid else 365
            # On 640x360: fcy=90, fh=120 -> face_top_src=30 -> ~160 px on 1920 canvas (< 420).
            pts.append(FocusPoint(at_ms=t, center_x=cx, center_y=90, face_height=120))
            t += step
        return tuple(pts)


def _director_v2_transcript(media_id: str) -> RawTranscript:
    """2 complete sentences: calm sentence 0, excited sentence 1 with orphan `لێی.` + digit `3`."""
    words = (
        # Sentence 0 (calm): 100..1500 ms
        Word(w="ئەمە", start_ms=100, end_ms=500, conf=0.95),
        Word(w="بابەتێکی", start_ms=540, end_ms=1_000, conf=0.95),
        Word(w="نوێیە.", start_ms=1_040, end_ms=1_500, conf=0.95),
        # Sentence 1 (excited): 1800..3600 ms — 4 words, trailing short orphan `لێی.` (gap 80ms)
        Word(w="3", start_ms=1_800, end_ms=2_150, conf=0.94),
        Word(w="گۆشەی", start_ms=2_200, end_ms=2_650, conf=0.96),
        Word(w="گرنگ", start_ms=2_700, end_ms=3_120, conf=0.95),
        Word(w="لێی.", start_ms=3_200, end_ms=3_600, conf=0.94),
    )
    return RawTranscript(
        media_id=media_id,
        text_ckb="ئەمە بابەتێکی نوێیە. 3 گۆشەی گرنگ لێی.",
        words=words,
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
        media_sha256=hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
    )


def _dialogue_lines(ass_text: str) -> list[str]:
    return [line for line in ass_text.splitlines() if line.startswith("Dialogue:")]


def test_pipeline_wires_director_v2_audio_camera_and_captions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-9 / T8 (D-363): pipeline wires two-pass broadcast loudness, content-aware push-ins,
    edge-guard camera stabilization, face-aware 2-line hook card, zero-orphan captions,
    excited karaoke micro-pop, and preserves raw.json / clip.transcript immutably.
    """
    ffmpeg = find_ffmpeg()
    if ffmpeg is None or not ffmpeg.is_file():
        pytest.skip("needs ffmpeg")

    from hawedit.audio_signals import analyze_sentence_audio as real_analyze_sentence_audio
    from hawedit.captions import build_ass as real_build_ass
    from hawedit.reframe import stabilize as real_stabilize
    from hawedit.render import (
        content_aware_push_schedule as real_content_aware_push,
    )
    from hawedit.render import (
        render_clip as real_render_clip,
    )

    render_calls: list[dict[str, Any]] = []
    push_calls: list[dict[str, Any]] = []
    stabilize_calls: list[dict[str, Any]] = []
    build_ass_calls: list[dict[str, Any]] = []

    def spy_analyze_sentence_audio(
        audio_path: Path, sentences: Sequence[Sentence]
    ) -> tuple[SentenceAudioMetrics, ...]:
        # Run the real WAV analyzer first, then inject deterministic calm/excited scores
        # so the 4s fixture cleanly exercises both calm and excited/burst director branches.
        measured = real_analyze_sentence_audio(audio_path, sentences)
        assert len(measured) == len(sentences)
        tuned: list[SentenceAudioMetrics] = []
        for idx, m in enumerate(measured):
            if idx == 0:
                tuned.append(
                    SentenceAudioMetrics(
                        sentence_index=m.sentence_index,
                        rms_db=m.rms_db,
                        rms_z=-0.4,
                        peak_burst_count=0,
                        speech_rate_wps=m.speech_rate_wps,
                        pause_before_ms=m.pause_before_ms,
                        excitement_score=0.20,
                        tags=(),
                    )
                )
            else:
                tuned.append(
                    SentenceAudioMetrics(
                        sentence_index=m.sentence_index,
                        rms_db=m.rms_db,
                        rms_z=1.6,
                        peak_burst_count=3,
                        speech_rate_wps=m.speech_rate_wps,
                        pause_before_ms=m.pause_before_ms,
                        excitement_score=0.88,
                        tags=("high-energy", "burst"),
                    )
                )
        return tuple(tuned)

    def spy_render_clip(*args: Any, **kwargs: Any) -> Any:
        render_calls.append(dict(kwargs))
        return real_render_clip(*args, **kwargs)

    def spy_content_aware_push(spans: Sequence[tuple[int, int]], **kwargs: Any) -> Any:
        push_calls.append({"spans": tuple(spans), **kwargs})
        return real_content_aware_push(spans, **kwargs)

    def spy_stabilize(points: Sequence[FocusPoint], **kwargs: Any) -> Any:
        stabilize_calls.append(dict(kwargs))
        return real_stabilize(points, **kwargs)

    def spy_build_ass(*args: Any, **kwargs: Any) -> str:
        build_ass_calls.append(dict(kwargs))
        return real_build_ass(*args, **kwargs)

    monkeypatch.setattr("hawedit.pipeline.analyze_sentence_audio", spy_analyze_sentence_audio)
    monkeypatch.setattr("hawedit.pipeline.render_clip", spy_render_clip)
    monkeypatch.setattr("hawedit.pipeline.content_aware_push_schedule", spy_content_aware_push)
    monkeypatch.setattr("hawedit.pipeline.stabilize", spy_stabilize)
    monkeypatch.setattr("hawedit.pipeline.build_ass", spy_build_ass)

    def spy_discover(
        norm: NormalizedTranscript,
        *,
        sentences: Sequence[Sentence] | None = None,
        audio_metrics: Sequence[SentenceAudioMetrics] | None = None,
    ) -> list[Candidate]:
        assert sentences is not None and len(sentences) == 2
        assert audio_metrics is not None and len(audio_metrics) == 2
        return [
            Candidate("v1", norm.media_id, 100, 3_600, DiscoveryPath.VERBAL, rank=1, score=0.95)
        ]

    # --- Phase 1: Episode batch mode (`max_clips=1`) -----------------------------------------
    transcript = _director_v2_transcript("hd-ep")
    original_text = transcript.text_ckb
    original_words = [(w.w, w.start_ms, w.end_ms, w.conf) for w in transcript.words]
    work_ep = tmp_path / "work_episode"

    ep_run = run_pipeline(
        FIXTURE,
        work_ep,
        media_id="hd-ep",
        transcript=transcript,
        discover=spy_discover,
        judge=_StubDirectorJudge(payoff_at_ms=2_600),
        auto_select=True,
        max_clips=1,
        min_clip_ms=1_000,
        eased_push=True,
        caption_style=CaptionStyle.WORD_HIGHLIGHT,
        subject_tracker=_LeaningForeheadFaceTracker(),
        min_face_share=0.0,
        encoder=Encoder.X264,
        polish_captions=True,
        ffmpeg=ffmpeg,
    )

    assert ep_run.episode_manifest is not None
    assert ep_run.episode_manifest.clips_count == 1
    assert ep_run.render is not None and not isinstance(ep_run.render, StageSkipped)
    assert ep_run.clip is not None

    # (a) Episode render passes two_pass_loudness=True and speech_chain=True with linear pass1.
    assert len(render_calls) == 1
    assert render_calls[0]["two_pass_loudness"] is True
    assert render_calls[0]["speech_chain"] is True
    assert ep_run.render.loudness_pass1 is not None

    # (b) content_aware_push_schedule received real audio_metrics excitement & clip-rel payoff.
    assert len(push_calls) >= 1
    ep_push = push_calls[0]
    assert ep_push["spans"]
    assert len(ep_push["excitement_by_span"]) == len(ep_push["spans"])
    assert max(ep_push["excitement_by_span"]) == pytest.approx(0.88)
    expected_clip_rel_payoff = 2_600 - ep_run.clip.in_ms
    assert ep_push["payoff_at_ms"] == expected_clip_rel_payoff

    # (c) stabilize received edge_guard_px = max(1, int(round(crop_w * 0.14))).
    crop_w, _ = vertical_crop_size(640, 360)
    expected_edge_guard = max(1, int(round(crop_w * 0.14)))
    assert len(stabilize_calls) >= 1
    assert stabilize_calls[0]["edge_guard_px"] == expected_edge_guard
    assert stabilize_calls[0]["dead_zone_px"] == max(1, crop_w // 10)

    # (d) build_ass received merge_short_orphans=True, excited_intervals_ms, & face_intervals.
    assert len(build_ass_calls) == 1
    ass_kw = build_ass_calls[0]
    assert ass_kw["merge_short_orphans"] is True
    excited_ivs = ass_kw["excited_intervals_ms"]
    assert len(excited_ivs) == 1
    assert excited_ivs[0] == (1_800, 3_600)
    face_ivs = ass_kw["face_intervals"]
    assert face_ivs is not None and len(face_ivs) >= 1
    assert any(f_top < 420 for _, _, f_top, _ in face_ivs)

    # Verify the actual generated .ass artifact on disk:
    ass_path = Path(ep_run.render.path).with_suffix(".ass")
    ass_text = ass_path.read_text(encoding="utf-8")
    dialogues = _dialogue_lines(ass_text)

    # Face-aware 2-line editorial hook card relocated off forehead (D-380 kinetic lift to y=1260),
    # <= 1 `\N`, clean fade.
    hook_lines = [line for line in dialogues if ",Hook," in line]
    assert len(hook_lines) == 1
    assert r"{\an2\move(540,1272,540,1260,0,160)\fad(0,250)}" in hook_lines[0]
    assert hook_lines[0].count(r"\N") <= 1
    assert r"\fscx107" not in ass_text

    # Zero-orphan merge: `لێی.` is merged into its preceding chunk rather than a 1-word flash.
    base_lines = [line for line in dialogues if ",Kurdish," in line]
    assert any("لێی." in line and "گرنگ" in line for line in base_lines)
    assert not any(line.split(",", 9)[-1].strip(" \u200f") == "لێی." for line in base_lines)

    # Excited karaoke micro-pop appears ONLY on excited sentence 1 words, never on calm sentence 0.
    hl_lines = [line for line in dialogues if ",KurdishHighlight," in line]
    calm_hl = [line for line in hl_lines if "ئەمە" in line]
    excited_hl = [line for line in hl_lines if "گۆشەی" in line]
    assert calm_hl and all(_EXCITED_POP_SNIPPET not in line for line in calm_hl)
    assert excited_hl and all(_EXCITED_POP_SNIPPET in line for line in excited_hl)

    # Sorani digit normalization (`3` -> `سێ`) applied in display ASS captions.
    assert "سێ" in ass_text

    # (e) raw.json on disk & clip.transcript stay strictly unmutated (invariant #1).
    stored_raw = TranscriptStore(work_ep / "transcripts").read_raw("hd-ep")
    assert stored_raw.text_ckb == original_text
    assert [(w.w, w.start_ms, w.end_ms, w.conf) for w in stored_raw.words] == original_words
    assert ep_run.clip.transcript.raw_ckb == original_text
    assert "3" in ep_run.clip.transcript.raw_ckb
    assert "سێ" not in ep_run.clip.transcript.raw_ckb

    # --- Phase 2: Single-clip mode (`max_clips=None`, `eased_push=True`) ---------------------
    render_calls.clear()
    push_calls.clear()
    stabilize_calls.clear()
    build_ass_calls.clear()

    work_single = tmp_path / "work_single_eased"
    single_run = run_pipeline(
        FIXTURE,
        work_single,
        media_id="hd-single",
        transcript=_director_v2_transcript("hd-single"),
        select_sentences=(0, 1),
        verdict=_make_verdict("direct", 100, 3_600, 2_600),
        eased_push=True,
        caption_style=CaptionStyle.WORD_HIGHLIGHT,
        subject_tracker=_LeaningForeheadFaceTracker(),
        min_face_share=0.0,
        encoder=Encoder.X264,
        ffmpeg=ffmpeg,
    )
    assert single_run.render is not None and not isinstance(single_run.render, StageSkipped)
    assert len(render_calls) == 1
    assert render_calls[0]["two_pass_loudness"] is True
    assert render_calls[0]["speech_chain"] is True
    assert len(push_calls) >= 1
    assert len(stabilize_calls) >= 1
    assert stabilize_calls[0]["edge_guard_px"] == expected_edge_guard
    assert len(build_ass_calls) == 1
    assert build_ass_calls[0]["merge_short_orphans"] is True
    assert build_ass_calls[0]["excited_intervals_ms"] == ((1_800, 3_600),)
    assert build_ass_calls[0]["face_intervals"] is not None

    # --- Phase 3: Single-clip default short fixture preserves two_pass_loudness=False --------
    render_calls.clear()
    work_fast = tmp_path / "work_single_default"
    fast_run = run_pipeline(
        FIXTURE,
        work_fast,
        media_id="hd-fast",
        transcript=_director_v2_transcript("hd-fast"),
        select_sentences=(0, 1),
        verdict=_make_verdict("direct", 100, 3_600, 2_600),
        eased_push=False,
        encoder=Encoder.X264,
        ffmpeg=ffmpeg,
    )
    assert fast_run.render is not None and not isinstance(fast_run.render, StageSkipped)
    assert len(render_calls) == 1
    assert render_calls[0]["two_pass_loudness"] is False
    assert render_calls[0]["speech_chain"] is None


def test_excited_caption_intervals_and_push_schedule_silence_remap() -> None:
    """Mid-episode clip (`clip_in_ms > 0`) with silence excision remaps `excited_intervals_ms`
    so `build_ass()` applies the micro-pop tag to the tightened words of excited sentences, and
    `_build_clip_punch_ins` falls back cleanly to `eased_push_schedule` when `audio_metrics` is
    absent.
    """
    clip_in_ms = 20_000
    clip_out_ms = 28_000
    s0 = Sentence(
        words=(
            Word(w="ئەمە", start_ms=20_200, end_ms=20_800, conf=0.95),
            Word(w="سەرەتایە.", start_ms=20_850, end_ms=21_400, conf=0.95),
        ),
        complete=True,
    )
    # 2_000 ms silence gap between s0 (21_400) and s1 (23_400) gets tightened.
    s1 = Sentence(
        words=(
            Word(w="خاڵی", start_ms=23_400, end_ms=24_000, conf=0.96),
            Word(w="سەرەکییە.", start_ms=24_050, end_ms=24_700, conf=0.96),
        ),
        complete=True,
    )
    sentences = (s0, s1)
    all_words = tuple(w for s in sentences for w in s.words)
    silence_plan = plan_silence_tightening(
        all_words,
        clip_in_ms=clip_in_ms,
        clip_out_ms=clip_out_ms,
        threshold_ms=500,
        target_gap_ms=150,
    )
    assert silence_plan.total_removed_ms > 0
    tightened, _ = tighten_sentences(sentences, threshold_ms=500, target_gap_ms=150)

    metrics = (
        SentenceAudioMetrics(0, -22.0, -0.5, 0, 2.0, 0, 0.25, ()),
        SentenceAudioMetrics(1, -13.0, 1.5, 2, 3.4, 2000, 0.55, ("burst",)),
    )
    excited = _excited_caption_intervals_ms(
        sentences,
        metrics,
        clip_in_ms=clip_in_ms,
        clip_out_ms=clip_out_ms,
        silence_plan=silence_plan,
        selected_sentences=sentences,
    )
    assert len(excited) == 1
    # Must match tightened s1's words (shifted earlier by total_removed_ms, anchored at clip_in_ms).
    assert excited[0][0] <= tightened[1].words[0].start_ms
    assert excited[0][1] >= tightened[1].words[-1].end_ms

    ffmpeg = find_ffmpeg()
    if ffmpeg is not None and ffmpeg.is_file():
        ass = build_ass(
            tightened,
            font_name=DEFAULT_CAPTION_FONT,
            font_size=VIRAL_FONT_SIZE,
            style=CaptionStyle.WORD_HIGHLIGHT,
            clip_in_ms=clip_in_ms,
            clip_duration_ms=silence_plan.effective_duration_ms,
            theme=VIRAL_THEME,
            fonts_dir=FONTS_DIR,
            excited_intervals_ms=excited,
        )
        hl_lines = [line for line in _dialogue_lines(ass) if ",KurdishHighlight," in line]
        calm_hl = [line for line in hl_lines if "ئەمە" in line]
        burst_hl = [line for line in hl_lines if "خاڵی" in line]
        assert calm_hl and all(_EXCITED_POP_SNIPPET not in line for line in calm_hl)
        assert burst_hl and all(_EXCITED_POP_SNIPPET in line for line in burst_hl)

    # Fallback to eased_push_schedule when audio_metrics is None.
    cfg = resolve_effective_configuration(eased_push=True)
    fallback_kf = _build_clip_punch_ins(
        (2_000,),
        6_000,
        (),
        config=cfg,
        eased_push=True,
        profile="default",
        sentences=sentences,
        audio_metrics=None,
        clip_in_ms=clip_in_ms,
        clip_out_ms=clip_out_ms,
        payoff_at_ms=24_000,
        silence_plan=None,
    )
    assert len(fallback_kf) >= 2
    assert max(z for _, z in fallback_kf) == pytest.approx(1.08)


def test_trim_trailing_flash_cut_eliminates_tail_camera_flashes() -> None:
    """D-364: trailing 18 ms / 122 ms / shot_cut flashes snap before the cut while keeping E3."""
    base_tail = Boundary(
        anchor_in_ms=1_000,
        anchor_out_ms=56_000,
        final_in_ms=920,
        final_out_ms=56_200,
        in_extended_by="lead",
        out_extended_by="tail",
        sentence_complete=True,
        confidence=0.95,
    )
    # 122 ms trailing flash (like ai-v2/verbal-4): cut at 56_078 -> snaps to 56_038 (>= 56_030).
    trimmed_122 = _trim_trailing_flash_cut(base_tail, (10_000, 56_078))
    assert trimmed_122.final_out_ms == 56_038

    # 18 ms trailing flash (like cooking-v2/verbal-3): cut at 56_182 -> snaps to 56_142.
    trimmed_18 = _trim_trailing_flash_cut(base_tail, (56_182,))
    assert trimmed_18.final_out_ms == 56_142

    # Natural silence or shot_cut ending right on a cut -> snaps 40 ms before cut.
    on_cut = Boundary(
        anchor_in_ms=1_000,
        anchor_out_ms=56_000,
        final_in_ms=920,
        final_out_ms=56_300,
        in_extended_by="lead",
        out_extended_by="shot_cut",
        sentence_complete=True,
        confidence=0.95,
    )
    assert _trim_trailing_flash_cut(on_cut, (56_300,)).final_out_ms == 56_260

    # Cut closer than min_tail_pad_ms (e.g. 20 ms after speech) is never trimmed past E3 pad.
    assert _trim_trailing_flash_cut(base_tail, (56_020,)).final_out_ms == 56_200
