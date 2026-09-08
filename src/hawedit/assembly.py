"""Multi-moment story assembly and unified editorial judging (§3 Stage 6, pro-edit T6).

Assembles non-contiguous sentence highlights across an episode into a single coherent story reel.
Re-offsets word and sentence timestamps onto a unified continuous timeline [0, total_duration_ms]
while preserving Kurdish invariant #1 (exact surface words) and invariant #2 (complete sentences).

The entire assembled narrative is scored as one unit by the editorial judge (AC-7), enforcing
strict §2 thresholds on hook strength and misleading-edit risk (AC-8).
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from hawedit.captions import CaptionStyle, build_ass, find_ffmpeg, subtitle_filter
from hawedit.clip import (
    MAX_MISLEADING_EDIT_RISK,
    MIN_HOOK_SCORE,
    EditorialBelowThreshold,
)
from hawedit.judge import EditorialJudge, InputMode, JudgeRequest, JudgeVerdict
from hawedit.keyframes import extract_judge_frames
from hawedit.normalize import normalize_sorani
from hawedit.render import crop_filter
from hawedit.sentences import Sentence
from hawedit.transcripts import Word

__all__ = [
    "AssembledReel",
    "AssemblySpan",
    "assemble_cold_open",
    "assemble_spans",
    "assembled_splice_filter",
    "judge_assembled_reel_multimodal",
    "judge_assembly",
    "render_assembled_reel",
]


@dataclass(frozen=True, slots=True)
class AssemblySpan:
    """One contiguous source span participating in an assembled reel."""

    span_index: int
    source_in_ms: int
    source_out_ms: int
    duration_ms: int
    sentences: tuple[Sentence, ...]

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


def assembled_splice_filter(spans: Sequence[AssemblySpan]) -> str:
    """Generate the FFmpeg filtergraph splicing participating spans in order (Task T4.9).

    Trims video and audio for each span, resets PTS, and concatenates them into
    single continuous [v_concat] and [a_concat] streams.
    """
    if not spans:
        raise ValueError("Cannot create splice filter for empty spans")

    v_trims: list[str] = []
    a_trims: list[str] = []
    concat_inputs: list[str] = []

    for i, span in enumerate(spans):
        in_s = span.source_in_ms / 1000.0
        out_s = span.source_out_ms / 1000.0
        v_trims.append(f"[0:v]trim=start={in_s:.3f}:end={out_s:.3f},setpts=PTS-STARTPTS[v{i}]")
        a_trims.append(f"[0:a]atrim=start={in_s:.3f}:end={out_s:.3f},asetpts=PTS-STARTPTS[a{i}]")
        concat_inputs.append(f"[v{i}][a{i}]")

    n = len(spans)
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
        style=caption_style,
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
    a_chain = "[a_concat]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[a_out]"
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
