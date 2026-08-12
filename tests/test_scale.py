"""Phase 5's trigger check, and a migration path bound to the code it describes (D-A15).

Two properties matter here, and neither is "the function runs": (1) the five trigger
conditions are the architecture record's own words, not a paraphrase that could drift from
them: and (2) `describe_migration_path()` names real modules and functions, checked to still
exist — the same binding discipline `test_claims.py` already holds README/PROGRESS to.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

from hawedit.scale import SCALE_TRIGGERS, evaluate_scale_triggers

ROOT = Path(__file__).resolve().parents[1]
ARCHITECTURE_DOC = ROOT / "AGENT_ARCHITECTURE_DEFINITIVE_2026-08-11.md"


def test_scale_triggers_are_numbered_one_through_five() -> None:
    assert [trigger.number for trigger in SCALE_TRIGGERS] == [1, 2, 3, 4, 5]


def test_every_trigger_condition_is_quoted_verbatim_from_the_architecture_record() -> None:
    """The record's own words, not a paraphrase — checked against the file itself so a future
    edit to either side is caught rather than silently drifting apart."""
    text = ARCHITECTURE_DOC.read_text(encoding="utf-8")
    missing = [t.number for t in SCALE_TRIGGERS if t.condition not in text]
    assert not missing, (
        f"trigger(s) {missing} do not appear verbatim in {ARCHITECTURE_DOC.name} — either this "
        f"module paraphrased the record, or the record changed and this module did not follow."
    )


def test_evaluate_refuses_a_missing_answer() -> None:
    answers = {t.number: False for t in SCALE_TRIGGERS if t.number != 3}
    with pytest.raises(ValueError, match=r"no answer given for trigger\(s\) \[3\]"):
        evaluate_scale_triggers(answers, assessed_by="hawa")


def test_evaluate_refuses_an_answer_for_an_unknown_trigger() -> None:
    answers = {t.number: False for t in SCALE_TRIGGERS} | {99: True}
    with pytest.raises(ValueError, match="do not exist"):
        evaluate_scale_triggers(answers, assessed_by="hawa")


def test_evaluate_refuses_an_unattributed_assessor() -> None:
    answers = {t.number: False for t in SCALE_TRIGGERS}
    with pytest.raises(ValueError, match="unattributed"):
        evaluate_scale_triggers(answers, assessed_by="  ")


def test_no_trigger_firing_does_not_recommend_migration() -> None:
    answers = {t.number: False for t in SCALE_TRIGGERS}
    assessment = evaluate_scale_triggers(answers, assessed_by="hawa")
    assert assessment.triggered == ()
    assert assessment.recommend_migration is False


def test_one_trigger_firing_recommends_migration_and_names_which_one() -> None:
    answers = {t.number: False for t in SCALE_TRIGGERS}
    answers[2] = True
    assessment = evaluate_scale_triggers(answers, assessed_by="hawa")
    assert [t.number for t in assessment.triggered] == [2]
    assert assessment.recommend_migration is True


def test_every_trigger_firing_is_reported_in_order() -> None:
    answers = {t.number: True for t in SCALE_TRIGGERS}
    assessment = evaluate_scale_triggers(answers, assessed_by="hawa")
    assert [t.number for t in assessment.triggered] == [1, 2, 3, 4, 5]


# --- the migration path is bound to real code, not free-floating prose -----------------------


def _migration_path_text() -> str:
    from hawedit.scale import describe_migration_path

    return describe_migration_path()


def test_migration_path_names_only_modules_that_exist() -> None:
    text = _migration_path_text()
    named = set(re.findall(r"`([a-z_]+\.py)`", text))
    assert named, "the migration path names no module at all — this test would prove nothing"
    on_disk = {p.name for p in (ROOT / "src" / "hawedit").glob("*.py")} | {
        p.name for p in (ROOT / "tests").glob("*.py")
    }
    missing = named - on_disk
    assert not missing, f"the migration path names modules that do not exist: {sorted(missing)}"


def test_migration_path_names_only_functions_that_exist() -> None:
    """Every backtick-quoted `bare_name(` is a function the prose claims is real."""
    text = _migration_path_text()
    named = sorted(set(re.findall(r"`([a-z_][a-z0-9_]*)\(", text)))
    assert named, "the migration path names no function at all — this test would prove nothing"
    module_names = ("durable_workflow", "durable", "events", "pipeline")
    missing = []
    for name in named:
        found = False
        for module_name in module_names:
            module = importlib.import_module(f"hawedit.{module_name}")
            if hasattr(module, name):
                found = True
                break
        if not found:
            missing.append(name)
    assert not missing, f"the migration path names functions that do not exist: {missing}"


def test_migration_path_states_durable_workflow_is_the_only_dbos_specific_module() -> None:
    """The claim that matters most, checked directly rather than trusted from the prose: grep
    the real source for who actually imports `durable_workflow.py`."""
    src = ROOT / "src" / "hawedit"
    importers = [
        p.name
        for p in src.glob("*.py")
        if p.name not in ("durable_workflow.py",)
        and re.search(r"^\s*from hawedit\.durable_workflow import", p.read_text("utf-8"), re.M)
    ]
    assert importers == ["durable.py"], (
        f"expected only durable.py to import durable_workflow.py, found: {importers}. The "
        f"migration path's claim that DBOS-specific code is isolated to one module is now false."
    )
