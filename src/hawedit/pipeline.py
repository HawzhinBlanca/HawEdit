"""One command that runs §3, and reports every stage it could not run.

Until this existed, every stage worked and nothing joined them, so "does this system work" was
a question you answered by reading a test suite. This is the thing you point at a video.

Three of §3's stages need models this machine does not have — Path A's Kurdish judge and
Stage 4's judge call need credentials and the §3 governance decision (`BLOCKED.md` #3), Path
B needs `VideoChat3-4B` weights and a GPU (`BLOCKED.md` #2), and Stage 1's ASR needs both
(`BLOCKED.md` #2, #6). A runner that quietly skipped them would produce a clip and a green
log, and you would have to already know that no model discovered it to understand what you
were looking at.

So every stage yields either a result or a `StageSkipped` that names its blocker,
`PipelineRun.complete` is false whenever anything was skipped, and the CLI exits non-zero on
an incomplete run. §1: fail visible, not silent. A run that rendered a clip and called itself
complete would be the most expensive kind of wrong, because nothing about the artifact reveals
that no judge scored it.

**The path that does run, end to end.** Two stages are stood in for rather than skipped —
a transcript for Stage 1 and a verdict for Stage 4, from a human today and from the models
when they arrive. The Stage 4 stand-in is not a convenience: `Clip.assert_renderable` refuses
a clip with no editorial block, because an unjudged clip has no meaning fidelity and no
misleading-edit risk, and §8.2 calls the second of those the metric that matters for a media
organisation. Without a verdict this builds a clip and stops. Given both, it runs six stages
of the blueprint against real media:

    Stage 0  ingest      16 kHz audio, 1 fps proxy, shot cuts, VAD          ingest.py
    §4.1     normalize   five collisions, raw written once and never again  transcripts.py
    Stage 2  index       BM25 + character 3-grams over the *normalized*     index.py
    §4.2     segment     sentences from punctuation and Stage 0's VAD       sentences.py
    Stage 5  fuse        §5 anchors + this run's real shot cuts             boundary.py
    Stage 6  render      9:16 crop, shaping=complex burn-in, encode         render.py

The joins are the point. Stage 5 fuses against the shot cuts Stage 0 found *on this video*,
and §4.2 segments against the VAD pauses from the same run — not against fixtures. Every
Kurdish invariant that governs those stages is enforced by the modules themselves; the runner
adds none of its own and weakens none.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hawedit.boundary import BoundaryInputs, IncompleteSentence, fuse_boundary
from hawedit.captions import build_ass
from hawedit.clip import Clip, ClipTranscript, DiscoveryPath, Qc
from hawedit.discovery import Candidate, MergedCandidate, merge_candidates
from hawedit.index import Bm25Index
from hawedit.ingest import IngestResult, ingest
from hawedit.judge import EditorialJudge, JudgeRequest, JudgeVerdict
from hawedit.render import RenderError, RenderResult, render_clip
from hawedit.sentences import Sentence, anchors_for, segment_sentences
from hawedit.transcripts import (
    NormalizedTranscript,
    RawTranscript,
    RawTranscriptImmutable,
    TranscriptStore,
    normalize_transcript,
)

__all__ = [
    "PipelineRun",
    "StageSkipped",
    "assert_contiguous",
    "assert_time_contiguous",
    "main",
    "run_pipeline",
]

FONTS_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"


@dataclass(frozen=True, slots=True)
class StageSkipped:
    """A stage that did not run, and what stopped it.

    Never an empty result. "Did not run" and "ran and found nothing" are different facts about
    the world and must not serialize to the same JSON — the same rule that keeps
    `IngestResult.diarization` at `None` rather than `[]`.
    """

    stage: str
    reason: str
    blocked_by: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "skipped": True,
            "stage": self.stage,
            "reason": self.reason,
            "blocked_by": list(self.blocked_by),
        }


@dataclass(frozen=True, slots=True)
class PipelineRun:
    """What one pass over one media file produced, and what it could not."""

    media_id: str
    source: str
    work_dir: str
    ingest: IngestResult | StageSkipped | None = None
    transcript: NormalizedTranscript | StageSkipped | None = None
    index: Bm25Index | StageSkipped | None = None
    sentences: tuple[Sentence, ...] = ()
    visual_index: StageSkipped | None = None
    discovery: StageSkipped | None = None
    editorial: StageSkipped | None = None
    candidates: tuple[MergedCandidate, ...] = ()
    boundary: object | None = None
    clip: Clip | None = None
    render: RenderResult | StageSkipped | None = None

    def skipped(self) -> tuple[tuple[str, StageSkipped], ...]:
        """Every stage that did not run, in pipeline order."""
        ordered = (
            ("ingest", self.ingest),
            ("transcript", self.transcript),
            ("index", self.index),
            ("visual_index", self.visual_index),
            ("discovery", self.discovery),
            ("editorial", self.editorial),
            ("boundary", self.boundary),
            ("render", self.render),
        )
        return tuple((name, value) for name, value in ordered if isinstance(value, StageSkipped))

    @property
    def complete(self) -> bool:
        """True only when every §3 stage ran.

        Producing a clip is not the same as being the system §3 describes, and a runner that
        conflated them would report success for a pipeline missing its discovery and its judge.
        """
        return not self.skipped()

    def to_dict(self) -> dict[str, Any]:
        def encode(value: object) -> Any:
            if value is None:
                return None
            if isinstance(value, StageSkipped):
                return value.to_dict()
            to_dict = getattr(value, "to_dict", None)
            return to_dict() if callable(to_dict) else str(value)

        return {
            "media_id": self.media_id,
            "source": self.source,
            "work_dir": self.work_dir,
            "complete": self.complete,
            "skipped": [name for name, _ in self.skipped()],
            "ingest": encode(self.ingest),
            "transcript": (
                self.transcript.to_dict()
                if isinstance(self.transcript, StageSkipped)
                else (
                    json.loads(self.transcript.to_json()) if self.transcript is not None else None
                )
            ),
            "sentence_count": len(self.sentences),
            "candidates": [c.to_dict() for c in self.candidates],
            "visual_index": encode(self.visual_index),
            "discovery": encode(self.discovery),
            "editorial": encode(self.editorial),
            "clip": self.clip.to_dict() if self.clip is not None else None,
            "render": (
                encode(self.render)
                if isinstance(self.render, StageSkipped)
                else (
                    {
                        "path": self.render.path,
                        "width": self.render.width,
                        "height": self.render.height,
                        "duration_ms": self.render.duration_ms,
                        "reframe": self.render.reframe.value,
                        "encoder": self.render.encoder.value,
                        "ffmpeg_version": self.render.ffmpeg_version,
                    }
                    if self.render is not None
                    else None
                )
            ),
        }


# The stages that need something this machine does not have. Written once, here, so the run
# report and the README cannot drift apart about what is missing.
_STAGE_1_ASR = StageSkipped(
    stage="transcript",
    reason=(
        "§3 Stage 1 needs omniASR_LLM_7B_v2 and omniASR_CTC_3B_v2. No weights and no GPU here, "
        "so no transcript was produced. Supply one with --transcript to run the rest."
    ),
    blocked_by=("BLOCKED.md #2", "BLOCKED.md #6"),
)
_STAGE_2_VISUAL = StageSkipped(
    stage="visual_index",
    reason="§3 Stage 2's visual index needs Qwen3-VL embedding and reranker weights, and a GPU.",
    blocked_by=("BLOCKED.md #2",),
)
_STAGE_3_DISCOVERY = StageSkipped(
    stage="discovery",
    reason=(
        "§3 Stage 3 needs both producers: Path A is the Kurdish judge over the full transcript "
        "(credentials + the ZDR governance decision), Path B is VideoChat3-4B (weights + GPU). "
        "The merge that unions them is built and tested — see discovery.py."
    ),
    blocked_by=("BLOCKED.md #2", "BLOCKED.md #3"),
)
_STAGE_3_NOTHING_FOUND = StageSkipped(
    stage="discovery",
    reason=(
        "Path A ran over the whole transcript and returned no candidates. That is a real "
        "answer about this media, not a failure — but no clip can be cut from it."
    ),
    blocked_by=("no candidates",),
)
_STAGE_4_JUDGE = StageSkipped(
    stage="editorial",
    reason=(
        "§3 Stage 4's judge is gemini-2.5-pro. No credentials, and §3 Stage 3's governance box "
        "must be answered before the first client job. The contract is built — see judge.py."
    ),
    blocked_by=("BLOCKED.md #3",),
)


def assert_time_contiguous(sentences: Sequence[Sentence], selection: tuple[int, ...]) -> None:
    """Refuse a selection whose span covers a sentence it does not include.

    `assert_contiguous` checks that the *indices* form a run. That is not the property that
    matters: the clip is cut in time, so what must hold is that no unselected sentence falls
    inside the selected span. Those coincide only when the sentence list is already in
    chronological order, and nothing guaranteed that — a caller-supplied transcript with words
    out of time order produces an index-contiguous selection whose window contains real,
    un-captioned Kurdish speech.

    That is precisely the defect `assert_contiguous` was added to prevent, reachable through a
    dimension the fix never checked. Found by the second independent review.
    """
    if not selection:
        return
    chosen = {sentences[i] for i in selection}
    start = min(s.start_ms for s in chosen)
    end = max(s.end_ms for s in chosen)
    swallowed = [
        (i, s)
        for i, s in enumerate(sentences)
        if i not in selection and s.start_ms < end and s.end_ms > start
    ]
    if swallowed:
        names = ", ".join(f"#{i} ({s.start_ms}-{s.end_ms} ms)" for i, s in swallowed)
        raise ValueError(
            f"the selected sentences span {start}-{end} ms, which overlaps sentence(s) not "
            f"selected: {names}. The clip would run across speech that has no caption and is "
            f"missing from the transcript that ships to the client (§4.1)."
        )


def assert_contiguous(selection: tuple[int, ...], total: int) -> None:
    """Refuse a selection that skips a sentence it spans.

    §5's anchors come from the first and last *selected* complete sentence, and the invariant
    check only compares numbers — so selecting sentences 0 and 2 produces a boundary spanning
    sentence 1, and the clip renders with real Kurdish speech in the middle that has no caption
    and is absent from the `raw_ckb` §4.1 says ships to the client. The numbers all agree; the
    artifact lies. Found by the independent review of 2026-08-07.

    Out-of-order indices are fine — sorted, they are still a run.

    Raises:
        ValueError: the selection has duplicates, or skips a sentence between its ends.
    """
    if len(set(selection)) != len(selection):
        raise ValueError(f"sentence selection {selection} contains a duplicate index")
    ordered = sorted(selection)
    if ordered and ordered != list(range(ordered[0], ordered[-1] + 1)):
        missing = sorted(set(range(ordered[0], ordered[-1] + 1)) - set(ordered))
        raise ValueError(
            f"sentence selection {selection} is not contiguous — it spans sentence(s) "
            f"{missing} without including them. The clip would run across speech that has no "
            f"caption and is missing from the transcript that ships to the client."
        )


def run_pipeline(
    source: Path,
    work_dir: Path,
    media_id: str | None = None,
    transcript: RawTranscript | None = None,
    select_sentences: tuple[int, ...] = (),
    qc: Qc | None = None,
    verdict: JudgeVerdict | None = None,
    discover: Callable[[NormalizedTranscript], Sequence[Candidate]] | None = None,
    judge: EditorialJudge | None = None,
    ffmpeg: Path | None = None,
) -> PipelineRun:
    """Run §3 over one media file, as far as the available models allow.

    Args:
        transcript: what §3 Stage 1 would have produced. Supplying one is how the rest of the
            pipeline runs today; it is written through `TranscriptStore`, so Kurdish invariant
            #1 governs it exactly as it will govern a real ASR result.
        select_sentences: indexes into the segmented sentences to cut a clip from. Empty means
            stop after indexing — this runner does not choose moments, because choosing them is
            §3 Stage 3's job and Stage 3 has no producers.
        qc: §5's QC block. Absent means the clip is built but never rendered: §2 puts a human
            gate before output, always, and a runner is not a human.
        discover: §3 Stage 3 Path A. Supply `PathADiscovery(...).discover` and the runner
            stops standing in for discovery and actually runs it. Path B stays absent — its
            model needs a GPU — and the union handles that: a verbal-only run is exactly what
            §3 says must never be filtered away.
        judge: §3 Stage 4. Supply `GeminiJudge(...)` and the runner scores the top candidate
            itself rather than needing `verdict` handed to it.
        verdict: what §3 Stage 4 would have returned. The second stand-in, for the same reason
            as `transcript`: `Clip.assert_renderable` refuses a clip with no editorial block,
            because an unjudged clip has no meaning fidelity and no misleading-edit risk and
            §8.2 calls the second of those the metric that matters for a media organisation.
            So without a verdict the pipeline builds a clip and stops — which is the gate
            working, not a limitation to route around.

    Raises:
        FileNotFoundError: `source` does not exist.
        ValueError: the transcript is for different media.
        IndexError: `select_sentences` names a sentence that does not exist.
    """
    if not source.exists():
        raise FileNotFoundError(f"no media at {source}")

    identifier = media_id or source.stem
    if transcript is not None and transcript.media_id != identifier:
        raise ValueError(
            f"transcript media_id {transcript.media_id!r} is not {identifier!r}. A transcript "
            f"of another episode would render a clip whose captions are fiction."
        )

    work_dir.mkdir(parents=True, exist_ok=True)

    # --- §3 Stage 0 ----------------------------------------------------------------------
    ingested = ingest(source, work_dir / "stage0", media_id=identifier, ffmpeg=ffmpeg)

    run = PipelineRun(
        media_id=identifier,
        source=str(source),
        work_dir=str(work_dir),
        ingest=ingested,
        transcript=_STAGE_1_ASR,
        visual_index=_STAGE_2_VISUAL,
        discovery=_STAGE_3_DISCOVERY,
        editorial=_STAGE_4_JUDGE,
    )
    if transcript is None:
        return run

    # --- §3 Stage 1 (supplied) + §4.1 -----------------------------------------------------
    store = TranscriptStore(work_dir / "transcripts")
    try:
        store.write_raw(transcript)
    except RawTranscriptImmutable:
        # Invariant #1: the canonical transcript is never rewritten. A second run over the
        # same work directory reads what is already there rather than overwriting it.
        transcript = store.read_raw(identifier)
    store.verify_raw_integrity(identifier)
    normalized = normalize_transcript(transcript)
    store.write_norm(normalized)

    # --- §3 Stage 2 (text half) -----------------------------------------------------------
    index = Bm25Index.from_transcript(normalized)

    # --- §4.2 sentence segmentation, against this run's own VAD ---------------------------
    vad_pauses = _pauses_between(ingested)
    sentences = segment_sentences(transcript.words, vad_pauses=vad_pauses)

    run = _replace(run, transcript=normalized, index=index, sentences=sentences)

    # --- §3 Stage 3 Path A ----------------------------------------------------------------
    merged: tuple[MergedCandidate, ...] = ()
    if discover is not None:
        verbal = tuple(discover(normalized))
        # Path B has no producer (its model needs a GPU), so the union runs one-sided. §3 is
        # explicit that this is correct rather than degraded: candidates from *either* path
        # proceed, and a verbal-only moment is the case the dual path exists to protect.
        merged = merge_candidates(list(verbal), [])
        run = _replace(
            run,
            discovery=None if merged else _STAGE_3_NOTHING_FOUND,
            candidates=merged,
            visual_index=_STAGE_2_VISUAL,
        )

    # --- §3 Stage 4 -----------------------------------------------------------------------
    if judge is not None and merged:
        top = merged[0]
        verdict = judge.judge(
            JudgeRequest.for_survivor(
                top,
                text_ckb=normalized.text_ckb,
            )
        )
        run = _replace(run, editorial=None)

    if not select_sentences:
        return run

    out_of_range = [i for i in select_sentences if not 0 <= i < len(sentences)]
    if out_of_range:
        raise IndexError(
            f"sentence index {out_of_range} is outside 0..{len(sentences) - 1}. The transcript "
            f"segmented into {len(sentences)} sentence(s)."
        )
    # After the range check on purpose: an index of 99 in a 3-sentence transcript is out of
    # range, and reporting it as "spans sentences 1..98" is true but useless.
    assert_contiguous(select_sentences, total=len(sentences))
    # Index contiguity is not time contiguity — see assert_time_contiguous.
    assert_time_contiguous(sentences, select_sentences)
    selected = tuple(sentences[i] for i in select_sentences)

    # --- §3 Stage 5 boundary fusion -------------------------------------------------------
    anchors = anchors_for(selected)
    if anchors is None:
        return _replace(
            run,
            boundary=StageSkipped(
                stage="boundary",
                reason=(
                    "no complete sentence in the selection, so §5 has no anchor. Kurdish "
                    "invariant #2 is reject, never render — a boundary invented here is how a "
                    "clip that starts mid-sentence reaches a client."
                ),
            ),
        )

    anchor_in, anchor_out = anchors
    boundary = fuse_boundary(
        BoundaryInputs(
            anchor_in_ms=anchor_in,
            anchor_out_ms=anchor_out,
            sentence_complete=True,
            # The join this runner exists to make: the shot cuts and speech regions below were
            # measured on *this* video by Stage 0 a few lines above, not supplied as fixtures.
            shot_cuts_ms=ingested.shot_cuts_ms,
            vad_onset_ms=ingested.speech[0].start_ms if ingested.speech else None,
        )
    )

    clip = Clip(
        clip_id=f"{identifier}-{select_sentences[0]}",
        media_id=identifier,
        in_ms=boundary.final_in_ms,
        out_ms=boundary.final_out_ms,
        # §3 Stage 3 discovers candidates and did not run. VERBAL records where this clip
        # *came from* — a human reading the transcript — and no clip here may claim BOTH.
        discovery_path=DiscoveryPath.VERBAL,
        boundary=boundary,
        transcript=ClipTranscript(
            raw_ckb=transcript.text_ckb,
            norm_ckb=normalized.text_ckb,
            en_aux=None,
            words=tuple(w for s in selected for w in s.words),
            asr=transcript.asr,
        ),
        editorial=verdict.to_editorial() if verdict is not None else None,
        output=(
            verdict.to_output(crop_target="static_centre", durations=(30,))
            if verdict is not None
            else None
        ),
        qc=qc,
    )
    run = _replace(run, boundary=boundary, clip=clip)

    # --- §3 Stage 6 render ----------------------------------------------------------------
    if verdict is None:
        # Not a shortcut around the gate — the gate's own conclusion, reached before spending
        # an encode on a clip that `assert_renderable` would refuse anyway.
        return _replace(
            run,
            render=StageSkipped(
                stage="render",
                reason=(
                    "§3 Stage 4 did not run, so the clip has no editorial block and §2's "
                    "render gate refuses it: an unjudged clip has no meaning fidelity and no "
                    "misleading-edit risk. Supply a verdict to render."
                ),
                blocked_by=("BLOCKED.md #3",),
            ),
        )

    ass_path = work_dir / "captions.ass"
    ass_path.write_text(build_ass(selected), encoding="utf-8")
    width, height = _proxy_dimensions(source, ffmpeg)
    try:
        rendered = render_clip(
            clip,
            source,
            ass_path,
            FONTS_DIR,
            work_dir / f"{clip.clip_id}.mp4",
            source_width=width,
            source_height=height,
            ffmpeg=ffmpeg,
        )
    except (ValueError, RenderError, IncompleteSentence) as exc:
        # The render gate refused. That is the gate working — §2 puts QC before output always,
        # and invariant #2 forbids rendering an unfinished sentence — so it is reported rather
        # than raised: the run is a partial result, not a crash.
        return _replace(
            run, render=StageSkipped(stage="render", reason=str(exc), blocked_by=("§2 QC gate",))
        )

    return _replace(run, render=rendered)


def _replace(run: PipelineRun, **changes: object) -> PipelineRun:
    from dataclasses import replace

    return replace(run, **changes)  # type: ignore[arg-type]


def _pauses_between(ingested: IngestResult) -> tuple[tuple[int, int], ...]:
    """Silences between Stage 0's VAD speech regions, for §4.2's pause-based segmentation.

    §4.2 mandates segmenting on VAD pauses as well as punctuation, and this is where the two
    stages actually meet: the gaps are computed from the speech regions this run detected.
    """
    speech = ingested.speech
    return tuple(
        (speech[i].end_ms, speech[i + 1].start_ms)
        for i in range(len(speech) - 1)
        if speech[i + 1].start_ms > speech[i].end_ms
    )


def _proxy_dimensions(source: Path, ffmpeg: Path | None) -> tuple[int, int]:
    """Source frame size, probed rather than assumed — the crop arithmetic depends on it."""
    import subprocess

    from hawedit.captions import find_ffmpeg
    from hawedit.ingest import IngestError

    binary = ffmpeg or find_ffmpeg()
    if binary is None:
        raise IngestError("no ffmpeg available — run scripts/fetch-ffmpeg.sh")
    output = subprocess.run(
        [
            str(binary.with_name("ffprobe")),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0:s=x",
            str(source),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    width, height = (int(value) for value in output.split("x")[:2])
    return width, height


def main(argv: list[str] | None = None) -> int:
    """`python -m hawedit.pipeline <video> [--transcript t.json] [--sentences 0,1]`.

    Exits non-zero on an incomplete run. A partial pipeline that exited 0 would be indis-
    tinguishable from a working one to anything scripting it.
    """
    parser = argparse.ArgumentParser(
        prog="hawedit.pipeline", description="Run §3 over one media file, as far as it can go."
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("--work-dir", type=Path, default=Path("work"))
    parser.add_argument("--media-id")
    parser.add_argument(
        "--transcript", type=Path, help="a transcript.raw.json to stand in for §3 Stage 1"
    )
    parser.add_argument("--sentences", help="comma-separated sentence indexes to cut, e.g. 0,1")
    parser.add_argument("--qc-pass", action="store_true", help="record a human QC pass (§2)")
    parser.add_argument("--json", action="store_true", help="print the run report as JSON")
    args = parser.parse_args(argv)

    transcript = (
        RawTranscript.from_json(args.transcript.read_text(encoding="utf-8"))
        if args.transcript
        else None
    )
    selection = tuple(int(i) for i in args.sentences.split(",")) if args.sentences else ()

    try:
        run = run_pipeline(
            args.source,
            args.work_dir,
            media_id=args.media_id,
            transcript=transcript,
            select_sentences=selection,
            qc=Qc(auto_pass=True, flags=(), human_reviewed=True) if args.qc_pass else None,
        )
    except FileNotFoundError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(run.to_dict(), ensure_ascii=False, indent=2))
    else:
        _print_report(run)
    return 0 if run.complete else 1


def _print_report(run: PipelineRun) -> None:
    print(f"media   {run.media_id}")
    if not isinstance(run.ingest, StageSkipped) and run.ingest is not None:
        print(
            f"stage 0 {run.ingest.duration_ms} ms · {len(run.ingest.shot_cuts_ms)} shot cut(s) · "
            f"{len(run.ingest.speech)} speech region(s) · diarization: not run"
        )
    if run.sentences:
        print(f"§4.2    {len(run.sentences)} sentence(s)")
    if run.clip is not None:
        print(f"stage 5 clip {run.clip.in_ms}..{run.clip.out_ms} ms")
    if run.render is not None and not isinstance(run.render, StageSkipped):
        print(f"stage 6 {run.render.path} ({run.render.width}x{run.render.height})")
    for name, skip in run.skipped():
        blockers = f" [{', '.join(skip.blocked_by)}]" if skip.blocked_by else ""
        print(f"SKIPPED {name}{blockers}: {skip.reason}")
    print(
        "\nrun is COMPLETE"
        if run.complete
        else f"\nrun is INCOMPLETE — {len(run.skipped())} stage(s) did not run"
    )


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    raise SystemExit(main())
