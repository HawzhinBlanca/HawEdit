"""Phase 2's read-only creative-director agent, checked against a real `report.json`.

Two layers, tested separately. The plain functions (`inspect_run`, `explain_run_state`,
`compare_candidates`) are unit-tested directly against real reports — one hand-built to cover
the "stopped early" and "candidates were rejected" shapes without paying for a real pipeline
run, one produced by an actual `run_durable` call so the field names this module reads are
checked against what `PipelineRun.to_dict()` genuinely emits rather than a fixture that could
drift from it. The agent itself is tested with `pydantic_ai.models.test.TestModel`, which never
calls a real provider — these tests prove the tools are wired (registered, `deps` reaches them,
the return values round-trip), not that any particular model gives a good answer, which this
module explicitly does not claim to control (see `agent.py`'s module docstring).
"""

from __future__ import annotations

import ast
import json
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest

pytest.importorskip("pydantic_ai")
dbos = pytest.importorskip("dbos")

from hawedit.agent import (  # noqa: E402
    TOOL_NAMES,
    CandidateComparison,
    Deps,
    RunExplanation,
    RunInspection,
    app_manifest,
    build_agent,
    compare_candidates,
    explain_run_state,
    inspect_run,
    run_quality_checks,
    run_timeline,
)
from hawedit.captions import find_ffmpeg  # noqa: E402
from hawedit.durable_workflow import configure_dbos, run_durable  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
AGENT_SRC = ROOT / "src" / "hawedit" / "agent.py"
FIXTURE = ROOT / "tests" / "fixtures" / "kurdish-speech-3cuts.mp4"

needs_ffmpeg = pytest.mark.skipif(find_ffmpeg() is None, reason="no ffmpeg — set HAWEDIT_FFMPEG")


@pytest.fixture(scope="module", autouse=True)
def _dbos_instance(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Same rationale as `test_durable.py`'s fixture: one launch, registry never destroyed."""
    db_path = tmp_path_factory.mktemp("dbos") / "test.sqlite"
    configure_dbos(system_database_url=f"sqlite:///{db_path}")
    yield
    dbos.DBOS.destroy()


def _write_report(work_dir: Path, **overrides: object) -> None:
    report: dict[str, object] = {
        "media_id": "fixture",
        "source": "x.mp4",
        "work_dir": str(work_dir),
        "complete": False,
        "skipped": ["transcript", "visual_index", "discovery", "editorial"],
        "ingest": {"skipped": False},
        "transcript": {
            "skipped": True,
            "stage": "transcript",
            "reason": "no Stage 1 producer was enabled.",
            "blocked_by": ["Stage 1 producer not enabled"],
        },
        "candidates": [],
        "rejected": [],
        "clip": None,
        "render": None,
        "delivery": None,
    }
    report.update(overrides)
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")


# --- read-only by construction, checked structurally ----------------------------------------


def test_agent_module_never_writes_a_file() -> None:
    """The property Phase 2 asks for — "make all proposals non-mutating" — proven, not stated.

    Walks `agent.py`'s own AST for any call whose name suggests a filesystem write
    (`write_text`, `write_bytes`, `open` with a write/append mode, `unlink`, `rename`,
    `replace`). A module that is read-only by construction has none of these; a docstring
    claiming it is read-only does not.
    """
    tree = ast.parse(AGENT_SRC.read_text(encoding="utf-8"))
    write_like = {"write_text", "write_bytes", "unlink", "rename", "replace", "mkdir", "rmdir"}
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name in write_like:
            offenders.append(f"line {node.lineno}: .{name}(...)")
        if name == "open":
            mode_arg = node.args[1] if len(node.args) > 1 else None
            mode_kw = next((kw.value for kw in node.keywords if kw.arg == "mode"), None)
            for candidate in (mode_arg, mode_kw):
                if isinstance(candidate, ast.Constant) and any(
                    flag in str(candidate.value) for flag in "wax"
                ):
                    offenders.append(f"line {node.lineno}: open(..., {candidate.value!r})")
    assert not offenders, f"agent.py contains a write-shaped call: {offenders}"


def test_the_built_agent_has_exactly_the_read_only_tools(tmp_path: Path) -> None:
    """`_function_toolset` is a private attribute — accepted here only because
    `pyproject.toml` pins `pydantic-ai-slim==2.28.0` exactly, so its shape cannot change under
    this test without a version bump this repo controls. A version bump that breaks the
    attribute fails this test loudly (`AttributeError`) rather than silently passing a check
    that stopped checking anything, which is the failure mode a private-API dependency risks.
    """
    from pydantic_ai.models.test import TestModel

    _write_report(tmp_path)
    agent = build_agent(TestModel(), Deps(work_dir=tmp_path))
    tool_names = {tool.name for tool in agent._function_toolset.tools.values()}
    assert tool_names == {
        "inspect_run",
        "explain_run_state",
        "compare_candidates",
        "run_timeline",
        "run_quality_checks",
        "inspect_project",
    }


def test_the_manifest_names_exactly_the_tools_the_agent_registers(tmp_path: Path) -> None:
    """The drift guard that makes the manifest worth showing a model at all.

    `build_agent` puts `app_manifest().as_prompt()` in the system prompt, and that paragraph
    tells the model which tools it can call. If `TOOL_NAMES` and the real registered toolset
    ever diverge, the model plans against tools that do not exist (or never learns about ones
    that do) — a failure that would show up as confusing model behaviour, not as an error.
    """
    from pydantic_ai.models.test import TestModel

    _write_report(tmp_path)
    agent = build_agent(TestModel(), Deps(work_dir=tmp_path))
    registered = {tool.name for tool in agent._function_toolset.tools.values()}
    assert set(app_manifest().tool_names) == registered
    assert set(TOOL_NAMES) == registered


# --- the plain functions, against real report shapes -----------------------------------------


def test_app_manifest_reports_a_real_installed_version() -> None:
    manifest = app_manifest()
    assert manifest.read_only is True
    assert manifest.hawedit_version, "an empty version string is not a fact about the build"


def test_the_manifest_actually_reaches_the_model(tmp_path: Path) -> None:
    """The defect this fixes (D-A8): `app_manifest()` existed, was exported and unit-tested, and
    was loaded by nothing — no model ever saw it. Asserted against the messages the model was
    actually sent, not against `build_agent`'s source.
    """
    from pydantic_ai.models.test import TestModel

    _write_report(tmp_path)
    agent = build_agent(TestModel(), Deps(work_dir=tmp_path))
    result = agent.run_sync("hello", deps=Deps(work_dir=tmp_path))
    system_parts = [
        part.content
        for message in result.all_messages()
        for part in getattr(message, "parts", ())
        if type(part).__name__ == "SystemPromptPart"
    ]
    combined = "\n".join(system_parts)
    assert "App manifest" in combined, f"no manifest in the system prompt: {combined!r}"
    assert app_manifest().hawedit_version in combined
    for tool_name in TOOL_NAMES:
        assert tool_name in combined, f"{tool_name} missing from the manifest the model saw"


def test_run_timeline_reads_the_event_ledger(tmp_path: Path) -> None:
    """The second half of D-A8: `agent.py`'s docstring claimed it read `events.jsonl` while no
    tool did. This is the capability that makes the claim true."""
    _write_report(tmp_path)
    ledger = [
        {
            "run_id": "fixture",
            "sequence": 1,
            "at_ms": 1000,
            "stage": "ingest",
            "state": "started",
            "reason": "",
        },
        {
            "run_id": "fixture",
            "sequence": 2,
            "at_ms": 1200,
            "stage": "ingest",
            "state": "completed",
            "reason": "",
        },
        {
            "run_id": "fixture",
            "sequence": 3,
            "at_ms": 1300,
            "stage": "transcript",
            "state": "skipped",
            "reason": "no Stage 1 producer was enabled.",
        },
    ]
    (tmp_path / "events.jsonl").write_text(
        "\n".join(json.dumps(event) for event in ledger) + "\n", encoding="utf-8"
    )
    timeline = run_timeline(tmp_path)
    assert timeline.available is True
    assert [event.stage for event in timeline.events] == ["ingest", "ingest", "transcript"]
    assert [event.state for event in timeline.events] == ["started", "completed", "skipped"]
    assert timeline.events[2].reason == "no Stage 1 producer was enabled."
    assert [event.sequence for event in timeline.events] == [1, 2, 3]


def test_a_non_durable_run_reports_no_ledger_rather_than_an_empty_one(tmp_path: Path) -> None:
    """ "No ledger was ever written" and "a ledger recorded nothing" are different facts, and
    `StageSkipped` is this codebase's own precedent for refusing to conflate them. Reported as
    a value rather than raised, because a run started through `hawedit` (not `hawedit-durable`)
    genuinely has no ledger and a model should be able to say so and carry on."""
    _write_report(tmp_path)
    timeline = run_timeline(tmp_path)
    assert timeline.available is False
    assert timeline.events == ()
    assert timeline.unavailable_reason is not None
    assert "events.jsonl" in timeline.unavailable_reason


def test_a_missing_ledger_does_not_end_an_agent_run(tmp_path: Path) -> None:
    """The behavioural half of the case above: `TestModel` calls every registered tool, so a
    tool that raised here would abort the whole conversation over an ordinary state."""
    from pydantic_ai.models.test import TestModel

    _write_report(tmp_path)
    agent = build_agent(TestModel(), Deps(work_dir=tmp_path))
    result = agent.run_sync("what happened?", deps=Deps(work_dir=tmp_path))
    assert '"available":false' in result.output.replace(" ", "")


def test_inspect_run_reads_the_stage_1_stopped_report(tmp_path: Path) -> None:
    _write_report(tmp_path)
    inspection = inspect_run(tmp_path)
    assert isinstance(inspection, RunInspection)
    assert inspection.complete is False
    assert "transcript" in inspection.skipped_stages
    assert inspection.candidate_count == 0
    assert inspection.clip_id is None
    assert inspection.delivery_complete is False


def test_inspect_run_reports_a_complete_delivered_run(tmp_path: Path) -> None:
    _write_report(
        tmp_path,
        complete=True,
        skipped=[],
        clip={"clip_id": "fixture-s0-1"},
        render={"path": str(tmp_path / "fixture-s0-1.mp4")},
        delivery={"srt_path": str(tmp_path / "fixture-s0-1.srt")},
    )
    inspection = inspect_run(tmp_path)
    assert inspection.complete is True
    assert inspection.clip_id == "fixture-s0-1"
    assert inspection.render_path == str(tmp_path / "fixture-s0-1.mp4")
    assert inspection.delivery_complete is True


def test_inspect_run_raises_a_clear_error_with_no_report(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="report.json"):
        inspect_run(tmp_path)


def test_explain_run_state_quotes_the_recorded_reason_not_a_paraphrase(tmp_path: Path) -> None:
    _write_report(tmp_path)
    explanation = explain_run_state(tmp_path)
    assert isinstance(explanation, RunExplanation)
    assert explanation.stopped_at_stage == "transcript"
    assert explanation.reason == "no Stage 1 producer was enabled."
    assert explanation.blocked_by == ("Stage 1 producer not enabled",)


def test_explain_run_state_names_the_first_stage_that_stopped_it(tmp_path: Path) -> None:
    """Editorial and boundary are both skipped in a real Stage-4-less run — the first in §3's
    order (editorial, since transcript ran here) is the cause; boundary is a consequence."""
    _write_report(
        tmp_path,
        skipped=["editorial", "boundary"],
        editorial={
            "skipped": True,
            "stage": "editorial",
            "reason": "no Stage 4 judge or persisted verdict was supplied.",
            "blocked_by": ["Stage 4 judgment not enabled"],
        },
        boundary={
            "skipped": True,
            "stage": "boundary",
            "reason": "no complete sentence in the selection, so §5 has no anchor.",
            "blocked_by": (),
        },
    )
    explanation = explain_run_state(tmp_path)
    assert explanation.stopped_at_stage == "editorial"
    assert explanation.reason == "no Stage 4 judge or persisted verdict was supplied."


def test_explain_run_state_on_a_complete_run_names_no_stopping_stage(tmp_path: Path) -> None:
    _write_report(tmp_path, complete=True, skipped=[])
    explanation = explain_run_state(tmp_path)
    assert explanation.complete is True
    assert explanation.stopped_at_stage is None
    assert explanation.reason is None


def test_compare_candidates_lists_survivors_and_rejections_with_reasons(tmp_path: Path) -> None:
    _write_report(
        tmp_path,
        candidates=[
            {
                "candidate_id": "fixture-0",
                "media_id": "fixture",
                "in_ms": 100,
                "out_ms": 4100,
                "discovery_path": "verbal",
                "sources": ["fixture-0"],
                "verbal_rank": 0,
                "visual_rank": None,
                "verbal_score": 0.9,
                "visual_score": None,
                "sv6d": None,
            }
        ],
        rejected=[
            {
                "media_id": "fixture",
                "in_ms": 4200,
                "out_ms": 8000,
                "discovery_path": "visual",
                "reject_reason": "below the survivor floor",
            }
        ],
        clip={"clip_id": "fixture-s0-1", "in_ms": 100, "out_ms": 4100},
    )
    comparison = compare_candidates(tmp_path)
    assert isinstance(comparison, CandidateComparison)
    assert len(comparison.candidates) == 1
    assert comparison.candidates[0].candidate_id == "fixture-0"
    assert comparison.candidates[0].discovery_path == "verbal"
    assert len(comparison.rejected) == 1
    assert comparison.rejected[0].reject_reason == "below the survivor floor"
    assert comparison.final_clip_span_ms == (100, 4100)


def test_compare_candidates_does_not_guess_which_candidate_won(tmp_path: Path) -> None:
    """No field on `CandidateComparison` claims to identify the selected candidate — the module
    docstring's own reasoning: a span-matching heuristic can be wrong once boundary fusion has
    moved the span, and a wrong guess is worse than the honest gap this asserts stays a gap."""
    fields = set(CandidateComparison.model_fields)
    assert fields == {"media_id", "candidates", "rejected", "final_clip_span_ms"}


# --- run_quality_checks (D-A18) ---------------------------------------------------------------


def test_run_quality_checks_raises_with_no_report(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="report.json"):
        run_quality_checks(tmp_path)


def test_run_quality_checks_reports_no_clip(tmp_path: Path) -> None:
    _write_report(tmp_path)  # clip=None by default
    report = run_quality_checks(tmp_path)
    assert report.all_passed is False
    assert [c.name for c in report.checks] == ["has_clip"]


_GOOD_BOUNDARY: dict[str, object] = {
    "anchor_in_ms": 100,
    "anchor_out_ms": 4100,
    "final_in_ms": 0,
    "final_out_ms": 4300,
    "in_extended_by": "vad_onset",
    "out_extended_by": "tail",
    "sentence_complete": True,
    "confidence": None,
}


_GOOD_QC: dict[str, object] = {"auto_pass": True, "flags": [], "human_reviewed": False}
_PRESENT: dict[str, object] = {"present": True}


def _clip_dict(
    boundary: dict[str, object] | None = _GOOD_BOUNDARY,
    qc: dict[str, object] | None = _GOOD_QC,
    editorial: dict[str, object] | None = _PRESENT,
    output: dict[str, object] | None = _PRESENT,
) -> dict[str, object]:
    return {
        "clip_id": "fixture-0",
        "boundary": boundary,
        "qc": qc,
        "editorial": editorial,
        "output": output,
    }


def test_run_quality_checks_all_pass(tmp_path: Path) -> None:
    _write_report(tmp_path, clip=_clip_dict())
    report = run_quality_checks(tmp_path)
    assert report.all_passed is True
    assert {c.name for c in report.checks} == {
        "boundary_invariant",
        "qc_gate",
        "editorial_present",
        "output_present",
    }
    assert all(c.passed for c in report.checks)


def test_run_quality_checks_flags_an_illegal_boundary(tmp_path: Path) -> None:
    bad_boundary = {**_GOOD_BOUNDARY, "final_out_ms": 3000}  # ends before the anchor
    _write_report(tmp_path, clip=_clip_dict(boundary=bad_boundary))
    report = run_quality_checks(tmp_path)
    assert report.all_passed is False
    by_name = {c.name: c for c in report.checks}
    assert by_name["boundary_invariant"].passed is False
    assert "mid-sentence" in by_name["boundary_invariant"].detail
    # Itemized, not short-circuited: the other three still ran and still passed.
    assert by_name["qc_gate"].passed is True
    assert by_name["editorial_present"].passed is True
    assert by_name["output_present"].passed is True


def test_run_quality_checks_flags_a_missing_boundary(tmp_path: Path) -> None:
    _write_report(tmp_path, clip=_clip_dict(boundary=None))
    report = run_quality_checks(tmp_path)
    by_name = {c.name: c for c in report.checks}
    assert by_name["boundary_invariant"].passed is False
    assert "no boundary recorded" in by_name["boundary_invariant"].detail


def test_run_quality_checks_flags_a_missing_qc_record(tmp_path: Path) -> None:
    _write_report(tmp_path, clip=_clip_dict(qc=None))
    report = run_quality_checks(tmp_path)
    by_name = {c.name: c for c in report.checks}
    assert by_name["qc_gate"].passed is False
    assert report.all_passed is False


def test_run_quality_checks_flags_a_qc_record_that_has_not_passed(tmp_path: Path) -> None:
    _write_report(
        tmp_path, clip=_clip_dict(qc={"auto_pass": False, "flags": [], "human_reviewed": False})
    )
    report = run_quality_checks(tmp_path)
    by_name = {c.name: c for c in report.checks}
    assert by_name["qc_gate"].passed is False


def test_run_quality_checks_accepts_human_reviewed_without_auto_pass(tmp_path: Path) -> None:
    _write_report(
        tmp_path, clip=_clip_dict(qc={"auto_pass": False, "flags": [], "human_reviewed": True})
    )
    report = run_quality_checks(tmp_path)
    by_name = {c.name: c for c in report.checks}
    assert by_name["qc_gate"].passed is True


def test_run_quality_checks_flags_a_missing_editorial_block(tmp_path: Path) -> None:
    _write_report(tmp_path, clip=_clip_dict(editorial=None))
    report = run_quality_checks(tmp_path)
    by_name = {c.name: c for c in report.checks}
    assert by_name["editorial_present"].passed is False
    assert report.all_passed is False


def test_run_quality_checks_flags_a_missing_output_block(tmp_path: Path) -> None:
    _write_report(tmp_path, clip=_clip_dict(output=None))
    report = run_quality_checks(tmp_path)
    by_name = {c.name: c for c in report.checks}
    assert by_name["output_present"].passed is False
    assert report.all_passed is False


def test_run_quality_checks_agrees_with_assert_renderable(tmp_path: Path) -> None:
    """The property that matters most: `all_passed` and "would `Clip.assert_renderable()`
    raise" cannot honestly disagree. Built from a real `Clip`, not a hand-typed dict, so this
    checks the two real implementations against each other rather than against a shape that
    could itself have drifted from `clip.py`."""
    from hawedit.boundary import Boundary, BoundaryInvariantViolated
    from hawedit.clip import Clip, ClipTranscript, DiscoveryPath, Editorial, Output, Qc
    from hawedit.transcripts import AsrProvenance, Word

    boundary = Boundary(**_GOOD_BOUNDARY)  # type: ignore[arg-type]
    words = (Word(w="کوردی", start_ms=0, end_ms=300, conf=0.9),)
    good_clip = Clip(
        clip_id="fixture-0",
        media_id="fixture",
        in_ms=boundary.final_in_ms,
        out_ms=boundary.final_out_ms,
        discovery_path=DiscoveryPath.VERBAL,
        boundary=boundary,
        transcript=ClipTranscript(
            raw_ckb="کوردی",
            norm_ckb="کوردی",
            en_aux=None,
            words=words,
            asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
        ),
        editorial=Editorial(
            hook_score=0.8,
            self_contained=True,
            meaning_fidelity=0.9,
            misleading_edit_risk=0.05,
            cultural_landing=0.8,
            narrative_role="payoff",
            judge="gemini-2.5-pro",
        ),
        output=Output(
            title_ckb="t",
            description_ckb="d",
            crop_target="9:16",
            caption_style="line",
            durations=(30,),
        ),
        qc=Qc(auto_pass=True, flags=(), human_reviewed=False),
    )
    illegal_boundary = replace(boundary, final_out_ms=3000)  # ends before anchor_out_ms=4100
    for clip, should_raise in (
        (good_clip, False),
        (replace(good_clip, boundary=illegal_boundary, out_ms=3000), True),
        (replace(good_clip, qc=None), True),
        (replace(good_clip, qc=Qc(auto_pass=False, flags=(), human_reviewed=False)), True),
        (replace(good_clip, editorial=None), True),
        (replace(good_clip, output=None), True),
    ):
        raised = False
        try:
            clip.assert_renderable()
        except (BoundaryInvariantViolated, ValueError):
            raised = True
        assert raised is should_raise, (
            f"assert_renderable() raised={raised}, expected {should_raise}"
        )

        _write_report(tmp_path, clip=clip.to_dict())
        report = run_quality_checks(tmp_path)
        assert report.all_passed is (not should_raise), (
            f"run_quality_checks disagreed with assert_renderable: all_passed="
            f"{report.all_passed}, assert_renderable raised={raised}"
        )


# --- the agent, driven by TestModel — never a real provider ----------------------------------


def test_inspect_run_tool_reaches_the_scoped_work_dir(tmp_path: Path) -> None:
    from pydantic_ai.models.test import TestModel

    _write_report(tmp_path, complete=True, skipped=[])
    agent = build_agent(TestModel(), Deps(work_dir=tmp_path))
    result = agent.run_sync("is this run done?", deps=Deps(work_dir=tmp_path))
    assert '"complete":true' in result.output.replace(" ", "")


def test_two_agents_scoped_to_different_work_dirs_stay_scoped(tmp_path: Path) -> None:
    """`work_dir` comes from `Deps` at construction, never a model-suppliable argument — the
    security property `agent.py`'s module docstring states. Two agents built against two
    different directories must never cross-read each other's report."""
    from pydantic_ai.models.test import TestModel

    a, b = tmp_path / "a", tmp_path / "b"
    _write_report(a, media_id="run-a")
    _write_report(b, media_id="run-b")

    agent_a = build_agent(TestModel(), Deps(work_dir=a))
    agent_b = build_agent(TestModel(), Deps(work_dir=b))

    result_a = agent_a.run_sync("what run is this?", deps=Deps(work_dir=a))
    result_b = agent_b.run_sync("what run is this?", deps=Deps(work_dir=b))

    assert "run-a" in result_a.output and "run-b" not in result_a.output
    assert "run-b" in result_b.output and "run-a" not in result_b.output


# --- against a real durable run, so the field names read here cannot drift from reality -------


@needs_ffmpeg
def test_the_tools_read_a_report_a_real_durable_run_actually_wrote(tmp_path: Path) -> None:
    work = tmp_path / "work"
    run_durable(
        [str(FIXTURE), "--work-dir", str(work), "--media-id", "fixture"],
        run_id="agent-inspection-case",
    )
    inspection = inspect_run(work)
    assert inspection.media_id == "fixture"
    assert inspection.complete is False  # no Stage 1 producer supplied

    explanation = explain_run_state(work)
    assert explanation.stopped_at_stage == "transcript"

    comparison = compare_candidates(work)
    assert comparison.candidates == ()
    assert comparison.final_clip_span_ms is None
