"""Fast Candidate Screener Funnel (D-275).

Ranks Stage 3 spans before full Stage 4 editorial judging. Predictions are not calibrated
quality, publication authority or a latency guarantee. Jev's legacy diagnostic wire codec
does not establish compatibility with the current typed TypeSafe API (D-276).
"""

from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Final, NoReturn, Protocol

from hawedit.credentials import CredentialError
from hawedit.discovery import MergedCandidate

TYPESAFE_API_KEY_ENV: Final[str] = "TYPESAFE_API_KEY"
TYPESAFE_API_URL: Final[str] = "https://api.typesafe.ai/v1/systemone"
_MAX_RESPONSE_BYTES: Final[int] = 2 * 1024**2
ScreenerTransport = Callable[[urllib.request.Request], bytes]


def _identifier(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 256
        or any(ord(char) < 32 for char in value)
    ):
        raise ValueError(f"{field} must be bounded nonempty text without controls")
    return value


def _number(value: object, field: str, ceiling: float = 1.0) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{field} must be in [0.0, {ceiling}] as a real numeric value")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError(f"{field} exceeds numeric bounds") from exc
    if not math.isfinite(number) or not 0 <= number <= ceiling:
        raise ValueError(f"{field} must be in [0.0, {ceiling}] as a finite numeric value")
    return number


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        raise ValueError("is_self_contained must be an actual Boolean, not coerced text")
    return value


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("Screener JSON repeats a field")
        result[name] = value
    return result


def _constant(value: str) -> NoReturn:
    raise ValueError("Screener JSON contains a nonfinite value")


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Screener {label} must be an object")
    return value


def _response(data: bytes) -> dict[str, Any]:
    if not isinstance(data, bytes) or len(data) > _MAX_RESPONSE_BYTES:
        raise ValueError("Screener response exceeds its byte bound")
    try:
        return _object(
            json.loads(data.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant),
            "response",
        )
    except (UnicodeError, RecursionError) as exc:
        raise ValueError("Screener response encoding or nesting was refused") from exc


def _http_response(request: urllib.request.Request) -> bytes:
    with urllib.request.urlopen(request, timeout=30) as response:
        data: bytes = response.read(_MAX_RESPONSE_BYTES + 1)
    if len(data) > _MAX_RESPONSE_BYTES:
        raise ValueError("Screener HTTP response exceeds its byte bound")
    return data


def _inputs(candidates: Sequence[tuple[MergedCandidate, str]], top_k: int) -> set[str]:
    if type(top_k) is not int or top_k < 1:
        raise ValueError("top_k must be a positive integer")
    identities: set[str] = set()
    for candidate, transcript in candidates:
        identifier = _identifier(candidate.candidate_id, "candidate_id")
        if identifier in identities:
            raise ValueError("Screener input repeats a candidate identity")
        if not isinstance(transcript, str) or not transcript.strip():
            raise ValueError("Screener input requires actual nonempty transcript text")
        identities.add(identifier)
    return identities


SCREENER_SCHEMA: Final[dict[str, Any]] = {
    "type": "OBJECT",
    "properties": {
        "candidates": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "candidate_id": {"type": "STRING"},
                    "hook_score": {
                        "type": "NUMBER",
                        "description": (
                            "0.0 to 1.0 rating of opening 3s viral scroll-stopping potential"
                        ),
                    },
                    "payoff_score": {
                        "type": "NUMBER",
                        "description": "0.0 to 1.0 rating of punchline/resolution strength",
                    },
                    "is_self_contained": {
                        "type": "BOOLEAN",
                        "description": (
                            "True if clip forms a complete thought without mid-sentence cuts"
                        ),
                    },
                    "misleading_risk": {
                        "type": "NUMBER",
                        "description": (
                            "0.0 to 1.0 probability that out-of-context edit "
                            "distorts speaker meaning"
                        ),
                    },
                },
                "required": [
                    "candidate_id",
                    "hook_score",
                    "payoff_score",
                    "is_self_contained",
                    "misleading_risk",
                ],
            },
        }
    },
    "required": ["candidates"],
}


def calculate_screener_score(
    *,
    hook_score: float,
    payoff_score: float,
    misleading_risk: float,
    is_self_contained: bool,
) -> float:
    """Calculate composite screener score matching HawEdit's editorial priorities."""
    if not is_self_contained:
        return 0.0
    base = 0.50 * hook_score + 0.35 * payoff_score + 0.15 * max(0.0, 1.0 - misleading_risk)
    return round(max(0.0, min(1.0, base)), 4)


@dataclass(frozen=True, slots=True)
class ScreenedCandidate:
    """A candidate span evaluated by a fast screener."""

    candidate_id: str
    hook_score: float
    payoff_score: float
    is_self_contained: bool
    misleading_risk: float
    composite_score: float
    screener: str
    raw: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        _identifier(self.candidate_id, "candidate_id")
        _identifier(self.screener, "screener")
        _boolean(self.is_self_contained)
        for field in ("hook_score", "payoff_score", "misleading_risk", "composite_score"):
            _number(getattr(self, field), field)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "hook_score": self.hook_score,
            "payoff_score": self.payoff_score,
            "is_self_contained": self.is_self_contained,
            "misleading_risk": self.misleading_risk,
            "composite_score": self.composite_score,
            "screener": self.screener,
        }


class CandidateScreener(Protocol):
    """Interface for candidate screeners."""

    @property
    def name(self) -> str: ...

    def screen(
        self,
        candidates: Sequence[tuple[MergedCandidate, str]],
        *,
        top_k: int = 5,
    ) -> tuple[ScreenedCandidate, ...]: ...


class GeminiFlashScreener:
    """Screener backed by Gemini 2.5 Flash / Flash-Lite using structured JSON schema."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_id: str = "gemini-2.5-flash-lite",
        transport: Callable[[urllib.request.Request], bytes] | None = None,
    ) -> None:
        self.model_id = model_id
        resolved_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not resolved_key:
            # Check HawEdit's credential vault
            from hawedit.credentials import read_credential

            resolved_key = read_credential("GEMINI_API_KEY")
        if not resolved_key:
            raise CredentialError(
                "GEMINI_API_KEY is required for GeminiFlashScreener; set GEMINI_API_KEY or "
                "run python -m hawedit.credentials"
            )
        self.api_key = resolved_key
        self._transport = transport or self._default_transport

    @property
    def name(self) -> str:
        return f"gemini-flash ({self.model_id})"

    @staticmethod
    def _default_transport(req: urllib.request.Request) -> bytes:
        return _http_response(req)

    def screen(
        self,
        candidates: Sequence[tuple[MergedCandidate, str]],
        *,
        top_k: int = 5,
    ) -> tuple[ScreenedCandidate, ...]:
        expected = _inputs(candidates, top_k)
        if not candidates:
            return ()

        items = [
            {"candidate_id": cand.candidate_id, "transcript_ckb": text} for cand, text in candidates
        ]
        prompt = (
            "You are a professional Kurdish viral video editor. "
            "Evaluate each candidate clip transcript for short-form reel potential "
            "(TikTok/Reels/Shorts). "
            "Score hook_score (0.0-1.0), payoff_score (0.0-1.0), is_self_contained (bool), "
            "and misleading_risk (0.0-1.0).\n\n"
            f"Input candidates:\n{json.dumps(items, ensure_ascii=False)}"
        )

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model_id}:generateContent?key={self.api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": SCREENER_SCHEMA,
                "temperature": 0.0,
            },
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        raw_bytes = self._transport(req)
        response_json = _response(raw_bytes)
        choices = response_json.get("candidates")
        if not isinstance(choices, list) or len(choices) != 1:
            raise ValueError("Screener response lacks exactly one structured completion")
        choice = _object(choices[0], "completion")
        if choice.get("finishReason", "STOP") != "STOP":
            raise ValueError("Screener completion was refused or incomplete")
        parts = _object(choice.get("content"), "completion content").get("parts")
        if not isinstance(parts, list) or not parts:
            raise ValueError("Screener completion lacks actual text parts")
        texts: list[str] = []
        for raw_part in parts:
            part = _object(raw_part, "completion part")
            if "thought" in part and type(part["thought"]) is not bool:
                raise ValueError("Screener thought marker is not a Boolean")
            if part.get("thought") is True:
                continue
            if not isinstance(part.get("text"), str):
                raise ValueError("Screener completion part lacks text")
            texts.append(part["text"])
        parsed = _response("".join(texts).encode("utf-8"))
        raw_list = parsed.get("candidates")
        if set(parsed) != {"candidates"} or not isinstance(raw_list, list):
            raise ValueError("Screener structured batch has unsupported fields")

        results: list[ScreenedCandidate] = []
        seen: set[str] = set()
        for raw_entry in raw_list:
            entry = _object(raw_entry, "candidate measurement")
            if set(entry) != set(SCREENER_SCHEMA["properties"]["candidates"]["items"]["required"]):
                raise ValueError("Screener candidate lacks the exact measured fields")
            cid = _identifier(entry["candidate_id"], "candidate_id")
            if cid not in expected or cid in seen:
                raise ValueError("Screener returned a foreign or repeated candidate identity")
            seen.add(cid)
            hook = _number(entry["hook_score"], "hook_score")
            payoff = _number(entry["payoff_score"], "payoff_score")
            self_contained = _boolean(entry["is_self_contained"])
            risk = _number(entry["misleading_risk"], "misleading_risk")
            comp = calculate_screener_score(
                hook_score=hook,
                payoff_score=payoff,
                misleading_risk=risk,
                is_self_contained=self_contained,
            )
            results.append(
                ScreenedCandidate(
                    candidate_id=cid,
                    hook_score=hook,
                    payoff_score=payoff,
                    is_self_contained=self_contained,
                    misleading_risk=risk,
                    composite_score=comp,
                    screener=self.name,
                    raw=entry,
                )
            )

        if seen != expected:
            raise ValueError("Screener omitted requested candidates; comparative ranking refused")
        # Rank only after validating the whole requested batch, including rows below top_k.
        results.sort(key=lambda s: (s.composite_score, s.hook_score), reverse=True)
        return tuple(results[:top_k])


class JevScreener:
    """Screener backed by TypeSafe AI's Jev System One decision model."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_url: str = TYPESAFE_API_URL,
        transport: Callable[[urllib.request.Request], bytes] | None = None,
    ) -> None:
        self.api_url = api_url
        resolved_key = api_key or os.environ.get(TYPESAFE_API_KEY_ENV)
        if not resolved_key:
            from hawedit.credentials import read_credential

            resolved_key = read_credential(TYPESAFE_API_KEY_ENV)
        if not resolved_key:
            raise CredentialError(
                "TYPESAFE_API_KEY is required for JevScreener; set TYPESAFE_API_KEY in "
                "environment or run python -m hawedit.credentials typesafe"
            )
        self.api_key = resolved_key
        self._transport = transport or self._default_transport

    @property
    def name(self) -> str:
        return "typesafe-jev"

    @staticmethod
    def _default_transport(req: urllib.request.Request) -> bytes:
        return _http_response(req)

    def screen_one(self, candidate_id: str, transcript: str) -> ScreenedCandidate:
        """Screen a single candidate span via TypeSafe Jev."""
        _identifier(candidate_id, "candidate_id")
        if not isinstance(transcript, str) or not transcript.strip():
            raise ValueError("Screener input requires actual nonempty transcript text")
        payload = {
            "state": transcript,
            "questions": {
                "is_self_contained": {
                    "type": "noul",
                    "instructions": (
                        "Does this speech transcript express a complete, self-contained thought "
                        "without starting or ending mid-sentence?"
                    ),
                },
                "hook_score": {
                    "type": "score",
                    "instructions": (
                        "Rate the scroll-stopping hook potential of the first sentence "
                        "from 0 to 100."
                    ),
                    "min": 0,
                    "max": 100,
                },
                "payoff_score": {
                    "type": "score",
                    "instructions": (
                        "Rate how strongly the ending delivers a punchline or satisfying "
                        "conclusion from 0 to 100."
                    ),
                    "min": 0,
                    "max": 100,
                },
                "misleading_risk": {
                    "type": "noul",
                    "instructions": (
                        "Would clipping this out of context distort the speaker's true intent "
                        "or meaning?"
                    ),
                },
            },
        }

        req = urllib.request.Request(
            self.api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        raw_bytes = self._transport(req)
        resp_json = _response(raw_bytes)
        if "answers" in resp_json:
            raise ValueError(
                "Current TypeSafe typed answers require the current-wire/model-policy repair; "
                "this legacy codec cannot measure that response"
            )
        questions = _object(resp_json.get("questions"), "legacy questions")
        if set(questions) != set(payload["questions"]):
            raise ValueError("Jev legacy response lacks the exact requested measurements")
        contained = _object(questions["is_self_contained"], "self-containment measurement")
        hook_q = _object(questions["hook_score"], "hook measurement")
        payoff_q = _object(questions["payoff_score"], "payoff measurement")
        risk_q = _object(questions["misleading_risk"], "risk measurement")
        self_contained = _boolean(contained.get("answer"))
        hook = _number(hook_q.get("answer"), "hook_score", 100.0) / 100.0
        payoff = _number(payoff_q.get("answer"), "payoff_score", 100.0) / 100.0
        risk = _number(risk_q.get("probability"), "misleading_risk")

        comp = calculate_screener_score(
            hook_score=hook,
            payoff_score=payoff,
            misleading_risk=risk,
            is_self_contained=self_contained,
        )

        return ScreenedCandidate(
            candidate_id=candidate_id,
            hook_score=hook,
            payoff_score=payoff,
            is_self_contained=self_contained,
            misleading_risk=risk,
            composite_score=comp,
            screener=self.name,
            raw=resp_json,
        )

    def screen(
        self,
        candidates: Sequence[tuple[MergedCandidate, str]],
        *,
        top_k: int = 5,
    ) -> tuple[ScreenedCandidate, ...]:
        _inputs(candidates, top_k)
        if not candidates:
            return ()

        results: list[ScreenedCandidate] = []
        for candidate, transcript in candidates:
            screened = self.screen_one(candidate.candidate_id, transcript)
            results.append(screened)

        results.sort(key=lambda s: (s.composite_score, s.hook_score), reverse=True)
        return tuple(results[:top_k])


def get_screener(
    name: str | None,
    *,
    gemini_key: str | None = None,
    typesafe_key: str | None = None,
    transport: ScreenerTransport | None = None,
) -> CandidateScreener | None:
    """Factory function to resolve candidate screener with fail-stop validation."""
    if not name or name.lower() in ("none", "false", "off"):
        return None
    normalized = name.lower().strip()
    if normalized in ("gemini", "gemini-flash", "flash", "flash-lite"):
        return GeminiFlashScreener(api_key=gemini_key, transport=transport)
    if normalized in ("jev", "typesafe", "typesafe-jev"):
        return JevScreener(api_key=typesafe_key, transport=transport)
    raise ValueError(
        f"Unknown screener name: {name!r}; valid choices are 'none', 'gemini-flash', 'jev'"
    )
