"""§3 Stage 3 Path A — the Kurdish judge reads the whole transcript.

    Send the **full normalized Sorani transcript** to the Kurdish judge in one pass. Not a
    filtered subset. A purely verbal moment — no motion, no visual signal — is invisible to
    every local component in this pipeline. If the visual stage filters first, the best clip
    in the episode is gone before anything that understands Kurdish ever reads it.

    Cost is not a reason to withhold it: a one-hour transcript is roughly 20K tokens, about
    $0.04 per source hour.

`discovery.py` built the union and had no producers. This is the first one, and it exists now
because `generativelanguage.googleapis.com` turned out to be reachable from this environment
while the model weights are not — so the half of Stage 3 that needs a hosted model is the half
that can be finished.

**"Not a filtered subset" is the whole design, and it is a refusal.** Every temptation here is
to send less: sample the transcript, drop the quiet parts, skip anything the local index scored
low. Each would be invisible in the output — the candidates that came back would still look
reasonable — and each would reintroduce exactly the failure §3 spends a paragraph on. So the
prompt carries the transcript entire, and a transcript too long for one request is **refused
with the arithmetic** rather than quietly split. Splitting would be this module deciding which
parts of a ten-hour transcript the Kurdish judge gets to read.

**Kurdish invariant #3 holds here too.** The judge is a model input, so it reads
`transcript.norm.json`. `assert_model_input` refuses a raw transcript at the door.

**A model asked for millisecond spans will invent one.** Every returned candidate is checked
against the transcript's own time range, because a candidate that runs past the media is a
clip that cannot be cut — and it would reach Stage 5 as a boundary to fuse rather than as a
mistake to reject.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Any, Final

from hawedit.clip import DiscoveryPath
from hawedit.discovery import Candidate
from hawedit.gemini import (
    API_ROOT,
    GeminiJudge,
    Governance,
    JudgeUnusable,
    Transport,
    count_tokens,
)
from hawedit.judge import InputMode, JudgeRequest
from hawedit.transcripts import NormalizedTranscript, assert_model_input

__all__ = [
    "CANDIDATE_SCHEMA",
    "PathADiscovery",
    "discover_verbal",
]

# The judge's output shape, enforced by the API rather than requested in prose.
CANDIDATE_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "in_ms": {"type": "integer"},
                    "out_ms": {"type": "integer"},
                    "score": {"type": "number"},
                    "reason_ckb": {"type": "string"},
                },
                "required": ["in_ms", "out_ms", "score", "reason_ckb"],
            },
        }
    },
    "required": ["candidates"],
}

_PROMPT = """You are the Kurdish editorial judge for a Central Kurdish (Sorani, ckb) video
repurposing system. This is candidate discovery over a complete transcript.

Read the WHOLE transcript below and find every moment that could stand alone as a short social
clip. Do not restrict yourself to the most obvious ones, and do not skip a moment because it is
purely spoken — a talking head with no motion is exactly what this pass exists to catch, and
nothing else in the system can see it.

For each candidate return:
- in_ms, out_ms: the span, in milliseconds from the start of the source. Both MUST fall within
  {start_ms}..{end_ms}, and out_ms MUST be greater than in_ms.
- score: how strong a clip it would make (0..1).
- reason_ckb: one short sentence, IN CENTRAL KURDISH (Sorani, Arabic script), saying why.

Return an empty list if nothing in this transcript would stand alone. That is a real answer.

Word timings, for locating your spans:
{timings}

Transcript:
{text}
"""


def _timing_table(transcript: NormalizedTranscript, limit: int = 4000) -> str:
    """Word timings the judge can locate spans by.

    Without these a language model has no way to answer in milliseconds and will guess. The
    list is truncated only at a size that would itself blow the request budget, and the
    truncation is stated in the prompt rather than silent.
    """
    words = transcript.words
    rows = [f"{w.start_ms}-{w.end_ms} {w.w}" for w in words[:limit]]
    if len(words) > limit:
        rows.append(f"[... {len(words) - limit} further words omitted from this timing table; ")
        rows.append("the transcript text below is complete]")
    return "\n".join(rows)


class PathADiscovery:
    """§3 Stage 3 Path A, behind the same §7 routing as the Stage 4 judge."""

    def __init__(
        self,
        api_key: str | None = None,
        model_id: str = "gemini-2.5-pro",
        governance: Governance | None = None,
        transport: Transport | None = None,
        max_attempts: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        # Composition rather than inheritance: Path A is not a `judge()` implementation — it
        # returns candidates, not a verdict — but it shares §7 routing, credentials, retry and
        # governance with the Stage 4 judge, and duplicating those is how two code paths end
        # up with two different governance checks.
        self._judge = GeminiJudge(
            api_key=api_key,
            model_id=model_id,
            governance=governance,
            transport=transport,
            max_attempts=max_attempts,
            sleep=sleep,
        )
        self.model_id = model_id

    @property
    def governance(self) -> Governance:
        return self._judge.governance

    def _prompt(self, transcript: NormalizedTranscript) -> str:
        # Invariant #3 at the door: the judge is a model input and reads norm, never raw.
        assert_model_input(transcript)
        words = transcript.words
        return _PROMPT.format(
            start_ms=words[0].start_ms if words else 0,
            end_ms=words[-1].end_ms if words else 0,
            timings=_timing_table(transcript),
            text=transcript.text_ckb,
        )

    def build_request(
        self, transcript: NormalizedTranscript, tokens: int | None = None
    ) -> JudgeRequest:
        """The §3 Stage 4 request object for this discovery pass, for costing and ceilings.

        Raises:
            TypeError: a raw transcript was passed (Kurdish invariant #3). `_prompt` checks
                this and `discover` goes through it, but this method is public and documented
                as usable on its own — and `RawTranscript` duck-types `NormalizedTranscript`
                exactly, so nothing but this call stops raw text reaching a `JudgeRequest` and
                from there the network. Found by the second independent review.
        """
        assert_model_input(transcript)
        return JudgeRequest(
            candidate_id=f"{transcript.media_id}-path-a",
            mode=InputMode.PATH_A_DISCOVERY,
            tokens=tokens,
            text_ckb=transcript.text_ckb,
        )

    def discover(self, transcript: NormalizedTranscript) -> tuple[Candidate, ...]:
        """Read the whole transcript and return every candidate the judge found.

        Raises:
            TypeError: a raw transcript was passed (Kurdish invariant #3).
            GeminiUnavailable: governance forbids the upload, or the API refused.
            RequestTooLarge: the transcript is too long for one pass — see the module docstring
                on why this refuses rather than splits.
            JudgeUnusable: a returned candidate is not one this system can use.
        """
        self.governance.assert_permits_upload()
        prompt = self._prompt(transcript)

        counted = count_tokens(prompt, self._judge._key, self.model_id, self._judge._transport)
        replace(self.build_request(transcript), tokens=counted).assert_within_tier()

        payload = json.dumps(
            {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": CANDIDATE_SCHEMA,
                    # Discovery is compared against a gold set in §8.2. A pass that returns a
                    # different candidate list each run makes Recall@K measure sampling.
                    "temperature": 0.0,
                },
            }
        ).encode("utf-8")

        body = self._judge._post(f"{API_ROOT}/models/{self.model_id}:generateContent", payload)
        return self._to_candidates(body, transcript)

    def _to_candidates(self, body: str, transcript: NormalizedTranscript) -> tuple[Candidate, ...]:
        try:
            text = json.loads(body)["candidates"][0]["content"]["parts"][0]["text"]
            found = json.loads(text)["candidates"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise JudgeUnusable(f"Path A returned nothing usable: {exc}") from exc

        words = transcript.words
        start_ms = words[0].start_ms if words else 0
        end_ms = words[-1].end_ms if words else 0

        checked: list[tuple[float, int, int, str]] = []
        for raw in found:
            try:
                in_ms, out_ms = int(raw["in_ms"]), int(raw["out_ms"])
                score = float(raw["score"])
                reason = str(raw.get("reason_ckb", ""))
            except (KeyError, TypeError, ValueError) as exc:
                raise JudgeUnusable(f"Path A candidate is malformed: {raw!r} ({exc})") from exc

            if out_ms <= in_ms:
                raise JudgeUnusable(
                    f"Path A candidate {in_ms}..{out_ms} has no length. A span that occupies no "
                    f"time cannot be cut, and Stage 5 would receive it as a boundary to fuse."
                )
            if in_ms < start_ms or out_ms > end_ms:
                raise JudgeUnusable(
                    f"Path A candidate {in_ms}..{out_ms} falls outside the transcript "
                    f"({start_ms}..{end_ms}). The judge invented a span past the media, and a "
                    f"clip cannot be cut from time the source does not have."
                )
            if not 0.0 <= score <= 1.0:
                raise JudgeUnusable(f"Path A candidate score {score} is outside [0, 1]")
            checked.append((score, in_ms, out_ms, reason))

        # Rank by score, densely and deterministically. §8.2 counts Recall@K by rank, so a gap
        # or a duplicate would make every K mean something slightly different. Ties break on
        # start time so a re-run never reshuffles a list someone is reviewing.
        checked.sort(key=lambda item: (-item[0], item[1]))
        return tuple(
            Candidate(
                candidate_id=f"{transcript.media_id}-verbal-{position}",
                media_id=transcript.media_id,
                in_ms=in_ms,
                out_ms=out_ms,
                path=DiscoveryPath.VERBAL,
                rank=position,
                score=score,
            )
            for position, (score, in_ms, out_ms, _reason) in enumerate(checked, start=1)
        )


def discover_verbal(
    transcript: NormalizedTranscript,
    api_key: str | None = None,
    **kwargs: Any,
) -> Sequence[Candidate]:
    """One-call Path A, for callers that do not need to hold the client."""
    return PathADiscovery(api_key=api_key, **kwargs).discover(transcript)
