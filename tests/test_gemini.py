"""The real §3 Stage 4 judge, tested without a key and without spending anything.

Every call goes through an injected transport. A suite that needed a live key to pass would
push people toward committing one, and `AGENTS.md` forbids exactly that — so the API contract
is exercised against recorded response shapes and the live path is one opt-in script.

What is worth testing here is not "does it call the API". It is the set of ways a model
integration fails while looking like it worked:

* the model answers in English, and every type downstream accepts a `str`;
* the model puts the payoff outside the clip, and the punchline ships past the out point;
* the model omits a field, and a default fills in a judgement nobody made;
* a 400 is retried three times, billing three times for one malformed request;
* a confidential transcript is uploaded before §3's governance box is answered.

Each of those is a test below. The last one is the only one with legal consequences.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from hawedit2.gemini import (
    VERDICT_SCHEMA,
    GeminiJudge,
    GeminiUnavailable,
    Governance,
    JudgeUnusable,
    count_tokens,
)
from hawedit2.judge import InputMode, JudgeRequest, RequestTooLarge
from hawedit2.registry import WrongRole

KEY = "test-key-not-real"
TITLE = "ڕۆژنامەوانی کوردی لە هەولێر"
DESCRIPTION = "بابەتێکی گرنگ دەربارەی ڕۆژنامەوانی کوردی"


def a_request(**overrides: Any) -> JudgeRequest:
    fields: dict[str, Any] = {
        "candidate_id": "c1",
        "mode": InputMode.STAGE_4_TRANSCRIPT_FIRST,
        "text_ckb": "ڕۆژنامەوانی کوردی لە هەولێر.",
        "clip_in_ms": 1_000,
        "clip_out_ms": 9_000,
    }
    fields.update(overrides)
    return JudgeRequest(**fields)


def verdict_fields(**overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "hook_score": 0.88,
        "self_contained": True,
        "payoff_at_ms": 4_000,
        "meaning_fidelity": 0.94,
        "misleading_edit_risk": 0.03,
        "cultural_landing": 0.86,
        "narrative_role": "payoff",
        "title_ckb": TITLE,
        "description_ckb": DESCRIPTION,
        "hashtags_ckb": ["#کوردی"],
    }
    fields.update(overrides)
    return fields


class Api:
    """A recording transport that answers countTokens and generateContent."""

    def __init__(self, tokens: int = 1_200, **overrides: Any) -> None:
        self.tokens = tokens
        self.fields = verdict_fields(**overrides)
        self.calls: list[str] = []

    def __call__(self, url: str, body: bytes | None = None) -> tuple[int, str]:
        self.calls.append(url.split("?")[0].rsplit("/", 1)[-1])
        if "countTokens" in url:
            return 200, json.dumps({"totalTokens": self.tokens})
        return 200, json.dumps(
            {"candidates": [{"content": {"parts": [{"text": json.dumps(self.fields)}]}}]}
        )


def a_judge(transport: Any, **kwargs: Any) -> GeminiJudge:
    kwargs.setdefault("sleep", lambda _s: None)
    return GeminiJudge(api_key=KEY, transport=transport, **kwargs)


# --- the happy path, and what it must still enforce ---------------------------------------


def test_a_verdict_comes_back_fully_validated() -> None:
    verdict = a_judge(Api()).judge(a_request())
    assert verdict.judge == "gemini-2.5-pro"
    assert verdict.candidate_id == "c1"
    assert verdict.payoff_at_ms == 4_000
    assert verdict.hashtags_ckb == ("#کوردی",)


def test_the_clip_span_comes_from_the_request_not_the_model() -> None:
    """The model is told the span; it does not get to redefine it.

    A judge that could move the boundaries would be doing Stage 5's job with none of Stage 5's
    inputs, and Kurdish invariant #2 is enforced on the boundary the fusion produced.
    """
    verdict = a_judge(Api()).judge(a_request(clip_in_ms=2_000, clip_out_ms=6_000))
    assert (verdict.clip_in_ms, verdict.clip_out_ms) == (2_000, 6_000)


def test_the_prompt_carries_the_transcript_and_the_span() -> None:
    judge = a_judge(Api())
    prompt = judge._prompt(a_request())
    assert "ڕۆژنامەوانی" in prompt
    assert "1000" in prompt and "9000" in prompt
    assert "Sorani" in prompt


def test_tokens_are_counted_before_the_billed_call() -> None:
    """§3's ceiling is about money, so it is checked against a real count, not a guess."""
    api = Api()
    a_judge(api).judge(a_request())
    assert api.calls[0].endswith("countTokens")
    assert api.calls[1].endswith("generateContent")


def test_the_response_schema_is_sent_rather_than_requested_in_prose() -> None:
    """ "Reply in JSON please" is how a stage acquires a 1% failure rate."""
    sent: list[dict[str, Any]] = []

    def transport(url: str, body: bytes | None = None) -> tuple[int, str]:
        if body:
            sent.append(json.loads(body))
        return Api()(url, body)

    a_judge(transport).judge(a_request())
    generation = sent[-1]["generationConfig"]
    assert generation["responseMimeType"] == "application/json"
    assert generation["responseSchema"] == VERDICT_SCHEMA
    assert generation["temperature"] == 0.0, (
        "a judge that disagrees with itself makes §8.2's regression comparison measure "
        "sampling noise rather than model quality"
    )


# --- the ways a model integration fails while looking like it worked ----------------------


def test_an_english_title_from_the_model_is_refused() -> None:
    """The quietest failure available. Every type downstream accepts a `str`."""
    with pytest.raises(JudgeUnusable, match="Kurdish"):
        a_judge(Api(title_ckb="Kurdish journalism in Erbil")).judge(a_request())


def test_a_payoff_outside_the_clip_is_refused() -> None:
    with pytest.raises(JudgeUnusable, match="payoff"):
        a_judge(Api(payoff_at_ms=99_000)).judge(a_request())


def test_a_score_out_of_range_is_refused() -> None:
    with pytest.raises(JudgeUnusable, match="hook_score"):
        a_judge(Api(hook_score=1.7)).judge(a_request())


def test_an_omitted_field_is_named_rather_than_defaulted() -> None:
    """A default here would invent a judgement nobody made."""
    api = Api()
    del api.fields["misleading_edit_risk"]
    with pytest.raises(JudgeUnusable, match="misleading_edit_risk"):
        a_judge(api).judge(a_request())


def test_a_non_json_response_is_refused() -> None:
    def transport(url: str, body: bytes | None = None) -> tuple[int, str]:
        if "countTokens" in url:
            return 200, json.dumps({"totalTokens": 10})
        return 200, json.dumps({"candidates": [{"content": {"parts": [{"text": "sorry!"}]}}]})

    with pytest.raises(JudgeUnusable, match="not JSON"):
        a_judge(transport).judge(a_request())


def test_an_empty_response_is_refused() -> None:
    def transport(url: str, body: bytes | None = None) -> tuple[int, str]:
        if "countTokens" in url:
            return 200, json.dumps({"totalTokens": 10})
        return 200, json.dumps({"candidates": []})

    with pytest.raises(JudgeUnusable, match="no content"):
        a_judge(transport).judge(a_request())


def test_a_request_with_no_transcript_is_refused_before_any_call() -> None:
    api = Api()
    with pytest.raises(JudgeUnusable, match="no transcript"):
        a_judge(api).judge(a_request(text_ckb=""))
    assert api.calls == [], "nothing should have been sent"


# --- money: the tier ceiling and retries ---------------------------------------------------


def test_a_request_over_the_tier_ceiling_is_refused_before_the_billed_call() -> None:
    """§3: keep each request under 200K tokens to stay on the lower Pro price tier."""
    api = Api(tokens=250_000)
    with pytest.raises(RequestTooLarge, match="200"):
        a_judge(api).judge(a_request())
    assert "generateContent" not in api.calls


def test_a_malformed_request_is_not_retried() -> None:
    """A 400 means this request is wrong. Retrying bills three times for one mistake."""
    calls: list[str] = []

    def transport(url: str, body: bytes | None = None) -> tuple[int, str]:
        calls.append(url)
        if "countTokens" in url:
            return 200, json.dumps({"totalTokens": 10})
        return 400, json.dumps({"error": {"message": "Invalid argument"}})

    with pytest.raises(GeminiUnavailable, match="refused"):
        a_judge(transport).judge(a_request())
    assert sum(1 for c in calls if "generateContent" in c) == 1


def test_a_rate_limit_is_retried_and_then_given_up_on() -> None:
    calls: list[str] = []

    def transport(url: str, body: bytes | None = None) -> tuple[int, str]:
        calls.append(url)
        if "countTokens" in url:
            return 200, json.dumps({"totalTokens": 10})
        return 429, json.dumps({"error": {"message": "Resource exhausted"}})

    with pytest.raises(GeminiUnavailable, match="3 attempts"):
        a_judge(transport).judge(a_request())
    assert sum(1 for c in calls if "generateContent" in c) == 3


def test_a_transient_failure_that_clears_produces_a_verdict() -> None:
    state = {"n": 0}

    def transport(url: str, body: bytes | None = None) -> tuple[int, str]:
        if "countTokens" in url:
            return 200, json.dumps({"totalTokens": 10})
        state["n"] += 1
        if state["n"] == 1:
            return 503, json.dumps({"error": {"message": "unavailable"}})
        return Api()(url, body)

    assert a_judge(transport).judge(a_request()).candidate_id == "c1"


def test_an_api_error_message_never_contains_the_key() -> None:
    """The key rides in the query string; an error that echoed the URL would leak it."""

    def transport(url: str, body: bytes | None = None) -> tuple[int, str]:
        if "countTokens" in url:
            return 200, json.dumps({"totalTokens": 10})
        return 403, json.dumps({"error": {"message": "Permission denied"}})

    with pytest.raises(GeminiUnavailable) as caught:
        a_judge(transport).judge(a_request())
    assert KEY not in str(caught.value)


# --- §3's governance box, as a check rather than a paragraph -------------------------------


def test_confidential_material_without_zero_data_retention_is_refused() -> None:
    """§3 Stage 3: for COMMS and KAAE material, ZDR is "mandatory, not advisory".

    The failure this prevents is not technical. Full-transcript discovery sends 100% of a
    client's transcript to Google, and §3 asks for that to be confirmed before the first
    client job — a paragraph nobody re-reads, so it is a value that has to be supplied.
    """
    judge = a_judge(Api(), governance=Governance(confidential=True))
    with pytest.raises(GeminiUnavailable, match="mandatory, not advisory"):
        judge.judge(a_request())


def test_claimed_zero_data_retention_must_name_who_confirmed_it() -> None:
    """An unattributed confirmation is not a confirmation."""
    judge = a_judge(Api(), governance=Governance(confidential=True, zero_data_retention=True))
    with pytest.raises(GeminiUnavailable, match="nobody is recorded"):
        judge.judge(a_request())


def test_confirmed_confidential_material_proceeds() -> None:
    judge = a_judge(
        Api(),
        governance=Governance(confidential=True, zero_data_retention=True, confirmed_by="Hawa"),
    )
    assert judge.judge(a_request()).candidate_id == "c1"


def test_non_confidential_material_needs_no_confirmation() -> None:
    assert a_judge(Api()).judge(a_request()).candidate_id == "c1"


# --- §7, before anything is billed ---------------------------------------------------------


def test_the_shadow_cannot_be_constructed_as_the_judge() -> None:
    """§3 Stage 4: gemini-3.1-pro is "evaluated, not routed"."""
    from hawedit2.judge import NotRoutable

    with pytest.raises(NotRoutable):
        a_judge(Api(), model_id="gemini-3.1-pro")


def test_a_model_outside_section_7_cannot_be_constructed() -> None:
    with pytest.raises((WrongRole, LookupError, ValueError)):
        a_judge(Api(), model_id="gpt-4o")


def test_a_missing_key_names_the_panel_that_fixes_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr("hawedit2.gemini.read_credential", lambda _n=None: None)
    with pytest.raises(GeminiUnavailable, match="hawedit2.credentials"):
        GeminiJudge(api_key=None, transport=Api())


# --- countTokens ----------------------------------------------------------------------------


def test_count_tokens_returns_the_apis_number() -> None:
    assert count_tokens("text", KEY, transport=Api(tokens=4_242)) == 4_242


def test_count_tokens_failure_is_not_silently_zero() -> None:
    """A zero would read as "this request is free and definitely under the ceiling"."""

    def failing(_url: str, _body: bytes | None = None) -> tuple[int, str]:
        return 500, "{}"

    with pytest.raises(GeminiUnavailable, match="countTokens"):
        count_tokens("text", KEY, transport=failing)
