"""Grounded story relations connecting narrative meaning to visual events (VE-05 / V05).

Connects canonical sentences to visual evidence IDs (keyframes, tracked events, subject
observations) with explicit relation semantics: question/answer, setup/payoff,
claim/qualification, earlier/later correction, demonstration/explanation, and visible reaction.

Enforces strict provenance: every relation MUST cite real canonical sentence IDs and real
visual event IDs. Fabricated or ungrounded references are rejected with StoryGroundingError.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from hawedit.transcripts import validate_media_id

__all__ = [
    "StoryGroundingError",
    "StoryMap",
    "StoryRelation",
    "StoryRelationKind",
    "build_story_map",
]


class StoryGroundingError(ValueError):
    """Raised when a story relation lacks canonical grounding or cites unobserved visual
    evidence."""


class StoryRelationKind(str, Enum):
    """Semantic narrative relation between verbal assertions and visual events."""

    QUESTION_ANSWER = "question_answer"
    SETUP_PAYOFF = "setup_payoff"
    CLAIM_QUALIFICATION = "claim_qualification"
    CORRECTION = "correction"
    DEMONSTRATION_EXPLANATION = "demonstration_explanation"
    VISIBLE_REACTION = "visible_reaction"


@dataclass(frozen=True, slots=True)
class StoryRelation:
    """One verified semantic relation connecting canonical speech to visual evidence."""

    relation_id: str
    kind: StoryRelationKind
    canonical_sentence_ids: tuple[str, ...]
    visual_event_ids: tuple[str, ...]
    in_ms: int
    out_ms: int
    confidence: float
    required_context_sentence_ids: tuple[str, ...] = ()
    summary: str = ""
    evidence_notes: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.relation_id, str) or not self.relation_id.strip():
            raise ValueError("relation_id must be a non-empty string")
        if not isinstance(self.kind, StoryRelationKind):
            raise TypeError(f"kind must be a StoryRelationKind, got {type(self.kind).__name__}")
        if not self.canonical_sentence_ids:
            raise StoryGroundingError("story relation requires at least one canonical sentence ID")
        for sid in self.canonical_sentence_ids:
            if not isinstance(sid, str) or not sid.strip():
                raise StoryGroundingError(f"invalid canonical sentence ID: {sid!r}")
        if not self.visual_event_ids:
            raise StoryGroundingError("story relation requires at least one visual event ID")
        for vid in self.visual_event_ids:
            if not isinstance(vid, str) or not vid.strip():
                raise StoryGroundingError(f"invalid visual event ID: {vid!r}")
        for cid in self.required_context_sentence_ids:
            if not isinstance(cid, str) or not cid.strip():
                raise StoryGroundingError(f"invalid required context sentence ID: {cid!r}")
        if type(self.in_ms) is not int or type(self.out_ms) is not int:
            raise TypeError("timestamps must be exact integers")
        if self.in_ms < 0:
            raise ValueError(f"in_ms must be non-negative, got {self.in_ms}")
        if self.out_ms <= self.in_ms:
            raise ValueError(f"out_ms ({self.out_ms}) must be > in_ms ({self.in_ms})")
        if type(self.confidence) not in (int, float) or not math.isfinite(self.confidence):
            raise TypeError("confidence must be a finite float")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError(f"confidence must be in 0.0..1.0, got {self.confidence}")

    @property
    def duration_ms(self) -> int:
        return self.out_ms - self.in_ms

    def to_dict(self) -> dict[str, Any]:
        return {
            "relation_id": self.relation_id,
            "kind": self.kind.value,
            "canonical_sentence_ids": list(self.canonical_sentence_ids),
            "visual_event_ids": list(self.visual_event_ids),
            "in_ms": self.in_ms,
            "out_ms": self.out_ms,
            "duration_ms": self.duration_ms,
            "confidence": round(float(self.confidence), 4),
            "required_context_sentence_ids": list(self.required_context_sentence_ids),
            "summary": self.summary,
            "evidence_notes": self.evidence_notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StoryRelation:
        return cls(
            relation_id=str(data["relation_id"]),
            kind=StoryRelationKind(str(data["kind"])),
            canonical_sentence_ids=tuple(str(s) for s in data["canonical_sentence_ids"]),
            visual_event_ids=tuple(str(v) for v in data["visual_event_ids"]),
            in_ms=int(data["in_ms"]),
            out_ms=int(data["out_ms"]),
            confidence=float(data["confidence"]),
            required_context_sentence_ids=tuple(
                str(c) for c in data.get("required_context_sentence_ids", ())
            ),
            summary=str(data.get("summary", "")),
            evidence_notes=str(data.get("evidence_notes", "")),
        )


@dataclass(frozen=True, slots=True)
class StoryMap:
    """Episode-level narrative relation map grounded in canonical and visual evidence."""

    media_id: str
    relations: tuple[StoryRelation, ...]
    known_sentence_ids: frozenset[str]
    known_visual_event_ids: frozenset[str]

    def __post_init__(self) -> None:
        validate_media_id(self.media_id)
        # Enforce strict grounding: every cited sentence and visual event must exist
        for rel in self.relations:
            for sid in rel.canonical_sentence_ids:
                if sid not in self.known_sentence_ids:
                    raise StoryGroundingError(
                        f"relation {rel.relation_id!r} cites ungrounded canonical "
                        f"sentence ID {sid!r}"
                    )
            for cid in rel.required_context_sentence_ids:
                if cid not in self.known_sentence_ids:
                    raise StoryGroundingError(
                        f"relation {rel.relation_id!r} cites ungrounded required "
                        f"context sentence ID {cid!r}"
                    )
            for vid in rel.visual_event_ids:
                if vid not in self.known_visual_event_ids:
                    raise StoryGroundingError(
                        f"relation {rel.relation_id!r} cites ungrounded visual event ID {vid!r}"
                    )

    def relations_for_interval(self, in_ms: int, out_ms: int) -> tuple[StoryRelation, ...]:
        """Return relations overlapping the given media interval."""
        return tuple(rel for rel in self.relations if rel.in_ms < out_ms and rel.out_ms > in_ms)

    def required_sentence_ids_for(self, relation_id: str) -> tuple[str, ...]:
        """Return all sentence IDs (core and required context) for a relation."""
        for rel in self.relations:
            if rel.relation_id == relation_id:
                ordered: list[str] = []
                for sid in rel.required_context_sentence_ids:
                    if sid not in ordered:
                        ordered.append(sid)
                for sid in rel.canonical_sentence_ids:
                    if sid not in ordered:
                        ordered.append(sid)
                return tuple(ordered)
        raise KeyError(f"relation {relation_id!r} not found in story map")

    def assert_candidate_preserves_required_context(
        self,
        candidate_in_ms: int,
        candidate_out_ms: int,
        sentence_spans: Mapping[str, tuple[int, int]],
    ) -> None:
        """Verify that an editorial candidate includes all required context for any active relation.

        If a payoff or answer is included, its setup/question context must not be severed.
        """
        for rel in self.relations:
            # Check if this relation's core landing beat overlaps the candidate
            core_overlap = rel.in_ms < candidate_out_ms and rel.out_ms > candidate_in_ms
            if not core_overlap:
                continue

            # Check all required context sentences
            for cid in rel.required_context_sentence_ids:
                span = sentence_spans.get(cid)
                if span is None:
                    raise StoryGroundingError(
                        f"required context sentence {cid!r} has no measured time span"
                    )
                c_start, c_end = span
                # Required context must be covered by the candidate interval
                if not (candidate_in_ms <= c_start and c_end <= candidate_out_ms):
                    raise StoryGroundingError(
                        f"candidate [{candidate_in_ms}..{candidate_out_ms}ms] severs "
                        f"required context sentence {cid!r} ([{c_start}..{c_end}ms]) "
                        f"for relation {rel.relation_id!r} ({rel.kind.value}: {rel.summary})"
                    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "media_id": self.media_id,
            "relations": [r.to_dict() for r in self.relations],
            "known_sentence_ids": sorted(self.known_sentence_ids),
            "known_visual_event_ids": sorted(self.known_visual_event_ids),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StoryMap:
        return cls(
            media_id=str(data["media_id"]),
            relations=tuple(StoryRelation.from_dict(r) for r in data.get("relations", ())),
            known_sentence_ids=frozenset(str(s) for s in data.get("known_sentence_ids", ())),
            known_visual_event_ids=frozenset(
                str(v) for v in data.get("known_visual_event_ids", ())
            ),
        )


def build_story_map(
    media_id: str,
    relations: Sequence[StoryRelation],
    known_sentence_ids: Sequence[str],
    known_visual_event_ids: Sequence[str],
) -> StoryMap:
    """Build and validate an episode-level StoryMap with grounded sentence and visual evidence."""
    return StoryMap(
        media_id=media_id,
        relations=tuple(relations),
        known_sentence_ids=frozenset(known_sentence_ids),
        known_visual_event_ids=frozenset(known_visual_event_ids),
    )
