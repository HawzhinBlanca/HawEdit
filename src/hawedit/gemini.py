"""The real §3 Stage 4 judge: `gemini-2.5-pro` behind the `EditorialJudge` interface.

    All routing goes through the `KURDISH_EDITORIAL_JUDGE` interface. Swapping providers
    must be a config change, never a refactor.

`judge.py` is the contract; this is one implementation of it. Nothing above this module knows
it is talking to Google — `route()` resolves the model against §7 and the pipeline holds an
`EditorialJudge`, so replacing this file is the config change §3 asks for.

Four choices worth stating, because each has a plausible alternative that fails quietly:

**Structured output, not prompt-and-parse.** The request carries a JSON schema and Gemini is
asked for `application/json`. Asking a model to "reply in JSON" and then parsing prose is how
a stage acquires a 1% failure rate that only shows up in production. A response that does not
match the schema is a `JudgeUnusable`, not a partially-filled verdict.

**Token counts come from `countTokens`, not from an estimate.** §3 Stage 4's ceiling — keep
each request under 200K to stay on the lower Pro price tier — is arithmetic, and
`JudgeRequest.assert_within_tier` refuses a request whose size is unknown. Google will count
the tokens for free, so there is no reason to guess and then be wrong about the bill.

**Every verdict goes through `JudgeVerdict`.** The Kurdish-script check, the payoff-inside-the-
clip check and the score ranges all apply to model output exactly as they apply to a hand-
written verdict. A model is not a trusted source; it is the least trusted one in the system.

**Retries are bounded and only for transient failures.** A 429 or a 5xx is worth retrying; a
400 means the request is wrong and retrying it just bills twice for the same mistake.

Governance, unchanged by any of this: §3 Stage 3's warning box says full-transcript discovery
sends 100% of every transcript to Google, and that for COMMS and KAAE material paid-tier Vertex
with zero-data-retention is *mandatory, not advisory*. This module refuses to run against
material marked confidential unless that has been confirmed — see `Governance`. This adapter
targets the Gemini Developer API, so even a confirmed setting cannot stand in for the Vertex
route the blueprint requires for confidential material.
"""

from __future__ import annotations

import base64
import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final

from hawedit.credentials import GEMINI_API_KEY, read_credential
from hawedit.judge import (
    KURDISH_EDITORIAL_JUDGE,
    InputMode,
    JudgeRequest,
    JudgeVerdict,
    route,
)

__all__ = [
    "API_ROOT",
    "VERDICT_SCHEMA",
    "GeminiJudge",
    "GeminiUnavailable",
    "Governance",
    "JudgeUnusable",
    "VertexGeminiJudge",
    "adc_access_token",
    "count_tokens",
]

API_ROOT: Final = "https://generativelanguage.googleapis.com/v1beta"

# Transient statuses only. A 400 means this request is malformed and a retry bills twice for
# the same mistake; a 403 means the key lacks access and will still lack it in two seconds.
# 0 is `_https`'s marker for an OSError — a reset connection, a DNS blip, a TLS hiccup.
# It was absent here, so a dropped connection was reported as "the judge refused this
# request" on the first attempt, sending someone to look at their prompt when the problem
# was the network. A 400 still does not retry: that request is wrong and will stay wrong.
_RETRYABLE: Final = frozenset({0, 429, 500, 502, 503, 504})


class GeminiUnavailable(RuntimeError):
    """Raised when the API could not be reached or refused the request outright."""


class JudgeUnusable(ValueError):
    """Raised when the model answered but the answer is not a verdict this system can use."""


def _strict_list(value: object) -> list[Any]:
    """Refuse a scalar where the schema declares an array.

    A Python `str` is iterable, so `tuple(x for x in "کورد")` yields four single-letter
    "hashtags" — each of which passes the Kurdish-script check individually, because a Kurdish
    letter is Kurdish script. The schema constrains what is *asked for*, never what is
    received. Shape without content, once more.
    """
    if not isinstance(value, list):
        raise JudgeUnusable(
            f"hashtags_ckb is {type(value).__name__} {value!r}, not an array. A string here "
            f"would be iterated into one 'hashtag' per character, and each character would "
            f"pass the Kurdish-script check on its own."
        )
    return value


def _strict_bool(value: object, field: str) -> bool:
    """Refuse anything that is not a real JSON boolean.

    `bool("false")` is True. This is the same guard `boundary.py` grew after the previous
    audit, applied where it was most obviously needed and least obviously present: the point
    where the least-trusted input in the system — a hosted model's response — becomes a field
    on a shipped artifact. Structured output makes a schema violation unlikely, not impossible,
    and nothing else re-checks the type before the value is used.
    """
    if not isinstance(value, bool):
        raise JudgeUnusable(
            f"the judge returned {field}={value!r} ({type(value).__name__}), not a JSON "
            f"boolean. bool({value!r}) would be {bool(value)} — a coercion here decides a "
            f"field that ships to the client."
        )
    return value


@dataclass(frozen=True, slots=True)
class Governance:
    """§3 Stage 3's warning box, as a value that has to be supplied.

        Full-transcript discovery means 100% of every transcript leaves your network […]
        For COMMS and KAAE material, paid tier and Vertex with zero-data-retention configured
        become **mandatory, not advisory**. Confirm this before the first client job runs.

    A boolean default of `False` would make the safe path the one nobody selects. So
    `confidential` is what the caller knows about the material, and `zero_data_retention` is
    what they have actually configured. Those values are necessary evidence, not a transport:
    this module's endpoint remains the Developer API, so confidential uploads stay refused
    until an actual Vertex implementation is selected.
    """

    confidential: bool = False
    zero_data_retention: bool = False
    confirmed_by: str = ""

    def assert_permits_upload(self) -> None:
        """Raises:
        GeminiUnavailable: confidential material would be sent without ZDR confirmed.
        """
        if self.confidential and not self.zero_data_retention:
            raise GeminiUnavailable(
                "this material is marked confidential and zero-data-retention is not "
                "configured. §3 Stage 3: for COMMS and KAAE material, paid tier and Vertex "
                "with ZDR are mandatory, not advisory — 100% of the transcript leaves the "
                "network. Confirm before the first client job (BLOCKED.md #3)."
            )
        if self.confidential and not self.confirmed_by.strip():
            raise GeminiUnavailable(
                "zero-data-retention is claimed but nobody is recorded as having confirmed it. "
                "§3 asks for a confirmation, and an unattributed one is not a confirmation."
            )
        if self.confidential:
            raise GeminiUnavailable(
                "confidential material requires a paid Vertex route with zero-data-retention, "
                "but this adapter calls the Gemini Developer API. Flags cannot change that "
                "endpoint; implement and select a Vertex transport before uploading it."
            )

    def assert_permits_vertex(self) -> None:
        """Permit confidential upload only with an attributed Vertex ZDR confirmation."""
        if self.confidential and not self.zero_data_retention:
            raise GeminiUnavailable(
                "confidential material requires Vertex zero-data-retention configuration"
            )
        if self.confidential and not self.confirmed_by.strip():
            raise GeminiUnavailable(
                "Vertex zero-data-retention is claimed but confirmed_by is empty"
            )


# The judge's output shape, as a schema the API enforces rather than a request in a prompt.
VERDICT_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "hook_score": {"type": "number"},
        "self_contained": {"type": "boolean"},
        "payoff_at_ms": {"type": "integer"},
        "meaning_fidelity": {"type": "number"},
        "misleading_edit_risk": {"type": "number"},
        "cultural_landing": {"type": "number"},
        "narrative_role": {"type": "string"},
        "title_ckb": {"type": "string"},
        "description_ckb": {"type": "string"},
        "hashtags_ckb": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "hook_score",
        "self_contained",
        "payoff_at_ms",
        "meaning_fidelity",
        "misleading_edit_risk",
        "cultural_landing",
        "narrative_role",
        "title_ckb",
        "description_ckb",
        "hashtags_ckb",
    ],
}

_PROMPT = """You are the Kurdish editorial judge for a Central Kurdish (Sorani, ckb) video
repurposing system. You are judging one candidate clip for social publication.

The candidate runs from {in_ms} to {out_ms} milliseconds in the source video. The transcript
below is ONLY the aligned candidate slice, normalized Sorani in Arabic script; it is not the
full episode. The carried Path A score and timestamped visual evidence are prior evidence from
Stage 3. Use them; do not pretend a visual beat is absent merely because it has no words.

Carried Path A score: {verbal_score}

Validated visual evidence:
{visual_context}

Judge it on:
- hook_score: how strongly the opening seconds hold attention (0..1)
- self_contained: whether it makes sense with no surrounding context
- payoff_at_ms: the millisecond position of the payoff. MUST be between {in_ms} and {out_ms}.
- meaning_fidelity: how faithfully the cut preserves what the speaker meant (0..1)
- misleading_edit_risk: risk the cut changes the meaning (0..1). This is the number a media
  organisation is judged on. Be pessimistic.
- cultural_landing: how well this lands with a Kurdish audience specifically (0..1)
- narrative_role: one of setup, escalation, payoff, aside
- title_ckb, description_ckb, hashtags_ckb: IN CENTRAL KURDISH (Sorani, Arabic script) ONLY.
  Never Latin script, never English, never Kurmanji. This is a Kurdish product.

Candidate transcript slice:
{text}

The request also contains {keyframe_count} source-timestamped keyframes. Judge visible claims
against those pixels; do not treat the textual SV6D description as a substitute for them.
"""

Transport = Callable[[str, bytes | None, Mapping[str, str]], tuple[int, str]]


def _https(
    url: str, body: bytes | None = None, headers: Mapping[str, str] | None = None
) -> tuple[int, str]:
    request_headers = dict(headers or {})
    if body:
        request_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(
        url,
        data=body,
        headers=request_headers,
        method="POST" if body else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except OSError as exc:
        return 0, str(exc)


def _api_error(status: int, body: str) -> str:
    """Return the API's own bounded error message without request metadata."""
    try:
        return f"HTTP {status}: {json.loads(body)['error']['message']}"
    except (ValueError, KeyError, TypeError):
        return f"HTTP {status}: {body[:200]}"


def count_tokens(
    text: str,
    api_key: str,
    model: str = KURDISH_EDITORIAL_JUDGE,
    transport: Transport = _https,
) -> int:
    """Ask Google how many tokens this is, rather than estimating it.

    §3 Stage 4's 200K ceiling is a real price boundary and `assert_within_tier` refuses a
    request of unknown size. `countTokens` costs nothing, so an estimate here would be a guess
    that could only be wrong about money.

    Raises:
        GeminiUnavailable: the API could not be reached or refused the request.
    """
    payload = json.dumps({"contents": [{"parts": [{"text": text}]}]}).encode("utf-8")
    status, body = transport(
        f"{API_ROOT}/models/{model}:countTokens", payload, {"x-goog-api-key": api_key}
    )
    if status != 200:
        raise GeminiUnavailable(f"countTokens failed — {_api_error(status, body)}")
    try:
        return int(json.loads(body)["totalTokens"])
    except (ValueError, KeyError, TypeError) as exc:
        raise GeminiUnavailable(f"countTokens returned no totalTokens: {exc}") from exc


def _count_parts(
    parts: list[dict[str, Any]],
    url: str,
    headers: Mapping[str, str],
    transport: Transport,
) -> int:
    payload = json.dumps({"contents": [{"parts": parts}]}).encode("utf-8")
    status, body = transport(url, payload, headers)
    if status != 200:
        raise GeminiUnavailable(f"countTokens failed — {_api_error(status, body)}")
    try:
        return int(json.loads(body)["totalTokens"])
    except (ValueError, KeyError, TypeError) as exc:
        raise GeminiUnavailable(f"countTokens returned no totalTokens: {exc}") from exc


class GeminiJudge:
    """§3 Stage 4's pinned judge, behind `EditorialJudge`.

    The model is resolved against §7 at construction, so this class cannot be pointed at the
    shadow or at a model the blueprint excludes — `route()` refuses both.
    """

    requires_keyframes = True

    def __init__(
        self,
        api_key: str | None = None,
        model_id: str = KURDISH_EDITORIAL_JUDGE,
        governance: Governance | None = None,
        transport: Transport | None = None,
        max_attempts: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.model_id = model_id
        self.governance = governance or Governance()
        self._transport = transport or _https
        self._max_attempts = max_attempts
        self._sleep = sleep

        # §7 first: a model outside the registry, or the shadow, must fail here rather than
        # after a billed call.
        route(self)

        key = api_key or read_credential(GEMINI_API_KEY)
        if not key:
            raise GeminiUnavailable(
                "no Gemini API key. Run `python -m hawedit.credentials` to store one, or set "
                f"{GEMINI_API_KEY} in the environment."
            )
        self._key = key

    def count_request_tokens(self, request: JudgeRequest) -> int:
        """The real token count for what this request would send.

        Governance runs first. This method builds the full prompt — transcript included — and
        posts it to Google, so it is a network egress path exactly like `judge()`. It did not
        check, which made it a live bypass of the one rule in this project with legal
        consequences: §3 Stage 3 calls ZDR "mandatory, not advisory" for COMMS and KAAE
        material. `smoke.py` calls this directly. Found by the independent review.
        """
        self._assert_governance()
        self._assert_keyframes(request)
        return _count_parts(
            self._parts(request),
            self._url("countTokens"),
            self._headers(),
            self._transport,
        )

    def _assert_governance(self) -> None:
        self.governance.assert_permits_upload()

    def _headers(self) -> Mapping[str, str]:
        return {"x-goog-api-key": self._key}

    def _url(self, method: str) -> str:
        return f"{API_ROOT}/models/{self.model_id}:{method}"

    @staticmethod
    def _assert_keyframes(request: JudgeRequest) -> None:
        if request.mode is not InputMode.PATH_A_DISCOVERY and not request.keyframes:
            raise JudgeUnusable(
                f"Stage 4 request {request.candidate_id!r} has no keyframes. Textual SV6D "
                "is prior evidence, not source pixels; refusing a text-only visual judgment."
            )

    def _parts(self, request: JudgeRequest) -> list[dict[str, Any]]:
        prompt = self._prompt(request)
        parts: list[dict[str, Any]] = []
        for frame in request.keyframes:
            parts.append({"text": f"Source keyframe at {frame.timestamp_ms} ms:"})
            parts.append(
                {
                    "inlineData": {
                        "mimeType": frame.mime_type,
                        "data": base64.b64encode(frame.data).decode("ascii"),
                    }
                }
            )
        parts.append({"text": prompt})
        return parts

    def count_parts(self, parts: list[dict[str, Any]]) -> int:
        """Count arbitrary content parts through this adapter's authenticated route."""
        self._assert_governance()
        return _count_parts(parts, self._url("countTokens"), self._headers(), self._transport)

    def generate_json(self, parts: list[dict[str, Any]], schema: Mapping[str, Any]) -> str:
        """Generate deterministic structured JSON through Developer API or Vertex."""
        self._assert_governance()
        payload = json.dumps(
            {
                "contents": [{"parts": parts}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": schema,
                    "temperature": 0.0,
                },
            }
        ).encode("utf-8")
        return self._post(self._url("generateContent"), payload)

    def _prompt(self, request: JudgeRequest) -> str:
        if not request.text_ckb and not request.visual_context:
            raise JudgeUnusable(
                f"request {request.candidate_id!r} carries neither transcript text nor visual "
                f"evidence. There is nothing for the judge to judge."
            )
        visual_context = "\n".join(f"- {item}" for item in request.visual_context) or "(none)"
        return _PROMPT.format(
            in_ms=request.clip_in_ms,
            out_ms=request.clip_out_ms,
            verbal_score=(
                f"{request.carried_verbal_score:.6f}"
                if request.carried_verbal_score is not None
                else "(not available)"
            ),
            visual_context=visual_context,
            text=request.text_ckb or "(no aligned speech in this candidate)",
            keyframe_count=len(request.keyframes),
        )

    def judge(self, request: JudgeRequest) -> JudgeVerdict:
        """Score one candidate.

        Raises:
            GeminiUnavailable: governance forbids the upload, or the API refused/was unreachable.
            RequestTooLarge: the request exceeds §3's 200K tier ceiling.
            JudgeUnusable: the model answered with something that is not a usable verdict.
        """
        self._assert_governance()
        self._assert_keyframes(request)
        # Count before sending. The ceiling is about money, so it is checked against the real
        # number rather than against whatever the caller believed when building the request.
        parts = self._parts(request)
        counted = _count_parts(
            parts,
            self._url("countTokens"),
            self._headers(),
            self._transport,
        )
        from dataclasses import replace

        replace(request, tokens=counted).assert_within_tier()

        payload = json.dumps(
            {
                "contents": [{"parts": parts}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": VERDICT_SCHEMA,
                    # Editorial judgment should not vary run to run for the same input: §8.2
                    # compares judges against a regression set, and a judge that disagrees
                    # with itself makes that comparison measure sampling noise.
                    "temperature": 0.0,
                },
            }
        ).encode("utf-8")

        body = self._post(self._url("generateContent"), payload)
        return self._to_verdict(body, request)

    def _post(self, url: str, payload: bytes) -> str:
        last = ""
        for attempt in range(1, self._max_attempts + 1):
            status, body = self._transport(url, payload, self._headers())
            if status == 200:
                return body
            last = _api_error(status, body)
            if status not in _RETRYABLE:
                raise GeminiUnavailable(f"the judge refused this request — {last}")
            if attempt < self._max_attempts:
                self._sleep(2.0**attempt)
        raise GeminiUnavailable(
            f"the judge was unreachable after {self._max_attempts} attempts — {last}"
        )

    def _to_verdict(self, body: str, request: JudgeRequest) -> JudgeVerdict:
        try:
            text = json.loads(body)["candidates"][0]["content"]["parts"][0]["text"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise JudgeUnusable(f"no content in the judge's response: {exc}") from exc
        try:
            fields = json.loads(text)
        except ValueError as exc:
            raise JudgeUnusable(
                f"the judge's response was not JSON despite responseMimeType: {exc}"
            ) from exc

        missing = [key for key in VERDICT_SCHEMA["required"] if key not in fields]
        if missing:
            raise JudgeUnusable(f"the judge omitted required fields: {missing}")

        try:
            # Every validation in JudgeVerdict applies to model output exactly as it applies to
            # a hand-written one: Kurdish script, payoff inside the clip, scores in range. A
            # model is the least trusted source in this system, not the most.
            return JudgeVerdict(
                candidate_id=request.candidate_id,
                hook_score=float(fields["hook_score"]),
                self_contained=_strict_bool(fields["self_contained"], "self_contained"),
                payoff_at_ms=int(fields["payoff_at_ms"]),
                meaning_fidelity=float(fields["meaning_fidelity"]),
                misleading_edit_risk=float(fields["misleading_edit_risk"]),
                cultural_landing=float(fields["cultural_landing"]),
                narrative_role=str(fields["narrative_role"]),
                title_ckb=str(fields["title_ckb"]),
                description_ckb=str(fields["description_ckb"]),
                hashtags_ckb=tuple(str(tag) for tag in _strict_list(fields["hashtags_ckb"])),
                judge=self.model_id,
                clip_in_ms=request.clip_in_ms,
                clip_out_ms=request.clip_out_ms,
            )
        except (ValueError, TypeError) as exc:
            raise JudgeUnusable(f"the judge's verdict failed validation: {exc}") from exc


def adc_access_token() -> str:
    """Refresh and return a short-lived Google Application Default Credentials token."""
    try:
        import google.auth
        from google.auth.transport.requests import Request
    except ImportError as exc:
        raise GeminiUnavailable(
            "Vertex requires the cloud extra: pip install -e '.[cloud]'"
        ) from exc
    credentials, _ = google.auth.default(scopes=("https://www.googleapis.com/auth/cloud-platform",))
    credentials.refresh(Request())
    token = getattr(credentials, "token", None)
    if not token:
        raise GeminiUnavailable("Application Default Credentials returned no access token")
    return str(token)


class VertexGeminiJudge(GeminiJudge):
    """Gemini on Vertex AI with ADC bearer authentication for confidential routing."""

    def __init__(
        self,
        project: str,
        *,
        location: str = "global",
        model_id: str = KURDISH_EDITORIAL_JUDGE,
        governance: Governance | None = None,
        token_provider: Callable[[], str] = adc_access_token,
        transport: Transport | None = None,
        max_attempts: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", project):
            raise ValueError(f"invalid Vertex project identifier {project!r}")
        if not re.fullmatch(r"[a-z][a-z0-9-]*", location):
            raise ValueError(f"invalid Vertex location {location!r}")
        self.model_id = model_id
        self.governance = governance or Governance()
        self.project = project
        self.location = location
        self._token_provider = token_provider
        self._transport = transport or _https
        self._max_attempts = max_attempts
        self._sleep = sleep
        self._key = ""
        route(self)

    def _assert_governance(self) -> None:
        self.governance.assert_permits_vertex()

    def _headers(self) -> Mapping[str, str]:
        token = self._token_provider()
        if not token:
            raise GeminiUnavailable("Vertex token provider returned an empty access token")
        return {"Authorization": f"Bearer {token}"}

    def _url(self, method: str) -> str:
        host = (
            "aiplatform.googleapis.com"
            if self.location == "global"
            else f"{self.location}-aiplatform.googleapis.com"
        )
        return (
            f"https://{host}/v1/projects/"
            f"{self.project}/locations/{self.location}/publishers/google/models/"
            f"{self.model_id}:{method}"
        )
