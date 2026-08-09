"""One command that runs §3, and reports every stage it could not run.

Until this existed, every stage worked and nothing joined them, so "does this system work" was
a question you answered by reading a test suite. This is the thing you point at a video.

Every model stage is now wired, but none is silently enabled: OmniASR needs its optional
runtime and checkpoints, local vision needs the GPU checkpoints, and Gemini/Vertex needs an
authorized cloud route. A runner that quietly skipped an unconfigured stage would produce a
clip and a green log, and you would have to already know that no model discovered it to
understand the artifact.

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
    Stage 2  windows     scenes segmented to ~1 fps × 64 frames             visual_index.py
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
import os
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol, TextIO

from hawedit.artifact_bundle import ArtifactBundle, BundleError
from hawedit.asr import CanonicalTranscriptProducer
from hawedit.boundary import Boundary, BoundaryInputs, IncompleteSentence, fuse_boundary
from hawedit.captions import CaptionStyle, build_ass
from hawedit.cli import machine_readable_stdout, use_utf8_streams
from hawedit.clip import Clip, ClipTranscript, DiscoveryPath, Qc, RejectedCandidate
from hawedit.credentials import CredentialError
from hawedit.delivery import DeliveryError, build_edl, build_srt
from hawedit.discovery import Candidate, MergedCandidate, merge_candidates
from hawedit.gemini import GeminiUnavailable, JudgeUnusable
from hawedit.index import Bm25Index
from hawedit.ingest import IngestError, IngestResult, ingest, probe_stream
from hawedit.judge import (
    EditorialJudge,
    JudgeRequest,
    JudgeVerdict,
    NotRoutable,
    RequestTooLarge,
)
from hawedit.keyframes import KeyframeError, extract_judge_frames
from hawedit.normalize import normalize_sorani
from hawedit.path_b import VideoUnderstanding
from hawedit.qwen_visual import EmbedderUnavailable
from hawedit.reframe import SubjectTracker
from hawedit.render import RenderError, RenderResult, frame_rate, render_clip
from hawedit.sentences import Sentence, anchors_for, segment_sentences
from hawedit.timelens import VisualEvidenceInterval, interval_for_fusion
from hawedit.transcripts import (
    NormalizedTranscript,
    RawTranscript,
    RawTranscriptImmutable,
    TranscriptStore,
    UnalignedSpeech,
    Word,
    normalize_transcript,
    validate_media_id,
)
from hawedit.video_grounding import GroundingError
from hawedit.video_input import VideoInputError
from hawedit.visual_index import (
    DECLARED_SAMPLING_FPS,
    MAX_FRAMES_PER_WINDOW,
    REFERENCE_FPS,
    SceneWindow,
    plan_scene_windows,
)
from hawedit.visual_pipeline import VisualComposer, VisualDiscoveryResult, VisualPipelineError

__all__ = [
    "Delivery",
    "PipelineRun",
    "StageSkipped",
    "assert_contiguous",
    "assert_time_contiguous",
    "main",
    "run_pipeline",
]


def _runtime_fonts_dir() -> Path:
    checkout = Path(__file__).resolve().parents[2] / "assets" / "fonts"
    installed = Path(sys.prefix) / "share" / "hawedit" / "assets" / "fonts"
    return checkout if checkout.is_dir() else installed


FONTS_DIR = _runtime_fonts_dir()


class TemporalGrounder(Protocol):
    """Stage 5 adapter; concrete implementations ground queries in exact scene windows."""

    def ground_all(
        self, windows: Sequence[SceneWindow], query: str
    ) -> tuple[VisualEvidenceInterval, ...]: ...


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
class Delivery:
    """§2's two sidecars, once they are on disk.

    Separate from `RenderResult` because they are separate deliverables: a run can produce a
    correct MP4 and still be unable to write an honest EDL when its rate has no supported CMX
    representation. That gap is a named `StageSkipped`, not a missing file nobody mentions.
    """

    srt_path: str
    edl_path: str
    editing_json_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "srt_path": self.srt_path,
            "edl_path": self.edl_path,
            "editing_json_path": self.editing_json_path,
        }


@dataclass(frozen=True, slots=True)
class PipelineRun:
    """What one pass over one media file produced, and what it could not."""

    media_id: str
    source: str
    work_dir: str
    ingest: IngestResult | StageSkipped | None = None
    transcript: NormalizedTranscript | StageSkipped | None = None
    # Speech the canonical transcript does not contain, carried up from the raw artifact.
    #
    # D-103 put this in `transcript.raw.json`, and the report a human reads is the normalized
    # transcript, which by design has no such field — so a run that dropped speech said nothing
    # about it here. Measured on the real 38-minute run: 2 of 547 regions, 664 ms of Kurdish, and
    # the emitted report mentioned neither. §1 of this module: fail visible, not silent. D-145.
    transcript_gaps: tuple[UnalignedSpeech, ...] = ()
    index: Bm25Index | StageSkipped | None = None
    sentences: tuple[Sentence, ...] = ()
    # §3 Stage 2's visual half splits into a part that needs weights and a part that does not.
    # The window plan is arithmetic over Stage 0's shot cuts, so it runs here on real media
    # even though the embedder cannot; `visual_index` stays skipped for the embedding itself.
    visual_windows: tuple[SceneWindow, ...] = ()
    visual_index: VisualDiscoveryResult | StageSkipped | None = None
    # Where the Path B retrieval query came from. The query itself is recorded by
    # `VisualDiscoveryResult`; this says who authorized its scope. `None` means Path B did not
    # run, never "the whole transcript was used implicitly". D-154.
    visual_query_source: str | None = None
    discovery: StageSkipped | None = None
    editorial: StageSkipped | None = None
    candidates: tuple[MergedCandidate, ...] = ()
    # Every candidate a decision ruled out, with the reason it was ruled out and the path that
    # found it. §5: "Rejection is a first-class outcome … that set is your only measure of
    # recall", and §8.2 measures Recall@20 *per discovery path*. `RejectedCandidate` was built,
    # validated and unit-tested with no producer anywhere in `src/`, so the measure had no data
    # at all. D-153.
    rejected: tuple[RejectedCandidate, ...] = ()
    boundary: object | None = None
    clip: Clip | None = None
    render: RenderResult | StageSkipped | None = None
    delivery: Delivery | StageSkipped | None = None

    def _rejected_by_path(self) -> dict[str, int]:
        """How many candidates each discovery path lost, which is what §8.2 partitions on.

        Every path that found a candidate appears, at zero if it lost none — a path missing
        from the split is indistinguishable from a path that was never run, and "if Path B
        never surfaces a winner Path A missed, collapse it" is a decision made on this table.
        """
        by_path = {candidate.discovery_path.value: 0 for candidate in self.candidates}
        for rejection in self.rejected:
            key = rejection.discovery_path.value
            by_path[key] = by_path.get(key, 0) + 1
        return by_path

    def _discovery_ran(self) -> dict[str, Any] | None:
        """What Stage 3 did, when it did something. `None` only where nothing is known.

        Success is evidenced by the candidates themselves, so the count and the per-path
        breakdown come from them rather than from a second record that could disagree — §8.2
        partitions on `discovery_path`, and a reader deciding whether the dual-path cost was
        justified needs that split, not a bare "ran".
        """
        if self.discovery is not None or not self.candidates:
            return None
        by_path: dict[str, int] = {}
        for candidate in self.candidates:
            key = candidate.discovery_path.value
            by_path[key] = by_path.get(key, 0) + 1
        return {
            "skipped": False,
            "stage": "discovery",
            "candidates": len(self.candidates),
            "by_path": dict(sorted(by_path.items())),
        }

    def _editorial_ran(self) -> dict[str, Any] | None:
        """Stage 4's verdict, when one was reached. `None` where nothing is known."""
        if self.editorial is not None or self.clip is None or self.clip.editorial is None:
            return None
        return {"skipped": False, "stage": "editorial", "judge": self.clip.editorial.judge}

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
            ("delivery", self.delivery),
        )
        return tuple((name, value) for name, value in ordered if isinstance(value, StageSkipped))

    @property
    def complete(self) -> bool:
        """True only when every §3 stage ran.

        Producing a clip is not the same as being the system §3 describes, and a runner that
        conflated them would report success for a pipeline missing its discovery and its judge.
        """
        # `None` means "this stage succeeded and has no separate result object" for the visual
        # index, discovery and editorial seams. It is also every dataclass field's construction
        # default, so "there are no StageSkipped values" alone lets an empty PipelineRun claim
        # success. Require the material evidence that a finished run necessarily leaves behind.
        return (
            not self.skipped()
            and isinstance(self.ingest, IngestResult)
            and isinstance(self.transcript, NormalizedTranscript)
            and isinstance(self.index, Bm25Index)
            and bool(self.visual_windows)
            and bool(self.candidates)
            and isinstance(self.boundary, Boundary)
            and isinstance(self.clip, Clip)
            and self.clip.editorial is not None
            and isinstance(self.render, RenderResult)
            and isinstance(self.delivery, Delivery)
        )

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
            "transcript_gaps": [
                {
                    "start_ms": gap.start_ms,
                    "end_ms": gap.end_ms,
                    "duration_ms": gap.end_ms - gap.start_ms,
                    "reason": gap.reason,
                }
                for gap in self.transcript_gaps
            ],
            "speech_without_transcription_ms": sum(
                gap.end_ms - gap.start_ms for gap in self.transcript_gaps
            ),
            "transcript": (
                self.transcript.to_dict()
                if isinstance(self.transcript, StageSkipped)
                else (
                    json.loads(self.transcript.to_json()) if self.transcript is not None else None
                )
            ),
            "index": (
                self.index.to_dict()
                if isinstance(self.index, StageSkipped)
                else (
                    {
                        "document_count": len(self.index.documents),
                        "ngram_size": self.index.ngram_size,
                        "ngram_weight": self.index.ngram_weight,
                    }
                    if self.index is not None
                    else None
                )
            ),
            "sentence_count": len(self.sentences),
            "visual_windows": [w.to_dict() for w in self.visual_windows],
            "visual_query_source": self.visual_query_source,
            "delivery": encode(self.delivery),
            "candidates": [c.to_dict() for c in self.candidates],
            # §5 makes rejection first-class and calls the rejection set "your only measure
            # of recall"; §8.2 measures Recall@20 *per discovery path*, so the split is here
            # rather than left for a reader to compute. Reported even when empty — an
            # absent key cannot be told apart from a build that does not record rejections,
            # which is the same reason D-145 reports zero gaps explicitly.
            "rejected": [r.to_dict() for r in self.rejected],
            "rejected_by_path": self._rejected_by_path(),
            "visual_index": encode(self.visual_index),
            # A stage that ran says so. `discovery` and `editorial` hold *only* a `StageSkipped`
            # or `None`, and `None` is how success was represented — so a reader checking
            # `report["discovery"]` got `null` whether Stage 3 produced candidates or was never
            # attempted, and had to cross-reference `candidates` to tell which. Measured on the
            # real 38-minute run: `discovery: null` alongside **7** merged candidates, with
            # "discovery" absent from `skipped` too. This module's §1 is fail visible, not
            # silent; a stage reporting nothing about itself is the silent case. D-146.
            "discovery": encode(self.discovery) or self._discovery_ran(),
            "editorial": encode(self.editorial) or self._editorial_ran(),
            "boundary": encode(self.boundary),
            "clip": self.clip.to_dict() if self.clip is not None else None,
            "render": (
                encode(self.render)
                if isinstance(self.render, StageSkipped)
                else (
                    {
                        "path": self.render.path,
                        "width": self.render.width,
                        "height": self.render.height,
                        # Both, because they are two facts and their agreement is the check.
                        "duration_ms": self.render.measured_duration_ms,
                        "requested_duration_ms": self.render.requested_duration_ms,
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
        "no Stage 1 producer was enabled. Supply --transcript or run the canonical "
        "omniASR_LLM_7B_v2 + omniASR_CTC_3B_v2 path with --omni-asr."
    ),
    blocked_by=("Stage 1 producer not enabled",),
)
_STAGE_2_VISUAL = StageSkipped(
    stage="visual_index",
    reason=(
        "local visual retrieval was not enabled. Use --visual to compose frame extraction, "
        "Qwen indexing, top-50 retrieval, reranking, a 5–10 survivor set and VideoChat3."
    ),
    blocked_by=("visual discovery not enabled",),
)
_STAGE_3_DISCOVERY = StageSkipped(
    stage="discovery",
    reason=(
        "no Stage 3 producer was enabled. Select --gemini or --vertex-project for Path A, "
        "--visual for composed Path B, or both for the two-sided union."
    ),
    blocked_by=("discovery producer not enabled",),
)
_STAGE_3_NOTHING_FOUND = StageSkipped(
    stage="discovery",
    reason=(
        "Every enabled discovery path ran and returned no candidates. That is a real answer "
        "about this media, not a model failure — but no clip can be cut from it."
    ),
    blocked_by=("no candidates",),
)
_STAGE_4_JUDGE = StageSkipped(
    stage="editorial",
    reason=(
        "no Stage 4 judge or persisted verdict was supplied. Use --gemini for non-confidential "
        "work, --vertex-project with governance confirmation for confidential work, or "
        "--verdict for an already-reviewed exact span. Note that §4 pins gemini-2.5-pro and it "
        "has a free-tier limit of exactly zero, so --gemini needs billing on the key's project "
        "— BLOCKED.md #3."
    ),
    blocked_by=("Stage 4 judgment not enabled",),
)


def _not_reached(stage: str, dependency: str) -> StageSkipped:
    return StageSkipped(
        stage=stage,
        reason=f"{stage} did not run because {dependency} was not available.",
        blocked_by=(dependency,),
    )


def _operational_failure(stage: str, component: str, exc: Exception) -> StageSkipped:
    """A known runtime/domain refusal, retaining its concrete cause in the run report."""
    detail = _safe_exception_text(str(exc), budget=1_024)
    reason = f"{component} failed with {type(exc).__name__}: {detail}"
    notes = _safe_exception_notes(exc)
    if notes:
        reason = f"{reason}; exception notes: {notes}"
    return StageSkipped(
        stage=stage,
        reason=reason,
        blocked_by=(component,),
    )


def _ingest_failure_run(
    identifier: str, source: Path, work_dir: Path, exc: IngestError | OSError
) -> PipelineRun:
    """Report an operational Stage 0 refusal without pretending later stages ran.

    Ingest is the root of the media clock, audio, VAD and shot-window graph. There is no
    meaningful partial object to synthesize when it fails, but there is a meaningful run
    report: Stage 0's concrete refusal followed by every dependent stage naming that root
    blocker. Returning it keeps ``--json`` machine-readable for the same operational failures
    that model stages already normalize, while source/argument/schema errors remain exceptions.
    """
    dependency = "Stage 0 ingest"
    return PipelineRun(
        media_id=identifier,
        source=str(source),
        work_dir=str(work_dir),
        ingest=_operational_failure("ingest", dependency, exc),
        transcript=_not_reached("transcript", dependency),
        index=_not_reached("index", dependency),
        visual_index=_not_reached("visual_index", dependency),
        discovery=_not_reached("discovery", dependency),
        editorial=_not_reached("editorial", dependency),
        boundary=_not_reached("boundary", dependency),
        render=_not_reached("render", dependency),
        delivery=_not_reached("delivery", dependency),
    )


def _safe_exception_text(value: str, budget: int) -> str:
    """A printable, single-line exception detail within a deterministic hard limit."""
    if budget <= 0:
        return ""
    kept: list[str] = []
    pending_space = False
    for character in value:
        if not character.isprintable() or character.isspace():
            pending_space = bool(kept)
            continue
        if pending_space:
            if len(kept) >= budget:
                kept[-1] = "…"
                return "".join(kept)
            kept.append(" ")
            pending_space = False
        if len(kept) >= budget:
            kept[-1] = "…"
            return "".join(kept)
        kept.append(character)
    return "".join(kept)


def _safe_exception_notes(exc: Exception, budget: int = 512, maximum: int = 4) -> str:
    """Printable, single-line exception notes within one deterministic total budget."""
    raw_notes = getattr(exc, "__notes__", ())
    if not isinstance(raw_notes, list | tuple) or budget <= 0 or maximum <= 0:
        return ""
    kept: list[str] = []
    remaining = budget
    for raw_note in raw_notes[:maximum]:
        if not isinstance(raw_note, str):
            continue
        separator = 3 if kept else 0
        available = remaining - separator
        if available <= 0:
            break
        normalized = _safe_exception_text(raw_note, available)
        if not normalized:
            continue
        kept.append(normalized)
        remaining -= separator + len(normalized)
        if remaining <= 0:
            break
    return " | ".join(kept)


@contextmanager
def _release_grounder_after_use(component: object) -> Iterator[None]:
    """Unload TimeLens without masking the inference failure that triggered cleanup."""
    closer = getattr(component, "close", None)
    try:
        yield
    except BaseException as primary:
        if callable(closer):
            try:
                closer()
            except BaseException as cleanup:
                primary.add_note(
                    "TimeLens cleanup failed: "
                    f"{type(cleanup).__name__}: {_safe_exception_text(str(cleanup), 384)}"
                )
        raise
    else:
        if callable(closer):
            try:
                closer()
            except (OSError, RuntimeError) as exc:
                raise GroundingError(
                    "TimeLens cleanup failed after inference: "
                    f"{type(exc).__name__}: {_safe_exception_text(str(exc), 384)}"
                ) from exc


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


def _candidate_priority(candidate: MergedCandidate) -> tuple[int, int, int, str]:
    """Order survivors without comparing unlike verbal and visual scores."""
    ranks = tuple(
        rank for rank in (candidate.verbal_rank, candidate.visual_rank) if rank is not None
    )
    best_rank = min(ranks) if ranks else sys.maxsize
    agreement = 0 if candidate.discovery_path is DiscoveryPath.BOTH else 1
    return best_rank, agreement, candidate.in_ms, candidate.candidate_id


def _candidate_for_judging(
    candidates: Sequence[MergedCandidate],
    selected_span: tuple[int, int] | None,
) -> MergedCandidate:
    """Choose the survivor being cut, or the best per-path-ranked survivor."""
    if not candidates:
        raise ValueError("cannot choose a candidate from an empty survivor list")
    if selected_span is None:
        return min(candidates, key=_candidate_priority)

    selected_in, selected_out = selected_span
    containing: list[MergedCandidate] = []
    for candidate in candidates:
        if candidate.in_ms <= selected_in and candidate.out_ms >= selected_out:
            containing.append(candidate)
    if not containing:
        raise ValueError(
            f"the selected sentence span {selected_in}..{selected_out} ms is not contained by "
            f"any of Stage 3's {len(candidates)} candidate(s). A partial overlap cannot carry "
            f"that candidate's score, path or visual evidence onto different footage."
        )
    return min(
        containing,
        key=lambda candidate: (
            candidate.out_ms - candidate.in_ms,
            *_candidate_priority(candidate),
        ),
    )


def _complete_sentences_within(
    candidate: MergedCandidate, sentences: Sequence[Sentence]
) -> list[int]:
    """Indices of the complete sentences lying wholly inside `candidate`.

    Shared by the selector and by the rejection record deliberately: the reason written into
    the artifact has to be the reason the code acted on, and two copies of this predicate could
    drift into a rejection that says "no complete sentence lies inside it" about a candidate the
    selector would have accepted.
    """
    return [
        index
        for index, sentence in enumerate(sentences)
        if sentence.complete
        and sentence.start_ms >= candidate.in_ms
        and sentence.end_ms <= candidate.out_ms
    ]


def _rejected_candidates(
    candidates: Sequence[MergedCandidate],
    chosen: MergedCandidate,
    sentences: Sequence[Sentence],
    selected_span: tuple[int, int] | None,
) -> tuple[RejectedCandidate, ...]:
    """§5: "Every rejected candidate keeps a `reject_reason` and its `discovery_path`."

    One producer, taken after the selection settles, so a candidate cannot be recorded twice
    under two decisions and counted twice in the recall it is the only measure of. The reasons
    are read off computations the runner already performed — the containment test
    `_candidate_for_judging` runs, and the eligibility `_automatic_sentence_selection` runs —
    never invented for the record.

    Nothing is recorded when nothing was chosen: a run that never reached a selection did not
    reject anything, and saying it did would put candidates in §8.2's rejection column that no
    decision ever ruled out.
    """
    rejected: list[RejectedCandidate] = []
    for candidate in candidates:
        if candidate.candidate_id == chosen.candidate_id:
            continue
        if sentences and not _complete_sentences_within(candidate, sentences):
            reason = (
                "no complete sentence lies wholly inside this candidate, so it cannot anchor "
                "a clip (Kurdish invariant #2)"
            )
        elif selected_span is not None and not (
            candidate.in_ms <= selected_span[0] and candidate.out_ms >= selected_span[1]
        ):
            reason = (
                f"does not contain the selected span {selected_span[0]}..{selected_span[1]} ms; "
                f"a partial overlap cannot carry this candidate's score or path onto different "
                f"footage"
            )
        else:
            reason = f"out-ranked by survivor {chosen.candidate_id}"
        rejected.append(
            RejectedCandidate(
                media_id=candidate.media_id,
                in_ms=candidate.in_ms,
                out_ms=candidate.out_ms,
                discovery_path=candidate.discovery_path,
                reject_reason=reason,
            )
        )
    return tuple(rejected)


def _automatic_sentence_selection(
    candidates: Sequence[MergedCandidate], sentences: Sequence[Sentence]
) -> tuple[int, ...]:
    """Choose complete contiguous sentence anchors wholly contained by the best survivor."""
    for candidate in sorted(candidates, key=_candidate_priority):
        eligible = _complete_sentences_within(candidate, sentences)
        if not eligible:
            continue
        runs: list[list[int]] = [[eligible[0]]]
        for index in eligible[1:]:
            if index == runs[-1][-1] + 1:
                runs[-1].append(index)
            else:
                runs.append([index])
        best = max(
            runs,
            key=lambda run: (
                sentences[run[-1]].end_ms - sentences[run[0]].start_ms,
                -run[0],
            ),
        )
        return tuple(best)
    return ()


def _prepare_selection(
    transcript: RawTranscript,
    sentences: Sequence[Sentence],
    selection: tuple[int, ...],
) -> tuple[tuple[int, ...], tuple[Sentence, ...], tuple[int, int] | None]:
    if not selection:
        return (), (), None
    _assert_render_alignment_complete(transcript)
    out_of_range = [i for i in selection if not 0 <= i < len(sentences)]
    if out_of_range:
        raise IndexError(
            f"sentence index {out_of_range} is outside 0..{len(sentences) - 1}. The "
            f"transcript segmented into {len(sentences)} sentence(s)."
        )
    assert_contiguous(selection, total=len(sentences))
    assert_time_contiguous(sentences, selection)
    ordered = tuple(sorted(selection))
    selected = tuple(sentences[i] for i in ordered)
    anchors = anchors_for(selected) if all(sentence.complete for sentence in selected) else None
    return ordered, selected, anchors


def _assert_render_alignment_complete(transcript: RawTranscript) -> None:
    """Rendering requires every raw token to have the exact aligned surface it captions."""
    raw_tokens = tuple(transcript.text_ckb.split())
    aligned_tokens = tuple(word.w for word in transcript.words)
    if raw_tokens != aligned_tokens:
        raise ValueError(
            "the supplied transcript is only partially or approximately aligned: rendering "
            "would rebuild raw_ckb and captions from Word.w and omit or alter ASR text. A "
            "renderable transcript requires exact token-for-token aligned surfaces."
        )


def _raw_text_for_words(transcript: RawTranscript, words: Sequence[Word]) -> str:
    """The exact canonical substring covered by `words`, including original whitespace."""
    if not words:
        raise ValueError("cannot extract raw text for an empty word selection")
    offsets: list[tuple[int, int]] = []
    cursor = 0
    for word in transcript.words:
        start = transcript.text_ckb.find(word.w, cursor)
        if start < 0:  # guarded by _assert_render_alignment_complete; defence in depth
            raise ValueError(f"aligned surface {word.w!r} is absent from canonical raw text")
        end = start + len(word.w)
        offsets.append((start, end))
        cursor = end
    first = next(i for i, word in enumerate(transcript.words) if word is words[0])
    last = next(i for i, word in reversed(tuple(enumerate(transcript.words))) if word is words[-1])
    return transcript.text_ckb[offsets[first][0] : offsets[last][1]]


def _candidate_slice_text(transcript: NormalizedTranscript, in_ms: int, out_ms: int) -> str:
    """Normalized aligned words inside a candidate, never the whole episode."""
    words = [w.w for w in transcript.words if w.start_ms < out_ms and w.end_ms > in_ms]
    return normalize_sorani(" ".join(words))


def _visual_retrieval_query(
    transcript: NormalizedTranscript,
    verbal: Sequence[Candidate],
    explicit: str | None,
) -> tuple[str, str] | None:
    """Return one bounded, provenance-bearing Path B query or refuse to invent one.

    An explicit operator query is authority to use exactly that normalized text. Otherwise the
    top Path A survivor scopes retrieval to the words aligned inside its own time span. The whole
    transcript is intentionally not a fallback: on the measured 38-minute episode its 35,185
    characters made the reranker request 40.89 GiB on a 23.99 GiB GPU before Stage 3 could run.
    """
    if explicit is not None:
        query = normalize_sorani(explicit)
        if not query.strip():
            raise ValueError("visual query must contain non-whitespace Sorani retrieval text")
        return query, "explicit"

    best = min(verbal, key=lambda item: (item.rank, item.candidate_id), default=None)
    if best is None:
        return None
    query = _candidate_slice_text(transcript, best.in_ms, best.out_ms)
    if not query.strip():
        return None
    return query, f"path_a:{best.candidate_id}"


def _candidate_work_component(candidate_id: str) -> str:
    """Stage 4 directory name derived from one safe candidate-id component.

    Scene-window IDs use colons as logical separators. They are valid candidate IDs but not
    portable filename characters, so only those separators are translated; every path-forming
    character and parent reference remains visible to the shared strict validator and is
    refused before keyframe extraction can touch the filesystem.
    """
    if not isinstance(candidate_id, str):
        raise ValueError(f"candidate_id must be a string, got {type(candidate_id).__name__}")
    component = candidate_id.replace(":", "_")
    try:
        return validate_media_id(component)
    except ValueError as exc:
        raise ValueError(
            f"candidate_id {candidate_id!r} is not a safe Stage 4 work component: {exc}"
        ) from exc


def _assert_verdict_matches_request(verdict: JudgeVerdict, request: JudgeRequest) -> None:
    """Refuse a judge adapter that returns a verdict for different footage."""
    if verdict.candidate_id != request.candidate_id:
        raise ValueError(
            f"judge returned candidate {verdict.candidate_id!r} for request "
            f"{request.candidate_id!r}; the verdict belongs to different footage"
        )
    if (verdict.clip_in_ms, verdict.clip_out_ms) != (
        request.clip_in_ms,
        request.clip_out_ms,
    ):
        raise ValueError(
            f"judge returned span {verdict.clip_in_ms}..{verdict.clip_out_ms} ms for request "
            f"{request.clip_in_ms}..{request.clip_out_ms} ms"
        )


def _vad_onset_for_anchor(
    ingested: IngestResult, anchor_in_ms: int, anchor_out_ms: int
) -> int | None:
    """The onset of speech containing the first anchor, never the episode's first speech."""
    containing = [
        segment for segment in ingested.speech if segment.start_ms <= anchor_in_ms < segment.end_ms
    ]
    if containing:
        return max(containing, key=lambda segment: segment.start_ms).start_ms
    overlapping = [
        segment
        for segment in ingested.speech
        if segment.start_ms < anchor_out_ms and segment.end_ms > anchor_in_ms
    ]
    return min(overlapping, key=lambda segment: segment.start_ms).start_ms if overlapping else None


def _clip_id(identifier: str, select_sentences: Sequence[int]) -> str:
    """The clip's id, derived in exactly one place.

    Both the overwrite guard and the files the run actually writes read it from here. A guard
    that computes a path a second way is a guard that can pass while the write collides.
    """
    return f"{identifier}-s{select_sentences[0]}-{select_sentences[-1]}"


def _delivery_artifact_paths(work_dir: Path, clip_id: str) -> tuple[Path, ...]:
    """The five files in the atomically published directory for one delivered clip."""
    return ArtifactBundle.final_paths_for(work_dir, clip_id)


def _legacy_delivery_artifact_paths(work_dir: Path, clip_id: str) -> tuple[Path, ...]:
    """Flat paths written before atomic bundle directories existed; never overwrite them."""
    return tuple(
        work_dir / f"{clip_id}.{suffix}" for suffix in ("ass", "mp4", "srt", "edl", "json")
    )


def _assert_no_existing_artifacts(
    work_dir: Path, identifier: str, select_sentences: Sequence[int]
) -> None:
    """Refuse an overwriting run *before* it spends GPU time or money.

    This check used to live beside the render step, ~180 lines after the billed Stage 4
    `generateContent` and after Stage 2/3's model calls — so a re-run into a used work
    directory paid Gemini, held both Qwen checkpoints and VideoChat3 on the GPU, and only then
    refused with nothing to show. The condition was knowable the whole time: it depends on
    `work_dir`, the media id and the sentence selection, and nothing else. D-071.

    Called at each point where the selection first becomes knowable — after an explicit
    selection is validated, and again after `--auto-select` settles one — because those are
    genuinely different times, not two copies of the rule.
    """
    if not select_sentences:
        # No selection, no clip, no artifacts. `run_pipeline` returns before the render step.
        return
    clip_id = _clip_id(identifier, select_sentences)
    final_paths = _delivery_artifact_paths(work_dir, clip_id)
    final_dir = final_paths[0].parent
    candidates = (final_dir, *_legacy_delivery_artifact_paths(work_dir, clip_id))
    existing = [path for path in candidates if os.path.lexists(path)]
    if existing:
        raise FileExistsError(
            "refusing to overwrite existing delivery artifact(s): "
            + ", ".join(str(path) for path in existing)
            + ". Use a new work directory for a new run."
        )


def _natural_silence_for_anchor(ingested: IngestResult, anchor_out_ms: int) -> int | None:
    """Where speech actually stops after the last selected word — §3 Stage 5's natural silence.

    The mirror of `_vad_onset_for_anchor`: that reads the *start* of the VAD region holding the
    first anchor, this reads the *end* of the region holding the last one. That the two are
    measured on different clocks is the whole point — `anchor_out` is a transcript time (a word's
    end, from §4.2's Viterbi alignment) while VAD measured when sound stopped, independently and
    from the audio itself. When the
    audible tail runs past the last word, §3 says the clip may end on the silence rather than
    mid-breath.

    `None` when `anchor_out` is not inside a speech region: the clip already ends in silence, so
    there is nothing to extend to. Deliberately **not** the next speech onset — that is the far
    side of the pause, and reaching across a whole silence to butt against the next speaker is
    the opposite of a natural stop. No threshold is invented here; every value returned is a
    measured region edge, which is also why it cannot run into the following region.
    """
    containing = [
        segment for segment in ingested.speech if segment.start_ms <= anchor_out_ms < segment.end_ms
    ]
    return max(segment.end_ms for segment in containing) if containing else None


def run_pipeline(
    source: Path,
    work_dir: Path,
    media_id: str | None = None,
    transcript: RawTranscript | None = None,
    asr: CanonicalTranscriptProducer | None = None,
    select_sentences: tuple[int, ...] = (),
    qc: Qc | None = None,
    verdict: JudgeVerdict | None = None,
    discover: Callable[[NormalizedTranscript], Sequence[Candidate]] | None = None,
    read_scenes: VideoUnderstanding | None = None,
    visual_composer: VisualComposer | None = None,
    visual_query: str | None = None,
    judge: EditorialJudge | None = None,
    temporal_grounder: TemporalGrounder | None = None,
    subject_tracker: SubjectTracker | None = None,
    auto_select: bool = False,
    visual_fps: float | None = None,
    visual_max_frames: int = MAX_FRAMES_PER_WINDOW,
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
            stops standing in for discovery and actually runs it.
        read_scenes: retired unsafe injection seam. Any non-``None`` value is refused because a
            bare reader has no retrieval/rerank provenance and can promote every scene. Use
            ``visual_composer`` so only bounded, scored survivors reach VideoChat3.
        visual_max_frames: the most frames any planned window may hold. Defaults to §3's
            ceiling and may only be lowered — the Path B reader's memory is the binding
            constraint on real hardware (D-138, D-143, `BLOCKED.md` #17).
        visual_fps: one sampling rate for every planned visual window. Omitted uses the
            blueprint's 1 fps planning reference, or the checkpoints' declared 2 fps ceiling
            when the composed model path is enabled.
        visual_query: an explicit Sorani Path B retrieval query. When omitted, the top Path A
            survivor's aligned transcript slice is used. If neither exists, Path B is reported
            skipped rather than silently sending the whole episode transcript to the GPU.
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
    if read_scenes is not None:
        raise ValueError(
            "unranked read_scenes injection is not a valid Path B producer; use VisualComposer "
            "so Qwen retrieval/reranking bounds the scenes sent to VideoChat3"
        )

    identifier = validate_media_id(media_id or source.stem)
    if transcript is not None and transcript.media_id != identifier:
        raise ValueError(
            f"transcript media_id {transcript.media_id!r} is not {identifier!r}. A transcript "
            f"of another episode would render a clip whose captions are fiction."
        )

    work_dir.mkdir(parents=True, exist_ok=True)

    # --- §3 Stage 0 ----------------------------------------------------------------------
    try:
        ingested = ingest(source, work_dir / "stage0", media_id=identifier, ffmpeg=ffmpeg)
    except (IngestError, OSError) as exc:
        return _ingest_failure_run(identifier, source, work_dir, exc)

    asr_failure: StageSkipped | None = None
    if transcript is None and asr is not None:
        try:
            transcript = asr.transcribe(
                identifier,
                Path(ingested.audio_path),
                ingested.speech,
                work_dir / "stage1",
                ffmpeg,
            )
        except RuntimeError as exc:
            asr_failure = _operational_failure("transcript", "canonical ASR runtime", exc)
        if transcript is not None and transcript.media_id != identifier:
            raise ValueError(
                f"canonical ASR returned media_id {transcript.media_id!r} for {identifier!r}"
            )

    # --- §3 Stage 2 (visual half, the part that needs no weights) --------------------------
    # "one embedding per scene … ~1 fps with a maximum of 64 frames, so segment before
    # embedding". The segmenting is arithmetic over the cuts Stage 0 just found on this video,
    # so it runs now and is real; only the embedding itself waits on the model.
    effective_visual_fps = (
        visual_fps
        if visual_fps is not None
        else (DECLARED_SAMPLING_FPS if visual_composer is not None else REFERENCE_FPS)
    )
    windows = plan_scene_windows(
        identifier,
        ingested.duration_ms,
        ingested.shot_cuts_ms,
        fps=effective_visual_fps,
        max_frames=visual_max_frames,
    )

    run = PipelineRun(
        media_id=identifier,
        source=str(source),
        work_dir=str(work_dir),
        ingest=ingested,
        transcript=_STAGE_1_ASR,
        index=_not_reached("index", "a transcript"),
        visual_windows=windows,
        visual_index=_STAGE_2_VISUAL,
        discovery=_STAGE_3_DISCOVERY,
        editorial=None if verdict is not None else _STAGE_4_JUDGE,
        boundary=_not_reached("boundary", "complete selected sentences"),
        render=_not_reached("render", "a judged boundary and QC pass"),
        delivery=_not_reached("delivery", "a successful render"),
    )
    if asr_failure is not None:
        return replace(run, transcript=asr_failure)
    if transcript is None:
        return run

    # --- §3 Stage 1 (supplied) + §4.1 -----------------------------------------------------
    store = TranscriptStore(work_dir / "transcripts")
    try:
        store.write_raw(transcript)
    except RawTranscriptImmutable:
        # Invariant #1: the canonical transcript is never rewritten. A second run over the
        # same work directory reads what is already there rather than overwriting it.
        stored = store.read_raw(identifier)
        if stored != transcript:
            raise RawTranscriptImmutable(
                f"{store.raw_path(identifier)} already contains a different canonical "
                "transcript. Reusing it would silently ignore the newly supplied words; use "
                "a new work directory or media_id."
            ) from None
        transcript = stored
    store.verify_raw_integrity(identifier)
    run = replace(run, transcript_gaps=transcript.unaligned)
    normalized = normalize_transcript(transcript)
    store.write_norm(normalized)

    # --- §4.2 sentence segmentation, against this run's own VAD ---------------------------
    vad_pauses = _pauses_between(ingested)
    sentences = segment_sentences(transcript.words, vad_pauses=vad_pauses)

    # --- §3 Stage 2 (text half) -----------------------------------------------------------
    # BM25 ranks passages, not a one-document episode. On the measured 38-minute transcript,
    # the old shape returned one 38.6-minute hit for every query; sentence documents produce
    # bounded windows and term rarity across 186 documents (D-164).
    index = Bm25Index.from_sentences(sentences, normalized)

    run = replace(run, transcript=normalized, index=index, sentences=sentences)

    select_sentences, selected, selected_anchors = _prepare_selection(
        transcript, sentences, select_sentences
    )
    # Before Stage 2/3 touch the GPU and before Stage 4 is billed. Deliberately after
    # `_prepare_selection`, so a selection naming a sentence that does not exist is still
    # reported as that error rather than as a collision.
    _assert_no_existing_artifacts(work_dir, identifier, select_sentences)

    # --- §3 Stage 3, both paths -------------------------------------------------------------
    merged: tuple[MergedCandidate, ...] = ()
    visual_result: VisualDiscoveryResult | None = None
    visual_skipped: StageSkipped | None = None
    visual_query_source: str | None = None
    discovery_skipped: StageSkipped | None = None
    if discover is not None or visual_composer is not None:
        verbal: tuple[Candidate, ...] = ()
        if discover is not None:
            try:
                verbal = tuple(discover(normalized))
            except (GeminiUnavailable, JudgeUnusable, NotRoutable, RequestTooLarge) as exc:
                discovery_skipped = _operational_failure(
                    "discovery", "Path A discovery runtime", exc
                )
        # Path B usually has no composed producer here, and §3 is explicit that
        # a one-sided union is correct rather than degraded: candidates from *either* path
        # proceed, and a verbal-only moment is the case the dual path exists to protect. When
        # a composer *is* supplied it retrieves and reranks before reading any scene.
        visual_candidates_tuple: tuple[Candidate, ...] = ()
        if visual_composer is not None:
            query_with_source = _visual_retrieval_query(normalized, verbal, visual_query)
            if query_with_source is None:
                visual_skipped = StageSkipped(
                    stage="visual_index",
                    reason=(
                        "Path B requires --visual-query or a Path A candidate whose aligned "
                        "transcript slice can scope retrieval; refusing the whole episode "
                        "transcript because the measured fallback exhausted GPU memory"
                    ),
                    blocked_by=("a retrieval query",),
                )
            else:
                query, visual_query_source = query_with_source
                try:
                    visual_result = visual_composer.discover(
                        source,
                        run.visual_windows,
                        query,
                        work_dir / "visual",
                        media_id=identifier,
                        ffmpeg=ffmpeg,
                    )
                except VisualPipelineError as exc:
                    visual_skipped = StageSkipped(
                        stage="visual_index",
                        reason=_safe_exception_text(str(exc), budget=1_024),
                        blocked_by=("visual retrieval refused this media",),
                    )
                else:
                    visual_candidates_tuple = visual_result.candidates
        merged = merge_candidates(list(verbal), list(visual_candidates_tuple))
        run = replace(
            run,
            discovery=discovery_skipped or (None if merged else _STAGE_3_NOTHING_FOUND),
            candidates=merged,
            visual_index=visual_result or visual_skipped or _STAGE_2_VISUAL,
            visual_query_source=visual_query_source,
        )

    if auto_select and not select_sentences and merged:
        automatic = _automatic_sentence_selection(merged, sentences)
        select_sentences, selected, selected_anchors = _prepare_selection(
            transcript, sentences, automatic
        )
        if not select_sentences:
            # The survivor exists, but none of it can become a sentence-complete clip. Stop
            # before extracting source pixels or making the billed Stage 4 call: a verdict for
            # footage the automatic path already knows it cannot cut has no downstream use.
            return replace(
                run,
                editorial=StageSkipped(
                    stage="editorial",
                    reason=(
                        "automatic selection found no complete contiguous sentence inside any "
                        "Stage 3 survivor, so Stage 4 was not called"
                    ),
                    blocked_by=("complete sentence anchors",),
                ),
                boundary=StageSkipped(
                    stage="boundary",
                    reason=(
                        "automatic selection found no complete contiguous sentence inside any "
                        "Stage 3 survivor"
                    ),
                    blocked_by=("complete sentence anchors",),
                ),
            )
        # `--auto-select` only knows which sentences it wants once Stage 3 has ranked
        # candidates, so this is the first moment the artifact names exist in that mode. Still
        # ahead of the billed Stage 4 call below.
        _assert_no_existing_artifacts(work_dir, identifier, select_sentences)

    # The survivor is chosen once, here, rather than again inside Stage 4. §5 makes rejection a
    # first-class outcome — "that set is your only measure of recall" — and a candidate ruled out
    # by two decisions would otherwise be recorded twice and counted twice. Choosing in one place
    # also means the record exists on a run whose Stage 4 is blocked, which is every run on this
    # machine until `BLOCKED.md` #3 clears.
    selected_candidate: MergedCandidate | None = None
    if merged and selected_anchors is not None:
        selected_candidate = _candidate_for_judging(merged, selected_anchors)
    elif merged and judge is not None and not selected:
        selected_candidate = _candidate_for_judging(merged, None)
    if selected_candidate is not None:
        run = replace(
            run,
            rejected=_rejected_candidates(merged, selected_candidate, sentences, selected_anchors),
        )

    # --- §3 Stage 4 -----------------------------------------------------------------------
    if judge is not None and merged and (not selected or selected_anchors is not None):
        assert selected_candidate is not None, "Stage 4's condition implies a chosen survivor"
        survivor = selected_candidate
        request_candidate = (
            replace(survivor, in_ms=selected_anchors[0], out_ms=selected_anchors[1])
            if selected_anchors is not None
            else survivor
        )
        candidate_work_component = _candidate_work_component(request_candidate.candidate_id)
        try:
            judge_frames = (
                extract_judge_frames(
                    source,
                    request_candidate.in_ms,
                    request_candidate.out_ms,
                    work_dir / "stage4" / candidate_work_component,
                    ffmpeg=ffmpeg,
                )
                if getattr(judge, "requires_keyframes", False)
                else ()
            )
        except KeyframeError as exc:
            return replace(
                run,
                editorial=_operational_failure("editorial", "Stage 4 keyframe extraction", exc),
            )
        request = JudgeRequest.for_survivor(
            request_candidate,
            text_ckb=_candidate_slice_text(
                normalized, request_candidate.in_ms, request_candidate.out_ms
            ),
            keyframes=judge_frames,
        )
        try:
            judged = judge.judge(request)
        except (GeminiUnavailable, JudgeUnusable, NotRoutable, RequestTooLarge) as exc:
            return replace(
                run,
                editorial=_operational_failure("editorial", "Stage 4 judge runtime", exc),
            )
        _assert_verdict_matches_request(judged, request)
        if judged.sv6d is None and survivor.sv6d is not None:
            judged = replace(judged, sv6d=survivor.sv6d)
        verdict = judged
        run = replace(run, editorial=None)

    if not select_sentences:
        return run

    try:
        editorial = verdict.to_editorial() if verdict is not None else None
    except NotRoutable as exc:
        return replace(
            run,
            editorial=_operational_failure("editorial", "Stage 4 verdict routing", exc),
        )

    # --- §3 Stage 5 boundary fusion -------------------------------------------------------
    anchors = selected_anchors
    if anchors is None:
        return replace(
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
    if (
        verdict is not None
        and judge is None
        and (
            verdict.clip_in_ms,
            verdict.clip_out_ms,
        )
        != (anchor_in, anchor_out)
    ):
        raise ValueError(
            f"supplied verdict scores {verdict.clip_in_ms}..{verdict.clip_out_ms} ms but the "
            f"selected sentence anchors are exactly {anchor_in}..{anchor_out} ms. Persisted "
            f"and live verdicts must identify the same footage."
        )
    timelens_interval = None
    if temporal_grounder is not None:
        temporal_span = selected_candidate.span if selected_candidate is not None else anchors
        grounding_windows = tuple(
            window
            for window in run.visual_windows
            if window.in_ms < temporal_span[1] and window.out_ms > temporal_span[0]
        )
        if not grounding_windows:
            raise ValueError(
                f"no visual window overlaps the Stage 5 span {temporal_span[0]}.."
                f"{temporal_span[1]} ms"
            )
        try:
            with _release_grounder_after_use(temporal_grounder):
                timelens_intervals = temporal_grounder.ground_all(
                    grounding_windows,
                    _candidate_slice_text(normalized, anchor_in, anchor_out),
                )
        except (GroundingError, EmbedderUnavailable, VideoInputError) as exc:
            return replace(
                run,
                boundary=_operational_failure("boundary", "TimeLens temporal grounding", exc),
            )
        timelens_interval = interval_for_fusion(
            timelens_intervals, anchor_in, anchor_out, identifier
        )

    boundary = fuse_boundary(
        BoundaryInputs(
            anchor_in_ms=anchor_in,
            anchor_out_ms=anchor_out,
            sentence_complete=True,
            # The join this runner exists to make: the shot cuts and speech regions below were
            # measured on *this* video by Stage 0 a few lines above, not supplied as fixtures.
            shot_cuts_ms=ingested.shot_cuts_ms,
            vad_onset_ms=_vad_onset_for_anchor(ingested, anchor_in, anchor_out),
            # §3 Stage 5 takes the latest of five out-point signals. This runner computed the
            # VAD silences a few hundred lines above (`_pauses_between`), spent them on §4.2's
            # sentence segmentation and then never handed Stage 5 its own — so `fuse_boundary`
            # had a `natural_silence` branch no caller could reach, and the fused out point was
            # three of the five. Four now; the fifth is `speaker_turn_end`, which needs the
            # gated diarization model (`BLOCKED.md` #4) and is absent for a stated reason
            # rather than by omission. D-070.
            natural_silence_ms=_natural_silence_for_anchor(ingested, anchor_out),
            timelens_interval_start_ms=(
                timelens_interval.start_ms if timelens_interval is not None else None
            ),
            timelens_interval_end_ms=(
                timelens_interval.end_ms if timelens_interval is not None else None
            ),
            # Stage 0 probed this file's length, so Stage 5 can be told where it stops. Without
            # it the 200 ms tail alone runs past the end of a short source — which is what this
            # runner had been doing, shipping a clip 138 ms shorter than the boundary it
            # recorded, until `render_clip` started measuring the artifact.
            media_duration_ms=ingested.duration_ms,
        )
    )

    selected_words = {word for sentence in selected for word in sentence.words}
    uncaptioned = [
        word
        for sentence in sentences
        for word in sentence.words
        if word not in selected_words
        and word.start_ms < boundary.final_out_ms
        and word.end_ms > boundary.final_in_ms
    ]
    if uncaptioned:
        first = uncaptioned[0]
        return replace(
            run,
            boundary=StageSkipped(
                stage="boundary",
                reason=(
                    f"soft boundary expansion {boundary.final_in_ms}..{boundary.final_out_ms} ms "
                    f"would include unselected speech beginning with {first.w!r} at "
                    f"{first.start_ms}..{first.end_ms} ms. Rendering it would ship speech "
                    "missing from the captions and clip transcript."
                ),
                blocked_by=("uncaptioned speech",),
            ),
        )

    clip_words = tuple(word for sentence in selected for word in sentence.words)
    raw_clip_text = _raw_text_for_words(transcript, clip_words)
    try:
        focus_points = (
            subject_tracker.track(source, boundary.final_in_ms, boundary.final_out_ms)
            if subject_tracker is not None
            else ()
        )
    except RuntimeError as exc:
        return replace(
            run,
            boundary=boundary,
            render=_operational_failure("render", "requested subject tracking", exc),
        )
    clip = Clip(
        clip_id=_clip_id(identifier, select_sentences),
        media_id=identifier,
        in_ms=boundary.final_in_ms,
        out_ms=boundary.final_out_ms,
        # §3 Stage 3 discovers candidates and did not run. VERBAL records where this clip
        # *came from* — a human reading the transcript — and no clip here may claim BOTH.
        discovery_path=(
            selected_candidate.discovery_path
            if selected_candidate is not None
            else DiscoveryPath.VERBAL
        ),
        boundary=boundary,
        transcript=ClipTranscript(
            raw_ckb=raw_clip_text,
            norm_ckb=normalize_sorani(raw_clip_text),
            en_aux=None,
            words=clip_words,
            asr=transcript.asr,
        ),
        editorial=editorial,
        output=(
            verdict.to_output(
                crop_target="face_tracked" if focus_points else "static_centre",
                durations=(max(1, round((boundary.final_out_ms - boundary.final_in_ms) / 1000)),),
            )
            if verdict is not None
            else None
        ),
        qc=qc,
    )
    run = replace(run, boundary=boundary, clip=clip)

    # --- §3 Stage 6 render ----------------------------------------------------------------
    if verdict is None:
        # Not a shortcut around the gate — the gate's own conclusion, reached before spending
        # an encode on a clip that `assert_renderable` would refuse anyway.
        return replace(
            run,
            render=StageSkipped(
                stage="render",
                reason=(
                    "§3 Stage 4 did not run, so the clip has no editorial block and §2's "
                    "render gate refuses it: an unjudged clip has no meaning fidelity and no "
                    "misleading-edit risk. Supply a verdict to render."
                ),
                blocked_by=("Stage 4 verdict",),
            ),
        )

    _, final_render, final_srt, final_edl, final_json = _delivery_artifact_paths(
        work_dir, clip.clip_id
    )
    # Kept as well as hoisted, and it costs nothing: the guard above runs before the expensive
    # stages, this one runs immediately before the first write. Anything that appeared in the
    # work directory while the models were running is still caught here.
    _assert_no_existing_artifacts(work_dir, identifier, select_sentences)
    try:
        clip.assert_renderable()
    except (ValueError, IncompleteSentence) as exc:
        return replace(
            run,
            render=StageSkipped(
                stage="render",
                reason=_safe_exception_text(str(exc), budget=1_024),
                blocked_by=("§2 QC/editorial gate",),
            ),
        )

    try:
        bundle = ArtifactBundle.create(work_dir, clip.clip_id)
    except BundleError as exc:
        return replace(
            run,
            render=StageSkipped(
                stage="render",
                reason=_safe_exception_text(str(exc), budget=1_024),
                blocked_by=("§2 atomic delivery bundle",),
            ),
            delivery=StageSkipped(
                stage="delivery",
                reason=_safe_exception_text(str(exc), budget=1_024),
                blocked_by=("§2 atomic delivery bundle",),
            ),
        )
    ass_path = bundle.staged_path("ass")
    render_path = bundle.staged_path("mp4")

    try:
        bundle.write_text(
            "ass",
            # The clip's own timeline. Without this every caption is scheduled at its source
            # time, lands past the end of a clip cut from mid-episode, and libass draws
            # nothing — a playable MP4 with no captions and no error.
            build_ass(
                selected,
                style=CaptionStyle.WORD_HIGHLIGHT,
                clip_in_ms=clip.in_ms,
                clip_duration_ms=clip.out_ms - clip.in_ms,
            ),
        )
        width, height = _proxy_dimensions(source, ffmpeg)
        rendered = render_clip(
            clip,
            source,
            ass_path,
            FONTS_DIR,
            render_path,
            source_width=width,
            source_height=height,
            focus_points=tuple((point.at_ms, point.center_x) for point in focus_points),
            ffmpeg=ffmpeg,
        )
    except (IngestError, RenderError, BundleError, OSError, ValueError) as exc:
        try:
            bundle.discard()
        except BundleError as cleanup_error:
            exc = RenderError(
                "private bundle cleanup also failed: "
                f"{_safe_exception_text(str(cleanup_error), budget=512)}; original failure: "
                f"{_safe_exception_text(str(exc), budget=512)}"
            )
        return replace(
            run,
            render=StageSkipped(
                stage="render",
                reason=_safe_exception_text(str(exc), budget=1_024),
                blocked_by=("Stage 6 render runtime",),
            ),
        )

    # --- §2's delivery set: MP4 · SRT/ASS · editing JSON · EDL -----------------------------
    # Nothing is public yet: the render and all sidecars live in one private sibling directory.
    try:
        # Build all three before writing any. This used to write the JSON, then the SRT, then
        # build the EDL — formerly an NTSC 29.97 fps source legitimately refused because
        # drop-frame support did not exist. The build-first ordering remains load-bearing for
        # unsupported fractional rates and any future sidecar validation failure: no partial
        # delivery set is briefly exposed before cleanup. D-072.
        editing_json = json.dumps(clip.to_dict(), ensure_ascii=False, indent=2)
        srt = build_srt(selected, clip_in_ms=clip.in_ms, clip_duration_ms=clip.out_ms - clip.in_ms)
        # The EDL's source timecodes are the *source's* timeline — where this clip was cut
        # from — so it takes the source's own frame rate. NTSC 30000/1001 selects SMPTE
        # drop-frame numbering; unsupported rates land here instead of silently drifting.
        edl = build_edl(
            clip_in_ms=clip.in_ms,
            clip_out_ms=clip.out_ms,
            fps=frame_rate(source, ffmpeg),
            title=f"{identifier} {clip.clip_id}",
        )
        bundle.write_text("json", editing_json)
        bundle.write_text("srt", srt)
        bundle.write_text("edl", edl)
        bundle.publish()
    except (DeliveryError, RenderError, BundleError, OSError) as exc:
        try:
            bundle.discard()
        except BundleError as cleanup_error:
            exc = DeliveryError(
                "private bundle cleanup also failed: "
                f"{_safe_exception_text(str(cleanup_error), budget=512)}; original failure: "
                f"{_safe_exception_text(str(exc), budget=512)}"
            )
        return replace(
            run,
            render=StageSkipped(
                stage="render",
                reason=(
                    "render completed privately but was not published: "
                    f"{_safe_exception_text(str(exc), budget=1_024)}"
                ),
                blocked_by=("§2 atomic delivery bundle",),
            ),
            delivery=StageSkipped(
                stage="delivery",
                reason=_safe_exception_text(str(exc), budget=1_024),
                blocked_by=("§2 delivery set",),
            ),
        )

    rendered = replace(rendered, path=str(final_render))
    return replace(
        run,
        render=rendered,
        delivery=Delivery(
            srt_path=str(final_srt),
            edl_path=str(final_edl),
            editing_json_path=str(final_json),
        ),
    )


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
    output = probe_stream(source, "stream=width,height", ffmpeg, video_only=True)
    try:
        width, height = (int(value) for value in output.split("x")[:2])
    except ValueError as exc:
        raise IngestError(f"could not read frame dimensions from {source}: {output!r}") from exc
    return width, height


def visible_cuda_devices() -> int:
    """How many CUDA devices this machine actually has. Separate so tests can replace it."""
    try:
        import torch
    except ImportError:  # pragma: no cover - the gpu extra is optional
        return 0
    count: int = torch.cuda.device_count()
    return count


def assert_devices_available(assignments: Mapping[str, str]) -> None:
    """Refuse a CUDA device this machine does not have, naming what §6 puts there.

    §6 assigns the video phase across two GPUs — `GPU 0 → VideoChat3-4B`, `GPU 1 → Embedding /
    Reranker / TimeLens2` — so the defaults below are two-GPU defaults. On a machine with fewer,
    a stage would otherwise die inside torch with a device-ordinal error that names neither the
    stage nor the remedy. Refusing here says both. D-137.
    """
    requested = {
        role: device
        for role, device in assignments.items()
        if device.startswith("cuda:") and device.split(":", 1)[1].isdigit()
    }
    if not requested:
        return
    available = visible_cuda_devices()
    missing = {
        role: device for role, device in requested.items() if int(device.split(":")[1]) >= available
    }
    if missing:
        named = "; ".join(f"{role} on {device}" for role, device in sorted(missing.items()))
        raise SystemExit(
            f"✗ this machine reports {available} CUDA device(s), and the run asks for {named}. "
            f"§6 assigns the video phase across two GPUs (GPU 0 → VideoChat3-4B, GPU 1 → "
            f"Embedding / Reranker / TimeLens2), so the defaults assume hawapc01's pair. On "
            f"fewer, pass the devices you have — e.g. --index-device cuda:0 --timelens-device "
            f"cuda:0 — and expect the video phase to serialise."
        )


def build_visual_composer(args: argparse.Namespace) -> VisualComposer:
    """Wire §3 Stage 2's index and Path B's reader onto the GPUs §6 assigns them.

    A separate function because the *wiring* is the decision, not the flag: the first version of
    D-137's test asserted the parsed defaults and reverting either model to `--visual-device` left
    it green. A default nothing reads is not an assignment. D-137.
    """
    from hawedit.models import ModelStore
    from hawedit.qwen_visual import QwenVisualEmbedder, QwenVisualReranker
    from hawedit.registry import REGISTRY
    from hawedit.video_reader import VideoChat3Reader

    model_store = ModelStore()
    embed_dir = model_store.path_for(REGISTRY["Qwen3-VL-Embedding-2B"])
    rerank_dir = model_store.path_for(REGISTRY["Qwen3-VL-Reranker-2B"])
    reader_dir = model_store.path_for(REGISTRY["MCG-NJU/VideoChat3-4B"])
    # §6, VIDEO PHASE: `GPU 0 -> VideoChat3-4B (segmented)` and `GPU 1 -> Embedding / Reranker /
    # TimeLens2 (sequential)`. All three used to take `--visual-device`, so on hawapc01 they landed
    # together on GPU 0 while GPU 1 held 1.3 GiB, and the real 38-minute run died with `CUDA out of
    # memory. Tried to allocate 21.83 GiB … 18.30 GiB is allocated by PyTorch`. Splitting them
    # freed 7.86 GiB on GPU 0. Measured 2026-08-09.
    return VisualComposer(
        QwenVisualEmbedder(embed_dir, device=args.index_device),
        lambda read: QwenVisualReranker(rerank_dir, read, device=args.index_device),
        lambda read, score: VideoChat3Reader(reader_dir, read, score, device=args.visual_device),
        keep=args.visual_keep,
    )


def build_parser() -> argparse.ArgumentParser:
    """The CLI surface, built here so its defaults can be asserted without a run.

    §6 assigns the video phase across two GPUs, and the defaults below are that assignment.
    Extracted from `main` because a default nothing can read is a default nothing can hold to
    the blueprint — D-137's test asserts on the parsed values, not on a comment.
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
    parser.add_argument(
        "--omni-asr",
        action="store_true",
        help="run canonical OmniASR LLM-7B + CTC-3B/Viterbi instead of supplying a transcript",
    )
    parser.add_argument(
        "--omni-asr-runtime",
        choices=("auto", "local", "wsl"),
        default="auto",
        help="OmniASR runtime; auto uses WSL2 on Windows and local inference elsewhere",
    )
    parser.add_argument("--wsl-distro", help="optional WSL distribution for canonical OmniASR")
    parser.add_argument(
        "--verdict", type=Path, help="a JudgeVerdict JSON document to stand in for Stage 4"
    )
    parser.add_argument(
        "--gemini",
        action="store_true",
        help="run Path A discovery and the Stage 4 Gemini judge (sends transcript data)",
    )
    parser.add_argument(
        "--vertex-project",
        help="route Path A and Stage 4 through Gemini on this Vertex AI project",
    )
    parser.add_argument("--vertex-location", default="global")
    parser.add_argument(
        "--visual",
        action="store_true",
        help="compose Qwen embedding/reranking and VideoChat3 over only the survivors",
    )
    parser.add_argument("--visual-query", help="Sorani visual retrieval query")
    parser.add_argument("--visual-keep", type=int, default=7)
    parser.add_argument("--visual-fps", type=float, default=None)
    parser.add_argument(
        "--visual-device",
        default="cuda:0",
        help="device for the Path B reader (VideoChat3-4B) — §6: GPU 0",
    )
    parser.add_argument(
        "--visual-max-frames",
        type=int,
        default=MAX_FRAMES_PER_WINDOW,
        help=(
            "most frames any planned window may hold; §3's ceiling by default and only "
            "lowerable. Measured on hawapc01, VideoChat3-4B reads at most 8 on a 3090 Ti "
            "(D-138); a lower ceiling means more, shorter windows (D-143)"
        ),
    )
    parser.add_argument(
        "--index-device",
        default="cuda:1",
        help="device for Stage 2 indexing (Qwen embedding + reranking) — §6: GPU 1",
    )
    parser.add_argument(
        "--auto-select",
        action="store_true",
        help="choose complete contiguous sentences contained by the best Stage 3 survivor",
    )
    parser.add_argument("--timelens", action="store_true", help="run TimeLens2 in Stage 5")
    parser.add_argument("--timelens-device", default="cuda:1")
    parser.add_argument(
        "--face-reframe",
        action="store_true",
        help="track the dominant face and dynamically move the vertical crop",
    )
    parser.add_argument(
        "--confidential", action="store_true", help="mark the source as confidential"
    )
    parser.add_argument(
        "--zero-data-retention",
        action="store_true",
        help="confirm the configured Gemini/Vertex route has zero-data-retention",
    )
    parser.add_argument(
        "--zdr-confirmed-by", default="", help="person who verified zero-data-retention"
    )
    parser.add_argument("--sentences", help="comma-separated sentence indexes to cut, e.g. 0,1")
    parser.add_argument("--qc-pass", action="store_true", help="record a human QC pass (§2)")
    parser.add_argument("--json", action="store_true", help="print the run report as JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    """`python -m hawedit.pipeline <video> [--transcript t.json] [--sentences 0,1]`.

    Exits non-zero on an incomplete run. A partial pipeline that exited 0 would be indis-
    tinguishable from a working one to anything scripting it.
    """
    use_utf8_streams()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.json:
        return _run_from_args(args, sys.stdout)
    # `--json` promises one JSON document on stdout, and stdout is shared with every library
    # this run loads. Measured on the real 38-minute run: two bare `print`s from
    # `transformers/utils/auto_docstring.py` put 580 bytes ahead of the report and `json.loads`
    # raised at character 0. The report owns the stream; everything else goes to stderr. D-119.
    with machine_readable_stdout() as report_stream:
        return _run_from_args(args, report_stream)


def _run_from_args(args: argparse.Namespace, report_stream: TextIO) -> int:
    """Everything after argument parsing. `report_stream` is where the one document goes."""
    try:
        if args.transcript and args.omni_asr:
            raise ValueError("--transcript and --omni-asr are mutually exclusive Stage 1 sources")
        if (args.omni_asr_runtime != "auto" or args.wsl_distro) and not args.omni_asr:
            raise ValueError("--omni-asr-runtime and --wsl-distro require --omni-asr")
        if args.gemini and args.vertex_project:
            raise ValueError("--gemini and --vertex-project are mutually exclusive cloud routes")
        if (args.gemini or args.vertex_project) and args.verdict:
            raise ValueError("cloud judging and --verdict are mutually exclusive Stage 4 sources")
        if (args.gemini or args.vertex_project) and not (args.transcript or args.omni_asr):
            raise ValueError("cloud discovery requires --transcript or --omni-asr")
        if args.sentences and not (args.transcript or args.omni_asr):
            raise ValueError("--sentences requires --transcript or --omni-asr")
        if args.verdict and (not (args.transcript or args.omni_asr) or not args.sentences):
            raise ValueError("--verdict requires a Stage 1 source and --sentences")
        if args.visual and not (args.transcript or args.omni_asr):
            raise ValueError("--visual requires --transcript or --omni-asr")
        if args.visual_query is not None and not args.visual:
            raise ValueError("--visual-query requires --visual")
        if args.visual_query is not None and not normalize_sorani(args.visual_query).strip():
            raise ValueError("--visual-query must contain non-whitespace Sorani retrieval text")
        if args.visual and not (args.visual_query or args.gemini or args.vertex_project):
            raise ValueError("--visual without Path A requires --visual-query")
        if args.qc_pass and not (args.sentences or args.auto_select):
            raise ValueError("--qc-pass requires --sentences or --auto-select")
        if args.auto_select and not (args.visual or args.gemini or args.vertex_project):
            raise ValueError("--auto-select needs at least one Stage 3 producer")
        if args.auto_select and not (args.transcript or args.omni_asr):
            raise ValueError("--auto-select requires --transcript or --omni-asr")
        if (args.timelens or args.face_reframe) and not (args.sentences or args.auto_select):
            raise ValueError("--timelens and --face-reframe require --sentences or --auto-select")
        if (args.confidential or args.zero_data_retention or args.zdr_confirmed_by) and not (
            args.gemini or args.vertex_project
        ):
            raise ValueError("governance flags apply only with a Gemini or Vertex route")

        transcript = (
            RawTranscript.from_json(args.transcript.read_text(encoding="utf-8"))
            if args.transcript
            else None
        )
        verdict = (
            JudgeVerdict.from_dict(json.loads(args.verdict.read_text(encoding="utf-8")))
            if args.verdict
            else None
        )
        selection = tuple(int(i) for i in args.sentences.split(",")) if args.sentences else ()

        discover = None
        judge = None
        governance = None
        if args.gemini or args.vertex_project:
            from hawedit.gemini import GeminiJudge, Governance, VertexGeminiJudge
            from hawedit.path_a import PathADiscovery

            governance = Governance(
                confidential=args.confidential,
                zero_data_retention=args.zero_data_retention,
                confirmed_by=args.zdr_confirmed_by,
            )
            judge = (
                VertexGeminiJudge(
                    args.vertex_project,
                    location=args.vertex_location,
                    governance=governance,
                )
                if args.vertex_project
                else GeminiJudge(governance=governance)
            )
            path_a = PathADiscovery(client=judge)
            discover = path_a.discover

        canonical_asr = None
        if args.omni_asr:
            from hawedit.asr import create_omni_asr_producer

            canonical_asr = create_omni_asr_producer(args.omni_asr_runtime, distro=args.wsl_distro)

        assert_devices_available(
            {
                **({"the Path B reader": args.visual_device} if args.visual else {}),
                **({"Stage 2 indexing": args.index_device} if args.visual else {}),
                **({"TimeLens2": args.timelens_device} if args.timelens else {}),
            }
        )

        visual_composer = None
        if args.visual:
            visual_composer = build_visual_composer(args)

        temporal_grounder = None
        if args.timelens:
            from hawedit.models import ModelStore
            from hawedit.registry import REGISTRY
            from hawedit.video_grounding import TimeLens2Grounder
            from hawedit.video_input import extract_window_frames

            temporal_grounder = TimeLens2Grounder(
                ModelStore().path_for(REGISTRY["MCG-NJU/TimeLens2-4B"]),
                lambda window: extract_window_frames(
                    args.source,
                    window,
                    args.work_dir / "timelens" / "frames" / window.window_id.replace(":", "_"),
                ),
                device=args.timelens_device,
            )

        subject_tracker = None
        if args.face_reframe:
            from hawedit.reframe import OpenCvFaceTracker

            subject_tracker = OpenCvFaceTracker()

        run = run_pipeline(
            args.source,
            args.work_dir,
            media_id=args.media_id,
            transcript=transcript,
            asr=canonical_asr,
            select_sentences=selection,
            qc=Qc(auto_pass=False, flags=(), human_reviewed=True) if args.qc_pass else None,
            verdict=verdict,
            discover=discover,
            visual_composer=visual_composer,
            visual_query=args.visual_query,
            judge=judge,
            temporal_grounder=temporal_grounder,
            subject_tracker=subject_tracker,
            auto_select=args.auto_select,
            visual_fps=args.visual_fps,
            visual_max_frames=args.visual_max_frames,
        )
    except (
        CredentialError,
        FileExistsError,
        FileNotFoundError,
        GeminiUnavailable,
        IngestError,
        KeyError,
        RawTranscriptImmutable,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(run.to_dict(), ensure_ascii=False, indent=2), file=report_stream)
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
    if run.visual_windows:
        # Printed even though `visual_index` is skipped just below. Stage 2's visual half is
        # two things, and only one of them is blocked; a report that showed the skip alone
        # would say a stage did nothing when part of it ran on this video.
        frames = sum(w.frame_count for w in run.visual_windows)
        suffix = (
            f" · {len(run.visual_index.survivors)} reranked survivor(s)"
            if isinstance(run.visual_index, VisualDiscoveryResult)
            else " · local visual retrieval not enabled"
        )
        print(
            f"stage 2 {len(run.visual_windows)} scene window(s) · {frames} frame(s) at "
            f"{run.visual_windows[0].fps} fps{suffix}"
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
