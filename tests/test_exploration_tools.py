"""The six remaining Phase 3 tools (D-A22/D-A23/D-A24/D-A25), and the guarantees they hold.

`inspect_project`/`list_candidates`/`preview_candidate` (`agent.py`) and `inspect_artifact`/
`compare_versions`/`propose_render`/`commit_render` (`proposals.py`) are all reads except
`commit_render`, so most of this file is ordinary coverage against hand-built reports — the
right level for functions whose job is reading fields off a dict.

Two properties get more than ordinary coverage, because both were found the hard way while
building these:

1. **None of these ever raises for a caller-supplied identifier that resolves to nothing.**
   `artifact_id`/`candidate_id`/`revision_id` all report a `found=False`-shaped value instead.
   A first version raised, and `tests/test_prompt_injection.py`'s `TestModel`-driven suite —
   which probes every registered tool with a placeholder string — failed on it immediately.
2. **`inspect_artifact` agrees with what the render functions would actually produce.** It
   reconstructs a revision the same way `render_boundary_revision`/`render_caption_revision`
   do; a second derivation that could disagree with the real encode would be worse than no tool.
   Checked against a real rendered revision, not asserted.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from hawedit.agent import inspect_project, list_candidates, preview_candidate
from hawedit.boundary import Boundary, BoundaryInvariantViolated
from hawedit.captions import CaptionsOutsideClip
from hawedit.clip import Clip, ClipTranscript, DiscoveryPath, Output
from hawedit.learning import DecisionOutcome, ReasonCode, read_decision_deltas
from hawedit.proposals import (
    RevisionRejected,
    commit_boundary_revision,
    commit_render,
    compare_versions,
    inspect_artifact,
    propose_boundary_revision,
    propose_render,
    render_boundary_revision,
)
from hawedit.sentences import Sentence
from hawedit.transcripts import AsrProvenance, Word

ROOT = Path(__file__).resolve().parents[1]

# The first word starts at `_BOUNDARY["anchor_in_ms"]`, not at 0. An anchor is where forced
# alignment says the selected sentences actually begin, so a fixture whose words start
# before its own anchor is a run that cannot happen — and it made a legal narrowing put
# captions before the clip, which is why the valid-direction equivalence could not be
# written against it. `anchor_out_ms` (4100) already matched the last word's end. D-A26.
_WORDS = (
    Word(w="ڕۆژنامەوانی", start_ms=100, end_ms=800, conf=0.95),
    Word(w="کوردی.", start_ms=800, end_ms=1_700, conf=0.94),
    Word(w="لە", start_ms=2_000, end_ms=2_400, conf=0.93),
    Word(w="هەولێر.", start_ms=2_400, end_ms=4_100, conf=0.92),
)

_BOUNDARY: dict[str, object] = {
    "anchor_in_ms": 100,
    "anchor_out_ms": 4100,
    "final_in_ms": 0,
    "final_out_ms": 4300,
    "in_extended_by": "vad_onset",
    "out_extended_by": "tail",
    "sentence_complete": True,
    "confidence": None,
}


def _clip_dict(caption_style: str = "line") -> dict[str, Any]:
    boundary = Boundary(**_BOUNDARY)  # type: ignore[arg-type]
    clip = Clip(
        clip_id="fixture-0",
        media_id="fixture",
        in_ms=boundary.final_in_ms,
        out_ms=boundary.final_out_ms,
        discovery_path=DiscoveryPath.VERBAL,
        boundary=boundary,
        transcript=ClipTranscript(
            raw_ckb="ڕۆژنامەوانی کوردی.",
            norm_ckb="ڕۆژنامەوانی کوردی.",
            en_aux=None,
            words=_WORDS,
            asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
        ),
        output=Output(
            title_ckb="t",
            description_ckb="d",
            crop_target="9:16",
            caption_style=caption_style,
            durations=(30,),
        ),
    )
    return clip.to_dict()


def _candidate(
    candidate_id: str,
    in_ms: int,
    out_ms: int,
    discovery_path: str = "verbal",
    verbal_rank: int | None = None,
    visual_rank: int | None = None,
    verbal_score: float | None = None,
    visual_score: float | None = None,
) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "media_id": "fixture",
        "in_ms": in_ms,
        "out_ms": out_ms,
        "discovery_path": discovery_path,
        "sources": [candidate_id],
        "verbal_rank": verbal_rank,
        "visual_rank": visual_rank,
        "verbal_score": verbal_score,
        "visual_score": visual_score,
        "sv6d": None,
    }


def _write_report(work_dir: Path, **overrides: Any) -> None:
    report: dict[str, Any] = {
        "media_id": "fixture",
        "source": "x.mp4",
        "work_dir": str(work_dir),
        "complete": True,
        "skipped": [],
        "boundary": _BOUNDARY,
        "candidates": [],
        "rejected": [],
        "clip": _clip_dict(),
        "render": None,
        "delivery": None,
        "selected_sentences": [dataclasses.asdict(Sentence(words=_WORDS, complete=True))],
        "transcript": {
            "media_id": "fixture",
            "text_ckb": "ڕۆژنامەوانی کوردی. لە هەولێر.",
            "source_sha256": "0" * 64,
            "words": [dataclasses.asdict(w) for w in _WORDS],
        },
    }
    report.update(overrides)
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")


def _approve_boundary(work_dir: Path, revision_id: str, in_ms: int, out_ms: int) -> None:
    proposal = propose_boundary_revision(work_dir, in_ms, out_ms)
    assert proposal.valid, proposal.violation
    commit_boundary_revision(
        work_dir,
        proposal,
        revision_id=revision_id,
        approved_by="hawa",
        reason_code=ReasonCode.PREFERENCE,
        confirm=lambda _: True,
    )


# --- inspect_project (D-A23) --------------------------------------------------------------------


def test_inspect_project_reports_a_bare_run(tmp_path: Path) -> None:
    _write_report(tmp_path)
    manifest = inspect_project(tmp_path)
    assert manifest.media_id == "fixture"
    assert manifest.complete is True
    assert manifest.has_events is False
    assert manifest.decision_count == 0
    assert manifest.revisions == ()


def test_inspect_project_counts_real_decisions_and_revisions(tmp_path: Path) -> None:
    """Against real records written by the real commit function, not hand-built stand-ins —
    `decision_count` and `revisions` must agree with what actually happened in this directory."""
    _write_report(tmp_path)
    _approve_boundary(tmp_path, "r1", 0, 4200)
    _approve_boundary(tmp_path, "r2", 0, 4250)
    manifest = inspect_project(tmp_path)
    assert manifest.decision_count == 2
    assert [r.revision_id for r in manifest.revisions] == ["r1", "r2"]
    assert {r.kind for r in manifest.revisions} == {"boundary"}
    assert {r.status for r in manifest.revisions} == {"approved_pending_render"}


def test_inspect_project_notices_an_event_ledger(tmp_path: Path) -> None:
    _write_report(tmp_path)
    (tmp_path / "events.jsonl").write_text("", encoding="utf-8")
    assert inspect_project(tmp_path).has_events is True


def test_inspect_project_raises_with_no_run(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="report.json"):
        inspect_project(tmp_path)


# --- list_candidates (D-A24) --------------------------------------------------------------------


def test_list_candidates_caps_at_the_limit_and_reports_the_real_total(tmp_path: Path) -> None:
    _write_report(
        tmp_path,
        candidates=[_candidate(f"c{i}", i * 100, i * 100 + 500) for i in range(1, 8)],
    )
    listed = list_candidates(tmp_path, limit=3)
    assert len(listed.candidates) == 3
    assert listed.total_available == 7, "the cap must not hide how many there really are"


def test_list_candidates_filters_to_one_discovery_path(tmp_path: Path) -> None:
    _write_report(
        tmp_path,
        candidates=[
            _candidate("v1", 0, 500, "verbal"),
            _candidate("x1", 600, 900, "visual"),
            _candidate("v2", 1000, 1500, "verbal"),
        ],
    )
    listed = list_candidates(tmp_path, discovery_path="verbal")
    assert [c.candidate_id for c in listed.candidates] == ["v1", "v2"]
    assert listed.total_available == 2


def test_list_candidates_orders_a_single_path_by_that_paths_own_rank(tmp_path: Path) -> None:
    """Within one path, ranking by that path's own 1-based ordinal is defensible —
    `discovery.py`'s `Candidate.rank`. Across paths it is not, which the next test pins."""
    _write_report(
        tmp_path,
        candidates=[
            _candidate("third", 0, 500, "verbal", verbal_rank=3),
            _candidate("first", 600, 900, "verbal", verbal_rank=1),
            _candidate("second", 1000, 1500, "verbal", verbal_rank=2),
        ],
    )
    listed = list_candidates(tmp_path, discovery_path="verbal")
    assert [c.candidate_id for c in listed.candidates] == ["first", "second", "third"]


def test_list_candidates_never_reorders_across_paths(tmp_path: Path) -> None:
    """`discovery.py`: "There is no defensible arithmetic between [verbal_score and
    visual_score]." With no path filter, the run's own recorded order is preserved exactly —
    inventing a cross-path order here would make that refusal meaningless one level removed."""
    recorded = [
        _candidate("v-low", 0, 500, "verbal", verbal_score=0.1),
        _candidate("x-high", 600, 900, "visual", visual_score=0.99),
        _candidate("v-high", 1000, 1500, "verbal", verbal_score=0.95),
    ]
    _write_report(tmp_path, candidates=recorded)
    listed = list_candidates(tmp_path, limit=10)
    assert [c.candidate_id for c in listed.candidates] == ["v-low", "x-high", "v-high"]


def test_list_candidates_sorts_an_unranked_candidate_last_not_first(tmp_path: Path) -> None:
    """Ranks are 1-based (`discovery.py`), so a missing rank must sort *after* real rank 1 — a
    `or 0` default would put it first and, combined with `limit`, evict the top candidate from
    a truncated list."""
    _write_report(
        tmp_path,
        candidates=[
            _candidate("unranked", 0, 500, "verbal", verbal_rank=None),
            _candidate("top", 600, 900, "verbal", verbal_rank=1),
        ],
    )
    listed = list_candidates(tmp_path, discovery_path="verbal", limit=1)
    assert [c.candidate_id for c in listed.candidates] == ["top"]


def test_list_candidates_does_not_rank_sort_the_both_path(tmp_path: Path) -> None:
    """A `DiscoveryPath.BOTH` candidate carries both ranks, and choosing between them is the
    cross-path arithmetic `discovery.py` refuses — so `"both"` keeps recorded order."""
    _write_report(
        tmp_path,
        candidates=[
            _candidate("second-by-verbal", 0, 500, "both", verbal_rank=2, visual_rank=1),
            _candidate("first-by-verbal", 600, 900, "both", verbal_rank=1, visual_rank=2),
        ],
    )
    listed = list_candidates(tmp_path, discovery_path="both")
    assert [c.candidate_id for c in listed.candidates] == [
        "second-by-verbal",
        "first-by-verbal",
    ]


def test_list_candidates_clamps_a_nonsense_limit_rather_than_raising(tmp_path: Path) -> None:
    """`limit` is agent-suppliable; an out-of-range value is a recoverable, reportable outcome
    (a short list), not an exception that ends the conversation."""
    _write_report(tmp_path, candidates=[_candidate("c1", 0, 500)])
    assert len(list_candidates(tmp_path, limit=0).candidates) == 1
    assert len(list_candidates(tmp_path, limit=-5).candidates) == 1


def test_list_candidates_refuses_an_unreal_discovery_path(tmp_path: Path) -> None:
    """Unlike `limit`, this raises: the tool schema closes `discovery_path` to a real enum
    before a model could supply a bad one, so reaching here with one is a direct-caller error."""
    _write_report(tmp_path)
    with pytest.raises(ValueError, match="discovery_path must be one of"):
        list_candidates(tmp_path, discovery_path="sideways")


# --- preview_candidate (D-A24) ------------------------------------------------------------------


def test_preview_candidate_returns_only_the_text_its_span_covers(tmp_path: Path) -> None:
    """The scoping that matters: one candidate's own span, not the transcript at large."""
    _write_report(tmp_path, candidates=[_candidate("c1", 0, 1_700)])
    preview = preview_candidate(tmp_path, "c1")
    assert preview.found is True
    assert preview.transcript_available is True
    assert preview.preview_text == "ڕۆژنامەوانی کوردی."
    assert "هەولێر." not in (preview.preview_text or ""), (
        "a word outside the candidate's span must not appear in its preview"
    )


def test_preview_candidate_includes_a_word_that_merely_overlaps_the_span(tmp_path: Path) -> None:
    """A word counts if its own span overlaps at all — how a caption cue is timed, rather than
    requiring exact containment, which would silently drop a word straddling either edge."""
    _write_report(tmp_path, candidates=[_candidate("edge", 700, 900)])
    preview = preview_candidate(tmp_path, "edge")
    assert preview.preview_text == "ڕۆژنامەوانی کوردی."


def test_preview_candidate_reports_an_unknown_id_as_not_found(tmp_path: Path) -> None:
    _write_report(tmp_path, candidates=[_candidate("c1", 0, 500)])
    preview = preview_candidate(tmp_path, "no-such-candidate")
    assert preview.found is False
    assert preview.in_ms is None
    assert preview.preview_text is None


def test_preview_candidate_distinguishes_no_transcript_from_empty_coverage(tmp_path: Path) -> None:
    """`StageSkipped`'s own "did not run" vs "ran and found nothing" distinction, applied here:
    a run with no transcript at all reports `transcript_available=False`, while a real
    transcript that happens to cover none of this span reports an empty string."""
    _write_report(
        tmp_path,
        candidates=[_candidate("c1", 0, 500)],
        transcript={"skipped": True, "stage": "transcript", "reason": "no producer"},
    )
    no_transcript = preview_candidate(tmp_path, "c1")
    assert no_transcript.found is True
    assert no_transcript.transcript_available is False
    assert no_transcript.preview_text is None

    _write_report(tmp_path, candidates=[_candidate("late", 90_000, 95_000)])
    empty_coverage = preview_candidate(tmp_path, "late")
    assert empty_coverage.transcript_available is True
    assert empty_coverage.preview_text == ""


# --- inspect_artifact (D-A22) -------------------------------------------------------------------


def test_inspect_artifact_resolves_the_original_clip(tmp_path: Path) -> None:
    _write_report(tmp_path)
    artifact = inspect_artifact(tmp_path, "original")
    assert artifact.found is True
    assert artifact.kind == "original"
    assert (artifact.in_ms, artifact.out_ms) == (0, 4300)
    assert artifact.caption_style == "line"
    assert artifact.status == "not_rendered"


def test_inspect_artifact_reports_a_rendered_original(tmp_path: Path) -> None:
    _write_report(tmp_path, render={"path": "out.mp4"})
    assert inspect_artifact(tmp_path, "original").status == "rendered"


def test_inspect_artifact_does_not_call_a_skipped_render_rendered(tmp_path: Path) -> None:
    """`StageSkipped.to_dict()` is *also* a dict, and `pipeline.py` sets `clip` before the render
    stage — so a run whose render failed or was gated has a populated clip and a skipped-shaped
    `render` with no file on disk. A bare `isinstance(..., dict)` would report that as rendered.
    Found by an adversarial review pass, not by a test: this file's other fixtures use
    `"render": None`, a shape the real pipeline never writes once a clip exists."""
    _write_report(
        tmp_path,
        render={
            "skipped": True,
            "stage": "render",
            "reason": "no usable encoder",
            "blocked_by": [],
        },
    )
    assert inspect_artifact(tmp_path, "original").status == "not_rendered"


def test_inspect_artifact_resolves_a_boundary_revision_to_its_new_span(tmp_path: Path) -> None:
    """A boundary revision changes the span and nothing else — `caption_style` stays the
    original's, exactly as `render_boundary_revision` reconstructs it."""
    _write_report(tmp_path)
    _approve_boundary(tmp_path, "narrower", 50, 4200)
    artifact = inspect_artifact(tmp_path, "narrower")
    assert artifact.found is True
    assert artifact.kind == "boundary"
    assert (artifact.in_ms, artifact.out_ms) == (50, 4200)
    assert artifact.caption_style == "line", "a boundary revision must not change caption style"
    assert artifact.status == "approved_pending_render"
    assert artifact.approved_by == "hawa"


def test_inspect_artifact_resolves_a_caption_revision_to_its_new_style(tmp_path: Path) -> None:
    """The mirror case: a caption revision changes the style and nothing else — the span stays
    the original's."""
    _write_report(tmp_path)
    (tmp_path / "revisions").mkdir(exist_ok=True)
    (tmp_path / "revisions" / "styled.json").write_text(
        json.dumps(
            {
                "kind": "caption",
                "revision_id": "styled",
                "media_id": "fixture",
                "proposed_caption_style": "word_highlight",
                "status": "approved_pending_render",
                "approved_by": "hawa",
            }
        ),
        encoding="utf-8",
    )
    artifact = inspect_artifact(tmp_path, "styled")
    assert artifact.kind == "caption"
    assert artifact.caption_style == "word_highlight"
    assert (artifact.in_ms, artifact.out_ms) == (0, 4300), (
        "a caption revision must not change the span"
    )


def test_inspect_artifact_treats_a_pre_d_a12_record_as_a_boundary_revision(tmp_path: Path) -> None:
    """A record written before D-A12 added `"kind"` has none — and every such record on disk is
    a boundary revision, the same backward-compatible default `render_boundary_revision` uses."""
    _write_report(tmp_path)
    (tmp_path / "revisions").mkdir(exist_ok=True)
    (tmp_path / "revisions" / "old.json").write_text(
        json.dumps(
            {
                "revision_id": "old",
                "media_id": "fixture",
                "proposed_final_in_ms": 20,
                "proposed_final_out_ms": 4280,
                "status": "approved_pending_render",
            }
        ),
        encoding="utf-8",
    )
    artifact = inspect_artifact(tmp_path, "old")
    assert artifact.kind == "boundary"
    assert (artifact.in_ms, artifact.out_ms) == (20, 4280)


def test_inspect_artifact_reports_an_unknown_kind_as_not_found_rather_than_raising(
    tmp_path: Path,
) -> None:
    """A record with a `kind` this codebase does not know must not fall through to the caption
    branch and `KeyError` on a `proposed_caption_style` it has no reason to carry — the same
    defect `replay_decision_deltas` already records having been found once, for a different
    consumer of the same widening `kind` field."""
    _write_report(tmp_path)
    (tmp_path / "revisions").mkdir(exist_ok=True)
    (tmp_path / "revisions" / "future.json").write_text(
        json.dumps({"kind": "trim", "revision_id": "future", "status": "approved_pending_render"}),
        encoding="utf-8",
    )
    artifact = inspect_artifact(tmp_path, "future")
    assert artifact.found is False
    assert compare_versions(tmp_path, "original", "future").both_found is False


@pytest.mark.parametrize(
    "probe",
    ["../../outside", "..\\..\\outside", "../secret", "a/b", "a\b", "..", "."],
)
def test_a_traversing_artifact_id_cannot_read_outside_the_work_dir(
    tmp_path: Path, probe: str
) -> None:
    """The property `agent.py`'s docstring claims for the whole agent surface: "there is no
    flag, config, or prompt phrasing that changes what directory a given agent instance can
    read".

    It was false here. `artifact_id` is interpolated into `work_dir/revisions/<id>.json`, and
    `inspect_artifact` is reachable from `explorer_agent`'s tool with a model-supplied string —
    so a prompt-injected transcript could ask a read-only agent to probe the host. Measured
    before the fix: `"../../outside"` returned `found=True` carrying the `status` and
    `approved_by` of a file outside the run. D-A27.

    The file below really exists and really is outside `work_dir`; a probe that resolves is a
    regression, not a hypothetical.
    """
    outside = tmp_path.parent / "outside.json"
    outside.write_text(
        json.dumps({"kind": "boundary", "status": "LEAKED", "approved_by": "someone-else"}),
        encoding="utf-8",
    )
    secret = tmp_path.parent / "secret.json"
    secret.write_text(
        json.dumps(
            {
                "kind": "boundary",
                "status": "LEAKED",
                "proposed_final_in_ms": 1,
                "proposed_final_out_ms": 2,
            }
        ),
        encoding="utf-8",
    )
    _write_report(tmp_path)

    artifact = inspect_artifact(tmp_path, probe)
    assert artifact.found is False, (
        f"artifact_id {probe!r} resolved to something — status={artifact.status!r}. An "
        f"identifier carrying a separator or a parent reference must never be looked up."
    )
    assert artifact.status is None


@pytest.mark.parametrize("probe", ["../../outside", "..\\..\\outside", "a/b"])
def test_a_traversing_revision_id_is_not_a_renderable_proposal(tmp_path: Path, probe: str) -> None:
    """The same guard on the other agent-facing entry point. `propose_render` reports it as an
    invalid proposal rather than raising, matching its own contract for every other
    unresolvable revision_id."""
    _write_report(tmp_path)
    proposal = propose_render(tmp_path, probe)
    assert proposal.valid is False
    assert "safe filename component" in (proposal.violation or "")


def test_a_traversing_revision_id_is_refused_outright_on_the_write_paths(
    tmp_path: Path,
) -> None:
    """Reads report; writes refuse. `commit_*`/`render_*` interpolate the id into six output
    paths (.json/.ass/.mp4/.srt/.edl), so "not found" would be the wrong answer — nothing was
    looked up, the name itself was rejected."""
    _write_report(tmp_path)
    with pytest.raises(ValueError, match="safe filename component"):
        render_boundary_revision(tmp_path, "../../escape")


def test_inspect_artifact_reports_an_unknown_id_as_not_found(tmp_path: Path) -> None:
    _write_report(tmp_path)
    artifact = inspect_artifact(tmp_path, "no-such-revision")
    assert artifact.found is False
    assert artifact.in_ms is None
    assert artifact.kind is None


def test_inspect_artifact_reports_not_found_when_the_run_has_no_clip(tmp_path: Path) -> None:
    """A run that never reached §3 Stage 5 — ordinary, not an error, matching
    `run_quality_checks`' own treatment of the same state (D-A18)."""
    _write_report(tmp_path, clip=None)
    assert inspect_artifact(tmp_path, "original").found is False


def test_inspect_artifact_raises_with_no_run(tmp_path: Path) -> None:
    """`work_dir` is never agent-suppliable, so this genuinely is a caller error."""
    with pytest.raises(FileNotFoundError, match="report.json"):
        inspect_artifact(tmp_path, "original")


# --- compare_versions (D-A22) -------------------------------------------------------------------


def test_compare_versions_detects_a_changed_span(tmp_path: Path) -> None:
    _write_report(tmp_path)
    _approve_boundary(tmp_path, "narrower", 50, 4200)
    comparison = compare_versions(tmp_path, "original", "narrower")
    assert comparison.both_found is True
    assert comparison.span_changed is True
    assert comparison.caption_style_changed is False


def test_compare_versions_reports_an_identical_pair_as_unchanged(tmp_path: Path) -> None:
    _write_report(tmp_path)
    comparison = compare_versions(tmp_path, "original", "original")
    assert comparison.both_found is True
    assert comparison.span_changed is False
    assert comparison.caption_style_changed is False


def test_compare_versions_reports_a_missing_artifact_rather_than_raising(tmp_path: Path) -> None:
    _write_report(tmp_path)
    comparison = compare_versions(tmp_path, "original", "no-such-revision")
    assert comparison.both_found is False
    assert comparison.a.found is True
    assert comparison.b.found is False


def test_compare_versions_never_claims_a_change_against_a_missing_artifact(tmp_path: Path) -> None:
    """The trap this avoids: an unfound artifact has `None` for every field, so a naive
    inequality against a real one would report both dimensions as "changed" — a confident,
    wrong answer where `both_found=False` is the honest one."""
    _write_report(tmp_path)
    comparison = compare_versions(tmp_path, "original", "nothing-here")
    assert comparison.span_changed is False
    assert comparison.caption_style_changed is False


# --- propose_render (D-A25) ---------------------------------------------------------------------


def test_propose_render_reports_a_missing_revision_as_invalid(tmp_path: Path) -> None:
    _write_report(tmp_path)
    proposal = propose_render(tmp_path, "never-committed")
    assert proposal.valid is False
    assert "no revision record" in (proposal.violation or "")


def test_propose_render_refuses_an_already_rendered_revision(tmp_path: Path) -> None:
    _write_report(tmp_path)
    _approve_boundary(tmp_path, "done", 50, 4200)
    record_path = tmp_path / "revisions" / "done.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["status"] = "rendered"
    record_path.write_text(json.dumps(record), encoding="utf-8")
    proposal = propose_render(tmp_path, "done")
    assert proposal.valid is False
    assert "approved_pending_render" in (proposal.violation or "")


def test_propose_render_refuses_a_run_with_no_persisted_selected_sentences(tmp_path: Path) -> None:
    """The same D-A7 precondition `render_boundary_revision` itself enforces — mirrored here so
    a proposal cannot call renderable something the render function would refuse."""
    _write_report(tmp_path)
    _approve_boundary(tmp_path, "r1", 50, 4200)
    _write_report(tmp_path, selected_sentences=[])
    proposal = propose_render(tmp_path, "r1")
    assert proposal.valid is False
    assert "selected sentences" in (proposal.violation or "")


def test_propose_render_refuses_a_tampered_illegal_boundary(tmp_path: Path) -> None:
    """`commit_boundary_revision` already refused an illegal span, so reaching this means the
    record was hand-edited since — `propose_render` re-checks the real invariant rather than
    trusting the status string, exactly as `render_boundary_revision` does before encoding."""
    _write_report(tmp_path)
    _approve_boundary(tmp_path, "tampered", 50, 4200)
    record_path = tmp_path / "revisions" / "tampered.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["proposed_final_out_ms"] = 2000  # now ends before the 4100 ms anchor
    record_path.write_text(json.dumps(record), encoding="utf-8")
    proposal = propose_render(tmp_path, "tampered")
    assert proposal.valid is False
    assert "no longer legal" in (proposal.violation or "")


def test_propose_render_refuses_a_present_but_falsy_kind(tmp_path: Path) -> None:
    """Only an *absent* `kind` defaults to boundary (a pre-D-A12 record). `""` is present and
    not a kind `render_boundary_revision` accepts — calling it renderable would let
    `commit_render` record an APPROVED delta for a render that then raises."""
    _write_report(tmp_path)
    _approve_boundary(tmp_path, "blank-kind", 50, 4200)
    record_path = tmp_path / "revisions" / "blank-kind.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["kind"] = ""
    record_path.write_text(json.dumps(record), encoding="utf-8")
    proposal = propose_render(tmp_path, "blank-kind")
    assert proposal.valid is False
    assert "unknown revision kind" in (proposal.violation or "")


def test_propose_render_still_accepts_a_pre_d_a12_record_with_no_kind(tmp_path: Path) -> None:
    """The control for the test above: an *absent* `kind` must still default to boundary, or the
    falsy-kind fix would have silently broken every record written before D-A12."""
    _write_report(tmp_path)
    _approve_boundary(tmp_path, "old-style", 50, 4200)
    record_path = tmp_path / "revisions" / "old-style.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    del record["kind"]
    record_path.write_text(json.dumps(record), encoding="utf-8")
    assert propose_render(tmp_path, "old-style").kind == "boundary"


def test_propose_render_agrees_with_what_the_render_functions_actually_refuse(
    tmp_path: Path,
) -> None:
    """The property `propose_render`'s docstring claims and nothing enforced until now.

    That docstring says "every check here mirrors a real precondition
    `render_boundary_revision`/`render_caption_revision` themselves enforce". A mirror with no
    equivalence test is exactly how `run_quality_checks` drifted from `Clip.assert_renderable()`
    — it accepted `auto_pass` alone after the render gate had been tightened to require
    `human_reviewed`, and only that pair's own equivalence test caught it (D-A26). This is the
    same guard for this pair.

    The dangerous direction is **propose says valid, render refuses**: an agent told a revision
    is ready to render, for something the gate throws out. Every variant below therefore checks
    both sides against each other rather than against a hand-written expectation.

    Needs no ffmpeg: every precondition these functions enforce raises before any encode starts,
    which is itself part of what the equivalence asserts.
    """
    checked = 0
    for label, mutate in (
        ("no revision record at all", lambda w: (w / "revisions" / "r.json").unlink()),
        ("status is not approved_pending_render", lambda w: _set_status(w, "rendered")),
        ("the run has no clip", lambda w: _write_report(w, clip=None)),
        (
            "the run predates persisted selected_sentences",
            lambda w: _write_report(w, selected_sentences=[]),
        ),
        (
            "the recorded boundary was tampered into an illegal span",
            lambda w: _set_field(w, "proposed_final_out_ms", 2_000),
        ),
    ):
        work = tmp_path / label.replace(" ", "-")[:40]
        _write_report(work)
        _approve_boundary(work, "r", 50, 4_200)
        mutate(work)

        proposal = propose_render(work, "r")
        raised: Exception | None = None
        try:
            render_boundary_revision(work, "r")
        except (
            FileNotFoundError,
            ValueError,
            BoundaryInvariantViolated,
            CaptionsOutsideClip,
        ) as exc:
            raised = exc

        verdict = f"raised {type(raised).__name__}" if raised else "accepted it"
        assert proposal.valid is (raised is None), (
            f"{label}: propose_render said valid={proposal.valid} while "
            f"render_boundary_revision {verdict} — the two disagree about the "
            f"same precondition."
        )
        checked += 1
    assert checked == 5, f"only {checked} variants compared; the equivalence went vacuous"


def _set_status(work_dir: Path, status: str) -> None:
    path = work_dir / "revisions" / "r.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["status"] = status
    path.write_text(json.dumps(record), encoding="utf-8")


def _set_field(work_dir: Path, key: str, value: object) -> None:
    path = work_dir / "revisions" / "r.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record[key] = value
    path.write_text(json.dumps(record), encoding="utf-8")


def test_propose_render_writes_nothing(tmp_path: Path) -> None:
    _write_report(tmp_path)
    _approve_boundary(tmp_path, "r1", 50, 4200)
    before = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file()}
    propose_render(tmp_path, "r1")
    after = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file()}
    assert after == before


# --- commit_render (D-A25): the refusals, and the record ----------------------------------------


def test_commit_render_refuses_an_invalid_proposal_without_asking_for_approval(
    tmp_path: Path,
) -> None:
    _write_report(tmp_path)
    proposal = propose_render(tmp_path, "never-committed")
    asked: list[str] = []

    def confirm(prompt: str) -> bool:
        asked.append(prompt)
        return True

    with pytest.raises(RevisionRejected, match="cannot render"):
        commit_render(tmp_path, proposal, "hawa", ReasonCode.PREFERENCE, confirm=confirm)
    assert asked == [], "an invalid proposal must never reach the approval prompt"
    (delta,) = read_decision_deltas(tmp_path / "decisions.jsonl")
    assert delta.outcome is DecisionOutcome.REFUSED_INVALID
    assert delta.kind == "render"
    assert delta.media_id == "never-committed", (
        "a render decision is about one revision, so the delta is recorded under its id"
    )


def test_commit_render_refuses_an_unattributed_approval(tmp_path: Path) -> None:
    _write_report(tmp_path)
    _approve_boundary(tmp_path, "r1", 50, 4200)
    proposal = propose_render(tmp_path, "r1")
    with pytest.raises(RevisionRejected, match="unattributed"):
        commit_render(tmp_path, proposal, "   ", ReasonCode.PREFERENCE, confirm=lambda _: True)
    deltas = read_decision_deltas(tmp_path / "decisions.jsonl")
    assert deltas[-1].outcome is DecisionOutcome.REFUSED_UNATTRIBUTED
    assert deltas[-1].kind == "render"


def test_commit_render_refuses_a_decline_and_renders_nothing(tmp_path: Path) -> None:
    _write_report(tmp_path)
    _approve_boundary(tmp_path, "r1", 50, 4200)
    proposal = propose_render(tmp_path, "r1")
    with pytest.raises(RevisionRejected, match="declined"):
        commit_render(tmp_path, proposal, "hawa", ReasonCode.ACCIDENT, confirm=lambda _: False)
    assert not (tmp_path / "revisions" / "r1.mp4").exists()
    deltas = read_decision_deltas(tmp_path / "decisions.jsonl")
    assert deltas[-1].outcome is DecisionOutcome.DECLINED
    assert deltas[-1].reason_code is ReasonCode.ACCIDENT
    assert deltas[-1].approved_by == "hawa"
