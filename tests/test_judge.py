"""§3 Stage 4 — the editorial judge contract.

    KURDISH_EDITORIAL_JUDGE = gemini-2.5-pro     # pinned, today
    SHADOW                  = gemini-3.1-pro     # evaluated, not routed

    All routing goes through the `KURDISH_EDITORIAL_JUDGE` interface. Swapping providers
    must be a config change, never a refactor.

Stage 4 is the only stage that is entirely someone else's model, so what is buildable here is
the contract around it — and the contract is where §3 puts most of its warnings. Four of them
have teeth:

**"Evaluated, not routed."** `gemini-3.1-pro` exists in §7 as a shadow. A shadow that can
score a shipped clip is not a shadow. Routing refuses it, and so does §5's `Editorial` block.

**"Empirical beats newer."** §3 pins 2.5 Pro because there is tested evidence on Hawa's Sorani
and none for 3.1 Pro. Promotion requires beating the incumbent on the Sorani regression set —
not tying, not being newer, and not on an empty set. Same discipline as §8.1's canonical-model
rule, for the same reason.

**"Keep each request under 200K tokens to stay on the lower Pro price tier."** §3's own
with-video figure is ~360K tokens per source hour, which is *above* that ceiling — so the
mode that costs the most is also the one that cannot be a single request. That is arithmetic,
and it is checked as arithmetic.

**"Don't pay the judge twice for the same reasoning."** A candidate Path A already scored
arrives at Stage 4 with its verbal judgment attached (§3 Stage 3, `discovery.py`). Asking the
judge to re-derive it is a bill, not a bug, which is exactly why nothing would ever catch it.

There is also a discrepancy inside the blueprint, recorded rather than resolved: §3 Stage 4
lists *payoff location* and *hashtags* among the judge's outputs, and §5's frozen JSON contract
has no cell for either. §5 is frozen, so the verdict carries them and the projection to §5
drops them explicitly — see D-030.
"""

from __future__ import annotations

import json

import pytest

from hawedit.clip import DiscoveryPath
from hawedit.discovery import Candidate, merge_candidates
from hawedit.judge import (
    CANDIDATE_SLICE_TOKENS_PER_HOUR,
    FULL_TRANSCRIPT_TOKENS_PER_HOUR,
    PRO_TIER_TOKEN_CEILING,
    VIDEO_TOKENS_PER_SECOND,
    WITH_VIDEO_TOKENS_PER_HOUR,
    EditorialJudge,
    InputMode,
    JudgeFrame,
    JudgeRequest,
    JudgeVerdict,
    NotRoutable,
    RequestTooLarge,
    ShadowVerdict,
    decide_judge,
    estimate_cost_usd,
    route,
    video_tokens,
)
from hawedit.registry import WrongRole

JUDGE = "gemini-2.5-pro"
SHADOW = "gemini-3.1-pro"

TITLE = "ڕۆژنامەوانی کوردی لە هەولێر"
DESCRIPTION = "بابەتێکی گرنگ دەربارەی ڕۆژنامەوانی"


def a_verdict(**overrides: object) -> JudgeVerdict:
    fields: dict[str, object] = {
        "candidate_id": "c1",
        "hook_score": 0.88,
        "self_contained": True,
        "payoff_at_ms": 4_000,
        "meaning_fidelity": 0.94,
        "misleading_edit_risk": 0.03,
        "cultural_landing": 0.86,
        "narrative_role": "payoff",
        "title_ckb": TITLE,
        "description_ckb": DESCRIPTION,
        "hashtags_ckb": ("#کوردی", "#هەولێر"),
        "judge": JUDGE,
        "clip_in_ms": 1_000,
        "clip_out_ms": 9_000,
    }
    fields.update(overrides)
    return JudgeVerdict(**fields)  # type: ignore[arg-type]


# --- "evaluated, not routed" ---------------------------------------------------------------


class _Judge:
    def __init__(self, model_id: str) -> None:
        self.model_id = model_id

    def judge(self, request: JudgeRequest) -> JudgeVerdict:
        return a_verdict(judge=self.model_id, candidate_id=request.candidate_id)


def test_the_pinned_judge_routes() -> None:
    entry = route(_Judge(JUDGE))
    assert entry.model_id == JUDGE
    assert entry.routable


def test_the_shadow_is_refused_at_the_routing_boundary() -> None:
    """§4's comment is not decoration: `# evaluated, not routed`.

    A shadow that can be routed is an incumbent nobody chose. This is the boundary that makes
    "switch only when 3.1 Pro beats 2.5 Pro" enforceable rather than a note in a document.
    """
    with pytest.raises(NotRoutable, match="evaluated, not routed"):
        route(_Judge(SHADOW))


def test_a_model_that_is_not_a_judge_at_all_is_refused() -> None:
    """Audit finding #8's rule at Stage 4's door: §7 membership is not suitability."""
    with pytest.raises(WrongRole, match="editorial judge"):
        route(_Judge("PySceneDetect"))


def test_a_shadow_verdict_is_a_different_type_from_a_routed_one() -> None:
    """The shadow still has to run — it is evaluated. It must not be *mistakable* for output.

    Two names for the same shape would let a shadow verdict reach §5's editorial block through
    any function annotated loosely enough. A distinct type makes that a typecheck failure.
    """
    shadow = ShadowVerdict(verdict=a_verdict(judge=SHADOW), incumbent=JUDGE)
    assert shadow.verdict.judge == SHADOW
    assert not isinstance(shadow, JudgeVerdict)


def test_a_shadow_verdict_cannot_be_built_from_the_pinned_judge() -> None:
    """A "shadow" run of the incumbent compares it against itself and always ties."""
    with pytest.raises(ValueError, match="incumbent"):
        ShadowVerdict(verdict=a_verdict(judge=JUDGE), incumbent=JUDGE)


def test_a_shadow_verdict_exists_because_the_shadow_is_evaluated() -> None:
    """The shadow has to be able to produce a verdict, or there is nothing to compare.

    Refusing to *construct* a shadow verdict would make "switch only when 3.1 Pro beats 2.5
    Pro" unenforceable for want of a 3.1 Pro result. Routability is a question about shipping,
    not about existing.
    """
    assert a_verdict(judge=SHADOW).judge == SHADOW


def test_a_shadow_verdict_cannot_become_a_clips_editorial_block() -> None:
    """The boundary that actually matters: where an opinion becomes part of a clip."""
    with pytest.raises(NotRoutable, match="evaluated, not routed"):
        a_verdict(judge=SHADOW).to_editorial()


def test_a_shadow_verdict_round_trips_through_to_dict_from_dict() -> None:
    """Added for `promotion.py`'s shadow-verdict ledger (D-A14) — a shadow opinion has to
    survive being written to `decisions.jsonl`'s sibling ledger and read back unchanged, the
    same round-trip `JudgeVerdict.to_dict`/`from_dict` already has."""
    shadow = ShadowVerdict(verdict=a_verdict(judge=SHADOW), incumbent=JUDGE)
    assert ShadowVerdict.from_dict(shadow.to_dict()) == shadow


def test_section_5s_editorial_block_refuses_the_shadow_a_second_time() -> None:
    """Defence at both ends, because a verdict can arrive as JSON that never passed through
    `to_editorial()` at all."""
    from hawedit.clip import Editorial

    with pytest.raises(ValueError, match="routable"):
        Editorial(
            hook_score=0.8,
            self_contained=True,
            meaning_fidelity=0.9,
            misleading_edit_risk=0.1,
            cultural_landing=0.8,
            narrative_role="payoff",
            judge=SHADOW,
        )


# --- the verdict, and what §3 Stage 4 says it must contain ---------------------------------


def test_every_score_is_a_probability() -> None:
    for field in ("hook_score", "meaning_fidelity", "misleading_edit_risk", "cultural_landing"):
        with pytest.raises(ValueError, match=field):
            a_verdict(**{field: 1.4})


def test_the_payoff_must_fall_inside_the_clip() -> None:
    """§3 Stage 4 lists *payoff location* among the judge's outputs.

    A payoff outside the clip is not a payoff — it is evidence the judge scored a different
    span than the one being cut, and shipping it would put the punchline past the out point.
    """
    with pytest.raises(ValueError, match="payoff"):
        a_verdict(payoff_at_ms=20_000)
    with pytest.raises(ValueError, match="payoff"):
        a_verdict(payoff_at_ms=0)


def test_a_payoff_on_the_boundary_is_accepted() -> None:
    assert a_verdict(payoff_at_ms=1_000).payoff_at_ms == 1_000
    assert a_verdict(payoff_at_ms=9_000).payoff_at_ms == 9_000


def test_an_english_title_is_refused() -> None:
    """The single quietest way this system fails a Kurdish client.

    Everything downstream accepts a string. A judge that answers in English produces a clip
    that renders, uploads and reads as finished work — in the wrong language.
    """
    with pytest.raises(ValueError, match="Kurdish"):
        a_verdict(title_ckb="Kurdish journalism in Erbil")


def test_an_english_description_is_refused() -> None:
    with pytest.raises(ValueError, match="Kurdish"):
        a_verdict(description_ckb="An important piece about journalism")


def test_a_latin_hashtag_is_refused() -> None:
    with pytest.raises(ValueError, match="Kurdish"):
        a_verdict(hashtags_ckb=("#kurdish",))


def test_the_verdicts_kurdish_text_is_normalized() -> None:
    """§4.1 applies to text the system produces, not only to text it receives.

    A title typed with `ه`+ZWNJ and the same title with `ە` are different strings, so an
    unnormalized title makes the clip unfindable by its own name in the §2 index.
    """
    verdict = a_verdict(title_ckb="ئه‌مه‌ باشه‌")
    assert verdict.title_ckb == "ئەمە باشە"


def test_an_empty_title_is_refused() -> None:
    with pytest.raises(ValueError, match="title"):
        a_verdict(title_ckb="   ")


def test_hashtags_may_be_absent_but_not_blank() -> None:
    assert a_verdict(hashtags_ckb=()).hashtags_ckb == ()
    with pytest.raises(ValueError, match="hashtag"):
        a_verdict(hashtags_ckb=("",))


# --- the projection onto §5's frozen contract ---------------------------------------------


def test_the_verdict_projects_onto_section_5s_editorial_block() -> None:
    editorial = a_verdict().to_editorial()
    assert editorial.judge == JUDGE
    assert editorial.hook_score == 0.88
    assert editorial.narrative_role == "payoff"


def test_the_projection_carries_both_fields_section_3_names_and_section_5_lacked() -> None:
    """D-030 found the gap; D-033 closes it — additively, so nothing already written breaks.

    `payoff_at_ms` is a judgment and lands in `editorial`. `hashtags_ckb` is a delivery
    artifact and lands in `output`, beside the title and description it ships with.
    """
    verdict = a_verdict()
    assert verdict.to_editorial().to_dict()["payoff_at_ms"] == 4_000
    output = verdict.to_output(crop_target="speaker_face", durations=(30,))
    assert output.to_dict()["hashtags_ckb"] == ["#کوردی", "#هەولێر"]


def test_a_section_5_document_written_before_the_two_fields_existed_still_loads() -> None:
    """The whole reason the fields are optional: §5 documents predate them.

    A required field would make every clip artifact written before today unreadable, which is
    a migration rather than an addition — and §5 is a frozen contract, so an addition that
    breaks readers is not an addition.
    """
    from hawedit.clip import Editorial, Output

    legacy_editorial = {
        "hook_score": 0.8,
        "self_contained": True,
        "meaning_fidelity": 0.9,
        "misleading_edit_risk": 0.1,
        "cultural_landing": 0.8,
        "narrative_role": "payoff",
        "judge": JUDGE,
        "sv6d": None,
    }
    assert Editorial.from_dict(legacy_editorial).payoff_at_ms is None

    legacy_output = {
        "title_ckb": TITLE,
        "description_ckb": DESCRIPTION,
        "crop_target": "speaker_face",
        "caption_style": "word_highlight",
        "durations": [30],
    }
    assert Output.from_dict(legacy_output).hashtags_ckb == ()


def test_the_verdict_fills_section_5s_output_block_titles() -> None:
    output = a_verdict().to_output(crop_target="speaker_face", durations=(15, 30, 60))
    assert output.title_ckb == TITLE
    assert output.description_ckb == DESCRIPTION


def test_the_verdict_round_trips_through_json() -> None:
    verdict = a_verdict()
    assert JudgeVerdict.from_dict(json.loads(json.dumps(verdict.to_dict()))) == verdict


def test_a_persisted_verdict_refuses_scalar_hashtags() -> None:
    payload = a_verdict().to_dict()
    payload["hashtags_ckb"] = "#کوردی"
    with pytest.raises(ValueError, match="array of strings"):
        JudgeVerdict.from_dict(payload)


def test_a_persisted_verdict_refuses_non_object_visual_evidence() -> None:
    payload = a_verdict().to_dict()
    payload["sv6d"] = "not an object"
    with pytest.raises(ValueError, match="JSON object"):
        JudgeVerdict.from_dict(payload)


# --- input modes, the token ceiling, and cost ----------------------------------------------


def test_the_modes_carry_section_3s_own_figures() -> None:
    assert FULL_TRANSCRIPT_TOKENS_PER_HOUR == 20_000
    assert CANDIDATE_SLICE_TOKENS_PER_HOUR == 20_000
    assert WITH_VIDEO_TOKENS_PER_HOUR == 360_000
    assert PRO_TIER_TOKEN_CEILING == 200_000


def test_video_bills_by_the_second_at_the_rate_section_3_gives() -> None:
    assert video_tokens(60, resolution="default") == 60 * VIDEO_TOKENS_PER_SECOND["default"]
    assert video_tokens(60, resolution="low") == 60 * VIDEO_TOKENS_PER_SECOND["low"]
    assert video_tokens(60, resolution="low") < video_tokens(60, resolution="default")


def test_the_with_video_mode_cannot_be_one_request_for_a_source_hour() -> None:
    """§3's own numbers contradict a single request, and the arithmetic says so.

    ~360K tokens per source hour against a 200K ceiling. §3 already prescribes the fix —
    "20 × 60 s segments" — but a caller who batches an hour into one call would silently
    leave the lower Pro price tier and pay more for the mode that already costs the most.
    """
    with pytest.raises(RequestTooLarge, match="200"):
        JudgeRequest(
            candidate_id="c1",
            mode=InputMode.STAGE_4_WITH_VIDEO,
            tokens=WITH_VIDEO_TOKENS_PER_HOUR,
        ).assert_within_tier()


def test_a_segment_sized_request_stays_on_the_lower_tier() -> None:
    one_segment = JudgeRequest(
        candidate_id="c1",
        mode=InputMode.STAGE_4_WITH_VIDEO,
        tokens=video_tokens(60, resolution="default"),
    )
    one_segment.assert_within_tier()  # must not raise
    assert one_segment.tokens is not None
    assert one_segment.tokens < PRO_TIER_TOKEN_CEILING


def test_a_request_of_unknown_size_cannot_be_certified() -> None:
    """ "Unmeasured is None" — and None is not "small enough"."""
    with pytest.raises(RequestTooLarge, match="unknown"):
        JudgeRequest(
            candidate_id="c1", mode=InputMode.STAGE_4_TRANSCRIPT_FIRST
        ).assert_within_tier()


def test_cost_follows_section_3s_table() -> None:
    assert estimate_cost_usd(FULL_TRANSCRIPT_TOKENS_PER_HOUR) == pytest.approx(0.04, abs=0.005)
    assert estimate_cost_usd(WITH_VIDEO_TOKENS_PER_HOUR) == pytest.approx(0.72, abs=0.02)


def test_the_batch_api_halves_the_bill() -> None:
    full = estimate_cost_usd(WITH_VIDEO_TOKENS_PER_HOUR)
    batched = estimate_cost_usd(WITH_VIDEO_TOKENS_PER_HOUR, batched=True)
    assert batched == pytest.approx(full / 2)
    assert batched == pytest.approx(0.36, abs=0.02)


def test_cached_input_reads_at_a_tenth() -> None:
    assert estimate_cost_usd(100_000, cached=True) == pytest.approx(estimate_cost_usd(100_000) / 10)


# --- "don't pay the judge twice" ------------------------------------------------------------


def _survivor(verbal_score: float | None) -> object:
    verbal = Candidate("v1", "ep01", 1_000, 9_000, DiscoveryPath.VERBAL, rank=1, score=verbal_score)
    visual = Candidate("x1", "ep01", 1_100, 9_100, DiscoveryPath.VISUAL, rank=1, score=0.6)
    return merge_candidates([verbal], [visual])[0]


def test_a_survivor_that_path_a_already_scored_carries_its_score_into_stage_4() -> None:
    """§3 Stage 3: "Stage 4 should add *visual* context to survivors, not re-derive verbal
    judgment. Don't pay the judge twice for the same reasoning."."""
    request = JudgeRequest.for_survivor(_survivor(0.91), tokens=20_000)  # type: ignore[arg-type]
    assert request.carried_verbal_score == 0.91
    assert request.mode is InputMode.STAGE_4_TRANSCRIPT_FIRST


def test_rerunning_path_a_discovery_on_a_scored_survivor_is_refused() -> None:
    """The failure mode is a bill, not an error, which is why nothing else would catch it."""
    with pytest.raises(ValueError, match="already scored"):
        JudgeRequest.for_survivor(
            _survivor(0.91),  # type: ignore[arg-type]
            tokens=20_000,
            mode=InputMode.PATH_A_DISCOVERY,
        )


def test_a_survivor_path_a_never_saw_carries_no_score() -> None:
    """A visual-only candidate has no verbal judgment to reuse — and None is not 0.0."""
    visual_only = merge_candidates(
        [], [Candidate("x1", "ep01", 1_000, 9_000, DiscoveryPath.VISUAL, rank=1, score=0.6)]
    )[0]
    request = JudgeRequest.for_survivor(visual_only, tokens=20_000)
    assert request.carried_verbal_score is None


# --- the promotion rule: "empirical beats newer" -------------------------------------------


def test_a_shadow_that_loses_the_regression_set_is_not_promoted() -> None:
    decision = decide_judge(incumbent_wins=8, shadow_wins=2, ties=0)
    assert not decision.switch
    assert any("8" in reason for reason in decision.reasons)


def test_a_shadow_that_merely_ties_is_not_promoted() -> None:
    """§3: "Switch only when 3.1 Pro beats 2.5 Pro." A tie is not beating."""
    decision = decide_judge(incumbent_wins=5, shadow_wins=5, ties=0)
    assert not decision.switch
    assert any(
        "tie" in reason.lower() or "not beat" in reason.lower() for reason in decision.reasons
    )


def test_an_empty_regression_set_can_never_promote() -> None:
    """ "You have tested evidence that it performs well on your Sorani. You have none for 3.1."

    Promotion on an empty set is promotion on nothing, which is exactly the "newer is better"
    reasoning §3 is written to prevent.
    """
    decision = decide_judge(incumbent_wins=0, shadow_wins=0, ties=0)
    assert not decision.switch
    assert any("no regression set" in reason.lower() for reason in decision.reasons)


def test_a_shadow_that_clearly_wins_is_promotable() -> None:
    decision = decide_judge(incumbent_wins=2, shadow_wins=18, ties=0)
    assert decision.switch
    assert decision.challenger == SHADOW


def test_a_narrow_win_on_a_tiny_set_is_not_enough() -> None:
    """Two items and one more win is noise. §3 asks for evidence, and n=3 is not evidence."""
    decision = decide_judge(incumbent_wins=1, shadow_wins=2, ties=0)
    assert not decision.switch
    assert any("items" in reason for reason in decision.reasons)


def test_the_deprecation_date_is_not_a_reason_to_switch() -> None:
    """§3: "Treat this as a managed migration with a shadow test, not a deadline."

    The October 2026 date applies to Vertex AI, not the Developer API. A decision function
    that took a date would encode the deadline reading the blueprint explicitly rejects.
    """
    import inspect

    source = inspect.signature(decide_judge)
    assert not any(
        "date" in name or "deadline" in name or "deprecat" in name for name in source.parameters
    ), f"decide_judge takes a date-shaped argument: {list(source.parameters)}"


# --- the interface itself -------------------------------------------------------------------


def test_any_object_with_the_two_members_satisfies_the_interface() -> None:
    """§3: "Swapping providers must be a config change, never a refactor."."""
    assert isinstance(_Judge(JUDGE), EditorialJudge)


def test_an_object_missing_the_judge_method_does_not() -> None:
    class NotAJudge:
        model_id = JUDGE

    assert not isinstance(NotAJudge(), EditorialJudge)


# --- the Kurdish-script gate must survive §4.1 normalization ------------------------------
#
# `_kurdish_field` checked `_is_kurdish` on the RAW string and then returned
# `normalize_sorani(...)`. §4.1 normalization can remove the characters that satisfied the
# check: `٠١٢` is Arabic-Indic, inside the block the check tests, and `unify_numeral` rewrites
# it to `012`. Measured before the fix: `_kurdish_field('٠١٢', 'title_ckb')` returned `'012'` —
# a title with no Kurdish script at all, past the guard written to refuse exactly that. Found by
# the 2026-08-09 adversarial pass. D-076.


def test_a_field_that_loses_its_kurdish_script_to_normalization_is_refused() -> None:
    """Asserted on the constructed verdict, which is what §5 and delivery consume."""
    with pytest.raises(ValueError, match="no Kurdish script"):
        a_verdict(title_ckb="٠١٢")
    with pytest.raises(ValueError, match="no Kurdish script"):
        a_verdict(description_ckb="٠١٢")
    with pytest.raises(ValueError, match="no Kurdish script"):
        a_verdict(hashtags_ckb=("٠١٢",))


def test_the_refusal_names_the_normalized_form_that_failed() -> None:
    """`٠١٢` looks Kurdish to a reader; the message has to show what it became."""
    with pytest.raises(ValueError) as raised:
        a_verdict(title_ckb="٠١٢")
    assert "'012'" in str(raised.value), str(raised.value)


def test_kurdish_text_that_merely_contains_digits_is_still_accepted() -> None:
    """The control. A guard that refused anything normalization touches passes the tests above.

    Kurdish script plus Arabic-Indic digits must survive, with the digits unified per §4.1 —
    otherwise the fix would reject ordinary titles that happen to carry a number.
    """
    verdict = a_verdict(title_ckb="یک ٠١")
    assert verdict.title_ckb == "یک 01"


def test_normalization_is_still_applied_to_an_accepted_field() -> None:
    """The second control: checking after normalizing must not stop normalizing."""
    verdict = a_verdict(title_ckb="ئه‌مه‌ باشه‌")
    assert verdict.title_ckb == "ئەمە باشە"


# --- what adversarial pass #15 found revertible (D-128) ---------------------------------


def test_a_tie_above_the_regression_floor_is_still_not_a_win() -> None:
    """`test_a_shadow_that_merely_ties_is_not_promoted` measures the floor, not the tie.

    It calls `decide_judge(incumbent_wins=5, shadow_wins=5)` — **10 items**, below the 20-item
    floor — so the answer comes from *"10 items is below the 20-item floor"* and never reaches
    the tie rule. Measured. And its reason assertion looks for `"tie"`, which matches the word
    **ties** in the header line every decision carries, so it would pass whatever the tie rule
    did. Changing `shadow_wins <= incumbent_wins` to `<` left the whole suite green.

    Ten and ten clears the floor, so only the tie rule can answer.
    """
    decision = decide_judge(incumbent_wins=10, shadow_wins=10, ties=0)
    assert not decision.switch
    assert any("tied with" in reason for reason in decision.reasons), decision.reasons
    assert not any("below the" in reason for reason in decision.reasons), (
        "the floor answered this, so the tie rule is still unmeasured"
    )


def test_a_one_win_margin_above_the_floor_does_promote() -> None:
    """The control. Refusing every tie *and* every win satisfies the test above and would pin
    the incumbent for ever — §3 asks for a managed migration, not a locked door."""
    decision = decide_judge(incumbent_wins=10, shadow_wins=11, ties=0)
    assert decision.switch, decision.reasons
    assert any("beat" in reason for reason in decision.reasons)


def test_a_request_exactly_at_the_tier_ceiling_is_refused() -> None:
    """§3: "Keep each request **under** 200K tokens." Exactly 200,000 is not under it.

    The existing tests assert the constant and refuse requests well over it, so `>=` could
    become `>` unnoticed — the boundary followed the operator, which is D-098's and D-122's
    shape. At the ceiling a request leaves the lower Pro price tier while reading as compliant.
    """
    at_ceiling = JudgeRequest(
        candidate_id="at-ceiling",
        mode=InputMode.STAGE_4_WITH_VIDEO,
        tokens=PRO_TIER_TOKEN_CEILING,
    )
    with pytest.raises(RequestTooLarge, match="ceiling"):
        at_ceiling.assert_within_tier()

    # The control: one token below it is compliant, so this is a boundary and not a blanket
    # refusal of the with-video mode §3 prescribes.
    JudgeRequest(
        candidate_id="under-ceiling",
        mode=InputMode.STAGE_4_WITH_VIDEO,
        tokens=PRO_TIER_TOKEN_CEILING - 1,
    ).assert_within_tier()


def test_more_keyframes_than_section_3_prescribes_are_refused() -> None:
    """§3 Stage 4's payload is "~20 keyframes", and the cap had no test.

    Inline image bytes are billed, so an unbounded count is a cost defect as well as a contract
    one — D-126 found the same module's frames could come from anywhere in the media.
    """
    frames = tuple(
        JudgeFrame(timestamp_ms=index * 100, mime_type="image/jpeg", data=b"\xff\xd8jpeg")
        for index in range(21)
    )
    with pytest.raises(ValueError, match="at most 20"):
        JudgeRequest(
            candidate_id="too-many",
            mode=InputMode.STAGE_4_TRANSCRIPT_FIRST,
            tokens=1_000,
            keyframes=frames,
        )
    # The control: exactly 20 is what §3 prescribes and must be accepted. The span is given
    # because `JudgeRequest` also refuses frames from outside the candidate — the >20 check runs
    # first, which is why the refusal above is the count and not the span.
    JudgeRequest(
        candidate_id="exactly-twenty",
        mode=InputMode.STAGE_4_TRANSCRIPT_FIRST,
        tokens=1_000,
        keyframes=frames[:20],
        clip_in_ms=0,
        clip_out_ms=2_100,
    )
