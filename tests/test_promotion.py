"""Shadow-verdict persistence and the judge promotion/rollback gate (D-A14).

`judge.py`'s `decide_judge` is pure and already tested (`test_judge.py`); this file checks the
part D-A14 actually adds — that its recommendation becomes a recorded, rollback-able version
only through a real human gate, the same refusal discipline `test_proposals.py` holds
`commit_boundary_revision` to.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hawedit.judge import KURDISH_EDITORIAL_JUDGE, JudgeDecision, JudgeVerdict, ShadowVerdict
from hawedit.promotion import (
    PromotionOutcome,
    PromotionRecord,
    PromotionRejected,
    current_judge,
    promote_judge,
    read_shadow_verdicts,
    record_shadow_verdict,
    rollback_judge,
)

JUDGE = "gemini-2.5-pro"
SHADOW = "gemini-3.1-pro"


def a_shadow_verdict(**overrides: object) -> ShadowVerdict:
    fields: dict[str, object] = {
        "candidate_id": "c1",
        "hook_score": 0.88,
        "self_contained": True,
        "payoff_at_ms": 4_000,
        "meaning_fidelity": 0.94,
        "misleading_edit_risk": 0.03,
        "cultural_landing": 0.86,
        "narrative_role": "payoff",
        "title_ckb": "ڕۆژنامەوانی کوردی لە هەولێر",
        "description_ckb": "بابەتێکی گرنگ دەربارەی ڕۆژنامەوانی",
        "hashtags_ckb": ("#کوردی",),
        "judge": SHADOW,
        "clip_in_ms": 1_000,
        "clip_out_ms": 9_000,
    }
    fields.update(overrides)
    return ShadowVerdict(verdict=JudgeVerdict(**fields), incumbent=JUDGE)  # type: ignore[arg-type]


_WINNING_DECISION = JudgeDecision(
    incumbent=JUDGE, challenger=SHADOW, switch=True, reasons=("beat the incumbent on 25 items",)
)
_LOSING_DECISION = JudgeDecision(
    incumbent=JUDGE, challenger=SHADOW, switch=False, reasons=("lost to the incumbent",)
)


# --- shadow-verdict persistence, per run ----------------------------------------------------


def test_a_recorded_shadow_verdict_reads_back_unchanged(tmp_path: Path) -> None:
    verdict = a_shadow_verdict()
    record_shadow_verdict(tmp_path, verdict)
    (read,) = read_shadow_verdicts(tmp_path)
    assert read == verdict


def test_multiple_shadow_verdicts_append_rather_than_overwrite(tmp_path: Path) -> None:
    record_shadow_verdict(tmp_path, a_shadow_verdict(candidate_id="c1"))
    record_shadow_verdict(tmp_path, a_shadow_verdict(candidate_id="c2"))
    verdicts = read_shadow_verdicts(tmp_path)
    assert [v.verdict.candidate_id for v in verdicts] == ["c1", "c2"]


def test_reading_shadow_verdicts_with_none_recorded_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_shadow_verdicts(tmp_path)


def test_a_torn_last_shadow_verdict_line_is_tolerated(tmp_path: Path) -> None:
    record_shadow_verdict(tmp_path, a_shadow_verdict())
    with (tmp_path / "shadow_verdicts.jsonl").open("a", encoding="utf-8") as handle:
        handle.write('{"verdict": {"candidate_id": "torn"')
    assert len(read_shadow_verdicts(tmp_path)) == 1


# --- PromotionRecord validation --------------------------------------------------------------


def test_a_promotion_record_needs_a_component() -> None:
    with pytest.raises(ValueError, match="no component"):
        PromotionRecord(
            component="",
            version=SHADOW,
            outcome=PromotionOutcome.PROMOTED,
            approved_by="hawa",
            sequence=1,
        )


def test_a_promotion_record_needs_an_approver() -> None:
    with pytest.raises(ValueError, match="no approver"):
        PromotionRecord(
            component="judge",
            version=SHADOW,
            outcome=PromotionOutcome.PROMOTED,
            approved_by=" ",
            sequence=1,
        )


def test_a_promotion_record_sequence_starts_at_one() -> None:
    with pytest.raises(ValueError, match="sequence starts at 1"):
        PromotionRecord(
            component="judge",
            version=SHADOW,
            outcome=PromotionOutcome.PROMOTED,
            approved_by="hawa",
            sequence=0,
        )


# --- current_judge: the pinned default until something is promoted --------------------------


def test_current_judge_is_the_pinned_default_with_no_ledger(tmp_path: Path) -> None:
    assert current_judge(tmp_path / "judge_promotions.jsonl") == KURDISH_EDITORIAL_JUDGE


def test_current_judge_reflects_the_latest_promotion(tmp_path: Path) -> None:
    ledger = tmp_path / "judge_promotions.jsonl"
    promote_judge(_WINNING_DECISION, "hawa", ledger_path=ledger, confirm=lambda _: True)
    assert current_judge(ledger) == SHADOW


# --- promote_judge: the gate's three refusals -------------------------------------------------


def test_promote_refuses_a_decision_that_did_not_recommend_switching(tmp_path: Path) -> None:
    ledger = tmp_path / "judge_promotions.jsonl"
    asked: list[str] = []

    def confirm(prompt: str) -> bool:
        asked.append(prompt)
        return True

    with pytest.raises(PromotionRejected, match="did not recommend switching"):
        promote_judge(_LOSING_DECISION, "hawa", ledger_path=ledger, confirm=confirm)
    assert asked == [], "a losing decision must never reach the approval prompt"
    assert not ledger.exists()


def test_promote_refuses_an_unattributed_approval(tmp_path: Path) -> None:
    ledger = tmp_path / "judge_promotions.jsonl"
    with pytest.raises(PromotionRejected, match="unattributed"):
        promote_judge(_WINNING_DECISION, "  ", ledger_path=ledger, confirm=lambda _: True)
    assert not ledger.exists()


def test_promote_refuses_a_decline_and_writes_nothing(tmp_path: Path) -> None:
    ledger = tmp_path / "judge_promotions.jsonl"
    with pytest.raises(PromotionRejected, match="declined"):
        promote_judge(_WINNING_DECISION, "hawa", ledger_path=ledger, confirm=lambda _: False)
    assert not ledger.exists()


def test_promote_writes_the_record_only_after_a_yes(tmp_path: Path) -> None:
    ledger = tmp_path / "judge_promotions.jsonl"
    path = promote_judge(_WINNING_DECISION, "hawa", ledger_path=ledger, confirm=lambda _: True)
    assert path == ledger
    record = json.loads(ledger.read_text(encoding="utf-8").strip())
    assert record["component"] == "judge"
    assert record["version"] == SHADOW
    assert record["outcome"] == "promoted"
    assert record["approved_by"] == "hawa"
    assert record["sequence"] == 1
    assert record["reasons"] == ["beat the incumbent on 25 items"]


def test_two_promotions_sequence_correctly(tmp_path: Path) -> None:
    ledger = tmp_path / "judge_promotions.jsonl"
    promote_judge(_WINNING_DECISION, "hawa", ledger_path=ledger, confirm=lambda _: True)
    second = JudgeDecision(incumbent=SHADOW, challenger="gemini-4.0-pro", switch=True, reasons=())
    promote_judge(second, "hawa2", ledger_path=ledger, confirm=lambda _: True)
    assert current_judge(ledger) == "gemini-4.0-pro"


# --- rollback_judge: restores the immediately preceding version -------------------------------


def test_rollback_refuses_with_no_promotion_recorded(tmp_path: Path) -> None:
    ledger = tmp_path / "judge_promotions.jsonl"
    with pytest.raises(PromotionRejected, match="nothing to roll back"):
        rollback_judge("hawa", ledger_path=ledger, confirm=lambda _: True)


def test_rollback_refuses_an_unattributed_approval(tmp_path: Path) -> None:
    ledger = tmp_path / "judge_promotions.jsonl"
    promote_judge(_WINNING_DECISION, "hawa", ledger_path=ledger, confirm=lambda _: True)
    with pytest.raises(PromotionRejected, match="unattributed"):
        rollback_judge(" ", ledger_path=ledger, confirm=lambda _: True)


def test_rollback_refuses_a_decline(tmp_path: Path) -> None:
    ledger = tmp_path / "judge_promotions.jsonl"
    promote_judge(_WINNING_DECISION, "hawa", ledger_path=ledger, confirm=lambda _: True)
    with pytest.raises(PromotionRejected, match="declined"):
        rollback_judge("hawa", ledger_path=ledger, confirm=lambda _: False)
    assert current_judge(ledger) == SHADOW, "a declined rollback must not change the active judge"


def test_rollback_after_one_promotion_restores_the_pinned_default(tmp_path: Path) -> None:
    ledger = tmp_path / "judge_promotions.jsonl"
    promote_judge(_WINNING_DECISION, "hawa", ledger_path=ledger, confirm=lambda _: True)
    rollback_judge("hawa", ledger_path=ledger, confirm=lambda _: True)
    assert current_judge(ledger) == KURDISH_EDITORIAL_JUDGE


def test_rollback_after_two_promotions_restores_the_first_challenger(tmp_path: Path) -> None:
    ledger = tmp_path / "judge_promotions.jsonl"
    promote_judge(_WINNING_DECISION, "hawa", ledger_path=ledger, confirm=lambda _: True)
    second = JudgeDecision(incumbent=SHADOW, challenger="gemini-4.0-pro", switch=True, reasons=())
    promote_judge(second, "hawa2", ledger_path=ledger, confirm=lambda _: True)
    rollback_judge("hawa3", ledger_path=ledger, confirm=lambda _: True)
    assert current_judge(ledger) == SHADOW


def test_rolling_back_twice_toggles_rather_than_unwinds_further(tmp_path: Path) -> None:
    """Documented behaviour, not a bug: rollback restores *the previous* version (singular),
    not an arbitrary point in history — this module's own stated scope."""
    ledger = tmp_path / "judge_promotions.jsonl"
    promote_judge(_WINNING_DECISION, "hawa", ledger_path=ledger, confirm=lambda _: True)
    rollback_judge("hawa2", ledger_path=ledger, confirm=lambda _: True)
    assert current_judge(ledger) == KURDISH_EDITORIAL_JUDGE
    rollback_judge("hawa3", ledger_path=ledger, confirm=lambda _: True)
    assert current_judge(ledger) == SHADOW


def test_the_default_ledger_path_is_under_dot_hawedit() -> None:
    from hawedit.promotion import DEFAULT_PROMOTION_LEDGER

    assert DEFAULT_PROMOTION_LEDGER.parts[:2] == (".hawedit", "judge_promotions.jsonl")
