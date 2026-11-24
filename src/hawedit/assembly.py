"""Multi-moment story assembly and unified editorial judging (§3 Stage 6, pro-edit T6).

Assembles non-contiguous sentence highlights across an episode into a single coherent story reel.
Re-offsets word and sentence timestamps onto a unified continuous timeline [0, total_duration_ms]
while preserving Kurdish invariant #1 (exact surface words) and invariant #2 (complete sentences).

The entire assembled narrative is scored as one unit by the editorial judge (AC-7), enforcing
strict §2 thresholds on hook strength and misleading-edit risk (AC-8).
"""

from __future__ import annotations

import subprocess
from bisect import bisect_left, bisect_right
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Final

from hawedit.captions import (
    KURDISH_NON_TERMINAL_WORDS,
    POPUP_MAX_CHARS,
    POPUP_MAX_WIDTH_PX,
    POPUP_MAX_WORDS,
    VIRAL_FONT_SIZE,
    VIRAL_THEME,
    CaptionStyle,
    build_ass,
    find_ffmpeg,
    subtitle_filter,
)
from hawedit.clip import (
    MAX_MISLEADING_EDIT_RISK,
    MIN_HOOK_SCORE,
    EditorialBelowThreshold,
)
from hawedit.condenser import interval_overlap_ms, score_interior_sentence
from hawedit.judge import EditorialJudge, InputMode, JudgeRequest, JudgeVerdict
from hawedit.keyframes import extract_judge_frames
from hawedit.normalize import normalize_sorani
from hawedit.render import crop_filter
from hawedit.sentences import Sentence, _is_dangling_fragment, assert_deliverable_order
from hawedit.silence import KURDISH_FILLER_TOKENS, audio_cut_fade_filters
from hawedit.transcripts import Word

__all__ = [
    "AssembledReel",
    "AssemblySpan",
    "ViralStoryPlan",
    "assemble_cold_open",
    "assemble_spans",
    "assembled_splice_filter",
    "judge_assembled_reel_multimodal",
    "judge_assembly",
    "plan_viral_story_cut",
    "render_assembled_reel",
]

_MIN_E3_PAD_MS: Final = 30
_MAX_E3_PAD_MS: Final = 120
_COLD_OPEN_MIN_CLIP_MS: Final = 25_000
_COLD_OPEN_LATE_FRACTION: Final = 0.40
_COLD_OPEN_MIN_BODY_OFFSET_MS: Final = 5_000

# Matches render_critic.py dependent clause starters so cold-open teasers never enter mid-clause.
_MID_CLAUSE_STARTERS: Final[frozenset[str]] = frozenset(
    {
        "چونکە",
        "چونكە",
        "وە",
        "یان",
        "بەڵام",
        "کە",
        "كە",
        "هەرچەندە",
        "لەبەرئەوەی",
        "لەبەر",
        "هەروەها",
        "بۆیە",
        "کەچی",
        "كەچی",
        "ئەگەر",
    }
)
_BAD_CLAUSE_OPENERS: Final[frozenset[str]] = _MID_CLAUSE_STARTERS | frozenset(
    {"و", "بە", "لە", "بۆ", "تا", "ئێ", "ئا", "نییە", "بوو", "بوون", "بێ", "بێت"}
)
_BAD_CLAUSE_CLOSERS: Final[frozenset[str]] = KURDISH_NON_TERMINAL_WORDS | frozenset(
    {"ئێ", "ئا", "یەعنی", "یانی"}
)
_CLAUSE_BREAK_PREV: Final[frozenset[str]] = _MID_CLAUSE_STARTERS | frozenset(
    {"و", "نییە", "بوو", "بوون"}
)
_CLAUSE_BREAK_NEXT: Final[frozenset[str]] = _MID_CLAUSE_STARTERS | frozenset({"و", "لەوانەیە"})
_PUNCT_STRIP: Final = ".,،!؟?؛;:"


@dataclass(frozen=True, slots=True)
class AssemblySpan:
    """One contiguous source span participating in an assembled reel."""

    span_index: int
    source_in_ms: int
    source_out_ms: int
    duration_ms: int
    sentences: tuple[Sentence, ...]
    role: str = "body"

    def __post_init__(self) -> None:
        if self.span_index < 0:
            raise ValueError(f"span_index must be non-negative, got {self.span_index}")
        if self.source_out_ms <= self.source_in_ms:
            raise ValueError(
                f"source_out_ms ({self.source_out_ms}) must be > in_ms ({self.source_in_ms})"
            )
        if self.duration_ms != self.source_out_ms - self.source_in_ms:
            expected = self.source_out_ms - self.source_in_ms
            raise ValueError(f"duration_ms ({self.duration_ms}) must equal {expected}")
        if not self.sentences:
            raise ValueError("AssemblySpan must contain at least one sentence")
        if self.role not in ("body", "cold_open"):
            raise ValueError(f"AssemblySpan.role must be 'body' or 'cold_open', got {self.role!r}")


@dataclass(frozen=True, slots=True)
class AssembledReel:
    """An assembled multi-moment reel with continuous re-offset timestamps."""

    spans: tuple[AssemblySpan, ...]
    assembled_sentences: tuple[Sentence, ...]
    total_duration_ms: int
    raw_text: str
    norm_text: str

    def __post_init__(self) -> None:
        if not self.spans:
            raise ValueError("AssembledReel must contain at least one span")
        if self.total_duration_ms <= 0:
            raise ValueError(f"total_duration_ms must be positive, got {self.total_duration_ms}")
        if not self.assembled_sentences:
            raise ValueError("AssembledReel must contain assembled sentences")


def assemble_spans(span_groups: Sequence[Sequence[Sentence]]) -> AssembledReel:
    """Assemble multiple non-contiguous sentence groups into a continuous timeline.

    Args:
        span_groups: A sequence of sentence groups, each representing a contiguous source span.

    Returns:
        An AssembledReel with re-offset word timestamps starting at t=0.

    Raises:
        ValueError: If span_groups is empty, or any sentence is incomplete or has no words.
    """
    if not span_groups:
        raise ValueError("Cannot assemble an empty sequence of span groups")

    spans: list[AssemblySpan] = []
    assembled_sentences: list[Sentence] = []
    current_timeline_offset_ms = 0

    for span_idx, group in enumerate(span_groups):
        sentence_tuple = tuple(group)
        if not sentence_tuple:
            raise ValueError(f"Span group {span_idx} is empty")

        for sent in sentence_tuple:
            if not sent.complete:
                raise ValueError(
                    f"Kurdish invariant #2 violation: sentence {sent.text!r} is incomplete"
                )
            if not sent.words:
                raise ValueError(f"Sentence in span {span_idx} has no words")

        group_in_ms = sentence_tuple[0].start_ms
        group_out_ms = sentence_tuple[-1].end_ms
        if group_out_ms <= group_in_ms:
            raise ValueError(f"Invalid span timing: in_ms={group_in_ms} >= out_ms={group_out_ms}")

        duration_ms = group_out_ms - group_in_ms

        # Re-offset word timestamps for this span onto the assembled continuous timeline
        for sent in sentence_tuple:
            shifted_words: list[Word] = []
            for word in sent.words:
                rel_start = word.start_ms - group_in_ms
                rel_end = word.end_ms - group_in_ms
                if rel_start < 0 or rel_end < rel_start:
                    raise ValueError(
                        f"Word {word.w!r} [{word.start_ms}:{word.end_ms}] outside span"
                    )
                shifted_words.append(
                    Word(
                        w=word.w,
                        start_ms=current_timeline_offset_ms + rel_start,
                        end_ms=current_timeline_offset_ms + rel_end,
                        conf=word.conf,
                    )
                )
            assembled_sentences.append(Sentence(words=tuple(shifted_words), complete=True))

        spans.append(
            AssemblySpan(
                span_index=span_idx,
                source_in_ms=group_in_ms,
                source_out_ms=group_out_ms,
                duration_ms=duration_ms,
                sentences=sentence_tuple,
            )
        )
        current_timeline_offset_ms += duration_ms

    raw_text = " ".join(sent.text for sent in assembled_sentences)
    norm_text = normalize_sorani(raw_text)

    return AssembledReel(
        spans=tuple(spans),
        assembled_sentences=tuple(assembled_sentences),
        total_duration_ms=current_timeline_offset_ms,
        raw_text=raw_text,
        norm_text=norm_text,
    )


def judge_assembly(reel: AssembledReel, judge: EditorialJudge) -> JudgeVerdict:
    """Score an assembled multi-moment reel with the editorial judge and enforce §2 thresholds.

    Per AC-7, the judge scores the assembled narrative as a unified reel rather than individual
    source spans.
    Per AC-8, the §2 editorial thresholds apply directly to the assembled verdict.

    Args:
        reel: The assembled multi-moment reel.
        judge: An authenticated EditorialJudge implementation.

    Returns:
        The validated JudgeVerdict.

    Raises:
        EditorialBelowThreshold: If hook, misleading risk, self-containment, or fidelity fail.
    """
    approx_tokens = max(1, len(reel.norm_text.split()) * 2)
    candidate_id = f"assembly-{len(reel.spans)}spans-{reel.total_duration_ms}ms"

    request = JudgeRequest(
        candidate_id=candidate_id,
        mode=InputMode.STAGE_4_TRANSCRIPT_FIRST,
        tokens=approx_tokens,
        text_ckb=reel.norm_text,
        clip_in_ms=0,
        clip_out_ms=reel.total_duration_ms,
    )

    verdict = judge.judge(request)

    # Enforce AC-8 editorial thresholds
    if verdict.hook_score < MIN_HOOK_SCORE:
        raise EditorialBelowThreshold(
            f"Assembled reel hook score {verdict.hook_score:.2f} < {MIN_HOOK_SCORE:.2f}"
        )
    if verdict.misleading_edit_risk > MAX_MISLEADING_EDIT_RISK:
        risk = verdict.misleading_edit_risk
        raise EditorialBelowThreshold(
            f"Assembled reel misleading edit risk {risk:.2f} > {MAX_MISLEADING_EDIT_RISK:.2f}"
        )
    if not verdict.self_contained:
        raise EditorialBelowThreshold("Assembled reel was judged not self-contained")
    if verdict.meaning_fidelity < 1.0:
        raise EditorialBelowThreshold(
            f"Assembled reel meaning fidelity {verdict.meaning_fidelity:.2f} is below 1.00"
        )

    return verdict


def assemble_cold_open(
    setup_sentences: Sequence[Sentence],
    payoff_sentence: Sentence,
) -> AssembledReel:
    """Assemble a cold-open narrative placing the payoff sentence first (Task T4.9).

    The payoff sentence acts as the opening 0–3s hook to maximize viewer engagement.
    The setup sentences follow chronologically to provide the narrative foundation.
    All word and sentence timestamps are re-offset onto a continuous timeline
    [0, total_duration_ms].

    Args:
        setup_sentences: Non-empty sequence of setup/context sentences.
        payoff_sentence: The climactic payoff sentence acting as the cold-open hook.

    Returns:
        AssembledReel containing [payoff_sentence] as span 0, followed by setup sentences as span 1.
    """
    if not payoff_sentence.complete:
        raise ValueError("Payoff sentence must be complete (Kurdish invariant #2)")
    if not payoff_sentence.words:
        raise ValueError("Payoff sentence has no words")
    if not setup_sentences:
        raise ValueError("setup_sentences cannot be empty")
    for s in setup_sentences:
        if not s.complete:
            raise ValueError("All setup sentences must be complete (Kurdish invariant #2)")
        if not s.words:
            raise ValueError("Setup sentence has no words")

    span_groups = [[payoff_sentence], list(setup_sentences)]
    return assemble_spans(span_groups)


def assembled_splice_filter(
    spans: Sequence[AssemblySpan],
    *,
    crossfade_ms: int = 0,
) -> str:
    """Generate the FFmpeg filtergraph splicing participating spans in order (Task T4.9, D-394).

    Trims video and audio for each span, resets PTS, and concatenates them into
    single continuous [v_concat] and [a_concat] streams. When ``crossfade_ms > 0``, applies
    symmetric equal-power quarter-sine ``afade`` ramps at every interior splice boundary so
    semantic multi-cut joins stay 0.000 ms frame-locked with zero clicks or harsh room-tone drops.
    """
    if not spans:
        raise ValueError("Cannot create splice filter for empty spans")
    if crossfade_ms < 0:
        raise ValueError(f"crossfade_ms must be non-negative, got {crossfade_ms}")

    v_trims: list[str] = []
    a_trims: list[str] = []
    concat_inputs: list[str] = []

    n = len(spans)
    for i, span in enumerate(spans):
        in_s = span.source_in_ms / 1000.0
        out_s = span.source_out_ms / 1000.0
        span_dur_ms = span.source_out_ms - span.source_in_ms
        if crossfade_ms > 0:
            eff_fade_ms = min(crossfade_ms, max(4, span_dur_ms // 4))
            fade_s = eff_fade_ms / 1000.0
            fades: list[str] = []
            if i > 0:
                fades.append(f"afade=t=in:st=0:d={fade_s:.3f}:curve=qsin")
            if i < n - 1:
                out_st = max(0.0, (span_dur_ms - eff_fade_ms) / 1000.0)
                fades.append(f"afade=t=out:st={out_st:.3f}:d={fade_s:.3f}:curve=qsin")
        else:
            fades = list(
                audio_cut_fade_filters(
                    span_dur_ms,
                    fade_in=(i > 0),
                    fade_out=(i < n - 1),
                )
            )
        a_chain = ",".join(["asetpts=PTS-STARTPTS", *fades])
        v_trims.append(f"[0:v]trim=start={in_s:.3f}:end={out_s:.3f},setpts=PTS-STARTPTS[v{i}]")
        a_trims.append(f"[0:a]atrim=start={in_s:.3f}:end={out_s:.3f},{a_chain}[a{i}]")
        concat_inputs.append(f"[v{i}][a{i}]")

    concat_clause = f"{''.join(concat_inputs)}concat=n={n}:v=1:a=1[v_concat][a_concat]"
    return ";".join(v_trims + a_trims + [concat_clause])


def render_assembled_reel(
    reel: AssembledReel,
    source_video_path: Path,
    output_path: Path,
    work_dir: Path,
    *,
    source_width: int = 1920,
    source_height: int = 1080,
    punch_ins: Sequence[tuple[int, float]] = (),
    title_ckb: str | None = None,
    caption_style: CaptionStyle = CaptionStyle.WORD_HIGHLIGHT,
    fonts_dir: Path | None = None,
    ffmpeg: Path | None = None,
) -> Path:
    """Render a real 9:16 vertical reel concatenating assembled spans with burned ASS subtitles."""
    if not source_video_path.is_file():
        raise FileNotFoundError(f"Source video not found: {source_video_path}")
    if output_path.exists():
        raise FileExistsError(f"Output file already exists: {output_path}")

    binary = ffmpeg or find_ffmpeg()
    if binary is None:
        raise RuntimeError("ffmpeg binary not found")

    resolved_fonts = fonts_dir or (Path(__file__).resolve().parents[2] / "assets" / "fonts")
    if not resolved_fonts.is_dir():
        raise FileNotFoundError(f"Fonts directory not found: {resolved_fonts}")

    work_dir.mkdir(parents=True, exist_ok=True)
    ass_path = work_dir / "assembled.ass"
    ass_content = build_ass(
        reel.assembled_sentences,
        font_size=VIRAL_FONT_SIZE,
        theme=VIRAL_THEME,
        style=caption_style,
        max_chars_per_line=POPUP_MAX_CHARS,
        max_words_per_event=POPUP_MAX_WORDS,
        max_popup_width_px=POPUP_MAX_WIDTH_PX,
        clip_in_ms=0,
        clip_duration_ms=reel.total_duration_ms,
        title_ckb=title_ckb,
        fonts_dir=resolved_fonts,
    )
    ass_path.write_text(ass_content, encoding="utf-8")

    splice_part = assembled_splice_filter(reel.spans)
    sub_filter = subtitle_filter(ass_path, resolved_fonts)

    video_filter = crop_filter(
        source_width=source_width,
        source_height=source_height,
        target_width=1080,
        target_height=1920,
        punch_ins=punch_ins,
    )

    v_chain = f"[v_concat]{video_filter},{sub_filter}[v_out]"
    outer_fades = ",".join(
        audio_cut_fade_filters(reel.total_duration_ms, fade_in=True, fade_out=True)
    )
    a_prefix = f"{outer_fades}," if outer_fades else ""
    a_chain = (
        f"[a_concat]{a_prefix}aformat=sample_fmts=fltp:"
        "sample_rates=48000:channel_layouts=stereo[a_out]"
    )
    full_filter = f"{splice_part};{v_chain};{a_chain}"

    duration_s = reel.total_duration_ms / 1000.0
    cmd = [
        str(binary),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source_video_path),
        "-filter_complex",
        full_filter,
        "-map",
        "[v_out]",
        "-map",
        "[a_out]",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-t",
        f"{duration_s:.3f}",
        str(output_path),
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        timeout=max(120.0, 60.0 + 4.0 * duration_s),
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg assembly render failed (exit {result.returncode}):\n{result.stderr}"
        )

    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError(f"Assembled render produced empty output at {output_path}")

    return output_path


def judge_assembled_reel_multimodal(
    reel: AssembledReel,
    rendered_mp4_path: Path,
    judge: EditorialJudge,
    work_dir: Path,
    *,
    frame_count: int = 5,
    ffmpeg: Path | None = None,
) -> JudgeVerdict:
    """Judge an assembled reel using video frames extracted from the render (Task T4.9)."""
    if not rendered_mp4_path.is_file():
        raise FileNotFoundError(f"Rendered reel not found: {rendered_mp4_path}")

    frames = extract_judge_frames(
        source=rendered_mp4_path,
        in_ms=0,
        out_ms=reel.total_duration_ms,
        work_dir=work_dir,
        count=frame_count,
        ffmpeg=ffmpeg,
    )

    approx_tokens = max(1, len(reel.norm_text.split()) * 2) + len(frames) * 300
    candidate_id = f"assembly-coldopen-{len(reel.spans)}spans-{reel.total_duration_ms}ms"

    request = JudgeRequest(
        candidate_id=candidate_id,
        mode=InputMode.STAGE_4_WITH_VIDEO,
        tokens=approx_tokens,
        keyframes=frames,
        text_ckb=reel.norm_text,
        clip_in_ms=0,
        clip_out_ms=reel.total_duration_ms,
    )

    verdict = judge.judge(request)

    # Gating AC-8 and Task T4.9 thresholds
    if verdict.hook_score < MIN_HOOK_SCORE:
        raise EditorialBelowThreshold(
            f"Assembled reel hook score {verdict.hook_score:.2f} < {MIN_HOOK_SCORE:.2f}"
        )
    if verdict.misleading_edit_risk > MAX_MISLEADING_EDIT_RISK:
        risk = verdict.misleading_edit_risk
        raise EditorialBelowThreshold(
            f"Assembled reel misleading edit risk {risk:.2f} > {MAX_MISLEADING_EDIT_RISK:.2f}"
        )
    if not verdict.self_contained:
        raise EditorialBelowThreshold("Assembled reel was judged not self-contained")
    if verdict.meaning_fidelity < 1.0:
        raise EditorialBelowThreshold(
            f"Assembled reel meaning fidelity {verdict.meaning_fidelity:.2f} is below 1.00"
        )

    return verdict


@dataclass(frozen=True, slots=True)
class ViralStoryPlan:
    """Planned cold-open teaser and middle-tangent story cut for a viral short reel (D-378)."""

    spans: tuple[AssemblySpan, ...]
    remapped_sentences: tuple[Sentence, ...]
    kept_sentence_indices: tuple[int, ...]
    dropped_sentence_indices: tuple[int, ...]
    applied_cold_open: bool
    applied_condense: bool
    source_duration_ms: int
    output_duration_ms: int
    cold_open_text: str | None = None
    cold_open_source_in_ms: int | None = None
    cold_open_source_out_ms: int | None = None

    def __post_init__(self) -> None:
        if not self.spans:
            raise ValueError("ViralStoryPlan must contain at least one span")
        if not self.remapped_sentences:
            raise ValueError("ViralStoryPlan must contain remapped sentences")
        if self.source_duration_ms <= 0:
            raise ValueError(f"source_duration_ms must be positive, got {self.source_duration_ms}")
        if self.output_duration_ms <= 0:
            raise ValueError(f"output_duration_ms must be positive, got {self.output_duration_ms}")
        span_total = sum(sp.duration_ms for sp in self.spans)
        if self.output_duration_ms != span_total:
            raise ValueError(
                f"output_duration_ms ({self.output_duration_ms}) must equal sum of span "
                f"durations ({span_total})"
            )
        if self.applied_cold_open:
            if len(self.spans) < 2 or self.spans[0].role != "cold_open":
                raise ValueError("applied_cold_open requires spans[0].role == 'cold_open' + body")
            if not self.cold_open_text or not self.cold_open_text.strip():
                raise ValueError("applied_cold_open requires non-empty cold_open_text")
            if (
                self.cold_open_source_in_ms != self.spans[0].source_in_ms
                or self.cold_open_source_out_ms != self.spans[0].source_out_ms
            ):
                raise ValueError("cold_open_source bounds must match spans[0]")
        else:
            if any(sp.role != "body" for sp in self.spans):
                raise ValueError("Non-cold-open plan cannot contain cold_open spans")
            if self.cold_open_text is not None:
                raise ValueError("Non-cold-open plan must have cold_open_text=None")
        assert_deliverable_order(self.remapped_sentences)

    @property
    def is_noop(self) -> bool:
        """True when neither cold-open teaser nor middle-tangent condensation was applied."""
        return not self.applied_cold_open and not self.applied_condense

    def to_dict(self) -> dict[str, Any]:
        """Serialize plan metadata for run artifacts and diagnostics."""
        return {
            "applied_cold_open": self.applied_cold_open,
            "applied_condense": self.applied_condense,
            "source_duration_ms": self.source_duration_ms,
            "output_duration_ms": self.output_duration_ms,
            "kept_sentence_indices": list(self.kept_sentence_indices),
            "dropped_sentence_indices": list(self.dropped_sentence_indices),
            "cold_open_text": self.cold_open_text,
            "cold_open_source_in_ms": self.cold_open_source_in_ms,
            "cold_open_source_out_ms": self.cold_open_source_out_ms,
            "spans": [
                {
                    "span_index": sp.span_index,
                    "role": sp.role,
                    "source_in_ms": sp.source_in_ms,
                    "source_out_ms": sp.source_out_ms,
                    "duration_ms": sp.duration_ms,
                }
                for sp in self.spans
            ],
        }


def _safe_edge_pad(avail_ms: int, boundary_pad_ms: int, *, has_adjacent_word: bool) -> int:
    """Compute E3-safe cut padding within [30, 120] ms without ever splitting an adjacent word."""
    if avail_ms <= 0:
        return 0
    if has_adjacent_word:
        if avail_ms >= _MIN_E3_PAD_MS * 2:
            return min(boundary_pad_ms, avail_ms - _MIN_E3_PAD_MS)
        if avail_ms >= _MIN_E3_PAD_MS:
            return min(boundary_pad_ms, avail_ms)
        return avail_ms
    return min(boundary_pad_ms, avail_ms)


def _assert_no_split_words(cut_ms: int, all_words: Sequence[Word]) -> None:
    """Fail-stop guard ensuring a cut timestamp never falls strictly inside any spoken word."""
    for word in all_words:
        if word.start_ms < cut_ms < word.end_ms:
            raise ValueError(
                f"Cut at {cut_ms} ms splits word {word.w!r} [{word.start_ms}..{word.end_ms} ms]"
            )


def _partition_indices(indices: Sequence[int]) -> list[tuple[int, ...]]:
    """Group sorted sentence indices into maximal contiguous runs."""
    runs: list[list[int]] = []
    for idx in indices:
        if not runs or idx != runs[-1][-1] + 1:
            runs.append([idx])
        else:
            runs[-1].append(idx)
    return [tuple(r) for r in runs]


def _build_body_spans(
    sentences: Sequence[Sentence],
    kept_indices: Sequence[int],
    clip_in_ms: int,
    clip_out_ms: int,
    boundary_pad_ms: int,
) -> tuple[AssemblySpan, ...]:
    """Construct contiguous body AssemblySpans with E3-safe boundary padding."""
    runs = _partition_indices(kept_indices)
    is_full_clip = len(runs) == 1 and len(kept_indices) == len(sentences)
    spans: list[AssemblySpan] = []

    for run_idx, run in enumerate(runs):
        run_sents = tuple(sentences[i] for i in run)
        first_w = run_sents[0].words[0]
        last_w = run_sents[-1].words[-1]

        if is_full_clip:
            span_in = clip_in_ms
            span_out = clip_out_ms
        else:
            if run_idx == 0:
                span_in = clip_in_ms
            else:
                prev_w = sentences[run[0] - 1].words[-1]
                avail_lead = max(0, first_w.start_ms - prev_w.end_ms)
                lead_pad = _safe_edge_pad(avail_lead, boundary_pad_ms, has_adjacent_word=True)
                span_in = max(clip_in_ms, first_w.start_ms - lead_pad)

            if run_idx == len(runs) - 1:
                span_out = clip_out_ms
            else:
                next_w = sentences[run[-1] + 1].words[0]
                avail_tail = max(0, next_w.start_ms - last_w.end_ms)
                tail_pad = _safe_edge_pad(avail_tail, boundary_pad_ms, has_adjacent_word=True)
                span_out = min(clip_out_ms, last_w.end_ms + tail_pad)

        spans.append(
            AssemblySpan(
                span_index=run_idx,
                source_in_ms=span_in,
                source_out_ms=span_out,
                duration_ms=span_out - span_in,
                sentences=run_sents,
                role="body",
            )
        )
    return tuple(spans)


def _remap_spans_to_sentences(spans: Sequence[AssemblySpan]) -> tuple[Sentence, ...]:
    """Map every span's sentences onto a continuous output timeline starting at 0 ms."""
    remapped: list[Sentence] = []
    offset_ms = 0
    for span in spans:
        for sent in span.sentences:
            shifted_words: list[Word] = []
            for word in sent.words:
                rel_start = word.start_ms - span.source_in_ms
                rel_end = word.end_ms - span.source_in_ms
                if rel_start < 0 or rel_end > span.duration_ms or rel_end <= rel_start:
                    raise ValueError(
                        f"Word {word.w!r} [{word.start_ms}:{word.end_ms}] outside span "
                        f"[{span.source_in_ms}:{span.source_out_ms}]"
                    )
                shifted_words.append(
                    Word(
                        w=word.w,
                        start_ms=offset_ms + rel_start,
                        end_ms=offset_ms + rel_end,
                        conf=word.conf,
                    )
                )
            remapped.append(Sentence(words=tuple(shifted_words), complete=sent.complete))
        offset_ms += span.duration_ms
    return tuple(remapped)


def _select_cold_open_span(
    body_spans: tuple[AssemblySpan, ...],
    all_words: tuple[Word, ...],
    *,
    clip_in_ms: int,
    clip_out_ms: int,
    payoff_at_ms: int | None,
    excited_intervals_ms: Sequence[tuple[int, int]],
    cold_open_min_ms: int,
    cold_open_max_ms: int,
    boundary_pad_ms: int,
) -> AssemblySpan | None:
    """Select the highest-impact late climax clause (1.8-3.4s) on clean E3 word boundaries."""
    body_duration_ms = sum(sp.duration_ms for sp in body_spans)
    if (clip_out_ms - clip_in_ms) < _COLD_OPEN_MIN_CLIP_MS:
        return None
    if body_duration_ms < _COLD_OPEN_MIN_CLIP_MS:
        return None

    min_late_body_ms = max(
        _COLD_OPEN_MIN_BODY_OFFSET_MS,
        int(body_duration_ms * _COLD_OPEN_LATE_FRACTION),
    )

    # Index all body sentences along with their parent span and output offset in the body.
    entries: list[tuple[AssemblySpan, int, Sentence]] = []
    offset_acc = 0
    for sp in body_spans:
        for sent in sp.sentences:
            entries.append((sp, offset_acc, sent))
        offset_acc += sp.duration_ms

    def _to_body_offset(source_ms: int, sp: AssemblySpan, sp_off: int) -> int:
        return sp_off + (source_ms - sp.source_in_ms)

    # Determine whether an explicit payoff or late vocal peak exists.
    payoff_entry_idx: int | None = None
    if payoff_at_ms is not None:
        for idx, (sp, sp_off, sent) in enumerate(entries):
            if sp.source_in_ms <= payoff_at_ms <= sp.source_out_ms:
                body_pos = _to_body_offset(payoff_at_ms, sp, sp_off)
                if body_pos >= min_late_body_ms and sent.start_ms <= payoff_at_ms <= sent.end_ms:
                    payoff_entry_idx = idx
                    break
        if payoff_entry_idx is None:
            # Payoff may land in a pause between sentences inside a late body span.
            nearest_idx: int | None = None
            nearest_dist: int | None = None
            for idx, (sp, sp_off, sent) in enumerate(entries):
                if _to_body_offset(sent.end_ms, sp, sp_off) < min_late_body_ms:
                    continue
                dist = min(abs(payoff_at_ms - sent.start_ms), abs(payoff_at_ms - sent.end_ms))
                if dist <= 3_000 and (nearest_dist is None or dist < nearest_dist):
                    nearest_dist = dist
                    nearest_idx = idx
            payoff_entry_idx = nearest_idx

    late_entry_indices = [
        idx
        for idx, (sp, sp_off, sent) in enumerate(entries)
        if _to_body_offset(sent.end_ms, sp, sp_off) > min_late_body_ms
    ]
    if not late_entry_indices:
        return None

    has_late_excited = any(
        interval_overlap_ms(
            max(sent.start_ms, sp.source_in_ms + max(0, min_late_body_ms - sp_off)),
            sent.end_ms,
            excited_intervals_ms,
        )
        > 0
        for idx in late_entry_indices
        for sp, sp_off, sent in (entries[idx],)
    )
    is_single_sentence = len(entries) == 1
    require_pause_bounded = is_single_sentence and payoff_entry_idx is None and not has_late_excited

    # Rank candidate late sentences: explicit payoff sentence first, then vocal energy + density.
    def _sentence_priority(idx: int) -> tuple[int, float]:
        if idx == payoff_entry_idx:
            return (1, 1.0)
        sp, sp_off, sent = entries[idx]
        sent_dur = max(1, sent.end_ms - sent.start_ms)
        exc_ratio = min(
            1.0, interval_overlap_ms(sent.start_ms, sent.end_ms, excited_intervals_ms) / sent_dur
        )
        wps = len(sent.words) / max(0.5, sent_dur / 1000.0)
        density = min(1.0, wps / 3.5)
        lateness = _to_body_offset(sent.end_ms, sp, sp_off) / max(1, body_duration_ms)
        return (0, 0.55 * exc_ratio + 0.25 * density + 0.20 * lateness)

    ordered_entries = sorted(late_entry_indices, key=_sentence_priority, reverse=True)

    word_starts = [w.start_ms for w in all_words]
    word_ends = [w.end_ms for w in all_words]
    ideal_dur_ms = 0.5 * (cold_open_min_ms + cold_open_max_ms)

    for entry_idx in ordered_entries:
        sp, sp_off, sent = entries[entry_idx]
        ws = sent.words
        n_words = len(ws)

        anchor_ms: int | None = None
        if entry_idx == payoff_entry_idx and payoff_at_ms is not None:
            anchor_ms = payoff_at_ms
        else:
            best_iv_ov = 0
            for iv_start, iv_end in excited_intervals_ms:
                lo = max(sent.start_ms, iv_start)
                hi = min(sent.end_ms, iv_end)
                if hi > lo and (hi - lo) > best_iv_ov:
                    mid = (lo + hi) // 2
                    if _to_body_offset(mid, sp, sp_off) >= min_late_body_ms:
                        best_iv_ov = hi - lo
                        anchor_ms = mid

        best_score: float | None = None
        best_candidate: tuple[int, int, tuple[Word, ...]] | None = None

        for i in range(n_words):
            w_first = ws[i]
            if _to_body_offset(w_first.start_ms, sp, sp_off) < min_late_body_ms:
                continue
            first_tok = w_first.w.strip().rstrip(_PUNCT_STRIP)
            if not first_tok or first_tok in _BAD_CLAUSE_OPENERS:
                continue

            # Find immediately preceding word across the entire clip for safe lead padding.
            prev_pos = bisect_right(word_ends, w_first.start_ms) - 1
            prev_word: Word | None = all_words[prev_pos] if prev_pos >= 0 else None
            # Guard against matching w_first itself (impossible since end_ms > start_ms)
            avail_lead = w_first.start_ms - clip_in_ms
            if prev_word is not None:
                avail_lead = min(avail_lead, w_first.start_ms - prev_word.end_ms)
            avail_lead = max(0, avail_lead)
            lead_pad = _safe_edge_pad(
                avail_lead,
                boundary_pad_ms,
                has_adjacent_word=(prev_word is not None),
            )
            span_in = w_first.start_ms - lead_pad

            if require_pause_bounded and i > 0 and lead_pad < _MIN_E3_PAD_MS:
                continue

            for j in range(i, n_words):
                w_last = ws[j]
                is_whole_sentence = i == 0 and j == n_words - 1
                word_count = j - i + 1
                if word_count < 3 and not is_whole_sentence:
                    continue

                raw_span_dur = w_last.end_ms - span_in
                if raw_span_dur > cold_open_max_ms:
                    break

                # Find immediately following word across the entire clip for safe tail padding.
                next_pos = bisect_left(word_starts, w_last.end_ms)
                next_word: Word | None = all_words[next_pos] if next_pos < len(all_words) else None
                avail_tail = clip_out_ms - w_last.end_ms
                if next_word is not None:
                    avail_tail = min(avail_tail, next_word.start_ms - w_last.end_ms)
                avail_tail = max(0, avail_tail)
                tail_pad = _safe_edge_pad(
                    avail_tail,
                    boundary_pad_ms,
                    has_adjacent_word=(next_word is not None),
                )
                span_out = w_last.end_ms + tail_pad
                span_dur = span_out - span_in

                if span_dur < cold_open_min_ms:
                    continue
                if span_dur > cold_open_max_ms:
                    # Clamp tail pad only if still E3-clean, otherwise stop expanding j.
                    trimmed_out = min(span_out, span_in + cold_open_max_ms)
                    if trimmed_out < w_last.end_ms:
                        break
                    trimmed_pad = trimmed_out - w_last.end_ms
                    if trimmed_pad > 0 and trimmed_pad < _MIN_E3_PAD_MS:
                        trimmed_out = w_last.end_ms
                        trimmed_pad = 0
                    span_out = trimmed_out
                    tail_pad = trimmed_pad
                    span_dur = span_out - span_in
                    if span_dur < cold_open_min_ms or span_dur > cold_open_max_ms:
                        break

                if require_pause_bounded and j < n_words - 1 and tail_pad < _MIN_E3_PAD_MS:
                    continue

                clause_words = ws[i : j + 1]
                last_tok = w_last.w.strip().rstrip(_PUNCT_STRIP)
                if not last_tok or last_tok in _BAD_CLAUSE_CLOSERS:
                    continue
                if _is_dangling_fragment(clause_words):
                    continue

                # Score this valid cold-open clause candidate.
                score = 0.0
                if anchor_ms is not None:
                    if w_first.start_ms <= anchor_ms <= w_last.end_ms:
                        score += 3.0
                    else:
                        dist = min(
                            abs(anchor_ms - w_first.start_ms), abs(anchor_ms - w_last.end_ms)
                        )
                        score += 2.5 * max(0.0, 1.0 - (dist / 6_000.0))

                if i == 0 or lead_pad >= _MIN_E3_PAD_MS:
                    score += 1.2
                elif i > 0:
                    prev_raw = ws[i - 1].w.strip()
                    prev_core = prev_raw.rstrip(_PUNCT_STRIP)
                    is_reduplication = (
                        prev_core == "و"
                        and i >= 2
                        and ws[i - 2].w.strip().rstrip(_PUNCT_STRIP) == first_tok
                    )
                    if not is_reduplication and (
                        prev_core in _CLAUSE_BREAK_PREV
                        or (bool(prev_raw) and prev_raw[-1] in _PUNCT_STRIP)
                    ):
                        score += 0.6

                if j == n_words - 1 or tail_pad >= _MIN_E3_PAD_MS:
                    score += 1.2
                elif j < n_words - 1:
                    next_core = ws[j + 1].w.strip().rstrip(_PUNCT_STRIP)
                    last_raw = w_last.w.strip()
                    if next_core in _CLAUSE_BREAK_NEXT or (
                        bool(last_raw) and last_raw[-1] in _PUNCT_STRIP
                    ):
                        score += 0.8

                if is_whole_sentence:
                    score += 0.8
                if j == n_words - 2:
                    score -= 0.8

                exc_ov = interval_overlap_ms(span_in, span_out, excited_intervals_ms)
                score += 1.5 * min(1.0, exc_ov / max(1, span_dur))

                dur_closeness = max(
                    0.0, 1.0 - abs(span_dur - ideal_dur_ms) / max(1.0, ideal_dur_ms)
                )
                score += 0.6 * dur_closeness

                filler_ratio = sum(1 for w in clause_words if w.w in KURDISH_FILLER_TOKENS) / len(
                    clause_words
                )
                wps = len(clause_words) / max(0.5, span_dur / 1000.0)
                score += 0.3 * min(1.0, wps / 3.5) - 0.5 * filler_ratio

                if best_score is None or score > best_score:
                    best_score = score
                    best_candidate = (span_in, span_out, clause_words)

        if best_candidate is not None:
            cand_in, cand_out, clause_words = best_candidate
            _assert_no_split_words(cand_in, all_words)
            _assert_no_split_words(cand_out, all_words)
            return AssemblySpan(
                span_index=0,
                source_in_ms=cand_in,
                source_out_ms=cand_out,
                duration_ms=cand_out - cand_in,
                sentences=(Sentence(words=clause_words, complete=True),),
                role="cold_open",
            )

    return None


def plan_viral_story_cut(
    sentences: Sequence[Sentence],
    clip_in_ms: int,
    clip_out_ms: int,
    *,
    payoff_at_ms: int | None = None,
    excited_intervals_ms: Sequence[tuple[int, int]] = (),
    target_max_ms: int = 48_000,
    target_min_ms: int = 30_000,
    enable_cold_open: bool = True,
    enable_condense: bool = True,
    cold_open_min_ms: int = 1_800,
    cold_open_max_ms: int = 3_400,
    boundary_pad_ms: int = 80,
) -> ViralStoryPlan:
    """Plan a viral cold-open hook teaser and middle-tangent condensation cut (D-378).

    Enforces strict fail-stop validation and E3 word-boundary invariants:
    - Never drops sentence 0 (hook/setup) or the final sentence (payoff/climax).
    - Never cuts inside any aligned word across outer or internal splice boundaries.
    - Respects [30, 120] ms E3 padding wherever adjacent pauses permit.
    - Remaps all captions onto a continuous output timeline matching ``assembled_splice_filter``.
    """
    if not sentences:
        raise ValueError("plan_viral_story_cut requires at least one sentence")
    if clip_in_ms < 0 or clip_out_ms <= clip_in_ms:
        raise ValueError(f"Invalid clip range: clip_in_ms={clip_in_ms}, clip_out_ms={clip_out_ms}")
    if target_min_ms <= 0 or target_max_ms < target_min_ms:
        raise ValueError(
            f"Invalid target duration bounds: min={target_min_ms}, max={target_max_ms}"
        )
    if cold_open_min_ms <= 0 or cold_open_max_ms < cold_open_min_ms:
        raise ValueError(
            f"Invalid cold-open duration bounds: min={cold_open_min_ms}, max={cold_open_max_ms}"
        )
    if not (_MIN_E3_PAD_MS <= boundary_pad_ms <= _MAX_E3_PAD_MS):
        raise ValueError(
            f"boundary_pad_ms must be in [{_MIN_E3_PAD_MS}, {_MAX_E3_PAD_MS}] ms per E3, "
            f"got {boundary_pad_ms}"
        )
    if payoff_at_ms is not None and not (clip_in_ms <= payoff_at_ms <= clip_out_ms):
        raise ValueError(
            f"payoff_at_ms ({payoff_at_ms}) must lie within [{clip_in_ms}, {clip_out_ms}]"
        )
    for iv_start, iv_end in excited_intervals_ms:
        if iv_end <= iv_start:
            raise ValueError(
                f"Invalid excited interval ({iv_start}, {iv_end}): end must exceed start"
            )

    sent_tuple = tuple(sentences)
    for idx, sent in enumerate(sent_tuple):
        if not sent.words:
            raise ValueError(f"Sentence {idx} has no words")
        if not sent.complete:
            raise ValueError(
                f"Kurdish invariant #2 violation: sentence {idx} ({sent.text!r}) is incomplete"
            )
        if sent.start_ms < clip_in_ms or sent.end_ms > clip_out_ms:
            raise ValueError(
                f"Sentence {idx} [{sent.start_ms}..{sent.end_ms}] lies outside clip "
                f"[{clip_in_ms}..{clip_out_ms}]"
            )
    assert_deliverable_order(sent_tuple)

    all_words = tuple(w for s in sent_tuple for w in s.words)
    source_duration_ms = clip_out_ms - clip_in_ms
    n_sents = len(sent_tuple)

    # 1. Smart Middle-Tangent Condensation (never drops sentence 0 or final sentence N-1).
    kept_set: set[int] = set(range(n_sents))
    body_spans = _build_body_spans(
        sent_tuple, tuple(range(n_sents)), clip_in_ms, clip_out_ms, boundary_pad_ms
    )
    body_duration_ms = sum(sp.duration_ms for sp in body_spans)
    applied_condense = False

    if enable_condense and n_sents >= 3 and body_duration_ms > target_max_ms:
        interior_scored = [
            (
                idx,
                score_interior_sentence(
                    sent_tuple[idx],
                    clip_in_ms=clip_in_ms,
                    clip_out_ms=clip_out_ms,
                    payoff_at_ms=payoff_at_ms,
                    excited_intervals_ms=excited_intervals_ms,
                ),
                sent_tuple[idx].end_ms - sent_tuple[idx].start_ms,
            )
            for idx in range(1, n_sents - 1)
        ]
        # Lowest narrative score first; tie-break by longer tangent first, then earlier index.
        interior_scored.sort(key=lambda item: (item[1], -item[2], item[0]))

        for idx, _score, _dur in interior_scored:
            candidate_kept = sorted(kept_set - {idx})
            candidate_spans = _build_body_spans(
                sent_tuple, candidate_kept, clip_in_ms, clip_out_ms, boundary_pad_ms
            )
            candidate_dur = sum(sp.duration_ms for sp in candidate_spans)
            if candidate_dur >= target_min_ms:
                kept_set.remove(idx)
                body_spans = candidate_spans
                body_duration_ms = candidate_dur
                applied_condense = True
                if body_duration_ms <= target_max_ms:
                    break

    for sp in body_spans:
        _assert_no_split_words(sp.source_in_ms, all_words)
        _assert_no_split_words(sp.source_out_ms, all_words)

    kept_indices = tuple(sorted(kept_set))
    dropped_indices = tuple(i for i in range(n_sents) if i not in kept_set)

    # 2. Smart Cold-Open Hook Teaser (late climax clause placed at 0..3.4s).
    cold_open_span: AssemblySpan | None = None
    if enable_cold_open:
        cold_open_span = _select_cold_open_span(
            body_spans,
            all_words,
            clip_in_ms=clip_in_ms,
            clip_out_ms=clip_out_ms,
            payoff_at_ms=payoff_at_ms,
            excited_intervals_ms=excited_intervals_ms,
            cold_open_min_ms=cold_open_min_ms,
            cold_open_max_ms=cold_open_max_ms,
            boundary_pad_ms=boundary_pad_ms,
        )

    final_spans: tuple[AssemblySpan, ...]
    if cold_open_span is not None:
        reindexed_body = tuple(replace(sp, span_index=i + 1) for i, sp in enumerate(body_spans))
        final_spans = (cold_open_span, *reindexed_body)
        applied_cold_open = True
        cold_open_text: str | None = cold_open_span.sentences[0].text
        cold_open_in: int | None = cold_open_span.source_in_ms
        cold_open_out: int | None = cold_open_span.source_out_ms
    else:
        final_spans = body_spans
        applied_cold_open = False
        cold_open_text = None
        cold_open_in = None
        cold_open_out = None

    remapped_sentences = _remap_spans_to_sentences(final_spans)
    output_duration_ms = sum(sp.duration_ms for sp in final_spans)

    return ViralStoryPlan(
        spans=final_spans,
        remapped_sentences=remapped_sentences,
        kept_sentence_indices=kept_indices,
        dropped_sentence_indices=dropped_indices,
        applied_cold_open=applied_cold_open,
        applied_condense=applied_condense,
        source_duration_ms=source_duration_ms,
        output_duration_ms=output_duration_ms,
        cold_open_text=cold_open_text,
        cold_open_source_in_ms=cold_open_in,
        cold_open_source_out_ms=cold_open_out,
    )
