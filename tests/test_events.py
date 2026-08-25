"""The observer boundary: what a run says about itself before it returns.

`PipelineRun` is a complete and honest record that arrives at the end. These tests cover the
other half — the events emitted while the run is still in flight — and, more importantly, that
the two cannot disagree. An event stream that reported a stage completed where the report
records a `StageSkipped` would be worse than no event stream: it would be a green timeline over
a run that refused, which is exactly the silent-success failure the whole project is written
against.

The unit tests below run anywhere. The integration tests drive the real fixture through
`run_pipeline` and need ffmpeg, like every other end-to-end test in this suite.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from hawedit.captions import find_ffmpeg
from hawedit.clip import Qc
from hawedit.events import RunEvent, RunEventLog, RunState, discard
from hawedit.judge import JudgeVerdict
from hawedit.pipeline import PipelineRun, StageSkipped, run_pipeline
from hawedit.transcripts import AsrProvenance, RawTranscript, Word

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "kurdish-speech-3cuts.mp4"
FIXTURE_SHA256 = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()

needs_ffmpeg = pytest.mark.skipif(find_ffmpeg() is None, reason="no ffmpeg — set HAWEDIT_FFMPEG")

# The same two complete Kurdish sentences `tests/test_pipeline.py` uses, whose timings sit
# inside the 4.16 s fixture.
WORDS = (
    Word(w="ڕۆژنامەوانی", start_ms=100, end_ms=800, conf=0.95),
    Word(w="کوردی.", start_ms=800, end_ms=1_700, conf=0.94),
    Word(w="لە", start_ms=2_000, end_ms=2_400, conf=0.93),
    Word(w="هەولێر.", start_ms=2_400, end_ms=4_100, conf=0.92),
)


def a_transcript(media_id: str = "fixture") -> RawTranscript:
    return RawTranscript(
        media_id=media_id,
        text_ckb="ڕۆژنامەوانی کوردی. لە هەولێر.",
        words=WORDS,
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
        media_sha256=FIXTURE_SHA256,
    )


def a_verdict(clip_in_ms: int, clip_out_ms: int) -> JudgeVerdict:
    return JudgeVerdict(
        candidate_id="fixture-0",
        hook_score=0.8,
        self_contained=True,
        payoff_at_ms=(clip_in_ms + clip_out_ms) // 2,
        meaning_fidelity=0.9,
        misleading_edit_risk=0.05,
        cultural_landing=0.8,
        narrative_role="payoff",
        title_ckb="ڕۆژنامەوانی کوردی لە هەولێر",
        description_ckb="بابەتێکی گرنگ دەربارەی ڕۆژنامەوانی",
        hashtags_ckb=("#کوردی",),
        judge="gemini-2.5-pro",
        clip_in_ms=clip_in_ms,
        clip_out_ms=clip_out_ms,
    )


def an_event(**overrides: object) -> RunEvent:
    fields: dict[str, object] = {
        "run_id": "fixture",
        "sequence": 1,
        "at_ms": 1_000,
        "stage": "ingest",
        "state": RunState.COMPLETED,
    }
    fields.update(overrides)
    return RunEvent(**fields)  # type: ignore[arg-type]


# --- the event contract -------------------------------------------------------------------


def test_a_skip_with_no_reason_is_refused() -> None:
    """A skip nobody can explain reads as a stage that was forgotten.

    `StageSkipped` exists so "did not run" and "ran and found nothing" cannot serialize to the
    same thing. A reasonless skip event throws that distinction away one layer further out.
    """
    with pytest.raises(ValueError, match="skipped with no reason"):
        an_event(state=RunState.SKIPPED)
    with pytest.raises(ValueError, match="skipped with no reason"):
        an_event(state=RunState.SKIPPED, reason="   ")


def test_a_completion_that_carries_a_reason_is_refused() -> None:
    """Only a skip has a reason. Anywhere else the field reads as a refusal that never was."""
    with pytest.raises(ValueError, match="Only a skip has a reason"):
        an_event(state=RunState.COMPLETED, reason="went fine")
    with pytest.raises(ValueError, match="Only a skip has a reason"):
        an_event(state=RunState.STARTED, reason="starting now")


def test_an_event_belongs_to_a_run_and_names_a_stage() -> None:
    with pytest.raises(ValueError, match="run_id is empty"):
        an_event(run_id="  ")
    with pytest.raises(ValueError, match="names no stage"):
        an_event(stage="")


def test_a_sequence_starts_at_one_and_a_timestamp_is_never_before_the_epoch() -> None:
    with pytest.raises(ValueError, match="sequence starts at 1"):
        an_event(sequence=0)
    with pytest.raises(ValueError, match="before the epoch"):
        an_event(at_ms=-1)


def test_an_event_serializes_to_a_flat_document() -> None:
    payload = an_event(state=RunState.SKIPPED, reason="no producer").to_dict()
    assert payload == {
        "run_id": "fixture",
        "sequence": 1,
        "at_ms": 1_000,
        "stage": "ingest",
        "state": "skipped",
        "reason": "no producer",
    }


# --- the log ------------------------------------------------------------------------------


def test_a_plain_list_is_already_a_sink() -> None:
    """`EventSink` is `Callable[[RunEvent], None]`, so `list.append` is one. No class needed."""
    events: list[RunEvent] = []
    log = RunEventLog("fixture", events.append)
    log.started("ingest")
    log.finished("ingest")
    assert [(event.stage, event.state) for event in events] == [
        ("ingest", RunState.STARTED),
        ("ingest", RunState.COMPLETED),
    ]


def test_a_timestamp_is_not_an_order() -> None:
    """Two events inside the same millisecond are ordinary; the cursor is the sequence.

    §Phase 1's replay contract is "reconnect by workflow ID and last event ID". Under a frozen
    clock every `at_ms` here is identical — which is what a fast stage looks like on a real
    clock too — and the stream is still totally ordered.
    """
    events: list[RunEvent] = []
    log = RunEventLog("fixture", events.append, clock=lambda: 1_700_000_000.0)
    for stage in ("ingest", "transcript", "index"):
        log.started(stage)
        log.finished(stage)
    assert len({event.at_ms for event in events}) == 1, "the frozen clock must not vary"
    assert [event.sequence for event in events] == [1, 2, 3, 4, 5, 6]


def test_finished_reports_a_skip_with_the_stage_s_own_reason() -> None:
    events: list[RunEvent] = []
    log = RunEventLog("fixture", events.append)
    log.finished("transcript", "no Stage 1 producer was enabled.")
    assert events[0].state is RunState.SKIPPED
    assert events[0].reason == "no Stage 1 producer was enabled."


def test_a_log_belongs_to_a_run() -> None:
    with pytest.raises(ValueError, match="run_id is empty"):
        RunEventLog("   ")


def test_the_default_sink_discards() -> None:
    """A run nobody is watching costs one call per stage and keeps no events anywhere."""
    log = RunEventLog("fixture")
    first = log.started("ingest")
    discard(first)  # the default sink: takes an event, keeps nothing, tells nobody
    assert log.finished("ingest").sequence == first.sequence + 1


# --- against a real run --------------------------------------------------------------------


@needs_ffmpeg
def test_a_run_reports_its_stages_before_it_returns(tmp_path: Path) -> None:
    """The point of the whole module: Stage 0 is known to have finished before Stage 1 starts.

    Without this the only report is the return value, which for a 38-minute source is most of
    an hour away — long enough that no durable workflow can checkpoint and no editor can watch.
    """
    events: list[RunEvent] = []
    run = run_pipeline(FIXTURE, tmp_path / "work", on_event=events.append)
    assert isinstance(run.transcript, StageSkipped), "no ASR producer here"
    stream = [(event.stage, event.state.value) for event in events]
    assert stream[:2] == [("ingest", "started"), ("ingest", "completed")]
    assert ("transcript", "skipped") in stream
    assert ("index", "started") not in stream, "Stage 1 stopped the run before the index"


@needs_ffmpeg
@pytest.mark.parametrize(
    ("label", "supplied"),
    [
        # Stops at Stage 1, so the only skip is the transcript's own constant.
        ("no-producers", {}),
        # Runs through Stage 1 and stops for want of a selection, which is the arrangement that
        # reaches `_skip_reason` — the editorial and boundary skips read their reasons from the
        # very objects the report carries. Without this case the parametrization covers only
        # the hard-coded constants and a mutation of `_skip_reason` survives the suite; it did,
        # measured, until this case was added.
        ("transcript-only", {"media_id": "fixture", "transcript": a_transcript()}),
    ],
)
def test_every_skipped_event_carries_the_reason_the_report_carries(
    tmp_path: Path, label: str, supplied: dict[str, object]
) -> None:
    """The invariant that makes the stream trustworthy: it cannot disagree with the record.

    A timeline showing a stage green over a report that records a refusal is worse than no
    timeline. Every skip event's reason is read from the `StageSkipped` the report will carry,
    never written a second time beside it — `_skip_reason` in `pipeline.py` is that bridge, and
    this asserts it end to end rather than trusting the call sites.
    """
    events: list[RunEvent] = []
    run = run_pipeline(
        FIXTURE,
        tmp_path / label,
        on_event=events.append,
        **supplied,  # type: ignore[arg-type]
    )
    recorded = {name: skip.reason for name, skip in run.skipped()}
    skipped_events = [event for event in events if event.state is RunState.SKIPPED]
    assert skipped_events, f"{label}: this run skips stages; the stream must say which"
    for event in skipped_events:
        assert event.stage in recorded, (
            f"the stream reports {event.stage!r} skipped and the report does not. An event "
            f"stream that invents a refusal is as bad as one that hides it."
        )
        assert event.reason == recorded[event.stage], (
            f"{event.stage}: the stream says {event.reason!r} and the report says "
            f"{recorded[event.stage]!r}. These are read from one object precisely so they "
            f"cannot drift; if this fails, a call site wrote the reason out a second time."
        )


@needs_ffmpeg
def test_no_stage_ends_without_having_started(tmp_path: Path) -> None:
    """A terminal event with no start is a stage a timeline would render out of nowhere."""
    events: list[RunEvent] = []
    run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="fixture",
        transcript=a_transcript(),
        select_sentences=(0, 1),
        qc=Qc(auto_pass=True, flags=(), human_reviewed=True),
        verdict=a_verdict(100, 4_100),
        on_event=events.append,
    )
    open_stages: set[str] = set()
    for event in events:
        if event.state is RunState.STARTED:
            assert event.stage not in open_stages, f"{event.stage} started twice without ending"
            open_stages.add(event.stage)
        else:
            assert event.stage in open_stages, f"{event.stage} ended without starting"
            open_stages.remove(event.stage)
    assert not open_stages, f"stages started and never ended: {sorted(open_stages)}"


@needs_ffmpeg
def test_a_full_run_reports_every_stage_through_delivery(tmp_path: Path) -> None:
    events: list[RunEvent] = []
    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="fixture",
        transcript=a_transcript(),
        select_sentences=(0, 1),
        qc=Qc(auto_pass=True, flags=(), human_reviewed=True),
        verdict=a_verdict(100, 4_100),
        on_event=events.append,
    )
    assert run.clip is not None and not isinstance(run.render, StageSkipped)
    completed = [event.stage for event in events if event.state is RunState.COMPLETED]
    assert completed == [
        "ingest",
        "visual_windows",
        "transcript",
        "sentences",
        "index",
        "editorial",
        "boundary",
        "render",
        "delivery",
    ], completed
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))


@needs_ffmpeg
def test_a_run_nobody_watches_produces_the_same_report(tmp_path: Path) -> None:
    """`on_event` is additive. Every existing caller passes nothing and is unaffected."""

    def report(work: str, **kwargs: object) -> str:
        run: PipelineRun = run_pipeline(
            FIXTURE,
            tmp_path / work,
            media_id="fixture",
            transcript=a_transcript(),
            select_sentences=(0, 1),
            qc=Qc(auto_pass=True, flags=(), human_reviewed=True),
            verdict=a_verdict(100, 4_100),
            **kwargs,  # type: ignore[arg-type]
        )
        # Every artifact path names the work directory, and the two runs need different ones —
        # so the one difference the comparison must tolerate is edited out by name rather than
        # by dropping whole fields, which would stop the comparison covering them.
        payload = json.dumps(run.to_dict(), ensure_ascii=False, sort_keys=True)
        return payload.replace(json.dumps(str(tmp_path / work))[1:-1], "<work>")

    events: list[RunEvent] = []
    assert report("unwatched") == report("watched", on_event=events.append)
    assert events, "the watched run must still have emitted"
