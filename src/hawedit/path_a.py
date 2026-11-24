"""§3 Stage 3 Path A — the Kurdish judge reads the whole transcript as numbered sentences.

    Send the **full normalized Sorani transcript** to the Kurdish judge in one pass. Not a
    filtered subset. A purely verbal moment — no motion, no visual signal — is invisible to
    every local component in this pipeline. If the visual stage filters first, the best clip
    in the episode is gone before anything that understands Kurdish ever reads it.

    Cost is not a reason to withhold it: a one-hour transcript is roughly 20K tokens, about
    $0.04 per source hour.

**Sentence numbers instead of milliseconds (D-344).** The legacy 4,000-word millisecond timing
table truncated long episodes (e.g. a 16,000-word podcast lost all timings past word 4,000) and
tempted the model into guessing word offsets. Path A now sends every normalized sentence as a
0-based numbered line `[i] <sentence>` across the entire transcript, receives inclusive sentence
indices `[start_sentence, end_sentence]`, and resolves timestamps deterministically in code from
CTC-aligned `Sentence` boundaries. Invalid, out-of-range, inverted, or incomplete-sentence indices
fail visibly (`JudgeUnusable`) instead of clamping or guessing.

**Kurdish invariant #3 holds here too.** The judge is a model input, so it reads
`transcript.norm.json` with normalized Sorani text. `assert_model_input` refuses raw transcripts
at the door.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Final

from hawedit.audio_signals import SentenceAudioMetrics
from hawedit.clip import MAX_CANDIDATE_SPAN_MS, MIN_CANDIDATE_SPAN_MS, DiscoveryPath
from hawedit.discovery import Candidate
from hawedit.gemini import (
    GeminiJudge,
    Governance,
    JudgeUnusable,
    Transport,
    extract_response_text,
)
from hawedit.judge import (
    KURDISH_EDITORIAL_JUDGE,
    BilledCall,
    InputMode,
    JudgeRequest,
    estimate_cost_usd,
)
from hawedit.normalize import normalize_sorani
from hawedit.sentences import Sentence, segment_sentences
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
                    "start_sentence": {"type": "integer"},
                    "end_sentence": {"type": "integer"},
                    "score": {"type": "number"},
                    "reason_ckb": {"type": "string"},
                },
                "required": ["start_sentence", "end_sentence", "score", "reason_ckb"],
            },
        }
    },
    "required": ["candidates"],
}

_AUDIO_GUIDANCE: Final[str] = (
    "\nAcoustic delivery tags ([high-energy], [burst], [fast]) mark vocal intensity and pacing "
    "peaks; prefer tight 30–55 s single-idea payoff arcs with strong opening energy or bursts.\n"
)

_PROMPT = """You are the Kurdish editorial judge for a Central Kurdish (Sorani, ckb) video
repurposing system. This is candidate discovery over a complete transcript.

Read ALL numbered sentences below and find every moment that could stand alone as a short social
clip. Do not restrict yourself to the most obvious ones, and do not skip a moment because it is
purely spoken — a talking head with no motion is exactly what this pass exists to catch, and
nothing else in the system can see it.

A clip here runs {min_s} to {max_s} seconds (strongly prefer crisp, high-retention 30 to 55 second
single-idea arcs over meandering 65+ second monologues). A one- or five-second span is a fragment
rather than a clip: it cannot carry a whole thought, and a later stage will refuse it as a
misleading edit. So return the inclusive range of complete sentences that holds the whole point —
the setup that makes it land and the payoff that follows — never exceeding {max_s} seconds total (a
single complete sentence is allowed when it already spans {min_s} to {max_s} seconds).
NEVER open on an unresolved pronoun or subject-less reference unless the subject is named within
the first 3 seconds, skip weak conversational throat-clearing or greetings so start_sentence lands
directly on the scroll-stopping hook sentence, and end cleanly on the payoff rather than drifting
into a second tangent.

For each candidate return:
- start_sentence, end_sentence: 0-based inclusive sentence numbers from the numbered transcript
  below. Both MUST fall within 0..{last_sentence}, end_sentence MUST be >= start_sentence, and the
  combined sentences SHOULD run roughly {min_s} to {max_s} seconds (each sentence's duration in
  seconds is shown at the end of its line). Code maps these exact sentence numbers to CTC-aligned
  timestamps; never guess millisecond values. NEVER choose a sentence tagged [incomplete] as
  start_sentence or end_sentence (an [incomplete] sentence may appear strictly inside a span, never
  as start_sentence or end_sentence).
- score: how strong a clip it would make (0..1).
- reason_ckb: one short sentence, IN CENTRAL KURDISH (Sorani, Arabic script), saying why.
{audio_guidance}
Return an empty list if nothing in this transcript would stand alone. That is a real answer.

Numbered sentences:
{numbered_sentences}
"""


def _numbered_sentences(
    sentences: Sequence[Sentence],
    audio_metrics: Sequence[SentenceAudioMetrics] | None = None,
) -> str:
    """Format every sentence with its 0-based index in normalized Sorani (no truncation)."""
    if not sentences:
        return "(no sentences)"
    metrics_by_idx = (
        {m.sentence_index: m for m in audio_metrics} if audio_metrics is not None else {}
    )
    lines: list[str] = []
    for index, sentence in enumerate(sentences):
        dur_s = max(0.0, (sentence.end_ms - sentence.start_ms) / 1000.0)
        tag = f" ({dur_s:.1f}s) [incomplete]" if not sentence.complete else f" ({dur_s:.1f}s)"
        metric = metrics_by_idx.get(index)
        if metric is not None and metric.tags:
            tag = f"{tag} [{', '.join(metric.tags)}]"
        lines.append(f"[{index}] {normalize_sorani(sentence.text)}{tag}")
    return "\n".join(lines)


def _sentence_cache_digest(
    transcript: NormalizedTranscript,
    sentences: Sequence[Sentence],
    audio_metrics: Sequence[SentenceAudioMetrics] | None = None,
    *,
    configuration: dict[str, Any] | None = None,
) -> str:
    body: dict[str, Any] = {
        "transcript": json.loads(transcript.to_json()),
        "sentences": [asdict(sentence) for sentence in sentences],
        "configuration": configuration,
        "prompt": _PROMPT,
        "schema": CANDIDATE_SCHEMA,
    }
    if audio_metrics is not None:
        body["audio_metrics"] = [asdict(metric) for metric in audio_metrics]
    payload = json.dumps(
        body,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_cached_candidates(
    path: Path, transcript: NormalizedTranscript, sentences: Sequence[Sentence]
) -> tuple[Candidate, ...]:
    """Cache bytes are input, not proof of a valid discovery result."""
    try:
        with path.open("rb") as stream:
            payload = stream.read(4 * 1024 * 1024 + 1)
        if len(payload) > 4 * 1024 * 1024:
            raise ValueError("cache exceeds the bounded record size")
        records = json.loads(payload)
        if not isinstance(records, list):
            raise ValueError("cache must contain a candidate array")
        starts = {sentence.start_ms for sentence in sentences if sentence.complete}
        ends = {sentence.end_ms for sentence in sentences if sentence.complete}
        found: list[Candidate] = []
        seen: set[str] = set()
        fields = {"candidate_id", "media_id", "in_ms", "out_ms", "path", "rank", "score"}
        for rank, record in enumerate(records, 1):
            if not isinstance(record, dict) or set(record) != fields:
                raise ValueError("cache candidate fields do not match the discovery schema")
            if (
                record["media_id"] != transcript.media_id
                or record["path"] != DiscoveryPath.VERBAL.value
                or not isinstance(record["candidate_id"], str)
                or not record["candidate_id"].strip()
                or record["candidate_id"] in seen
                or type(record["rank"]) is not int
                or record["rank"] != rank
                or type(record["in_ms"]) is not int
                or record["in_ms"] not in starts
                or type(record["out_ms"]) is not int
                or record["out_ms"] not in ends
                or record["out_ms"] <= record["in_ms"]
                or type(record["score"]) not in (int, float)
                or not math.isfinite(record["score"])
                or not 0 <= record["score"] <= 1
            ):
                raise ValueError("cache candidate identity, alignment, rank or score is invalid")
            seen.add(record["candidate_id"])
            found.append(Candidate(**dict(record, path=DiscoveryPath.VERBAL)))
        return tuple(found)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise JudgeUnusable(f"Path A discovery cache refused: {exc}") from exc


class PathADiscovery:
    """§3 Stage 3 Path A, behind the same §7 routing as the Stage 4 judge."""

    def __init__(
        self,
        api_key: str | None = None,
        model_id: str = KURDISH_EDITORIAL_JUDGE,
        governance: Governance | None = None,
        transport: Transport | None = None,
        max_attempts: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        client: GeminiJudge | None = None,
        *,
        k: int = 5,
        min_votes: int = 2,
        iou_threshold: float = 0.6,
        cache_dir: Path | None = None,
    ) -> None:
        # Composition rather than inheritance: Path A is not a `judge()` implementation — it
        # returns candidates, not a verdict — but it shares §7 routing, credentials, retry and
        # governance with the Stage 4 judge, and duplicating those is how two code paths end
        # up with two different governance checks.
        if client is not None and any(
            value is not None for value in (api_key, governance, transport)
        ):
            raise ValueError("client is mutually exclusive with Path A transport arguments")
        self._judge = client or GeminiJudge(
            api_key=api_key,
            model_id=model_id,
            governance=governance,
            transport=transport,
            max_attempts=max_attempts,
            sleep=sleep,
        )
        self.model_id = self._judge.model_id
        self.last_billed_call: BilledCall | None = None
        self.billed_calls: list[BilledCall] = []
        self.k = k
        self.min_votes = min_votes
        self.iou_threshold = iou_threshold
        self.cache_dir = cache_dir

    @property
    def governance(self) -> Governance:
        return self._judge.governance

    def _resolve_sentences(
        self, transcript: NormalizedTranscript, sentences: Sequence[Sentence] | None
    ) -> tuple[Sentence, ...]:
        assert_model_input(transcript)
        if sentences is not None:
            return tuple(sentences)
        return segment_sentences(transcript.words)

    def _prompt(
        self,
        transcript: NormalizedTranscript,
        sentences: Sequence[Sentence] | None = None,
        audio_metrics: Sequence[SentenceAudioMetrics] | None = None,
    ) -> str:
        # Invariant #3 at the door: the judge is a model input and reads norm, never raw.
        resolved = self._resolve_sentences(transcript, sentences)
        last_sentence = len(resolved) - 1 if resolved else 0
        audio_guidance = _AUDIO_GUIDANCE if audio_metrics else ""
        return _PROMPT.format(
            min_s=MIN_CANDIDATE_SPAN_MS // 1_000,
            max_s=MAX_CANDIDATE_SPAN_MS // 1_000,
            last_sentence=last_sentence,
            audio_guidance=audio_guidance,
            numbered_sentences=_numbered_sentences(resolved, audio_metrics=audio_metrics),
        )

    def build_request(
        self, transcript: NormalizedTranscript, tokens: int | None = None
    ) -> JudgeRequest:
        """The §3 Stage 4 request object for this discovery pass, for costing and ceilings.

        Raises:
            TypeError: a raw transcript was passed (Kurdish invariant #3).
        """
        assert_model_input(transcript)
        return JudgeRequest(
            candidate_id=f"{transcript.media_id}-path-a",
            mode=InputMode.PATH_A_DISCOVERY,
            tokens=tokens,
            text_ckb=transcript.text_ckb,
        )

    def discover(
        self,
        transcript: NormalizedTranscript,
        *,
        k: int | None = None,
        sentences: Sequence[Sentence] | None = None,
        audio_metrics: Sequence[SentenceAudioMetrics] | None = None,
    ) -> tuple[Candidate, ...]:
        """Read the whole numbered transcript and return candidate moments via K-run voting."""
        resolved = self._resolve_sentences(transcript, sentences)
        effective_k = k if k is not None else self.k
        if effective_k <= 1:
            return self._discover_single(
                transcript, sentences=resolved, audio_metrics=audio_metrics
            )

        transcript_hash = _sentence_cache_digest(
            transcript,
            resolved,
            audio_metrics=audio_metrics,
            configuration={
                "model": self.model_id,
                "provider": type(self._judge).__qualname__,
                "min_votes": self.min_votes,
                "iou_threshold": self.iou_threshold,
            },
        )
        if self.cache_dir is not None and self.cache_dir.is_dir():
            cache_file = self.cache_dir / f"path_a_{transcript_hash}_k{effective_k}.json"
            if cache_file.is_file():
                return _read_cached_candidates(cache_file, transcript, resolved)

        runs: list[tuple[Candidate, ...]] = []
        last_unusable: JudgeUnusable | None = None
        for _ in range(effective_k):
            try:
                runs.append(
                    self._discover_single(
                        transcript, sentences=resolved, audio_metrics=audio_metrics
                    )
                )
            except JudgeUnusable as exc:
                last_unusable = exc
        if len(runs) < self.min_votes:
            if last_unusable is not None:
                raise last_unusable
            raise JudgeUnusable("Path A discovery produced fewer usable passes than min_votes")

        from hawedit.discovery import vote_candidate_spans

        voted = vote_candidate_spans(
            runs,
            iou_match=self.iou_threshold,
            min_votes=self.min_votes,
            media_id=transcript.media_id,
        )

        if self.cache_dir is not None and self.cache_dir.is_dir():
            cache_file = self.cache_dir / f"path_a_{transcript_hash}_k{effective_k}.json"
            with contextlib.suppress(Exception):
                cache_file.write_text(
                    json.dumps(
                        [
                            {
                                "candidate_id": c.candidate_id,
                                "media_id": c.media_id,
                                "in_ms": c.in_ms,
                                "out_ms": c.out_ms,
                                "path": c.path.value,
                                "rank": c.rank,
                                "score": c.score,
                            }
                            for c in voted
                        ],
                        indent=2,
                    ),
                    encoding="utf-8",
                )

        return voted

    def _discover_single(
        self,
        transcript: NormalizedTranscript,
        sentences: Sequence[Sentence] | None = None,
        audio_metrics: Sequence[SentenceAudioMetrics] | None = None,
    ) -> tuple[Candidate, ...]:
        """Single discovery pass against Gemini API."""
        resolved = self._resolve_sentences(transcript, sentences)
        prompt = self._prompt(transcript, sentences=resolved, audio_metrics=audio_metrics)

        parts = [{"text": prompt}]
        counted = self._judge.count_parts(parts)
        replace(self.build_request(transcript), tokens=counted).assert_within_tier()
        body = self._judge.generate_json(parts, CANDIDATE_SCHEMA)
        call = BilledCall(
            model=self.model_id,
            tokens=counted,
            cost_usd_estimate=estimate_cost_usd(counted),
            stage="discovery",
            candidate_id=f"{transcript.media_id}-path-a",
        )
        self.last_billed_call = call
        self.billed_calls.append(call)
        return self._to_candidates(body, transcript, sentences=resolved)

    def _to_candidates(
        self,
        body: str,
        transcript: NormalizedTranscript,
        sentences: Sequence[Sentence] | None = None,
    ) -> tuple[Candidate, ...]:
        resolved = self._resolve_sentences(transcript, sentences)
        try:
            text = extract_response_text(body)
            document = json.loads(text)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise JudgeUnusable(f"Path A returned nothing usable: {exc}") from exc
        if not isinstance(document, dict):
            raise JudgeUnusable(
                f"Path A response must be a JSON object, got {type(document).__name__}"
            )
        found = document.get("candidates")
        if not isinstance(found, list):
            raise JudgeUnusable(
                f"Path A candidates must be a JSON array, got {type(found).__name__}"
            )

        checked: list[tuple[float, int, int, str]] = []
        sentence_count = len(resolved)
        for raw in found:
            if not isinstance(raw, dict):
                raise JudgeUnusable(
                    f"Path A candidate must be a JSON object, got {type(raw).__name__}"
                )
            try:
                raw_start = raw["start_sentence"]
                raw_end = raw["end_sentence"]
                raw_score = raw["score"]
                if isinstance(raw_start, bool) or not isinstance(raw_start, int):
                    raise TypeError(f"start_sentence must be a JSON integer, got {raw_start!r}")
                if isinstance(raw_end, bool) or not isinstance(raw_end, int):
                    raise TypeError(f"end_sentence must be a JSON integer, got {raw_end!r}")
                if (
                    isinstance(raw_score, bool)
                    or not isinstance(raw_score, int | float)
                    or (isinstance(raw_score, float) and not math.isfinite(raw_score))
                ):
                    raise TypeError(f"score must be a finite JSON number, got {raw_score!r}")
                if not 0.0 <= raw_score <= 1.0:
                    raise ValueError(f"score {raw_score} is outside [0, 1]")
                start_idx, end_idx = raw_start, raw_end
                score = float(raw_score)
                reason_value = raw["reason_ckb"]
                if not isinstance(reason_value, str):
                    raise TypeError(
                        f"reason_ckb must be a JSON string, got {type(reason_value).__name__}"
                    )
                reason = reason_value
            except (KeyError, TypeError, ValueError) as exc:
                raise JudgeUnusable(f"Path A candidate is malformed: {raw!r} ({exc})") from exc

            if start_idx < 0 or end_idx >= sentence_count:
                raise JudgeUnusable(
                    f"Path A candidate {start_idx}..{end_idx} falls outside the valid "
                    f"sentence range (0..{max(0, sentence_count - 1)})."
                )
            if end_idx < start_idx:
                raise JudgeUnusable(
                    f"Path A candidate {start_idx}..{end_idx} is inverted "
                    f"(end_sentence < start_sentence)."
                )
            start_sentence = resolved[start_idx]
            end_sentence = resolved[end_idx]
            if not start_sentence.complete or not end_sentence.complete:
                raise JudgeUnusable(
                    f"Path A candidate {start_idx}..{end_idx} terminates on an incomplete "
                    f"sentence boundary; §5 forbids fragments."
                )
            in_ms = start_sentence.start_ms
            out_ms = end_sentence.end_ms
            if out_ms <= in_ms:
                raise JudgeUnusable(
                    f"Path A candidate sentences {start_idx}..{end_idx} occupy no time "
                    f"({in_ms}..{out_ms} ms)."
                )
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
    *,
    sentences: Sequence[Sentence] | None = None,
    audio_metrics: Sequence[SentenceAudioMetrics] | None = None,
    **kwargs: Any,
) -> Sequence[Candidate]:
    """One-call Path A, for callers that do not need to hold the client."""
    return PathADiscovery(api_key=api_key, **kwargs).discover(
        transcript, sentences=sentences, audio_metrics=audio_metrics
    )
