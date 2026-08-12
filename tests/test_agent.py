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
from pathlib import Path

import pytest

pytest.importorskip("pydantic_ai")
dbos = pytest.importorskip("dbos")

from hawedit.agent import (  # noqa: E402
    CandidateComparison,
    Deps,
    RunExplanation,
    RunInspection,
    app_manifest,
    build_agent,
    compare_candidates,
    explain_run_state,
    inspect_run,
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


def test_the_built_agent_has_exactly_the_three_read_only_tools(tmp_path: Path) -> None:
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
    assert tool_names == {"inspect_run_tool", "explain_run_state_tool", "compare_candidates_tool"}


# --- the plain functions, against real report shapes -----------------------------------------


def test_app_manifest_reports_a_real_installed_version() -> None:
    manifest = app_manifest()
    assert manifest.read_only is True
    assert manifest.hawedit_version, "an empty version string is not a fact about the build"


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
