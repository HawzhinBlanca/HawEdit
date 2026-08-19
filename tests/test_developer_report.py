"""`export_developer_report`'s data model: composition, sanitization, and the JSONL ledger.

`build_developer_report` is pure and gets ordinary coverage here. `write_developer_report` is
the only write in `developer_report.py` and is not a tool any agent registers — checked from
the agent side in `test_diagnostics_agent.py`, not here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hawedit.developer_report import (
    DeveloperReport,
    SanitizationError,
    build_developer_report,
    read_developer_reports,
    write_developer_report,
)


def a_report(**overrides: object) -> DeveloperReport:
    fields: dict[str, object] = {
        "summary": "boundary revision accepts a span past the source's own duration",
        "reproduction_steps": (
            "run the pipeline on a 4162 ms fixture",
            "propose_boundary_revision(work, final_in_ms=0, final_out_ms=999999)",
        ),
        "expected_behavior": (
            "propose_boundary_revision should refuse a span past media_duration_ms"
        ),
        "actual_behavior": "the proposal is reported valid",
        "suspected_component": "boundary.py's assert_boundary_invariant",
        "workflow_id": "wf-123",
        "artifact_ids": ("report.json",),
    }
    fields.update(overrides)
    return build_developer_report(**fields)  # type: ignore[arg-type]


# --- DeveloperReport validation ------------------------------------------------------------


def test_a_well_formed_report_constructs() -> None:
    report = a_report()
    assert report.summary
    assert report.sequence == 1


def test_a_report_needs_a_summary() -> None:
    with pytest.raises(ValueError, match="summary"):
        a_report(summary="   ")


def test_a_report_needs_at_least_one_reproduction_step() -> None:
    with pytest.raises(ValueError, match="reproduction step"):
        a_report(reproduction_steps=())


def test_a_reproduction_step_must_not_be_blank() -> None:
    with pytest.raises(ValueError, match="not be blank"):
        a_report(reproduction_steps=("do the thing", "   "))


def test_a_report_needs_expected_behavior() -> None:
    with pytest.raises(ValueError, match="expected behavior"):
        a_report(expected_behavior=" ")


def test_a_report_needs_actual_behavior() -> None:
    with pytest.raises(ValueError, match="actual behavior"):
        a_report(actual_behavior=" ")


def test_a_report_needs_a_suspected_component() -> None:
    with pytest.raises(ValueError, match="suspected component"):
        a_report(suspected_component=" ")


def test_workflow_id_and_artifact_ids_are_optional() -> None:
    report = a_report(workflow_id=None, artifact_ids=())
    assert report.workflow_id is None
    assert report.artifact_ids == ()


# --- sanitization: no Kurdish-script content in a report about the application -------------


def test_kurdish_script_in_the_summary_is_refused() -> None:
    with pytest.raises(SanitizationError, match="summary"):
        a_report(summary="ڕۆژنامەوانی broke the pipeline")


def test_kurdish_script_in_a_reproduction_step_is_refused() -> None:
    with pytest.raises(SanitizationError, match=r"reproduction_steps\[1\]"):
        a_report(reproduction_steps=("run it", "with transcript ڕۆژ pasted in"))


def test_kurdish_script_in_expected_behavior_is_refused() -> None:
    with pytest.raises(SanitizationError, match="expected_behavior"):
        a_report(expected_behavior="should render ڕۆژ correctly")


def test_kurdish_script_in_actual_behavior_is_refused() -> None:
    with pytest.raises(SanitizationError, match="actual_behavior"):
        a_report(actual_behavior="renders ڕۆژ as boxes")


def test_kurdish_script_in_suspected_component_is_refused() -> None:
    with pytest.raises(SanitizationError, match="suspected_component"):
        a_report(suspected_component="captions.py — ڕۆژ handling")


def test_english_prose_about_kurdish_handling_is_accepted() -> None:
    """The control case: describing a Kurdish-text defect in English, without quoting the
    text itself, must not trip the sanitizer — the rule is about the script, not the topic."""
    report = a_report(
        summary="Kurdish captions render as boxes on the fixture",
        actual_behavior="the shipped font is missing glyphs for several Sorani letters",
    )
    assert "boxes" in report.summary
    assert "glyphs" in report.actual_behavior


def test_ordinary_ascii_punctuation_is_not_flagged() -> None:
    """The control for the control: an unrelated field with no Kurdish text at all must pass."""
    report = a_report(summary="crash on empty transcript: IndexError at sentences.py:42")
    assert "IndexError" in report.summary


# --- the JSONL ledger ------------------------------------------------------------------------


def test_a_written_report_reads_back_unchanged(tmp_path: Path) -> None:
    report = a_report()
    write_developer_report(tmp_path, report)
    (read,) = read_developer_reports(tmp_path)
    assert read.summary == report.summary
    assert read.reproduction_steps == report.reproduction_steps
    assert read.workflow_id == report.workflow_id


def test_multiple_reports_append_and_sequence(tmp_path: Path) -> None:
    write_developer_report(tmp_path, a_report(summary="first defect"))
    write_developer_report(tmp_path, a_report(summary="second defect"))
    reports = read_developer_reports(tmp_path)
    assert [r.summary for r in reports] == ["first defect", "second defect"]
    assert [r.sequence for r in reports] == [1, 2]


def test_reading_with_none_filed_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_developer_reports(tmp_path)


def test_a_torn_last_line_is_tolerated(tmp_path: Path) -> None:
    write_developer_report(tmp_path, a_report())
    with (tmp_path / "developer_reports.jsonl").open("a", encoding="utf-8") as handle:
        handle.write('{"summary": "torn')
    assert len(read_developer_reports(tmp_path)) == 1


def test_write_is_the_only_thing_that_creates_the_ledger_file(tmp_path: Path) -> None:
    assert not (tmp_path / "developer_reports.jsonl").exists()
    write_developer_report(tmp_path, a_report())
    assert (tmp_path / "developer_reports.jsonl").is_file()


def test_workflow_id_is_the_one_report_field_not_glyph_sanitised() -> None:
    """Pins a real, narrow gap rather than implying it is closed.

    D-A17 says "every free-text field is refused if it contains a character from
    `KURDISH_REQUIRED_GLYPHS`". Measured across all six fields, five hold and `workflow_id`
    does not — found by testing the claim `tests/test_prompt_injection.py`'s declaration table
    made about it, rather than trusting the table (D-A29).

    Not silently fixed: `workflow_id` carries `hawedit-run:<resolved work_dir>`, so refusing
    Kurdish script would refuse a legitimate run whose directory is named in Kurdish. Closing it
    means choosing between that and constraining the field to a DBOS workflow id's real shape —
    a decision worth making deliberately. This test fails if either the gap closes or the other
    five stop holding, so neither can change unnoticed.
    """
    k = "ک"
    ok = dict(
        summary="s",
        expected_behavior="e",
        actual_behavior="a",
        suspected_component="c",
        workflow_id="w",
    )
    steps = ["a"]

    with pytest.raises(SanitizationError):
        build_developer_report(reproduction_steps=steps, **{**ok, "summary": f"x{k}y"})
    with pytest.raises(SanitizationError):
        build_developer_report(reproduction_steps=steps, **{**ok, "expected_behavior": f"x{k}y"})
    with pytest.raises(SanitizationError):
        build_developer_report(reproduction_steps=steps, **{**ok, "actual_behavior": f"x{k}y"})
    with pytest.raises(SanitizationError):
        build_developer_report(reproduction_steps=steps, **{**ok, "suspected_component": f"x{k}y"})
    with pytest.raises(SanitizationError):
        build_developer_report(reproduction_steps=[f"x{k}y"], **ok)

    # The gap, stated: this does not raise today.
    report = build_developer_report(reproduction_steps=steps, **{**ok, "workflow_id": f"x{k}y"})
    assert report.workflow_id == f"x{k}y", (
        "workflow_id started refusing Kurdish script. If that was deliberate, this test and "
        "the declaration table in tests/test_prompt_injection.py both need updating — and a "
        "run whose work_dir is named in Kurdish now needs checking."
    )
