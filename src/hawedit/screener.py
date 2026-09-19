"""Fast Candidate Screener Funnel (D-275).

Evaluates Stage 3 candidate spans in sub-second time using cheap/fast System One decision
models (Gemini 2.5 Flash / Flash-Lite or TypeSafe Jev), pruning large candidate pools down
to the top survivors before dispatching to Stage 4 Gemini 2.5 Pro for full Sorani Kurdish
editorial copywriting.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Final, Protocol

from hawedit.credentials import CredentialError
from hawedit.discovery import MergedCandidate

TYPESAFE_API_KEY_ENV: Final[str] = "TYPESAFE_API_KEY"
TYPESAFE_API_URL: Final[str] = "https://api.typesafe.ai/v1/systemone"

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
        if not (0.0 <= self.hook_score <= 1.0):
            raise ValueError(f"hook_score must be in [0.0, 1.0], got {self.hook_score}")
        if not (0.0 <= self.payoff_score <= 1.0):
            raise ValueError(f"payoff_score must be in [0.0, 1.0], got {self.payoff_score}")
        if not (0.0 <= self.misleading_risk <= 1.0):
            raise ValueError(f"misleading_risk must be in [0.0, 1.0], got {self.misleading_risk}")
        if not (0.0 <= self.composite_score <= 1.0):
            raise ValueError(f"composite_score must be in [0.0, 1.0], got {self.composite_score}")

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
        with urllib.request.urlopen(req, timeout=30) as resp:
            data: bytes = resp.read()
            return data

    def screen(
        self,
        candidates: Sequence[tuple[MergedCandidate, str]],
        *,
        top_k: int = 5,
    ) -> tuple[ScreenedCandidate, ...]:
        if not candidates:
            return ()
        if top_k < 1:
            raise ValueError(f"top_k must be at least 1, got {top_k}")

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
        response_json = json.loads(raw_bytes.decode("utf-8"))
        text_content = (
            response_json.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "{}")
        )
        parsed = json.loads(text_content)
        raw_list = parsed.get("candidates", [])

        results: list[ScreenedCandidate] = []
        for entry in raw_list:
            cid = str(entry.get("candidate_id", ""))
            hook = float(entry.get("hook_score", 0.0))
            payoff = float(entry.get("payoff_score", 0.0))
            self_contained = bool(entry.get("is_self_contained", False))
            risk = float(entry.get("misleading_risk", 0.0))
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

        # Sort descending by composite score, then hook score
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
        with urllib.request.urlopen(req, timeout=30) as resp:
            data: bytes = resp.read()
            return data

    def screen_one(self, candidate_id: str, transcript: str) -> ScreenedCandidate:
        """Screen a single candidate span via TypeSafe Jev."""
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
        resp_json = json.loads(raw_bytes.decode("utf-8"))
        questions = resp_json.get("questions", {})

        self_contained_q = questions.get("is_self_contained", {})
        self_contained = bool(self_contained_q.get("answer", False))
        hook_raw = float(questions.get("hook_score", {}).get("answer", 0.0)) / 100.0
        payoff_raw = float(questions.get("payoff_score", {}).get("answer", 0.0)) / 100.0
        risk_raw = float(questions.get("misleading_risk", {}).get("probability", 0.0))

        hook = max(0.0, min(1.0, hook_raw))
        payoff = max(0.0, min(1.0, payoff_raw))
        risk = max(0.0, min(1.0, risk_raw))

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
        if not candidates:
            return ()
        if top_k < 1:
            raise ValueError(f"top_k must be at least 1, got {top_k}")

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
) -> CandidateScreener | None:
    """Factory function to resolve candidate screener with fail-stop validation."""
    if not name or name.lower() in ("none", "false", "off"):
        return None
    normalized = name.lower().strip()
    if normalized in ("gemini", "gemini-flash", "flash", "flash-lite"):
        return GeminiFlashScreener(api_key=gemini_key)
    if normalized in ("jev", "typesafe", "typesafe-jev"):
        return JevScreener(api_key=typesafe_key)
    raise ValueError(
        f"Unknown screener name: {name!r}; valid choices are 'none', 'gemini-flash', 'jev'"
    )
