"""M1.5 — §3 Stage 1's validator escalation rule.

§3 Stage 1: "compute mean token log-probability per segment from CTC posteriors. Route the
bottom quartile, and any segment where LLM-7B and CTC-3B disagree materially, to the
validator. **Never escalate on duration or word-count heuristics.**"

That prohibition is the interesting part and is tested directly: a long segment and a short
one with the same acoustic confidence and the same agreement must receive the same decision.
Escalating by length is the cheap proxy everyone reaches for, and it spends the validator's
4 GiB on segments that were never in doubt.
"""

from __future__ import annotations

import pytest

from hawedit2.escalation import (
    DEFAULT_DISAGREEMENT_CER,
    SegmentScore,
    materially_disagree,
    select_for_validation,
)

CLEAN = "ئەمە زۆر باشە"


def score(
    segment_id: str,
    mean_logprob: float,
    ctc_text: str = CLEAN,
    llm_text: str = CLEAN,
    duration_s: float = 10.0,
) -> SegmentScore:
    return SegmentScore(
        segment_id=segment_id,
        mean_logprob=mean_logprob,
        llm_text=llm_text,
        ctc_text=ctc_text,
        duration_s=duration_s,
    )


# --- the bottom quartile ---------------------------------------------------------------


def test_the_lowest_quartile_by_log_probability_is_escalated() -> None:
    scores = [score(f"s{i}", mean_logprob=-0.1 * i) for i in range(8)]
    decisions = select_for_validation(scores)
    escalated = {d.segment_id for d in decisions if d.escalate}
    assert escalated == {"s7", "s6"}, "8 segments -> bottom 2"


def test_the_quartile_is_computed_from_the_worst_scores_not_a_fixed_threshold() -> None:
    """A uniformly excellent batch still has a worst quarter — that is what a quartile is."""
    scores = [score(f"s{i}", mean_logprob=-0.01 * i) for i in range(4)]
    escalated = {d.segment_id for d in select_for_validation(scores) if d.escalate}
    assert escalated == {"s3"}


def test_too_few_segments_for_a_quartile_escalates_none_by_confidence() -> None:
    """With three segments there is no bottom quarter. Disagreement still applies."""
    scores = [score(f"s{i}", mean_logprob=-0.1 * i) for i in range(3)]
    assert not any(d.escalate for d in select_for_validation(scores))


def test_an_empty_batch_produces_no_decisions() -> None:
    assert select_for_validation([]) == ()


# --- material disagreement -------------------------------------------------------------


def test_identical_hypotheses_do_not_disagree() -> None:
    assert materially_disagree(CLEAN, CLEAN) is False


def test_an_encoding_difference_is_not_a_disagreement() -> None:
    """§4.1 again: the two models typing the same Kurdish differently is not disagreement."""
    assert materially_disagree("ئه‌مه‌ زۆر باشه‌", "ئەمە زۆر باشە") is False


def test_a_substantive_difference_is_a_disagreement() -> None:
    assert materially_disagree(CLEAN, "ئەمە زۆر خراپە") is True


def test_disagreement_escalates_a_confident_segment() -> None:
    """High confidence is not safety when the two models read the audio differently."""
    scores = [score(f"s{i}", mean_logprob=-0.01) for i in range(8)]
    scores[0] = score("s0", mean_logprob=-0.01, llm_text="ئەمە زۆر خراپە")
    decisions = {d.segment_id: d for d in select_for_validation(scores)}
    assert decisions["s0"].escalate
    assert "disagree" in decisions["s0"].reason


def test_the_disagreement_threshold_is_configurable() -> None:
    assert materially_disagree(CLEAN, "ئەمە زۆر باشەx", threshold_cer=0.9) is False
    assert materially_disagree(CLEAN, "ئەمە زۆر باشەx", threshold_cer=0.01) is True


def test_the_default_threshold_is_recorded_not_implicit() -> None:
    assert 0.0 < DEFAULT_DISAGREEMENT_CER < 1.0


# --- the prohibition §3 Stage 1 states explicitly --------------------------------------


def test_duration_does_not_influence_the_decision() -> None:
    """ "Never escalate on duration or word-count heuristics." Same confidence, same
    agreement, wildly different lengths — the decisions must match."""
    short = [score(f"s{i}", mean_logprob=-0.1 * i, duration_s=2.0) for i in range(8)]
    long = [score(f"s{i}", mean_logprob=-0.1 * i, duration_s=38.0) for i in range(8)]
    assert [d.escalate for d in select_for_validation(short)] == [
        d.escalate for d in select_for_validation(long)
    ]


def test_word_count_does_not_influence_the_decision() -> None:
    wordy = "ئەمە زۆر باشە و جوانە و گرنگە و باشترە"
    scores_a = [score(f"s{i}", mean_logprob=-0.1 * i) for i in range(8)]
    scores_b = [
        score(f"s{i}", mean_logprob=-0.1 * i, ctc_text=wordy, llm_text=wordy) for i in range(8)
    ]
    assert [d.escalate for d in select_for_validation(scores_a)] == [
        d.escalate for d in select_for_validation(scores_b)
    ]


# --- decisions explain themselves ------------------------------------------------------


def test_every_decision_carries_a_reason() -> None:
    scores = [score(f"s{i}", mean_logprob=-0.1 * i) for i in range(8)]
    for decision in select_for_validation(scores):
        assert decision.reason


def test_a_confidence_escalation_says_so() -> None:
    scores = [score(f"s{i}", mean_logprob=-0.1 * i) for i in range(8)]
    worst = next(d for d in select_for_validation(scores) if d.segment_id == "s7")
    assert "quartile" in worst.reason


def test_decisions_are_returned_for_every_segment_in_order() -> None:
    scores = [score(f"s{i}", mean_logprob=-0.1 * i) for i in range(8)]
    assert [d.segment_id for d in select_for_validation(scores)] == [f"s{i}" for i in range(8)]


def test_a_segment_with_no_ctc_confidence_is_refused() -> None:
    """§3 Stage 1 escalates on CTC posteriors. Without one there is nothing to rank on, and
    guessing would silently reintroduce a length heuristic."""
    with pytest.raises(ValueError, match="mean_logprob"):
        SegmentScore(
            segment_id="s",
            mean_logprob=0.5,  # positive: not a log-probability
            llm_text=CLEAN,
            ctc_text=CLEAN,
            duration_s=10.0,
        )
