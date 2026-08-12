"""The decision-delta ledger, checked at the level it actually enforces things: construction.

`proposals.py`'s `commit_boundary_revision`/`commit_caption_revision` are what actually produce
`DecisionDelta` records in this codebase; this file is the data model on its own — validation,
the JSONL round-trip, and sequencing — the same split `test_events.py` and `events.py` have.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hawedit.learning import (
    DecisionDelta,
    DecisionOutcome,
    JsonlDecisionSink,
    ReasonCode,
    read_decision_deltas,
    record_decision_delta,
)

_PROPOSAL: dict[str, object] = {"proposed_final_in_ms": 0, "proposed_final_out_ms": 4500}


# --- DecisionDelta validation --------------------------------------------------------------


def test_an_approved_delta_needs_a_reason_code() -> None:
    with pytest.raises(ValueError, match="reason_code"):
        DecisionDelta(
            media_id="fixture",
            kind="boundary",
            outcome=DecisionOutcome.APPROVED,
            proposal=_PROPOSAL,
            sequence=1,
            approved_by="hawa",
        )


def test_a_declined_delta_needs_a_reason_code() -> None:
    with pytest.raises(ValueError, match="reason_code"):
        DecisionDelta(
            media_id="fixture",
            kind="boundary",
            outcome=DecisionOutcome.DECLINED,
            proposal=_PROPOSAL,
            sequence=1,
            approved_by="hawa",
        )


def test_a_refused_invalid_delta_must_not_carry_a_reason_code() -> None:
    with pytest.raises(ValueError, match="never reached a human"):
        DecisionDelta(
            media_id="fixture",
            kind="boundary",
            outcome=DecisionOutcome.REFUSED_INVALID,
            proposal=_PROPOSAL,
            sequence=1,
            reason_code=ReasonCode.PREFERENCE,
        )


def test_a_refused_unattributed_delta_must_not_carry_approved_by() -> None:
    with pytest.raises(ValueError, match="never reached a human"):
        DecisionDelta(
            media_id="fixture",
            kind="boundary",
            outcome=DecisionOutcome.REFUSED_UNATTRIBUTED,
            proposal=_PROPOSAL,
            sequence=1,
            approved_by="hawa",
        )


def test_an_approved_delta_needs_an_attributed_approver() -> None:
    with pytest.raises(ValueError, match="approved_by"):
        DecisionDelta(
            media_id="fixture",
            kind="boundary",
            outcome=DecisionOutcome.APPROVED,
            proposal=_PROPOSAL,
            sequence=1,
            reason_code=ReasonCode.PREFERENCE,
        )


def test_an_unknown_kind_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown decision kind"):
        DecisionDelta(
            media_id="fixture",
            kind="render_variant",
            outcome=DecisionOutcome.REFUSED_INVALID,
            proposal=_PROPOSAL,
            sequence=1,
        )


def test_sequence_must_be_positive() -> None:
    with pytest.raises(ValueError, match="sequence starts at 1"):
        DecisionDelta(
            media_id="fixture",
            kind="boundary",
            outcome=DecisionOutcome.REFUSED_INVALID,
            proposal=_PROPOSAL,
            sequence=0,
        )


def test_a_well_formed_approved_delta_constructs() -> None:
    delta = DecisionDelta(
        media_id="fixture",
        kind="boundary",
        outcome=DecisionOutcome.APPROVED,
        proposal=_PROPOSAL,
        sequence=1,
        reason_code=ReasonCode.PREFERENCE,
        approved_by="hawa",
    )
    assert delta.reason_code is ReasonCode.PREFERENCE


# --- the JSONL ledger, same shape as events.py's -------------------------------------------


def test_the_ledger_round_trips_every_field(tmp_path: Path) -> None:
    path = tmp_path / "decisions.jsonl"
    sink = JsonlDecisionSink(path)
    delta = DecisionDelta(
        media_id="fixture",
        kind="caption",
        outcome=DecisionOutcome.APPROVED,
        proposal={"proposed_caption_style": "word_highlight"},
        sequence=1,
        reason_code=ReasonCode.EXPERIMENT,
        approved_by="hawa",
    )
    sink(delta)
    sink.close()
    (read,) = read_decision_deltas(path)
    assert read == delta


def test_the_ledger_round_trips_a_refused_delta_with_no_reason_or_approver(
    tmp_path: Path,
) -> None:
    """`None` fields must survive JSON round-trip, not silently become the string `"None"` or
    be dropped and default wrong on the way back."""
    path = tmp_path / "decisions.jsonl"
    sink = JsonlDecisionSink(path)
    delta = DecisionDelta(
        media_id="fixture",
        kind="boundary",
        outcome=DecisionOutcome.REFUSED_INVALID,
        proposal=_PROPOSAL,
        sequence=1,
    )
    sink(delta)
    sink.close()
    (read,) = read_decision_deltas(path)
    assert read.reason_code is None
    assert read.approved_by is None


def test_read_raises_with_no_ledger(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_decision_deltas(tmp_path / "decisions.jsonl")


def test_a_torn_last_line_is_tolerated(tmp_path: Path) -> None:
    """Same crash-recovery property `events.py`'s `read_events` has: a write that landed
    mid-line must not lose every line that came before it."""
    path = tmp_path / "decisions.jsonl"
    sink = JsonlDecisionSink(path)
    sink(
        DecisionDelta(
            media_id="fixture",
            kind="boundary",
            outcome=DecisionOutcome.REFUSED_INVALID,
            proposal=_PROPOSAL,
            sequence=1,
        )
    )
    sink.close()
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"media_id": "fixture", "kind": "boundary", "seque')  # torn
    deltas = read_decision_deltas(path)
    assert len(deltas) == 1


# --- record_decision_delta: sequencing and appending ----------------------------------------


def test_record_decision_delta_assigns_sequential_numbers(tmp_path: Path) -> None:
    first = record_decision_delta(
        tmp_path,
        "fixture",
        "boundary",
        DecisionOutcome.REFUSED_INVALID,
        _PROPOSAL,
    )
    second = record_decision_delta(
        tmp_path,
        "fixture",
        "boundary",
        DecisionOutcome.APPROVED,
        _PROPOSAL,
        reason_code=ReasonCode.PREFERENCE,
        approved_by="hawa",
    )
    assert first.sequence == 1
    assert second.sequence == 2
    deltas = read_decision_deltas(tmp_path / "decisions.jsonl")
    assert [d.sequence for d in deltas] == [1, 2]


def test_record_decision_delta_creates_the_ledger_file(tmp_path: Path) -> None:
    assert not (tmp_path / "decisions.jsonl").exists()
    record_decision_delta(
        tmp_path, "fixture", "caption", DecisionOutcome.REFUSED_UNATTRIBUTED, _PROPOSAL
    )
    assert (tmp_path / "decisions.jsonl").is_file()


def test_the_ledger_is_flushed_per_line_not_buffered(tmp_path: Path) -> None:
    """The property `JsonlEventSink` exists for, checked here too: a reader must see a
    just-recorded decision without the writer being closed first."""
    record_decision_delta(
        tmp_path, "fixture", "boundary", DecisionOutcome.REFUSED_INVALID, _PROPOSAL
    )
    raw = (tmp_path / "decisions.jsonl").read_text(encoding="utf-8")
    assert json.loads(raw.strip())["media_id"] == "fixture"
