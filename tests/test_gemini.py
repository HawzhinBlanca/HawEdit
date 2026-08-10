"""The real §3 Stage 4 judge, tested without a key and without spending anything.

Every call goes through an injected transport. A suite that needed a live key to pass would
push people toward committing one, and `AGENTS.md` forbids exactly that — so the API contract
is exercised against recorded response shapes and the live path is one opt-in script.

What is worth testing here is not "does it call the API". It is the set of ways a model
integration fails while looking like it worked:

* the model answers in English, and every type downstream accepts a `str`;
* the model puts the payoff outside the clip, and the punchline ships past the out point;
* the model omits a field, and a default fills in a judgement nobody made;
* an ambiguous network failure replays a billed non-idempotent generation;
* a confidential transcript is uploaded before §3's governance box is answered.

Each of those is a test below. The last one is the only one with legal consequences.
"""

from __future__ import annotations

import base64
import json
import sys
import urllib.request
from collections.abc import Callable, Mapping
from types import ModuleType
from typing import Any

import pytest

from hawedit.gemini import (
    VERDICT_SCHEMA,
    GeminiJudge,
    GeminiUnavailable,
    Governance,
    JudgeUnusable,
    VertexGeminiJudge,
    adc_access_token,
    count_tokens,
)
from hawedit.judge import (
    JUDGE_SHADOW,
    KURDISH_EDITORIAL_JUDGE,
    InputMode,
    JudgeFrame,
    JudgeRequest,
    NotRoutable,
    RequestTooLarge,
)
from hawedit.registry import WrongRole

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
    if "keyframes" not in fields:
        fields["keyframes"] = (
            JudgeFrame(
                timestamp_ms=(fields["clip_in_ms"] + fields["clip_out_ms"]) // 2,
                mime_type="image/jpeg",
                data=b"actual-jpeg-bytes",
            ),
        )
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

    def __init__(self, tokens: object = 1_200, **overrides: Any) -> None:
        self.tokens = tokens
        self.fields = verdict_fields(**overrides)
        self.calls: list[str] = []
        self.urls: list[str] = []
        self.headers: list[dict[str, str]] = []

    def __call__(self, url: str, body: bytes | None, headers: Mapping[str, str]) -> tuple[int, str]:
        self.urls.append(url)
        self.headers.append(dict(headers))
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


def test_the_prompt_carries_stage_3_verbal_and_visual_evidence() -> None:
    judge = a_judge(Api())
    prompt = judge._prompt(
        a_request(
            carried_verbal_score=0.91,
            visual_context=("retention: 2.400s visible reaction",),
        )
    )
    assert "0.910000" in prompt
    assert "retention: 2.400s visible reaction" in prompt
    assert "candidate slice" in prompt


def test_tokens_are_counted_before_the_billed_call() -> None:
    """§3's ceiling is about money, so it is checked against a real count, not a guess."""
    api = Api()
    a_judge(api).judge(a_request())
    assert api.calls[0].endswith("countTokens")
    assert api.calls[1].endswith("generateContent")


def test_api_key_is_sent_in_a_header_never_in_the_url() -> None:
    api = Api()
    a_judge(api).judge(a_request())
    assert all(KEY not in url and "?key=" not in url for url in api.urls)
    assert all(headers.get("x-goog-api-key") == KEY for headers in api.headers)


def test_the_response_schema_is_sent_rather_than_requested_in_prose() -> None:
    """ "Reply in JSON please" is how a stage acquires a 1% failure rate."""
    sent: list[dict[str, Any]] = []

    def transport(url: str, body: bytes | None, headers: Mapping[str, str]) -> tuple[int, str]:
        if body:
            sent.append(json.loads(body))
        return Api()(url, body, headers)

    a_judge(transport).judge(a_request())
    generation = sent[-1]["generationConfig"]
    assert generation["responseMimeType"] == "application/json"
    assert generation["responseSchema"] == VERDICT_SCHEMA
    assert generation["temperature"] == 0.0, (
        "a judge that disagrees with itself makes §8.2's regression comparison measure "
        "sampling noise rather than model quality"
    )


def test_stage_4_sends_actual_keyframe_bytes_to_count_and_generate() -> None:
    sent: list[dict[str, Any]] = []

    def transport(url: str, body: bytes | None, headers: Mapping[str, str]) -> tuple[int, str]:
        if body:
            sent.append(json.loads(body))
        return Api()(url, body, headers)

    a_judge(transport).judge(a_request())
    assert len(sent) == 2
    for payload in sent:
        inline = next(
            part["inlineData"] for part in payload["contents"][0]["parts"] if "inlineData" in part
        )
        assert inline["mimeType"] == "image/jpeg"
        assert base64.b64decode(inline["data"]) == b"actual-jpeg-bytes"


def test_stage_4_refuses_textual_visual_context_without_source_pixels() -> None:
    with pytest.raises(JudgeUnusable, match="no keyframes"):
        a_judge(Api()).judge(a_request(keyframes=(), visual_context=("a person gestures",)))


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


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("hook_score", True),
        ("meaning_fidelity", "0.94"),
        ("misleading_edit_risk", float("nan")),
        ("cultural_landing", float("inf")),
        ("payoff_at_ms", True),
    ),
)
def test_schema_invalid_numeric_verdict_fields_are_refused(field: str, value: object) -> None:
    with pytest.raises(JudgeUnusable, match=field):
        a_judge(Api(**{field: value})).judge(a_request())


@pytest.mark.parametrize("tokens", (True, -1, "5", 1.5))
def test_invalid_token_counts_are_refused_before_generation(tokens: object) -> None:
    api = Api(tokens=tokens)
    with pytest.raises(GeminiUnavailable, match="non-negative JSON integer"):
        a_judge(api).judge(a_request())
    assert len(api.calls) == 1 and api.calls[0].endswith("countTokens")


def test_an_omitted_field_is_named_rather_than_defaulted() -> None:
    """A default here would invent a judgement nobody made."""
    api = Api()
    del api.fields["misleading_edit_risk"]
    with pytest.raises(JudgeUnusable, match="misleading_edit_risk"):
        a_judge(api).judge(a_request())


def test_a_non_json_response_is_refused() -> None:
    def transport(url: str, body: bytes | None, _headers: Mapping[str, str]) -> tuple[int, str]:
        if "countTokens" in url:
            return 200, json.dumps({"totalTokens": 10})
        return 200, json.dumps({"candidates": [{"content": {"parts": [{"text": "sorry!"}]}}]})

    with pytest.raises(JudgeUnusable, match="not JSON"):
        a_judge(transport).judge(a_request())


@pytest.mark.parametrize("payload", (None, True, 1, []))
def test_a_verdict_container_must_be_a_json_object(payload: object) -> None:
    api = Api()
    api.fields = payload  # type: ignore[assignment]
    with pytest.raises(JudgeUnusable, match="JSON object"):
        a_judge(api).judge(a_request())


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("title_ckb", {"کورد": "garbage"}),
        ("description_ckb", ["کورد"]),
        ("hashtags_ckb", [{"کورد": 1}]),
    ),
)
def test_structured_values_cannot_be_stringified_into_editorial_text(
    field: str, value: object
) -> None:
    with pytest.raises(JudgeUnusable, match=field):
        a_judge(Api(**{field: value})).judge(a_request())


def test_an_empty_response_is_refused() -> None:
    def transport(url: str, body: bytes | None, _headers: Mapping[str, str]) -> tuple[int, str]:
        if "countTokens" in url:
            return 200, json.dumps({"totalTokens": 10})
        return 200, json.dumps({"candidates": []})

    with pytest.raises(JudgeUnusable, match="no content"):
        a_judge(transport).judge(a_request())


def test_a_request_with_no_transcript_is_refused_before_any_call() -> None:
    api = Api()
    with pytest.raises(JudgeUnusable, match="neither transcript"):
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

    def transport(url: str, body: bytes | None, _headers: Mapping[str, str]) -> tuple[int, str]:
        calls.append(url)
        if "countTokens" in url:
            return 200, json.dumps({"totalTokens": 10})
        return 400, json.dumps({"error": {"message": "Invalid argument"}})

    with pytest.raises(GeminiUnavailable, match="refused"):
        a_judge(transport).judge(a_request())
    assert sum(1 for c in calls if "generateContent" in c) == 1


def test_a_rate_limit_is_not_retried_without_provider_idempotency() -> None:
    calls: list[str] = []

    def transport(url: str, body: bytes | None, _headers: Mapping[str, str]) -> tuple[int, str]:
        calls.append(url)
        if "countTokens" in url:
            return 200, json.dumps({"totalTokens": 10})
        return 429, json.dumps({"error": {"message": "Resource exhausted"}})

    with pytest.raises(GeminiUnavailable, match="was not retried"):
        a_judge(transport).judge(a_request())
    assert sum(1 for c in calls if "generateContent" in c) == 1


def test_a_transient_generation_failure_is_not_replayed_even_if_next_call_would_pass() -> None:
    state = {"n": 0}

    def transport(url: str, body: bytes | None, headers: Mapping[str, str]) -> tuple[int, str]:
        if "countTokens" in url:
            return 200, json.dumps({"totalTokens": 10})
        state["n"] += 1
        if state["n"] == 1:
            return 503, json.dumps({"error": {"message": "unavailable"}})
        return Api()(url, body, headers)

    with pytest.raises(GeminiUnavailable, match="was not retried"):
        a_judge(transport).judge(a_request())
    assert state["n"] == 1


def test_an_api_error_message_never_contains_the_key() -> None:
    """Neither transport metadata nor a provider error may leak the key."""

    def transport(url: str, body: bytes | None, _headers: Mapping[str, str]) -> tuple[int, str]:
        if "countTokens" in url:
            return 200, json.dumps({"totalTokens": 10})
        return 403, json.dumps({"error": {"message": "Permission denied"}})

    with pytest.raises(GeminiUnavailable) as caught:
        a_judge(transport).judge(a_request())
    assert KEY not in str(caught.value)


def test_structured_provider_error_is_printable_and_bounded() -> None:
    def transport(_url: str, _body: bytes | None, _headers: Mapping[str, str]) -> tuple[int, str]:
        return 400, json.dumps({"error": {"message": "bad\x00\n" + "E" * 1_000_000}})

    with pytest.raises(GeminiUnavailable) as caught:
        GeminiJudge(api_key=KEY, transport=transport).count_parts([{"text": "hello"}])
    detail = str(caught.value)
    assert len(detail) < 600
    assert "\x00" not in detail and "\n" not in detail
    assert "E" * 512 not in detail
    assert detail.endswith("...")


def test_https_refuses_oversized_response_before_json_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class OversizedResponse:
        status = 200

        def __enter__(self) -> OversizedResponse:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, size: int = -1) -> bytes:
            assert size == (1 << 20) + 1
            return b"x" * size

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: OversizedResponse(),
    )
    with pytest.raises(GeminiUnavailable, match="exceeded 1048576 bytes"):
        GeminiJudge(api_key=KEY).count_parts([{"text": "hello"}])


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


def test_flags_cannot_turn_the_developer_api_into_a_confidential_vertex_route() -> None:
    judge = a_judge(
        Api(),
        governance=Governance(confidential=True, zero_data_retention=True, confirmed_by="Hawa"),
    )
    with pytest.raises(GeminiUnavailable, match="Developer API"):
        judge.judge(a_request())


def test_non_confidential_material_needs_no_confirmation() -> None:
    assert a_judge(Api()).judge(a_request()).candidate_id == "c1"


def test_confidential_vertex_route_uses_adc_bearer_and_multimodal_payload() -> None:
    api = Api()
    judge = VertexGeminiJudge(
        "news-project",
        location="global",
        governance=Governance(
            confidential=True,
            zero_data_retention=True,
            confirmed_by="data-protection-officer",
        ),
        token_provider=lambda: "adc-token",
        transport=api,
        sleep=lambda _seconds: None,
    )
    assert judge.judge(a_request()).candidate_id == "c1"
    assert all(
        url.startswith(
            "https://aiplatform.googleapis.com/v1/projects/news-project/locations/global/"
        )
        for url in api.urls
    )
    assert all(headers == {"Authorization": "Bearer adc-token"} for headers in api.headers)
    assert all("key=" not in url for url in api.urls)


@pytest.mark.parametrize("failure", [PermissionError("denied"), UnicodeError("bad token")])
def test_vertex_token_provider_io_failures_are_normalized_before_transport(
    failure: Exception,
) -> None:
    api = Api()

    def fail() -> str:
        raise failure

    judge = VertexGeminiJudge("news-project", token_provider=fail, transport=api)
    with pytest.raises(GeminiUnavailable, match="no request was sent"):
        judge.count_parts([{"text": "hello"}])
    assert api.calls == []


def test_vertex_token_provider_does_not_hide_programmer_failures() -> None:
    def fail() -> str:
        raise AssertionError("control")

    with pytest.raises(AssertionError, match="control"):
        VertexGeminiJudge("news-project", token_provider=fail, transport=Api()).count_parts(
            [{"text": "hello"}]
        )


def test_adc_auth_operational_failure_is_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeGoogleAuthError(Exception):
        pass

    google = ModuleType("google")
    auth = ModuleType("google.auth")
    exceptions = ModuleType("google.auth.exceptions")
    transport = ModuleType("google.auth.transport")
    requests = ModuleType("google.auth.transport.requests")

    def fail_default(*, scopes: tuple[str, ...]) -> tuple[object, None]:
        assert scopes == ("https://www.googleapis.com/auth/cloud-platform",)
        raise FakeGoogleAuthError("provider detail must not escape")

    class Request:
        pass

    auth.default = fail_default  # type: ignore[attr-defined]
    exceptions.GoogleAuthError = FakeGoogleAuthError  # type: ignore[attr-defined]
    requests.Request = Request  # type: ignore[attr-defined]
    google.auth = auth  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.auth", auth)
    monkeypatch.setitem(sys.modules, "google.auth.exceptions", exceptions)
    monkeypatch.setitem(sys.modules, "google.auth.transport", transport)
    monkeypatch.setitem(sys.modules, "google.auth.transport.requests", requests)

    with pytest.raises(GeminiUnavailable, match="no request was sent"):
        adc_access_token()


def test_regional_vertex_route_uses_the_regional_endpoint() -> None:
    judge = VertexGeminiJudge(
        "news-project",
        location="europe-west4",
        token_provider=lambda: "token",
        transport=Api(),
    )
    assert judge._url("generateContent").startswith(
        "https://europe-west4-aiplatform.googleapis.com/"
    )


def test_vertex_resource_ids_cannot_inject_a_different_url_path() -> None:
    with pytest.raises(ValueError, match="project"):
        VertexGeminiJudge("project/locations/other", token_provider=lambda: "token")


# --- §7, before anything is billed ---------------------------------------------------------


def _concrete_judges() -> dict[str, Callable[[str], GeminiJudge]]:
    """Every constructible judge, with the minimum dependencies needed to instantiate it."""
    return {
        "GeminiJudge": lambda model_id: GeminiJudge(
            model_id=model_id,
            api_key=KEY,
            transport=Api(),
            sleep=lambda _seconds: None,
        ),
        "VertexGeminiJudge": lambda model_id: VertexGeminiJudge(
            "news-project",
            model_id=model_id,
            token_provider=lambda: "adc-token",
            transport=Api(),
            sleep=lambda _seconds: None,
        ),
    }


def _judge_class_names() -> set[str]:
    """GeminiJudge and every transitive production subclass currently loaded."""
    seen = {GeminiJudge}
    frontier = [GeminiJudge]
    while frontier:
        for child in frontier.pop().__subclasses__():
            if child not in seen:
                seen.add(child)
                frontier.append(child)
    return {cls.__name__ for cls in seen}


def test_every_constructible_judge_has_a_routing_constructor_here() -> None:
    """A new subclass fails until its independent §7 constructor path is held."""
    covered = set(_concrete_judges())
    actual = _judge_class_names()
    assert actual == covered, (
        f"judge classes without routing coverage: {sorted(actual - covered)}; "
        f"stale constructors: {sorted(covered - actual)}"
    )


@pytest.mark.parametrize("name", sorted(_concrete_judges()))
def test_no_concrete_judge_can_be_built_as_the_shadow(name: str) -> None:
    with pytest.raises(NotRoutable):
        _concrete_judges()[name](JUDGE_SHADOW)


@pytest.mark.parametrize("name", sorted(_concrete_judges()))
def test_every_concrete_judge_accepts_the_pinned_incumbent(name: str) -> None:
    """Control: a constructor that rejected every model would pass the shadow test alone."""
    judge = _concrete_judges()[name](KURDISH_EDITORIAL_JUDGE)
    assert judge.model_id == KURDISH_EDITORIAL_JUDGE
    assert KURDISH_EDITORIAL_JUDGE in judge._url("generateContent")


def test_the_shadow_cannot_be_constructed_as_the_judge() -> None:
    """§3 Stage 4: gemini-3.1-pro is "evaluated, not routed"."""
    with pytest.raises(NotRoutable):
        a_judge(Api(), model_id="gemini-3.1-pro")


def test_model_routing_remains_eager_while_credentials_are_deferred(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hawedit.judge import NotRoutable

    def credential_must_not_be_read(_name: str | None = None) -> str:
        raise AssertionError("credential acquisition ran before static routing")

    monkeypatch.setattr("hawedit.gemini.read_credential", credential_must_not_be_read)
    with pytest.raises(NotRoutable):
        GeminiJudge(api_key=None, model_id="gemini-3.1-pro", transport=Api())


def test_a_model_outside_section_7_cannot_be_constructed() -> None:
    with pytest.raises((WrongRole, LookupError, ValueError)):
        a_judge(Api(), model_id="gpt-4o")


def test_key_acquisition_is_lazy_and_missing_key_names_the_panel_on_first_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr("hawedit.gemini.read_credential", lambda _n=None: None)
    api = Api()
    judge = GeminiJudge(api_key=None, transport=api)

    with pytest.raises(GeminiUnavailable, match="hawedit.credentials"):
        judge.count_parts([{"text": "hello"}])
    assert api.calls == []


@pytest.mark.parametrize("failure", [PermissionError("denied"), UnicodeError("bad utf-8")])
def test_deferred_key_storage_failures_are_normalized_before_transport(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    def fail(_name: str | None = None) -> str:
        raise failure

    api = Api()
    monkeypatch.setattr("hawedit.gemini.read_credential", fail)
    judge = GeminiJudge(api_key=None, transport=api)

    with pytest.raises(GeminiUnavailable, match="no request was sent"):
        judge.count_parts([{"text": "hello"}])
    assert api.calls == []


def test_deferred_key_does_not_hide_programmer_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(_name: str | None = None) -> str:
        raise AssertionError("control")

    monkeypatch.setattr("hawedit.gemini.read_credential", fail)
    with pytest.raises(AssertionError, match="control"):
        GeminiJudge(api_key=None, transport=Api()).count_parts([{"text": "hello"}])


def test_deferred_key_is_read_once_and_still_sent_only_in_the_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reads = 0

    def credential(_name: str | None = None) -> str:
        nonlocal reads
        reads += 1
        return KEY

    api = Api()
    monkeypatch.setattr("hawedit.gemini.read_credential", credential)
    judge = GeminiJudge(api_key=None, transport=api)
    assert reads == 0

    judge.count_parts([{"text": "first"}])
    judge.count_parts([{"text": "second"}])

    assert reads == 1
    assert all(KEY not in url for url in api.urls)
    assert all(headers == {"x-goog-api-key": KEY} for headers in api.headers)


# --- countTokens ----------------------------------------------------------------------------


def test_count_tokens_returns_the_apis_number() -> None:
    assert count_tokens("text", KEY, transport=Api(tokens=4_242)) == 4_242


def test_count_tokens_failure_is_not_silently_zero() -> None:
    """A zero would read as "this request is free and definitely under the ceiling"."""

    def failing(_url: str, _body: bytes | None, _headers: Mapping[str, str]) -> tuple[int, str]:
        return 500, "{}"

    with pytest.raises(GeminiUnavailable, match="countTokens"):
        count_tokens("text", KEY, transport=failing)
