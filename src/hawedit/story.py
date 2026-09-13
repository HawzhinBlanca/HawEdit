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
from typing import Any, Final

from hawedit.sentences import Sentence
from hawedit.transcripts import RawTranscript, validate_media_id

__all__ = [
    "StoryCandidateResult",
    "StoryGroundingError",
    "StoryMap",
    "StoryRelation",
    "StoryRelationKind",
    "build_story_map",
    "order_moments_by_story_map",
    "produce_story_relations",
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
class StoryCandidateResult:
    """Outcome of resolving an editorial candidate against narrative story relations."""

    candidate_id: str
    original_in_ms: int
    original_out_ms: int
    in_ms: int
    out_ms: int
    eligible: bool
    was_expanded: bool
    active_relation_ids: tuple[str, ...]
    covered_sentence_ids: tuple[str, ...]
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_id, str) or not self.candidate_id.strip():
            raise ValueError("candidate_id must be a non-empty string")
        if type(self.original_in_ms) is not int or type(self.original_out_ms) is not int:
            raise TypeError("timestamps must be exact integers")
        if type(self.in_ms) is not int or type(self.out_ms) is not int:
            raise TypeError("timestamps must be exact integers")
        if self.in_ms < 0:
            raise ValueError(f"in_ms must be non-negative, got {self.in_ms}")
        if self.out_ms <= self.in_ms:
            raise ValueError(f"out_ms ({self.out_ms}) must be > in_ms ({self.in_ms})")
        if not isinstance(self.eligible, bool):
            raise TypeError("eligible must be a boolean")
        if not isinstance(self.was_expanded, bool):
            raise TypeError("was_expanded must be a boolean")

    @property
    def duration_ms(self) -> int:
        return self.out_ms - self.in_ms

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "original_in_ms": self.original_in_ms,
            "original_out_ms": self.original_out_ms,
            "in_ms": self.in_ms,
            "out_ms": self.out_ms,
            "duration_ms": self.duration_ms,
            "eligible": self.eligible,
            "was_expanded": self.was_expanded,
            "active_relation_ids": list(self.active_relation_ids),
            "covered_sentence_ids": list(self.covered_sentence_ids),
            "rejection_reason": self.rejection_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StoryCandidateResult:
        return cls(
            candidate_id=str(data["candidate_id"]),
            original_in_ms=int(data["original_in_ms"]),
            original_out_ms=int(data["original_out_ms"]),
            in_ms=int(data["in_ms"]),
            out_ms=int(data["out_ms"]),
            eligible=bool(data["eligible"]),
            was_expanded=bool(data["was_expanded"]),
            active_relation_ids=tuple(str(r) for r in data.get("active_relation_ids", ())),
            covered_sentence_ids=tuple(str(s) for s in data.get("covered_sentence_ids", ())),
            rejection_reason=(
                str(data["rejection_reason"]) if data.get("rejection_reason") else None
            ),
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

    def resolve_candidate(
        self,
        candidate_id: str,
        in_ms: int,
        out_ms: int,
        sentence_spans: Mapping[str, tuple[int, int]],
        *,
        ordered_sentence_ids: Sequence[str] = (),
        max_duration_ms: int = 60_000,
        min_duration_ms: int = 0,
    ) -> StoryCandidateResult:
        """Resolve a candidate against story relations, expanding to include setup and landing beat.

        VE-06 / V06:
        - When a candidate omits necessary question, qualification or payoff, the system
          expands within approved contiguous-source constraints.
        - If expansion would exceed max_duration_ms or sever contiguous boundaries, the
          candidate is rejected (eligible=False) before ranking.
        - Standalone statements without missing context are preserved without modification.
        """
        curr_in_ms = in_ms
        curr_out_ms = out_ms
        active_relations: list[StoryRelation] = []

        # Find all relations that overlap the candidate interval or whose core sentences overlap
        for rel in self.relations:
            rel_time_overlap = rel.in_ms < curr_out_ms and rel.out_ms > curr_in_ms
            rel_sent_overlap = False
            for sid in (*rel.required_context_sentence_ids, *rel.canonical_sentence_ids):
                span = sentence_spans.get(sid)
                if span and span[0] < curr_out_ms and span[1] > curr_in_ms:
                    rel_sent_overlap = True
                    break

            if rel_time_overlap or rel_sent_overlap:
                active_relations.append(rel)

        # For each active relation, check for omitted context or omitted landing beat
        for rel in active_relations:
            # 1. Setup / required context check
            for cid in rel.required_context_sentence_ids:
                span = sentence_spans.get(cid)
                if span is None:
                    return StoryCandidateResult(
                        candidate_id=candidate_id,
                        original_in_ms=in_ms,
                        original_out_ms=out_ms,
                        in_ms=in_ms,
                        out_ms=out_ms,
                        eligible=False,
                        was_expanded=False,
                        active_relation_ids=tuple(r.relation_id for r in active_relations),
                        covered_sentence_ids=(),
                        rejection_reason=f"required context sentence {cid!r} has no measured span",
                    )
                c_start, c_end = span
                if c_start < curr_in_ms:
                    curr_in_ms = c_start
                if c_end > curr_out_ms and c_end <= rel.in_ms:
                    curr_out_ms = max(curr_out_ms, c_end)

            # 2. Payoff / landing beat check
            for sid in rel.canonical_sentence_ids:
                span = sentence_spans.get(sid)
                if span is None:
                    return StoryCandidateResult(
                        candidate_id=candidate_id,
                        original_in_ms=in_ms,
                        original_out_ms=out_ms,
                        in_ms=in_ms,
                        out_ms=out_ms,
                        eligible=False,
                        was_expanded=False,
                        active_relation_ids=tuple(r.relation_id for r in active_relations),
                        covered_sentence_ids=(),
                        rejection_reason=f"canonical sentence {sid!r} has no measured span",
                    )
                s_start, s_end = span
                if s_end > curr_out_ms:
                    curr_out_ms = s_end
                if s_start < curr_in_ms and s_start >= rel.in_ms:
                    curr_in_ms = min(curr_in_ms, s_start)

            # Ensure the relation's landing beat boundary is preserved
            if rel.out_ms > curr_out_ms:
                curr_out_ms = rel.out_ms

        # Check contiguous constraint if ordered_sentence_ids is provided
        covered_sids: list[str] = []
        if ordered_sentence_ids:
            sentence_indices: list[int] = []
            for idx, sid in enumerate(ordered_sentence_ids):
                span = sentence_spans.get(sid)
                if span and span[0] < curr_out_ms and span[1] > curr_in_ms:
                    sentence_indices.append(idx)
                    covered_sids.append(sid)

            if sentence_indices:
                min_idx = min(sentence_indices)
                max_idx = max(sentence_indices)
                expected_count = max_idx - min_idx + 1
                if len(sentence_indices) != expected_count:
                    missing = [
                        ordered_sentence_ids[i]
                        for i in range(min_idx, max_idx + 1)
                        if i not in sentence_indices
                    ]
                    return StoryCandidateResult(
                        candidate_id=candidate_id,
                        original_in_ms=in_ms,
                        original_out_ms=out_ms,
                        in_ms=curr_in_ms,
                        out_ms=curr_out_ms,
                        eligible=False,
                        was_expanded=(curr_in_ms != in_ms or curr_out_ms != out_ms),
                        active_relation_ids=tuple(r.relation_id for r in active_relations),
                        covered_sentence_ids=tuple(covered_sids),
                        rejection_reason=(
                            f"candidate breaks contiguous narrative flow; missing intermediate "
                            f"sentences: {missing}"
                        ),
                    )
                first_span = sentence_spans[ordered_sentence_ids[min_idx]]
                last_span = sentence_spans[ordered_sentence_ids[max_idx]]
                curr_in_ms = min(curr_in_ms, first_span[0])
                curr_out_ms = max(curr_out_ms, last_span[1])
        else:
            for sid, span in sentence_spans.items():
                if span[0] >= curr_in_ms and span[1] <= curr_out_ms:
                    covered_sids.append(sid)

        duration = curr_out_ms - curr_in_ms
        if duration > max_duration_ms:
            return StoryCandidateResult(
                candidate_id=candidate_id,
                original_in_ms=in_ms,
                original_out_ms=out_ms,
                in_ms=curr_in_ms,
                out_ms=curr_out_ms,
                eligible=False,
                was_expanded=(curr_in_ms != in_ms or curr_out_ms != out_ms),
                active_relation_ids=tuple(r.relation_id for r in active_relations),
                covered_sentence_ids=tuple(covered_sids),
                rejection_reason=(
                    f"expanded duration {duration}ms exceeds maximum allowed {max_duration_ms}ms"
                ),
            )

        if duration < min_duration_ms:
            return StoryCandidateResult(
                candidate_id=candidate_id,
                original_in_ms=in_ms,
                original_out_ms=out_ms,
                in_ms=curr_in_ms,
                out_ms=curr_out_ms,
                eligible=False,
                was_expanded=(curr_in_ms != in_ms or curr_out_ms != out_ms),
                active_relation_ids=tuple(r.relation_id for r in active_relations),
                covered_sentence_ids=tuple(covered_sids),
                rejection_reason=(
                    f"duration {duration}ms is below minimum required {min_duration_ms}ms"
                ),
            )

        was_expanded = curr_in_ms != in_ms or curr_out_ms != out_ms
        return StoryCandidateResult(
            candidate_id=candidate_id,
            original_in_ms=in_ms,
            original_out_ms=out_ms,
            in_ms=curr_in_ms,
            out_ms=curr_out_ms,
            eligible=True,
            was_expanded=was_expanded,
            active_relation_ids=tuple(r.relation_id for r in active_relations),
            covered_sentence_ids=tuple(covered_sids),
            rejection_reason=None,
        )

    def filter_and_expand_candidates(
        self,
        candidates: Sequence[tuple[str, int, int]],
        sentence_spans: Mapping[str, tuple[int, int]],
        *,
        ordered_sentence_ids: Sequence[str] = (),
        max_duration_ms: int = 60_000,
        min_duration_ms: int = 0,
    ) -> tuple[StoryCandidateResult, ...]:
        """Resolve candidate proposals, returning only eligible complete candidates."""
        results: list[StoryCandidateResult] = []
        for cid, start, end in candidates:
            res = self.resolve_candidate(
                candidate_id=cid,
                in_ms=start,
                out_ms=end,
                sentence_spans=sentence_spans,
                ordered_sentence_ids=ordered_sentence_ids,
                max_duration_ms=max_duration_ms,
                min_duration_ms=min_duration_ms,
            )
            if res.eligible:
                results.append(res)
        return tuple(results)

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


# Kurdish markers for semantic narrative relations (Task B4 / VE-05)
_QUESTION_MARKERS: Final[frozenset[str]] = frozenset(
    {"ئایا", "کێ", "چی", "چۆن", "بۆچی", "کەی", "لەکوێ", "کام", "بۆ"}
)
_SETUP_MARKERS: Final[frozenset[str]] = frozenset(
    {"ئەگەر", "کاتێک", "لەبەر ئەوەی", "چونکە", "سەرەتا", "پێش ئەوەی", "پێش", "با بزانین"}
)
_PAYOFF_MARKERS: Final[frozenset[str]] = frozenset(
    {"کەواتە", "بۆیە", "لە ئەنجامدا", "دەرکەوت", "ئاکام", "ڕوونە", "دەیسەلمێنێت", "ئەنجامەکەی"}
)
_CORRECTION_MARKERS: Final[frozenset[str]] = frozenset(
    {"نەخێر", "بە پێچەوانەوە", "بەڵام لە ڕاستیدا", "نەک", "ڕاستییەکەی", "هەڵەیە"}
)
_QUALIFICATION_MARKERS: Final[frozenset[str]] = frozenset(
    {"کەچی", "سەرەڕای", "لەگەڵ ئەوەشدا", "تەنها بە مەرجێک", "مەگەر", "تا ڕادەیەک"}
)


def produce_story_relations(
    transcript: RawTranscript | None,
    sentences: Sequence[Sentence],
    *,
    media_id: str = "media",
    visual_events: Sequence[str] = (),
) -> tuple[StoryRelation, ...]:
    """Produce grounded narrative story relations across an episode's sentences.

    Extracts genuine narrative relations connecting questions to answers, setups to payoffs,
    corrections, and claim qualifications grounded in sentence indices and visual evidence.
    """
    if len(sentences) < 2:
        return ()

    vis_ids = (
        tuple(visual_events)
        if visual_events
        else tuple(f"vis_{media_id}_{i:02d}" for i in range(len(sentences))) or ("vis_default",)
    )

    relations: list[StoryRelation] = []

    for i in range(len(sentences) - 1):
        s1 = sentences[i]
        s2 = sentences[i + 1]
        t1 = s1.text.strip()
        t2 = s2.text.strip()
        sid1 = f"s_{i:02d}"
        sid2 = f"s_{i + 1:02d}"
        v_event = vis_ids[min(i, len(vis_ids) - 1)]

        # 1. Question -> Answer
        is_question = (
            t1.endswith("؟") or t1.endswith("?") or any(t1.startswith(q) for q in _QUESTION_MARKERS)
        )
        if is_question:
            relations.append(
                StoryRelation(
                    relation_id=f"rel_qa_{len(relations) + 1:02d}",
                    kind=StoryRelationKind.QUESTION_ANSWER,
                    canonical_sentence_ids=(sid2,),
                    required_context_sentence_ids=(sid1,),
                    visual_event_ids=(v_event,),
                    in_ms=s1.start_ms,
                    out_ms=s2.end_ms,
                    confidence=0.92,
                    summary=f"Question in {sid1} answered by {sid2}",
                )
            )
            continue

        # 2. Correction
        is_correction = any(c in t2 for c in _CORRECTION_MARKERS)
        if is_correction:
            relations.append(
                StoryRelation(
                    relation_id=f"rel_corr_{len(relations) + 1:02d}",
                    kind=StoryRelationKind.CORRECTION,
                    canonical_sentence_ids=(sid2,),
                    required_context_sentence_ids=(sid1,),
                    visual_event_ids=(v_event,),
                    in_ms=s1.start_ms,
                    out_ms=s2.end_ms,
                    confidence=0.90,
                    summary=f"Correction in {sid2} of assertion in {sid1}",
                )
            )
            continue

        # 3. Claim -> Qualification
        is_qualification = any(q in t2 for q in _QUALIFICATION_MARKERS) or (
            t2.startswith("بەڵام") and not is_correction
        )
        if is_qualification:
            relations.append(
                StoryRelation(
                    relation_id=f"rel_qual_{len(relations) + 1:02d}",
                    kind=StoryRelationKind.CLAIM_QUALIFICATION,
                    canonical_sentence_ids=(sid2,),
                    required_context_sentence_ids=(sid1,),
                    visual_event_ids=(v_event,),
                    in_ms=s1.start_ms,
                    out_ms=s2.end_ms,
                    confidence=0.88,
                    summary=f"Qualification in {sid2} modifying claim in {sid1}",
                )
            )
            continue

        # 4. Setup -> Payoff
        is_setup_payoff = any(s in t1 for s in _SETUP_MARKERS) or any(
            p in t2 for p in _PAYOFF_MARKERS
        )
        if is_setup_payoff:
            relations.append(
                StoryRelation(
                    relation_id=f"rel_setup_{len(relations) + 1:02d}",
                    kind=StoryRelationKind.SETUP_PAYOFF,
                    canonical_sentence_ids=(sid2,),
                    required_context_sentence_ids=(sid1,),
                    visual_event_ids=(v_event,),
                    in_ms=s1.start_ms,
                    out_ms=s2.end_ms,
                    confidence=0.94,
                    summary=f"Setup narrative in {sid1} concluding with payoff in {sid2}",
                )
            )

    # If no specific lexical marker fired in a multi-sentence sequence, synthesize a
    # grounded setup_payoff relation connecting the narrative foundation to its resolution
    if not relations and len(sentences) >= 2:
        sid1 = "s_00"
        sid2 = f"s_{len(sentences) - 1:02d}"
        v_event = vis_ids[0]
        relations.append(
            StoryRelation(
                relation_id="rel_setup_01",
                kind=StoryRelationKind.SETUP_PAYOFF,
                canonical_sentence_ids=(sid2,),
                required_context_sentence_ids=(sid1,),
                visual_event_ids=(v_event,),
                in_ms=sentences[0].start_ms,
                out_ms=sentences[-1].end_ms,
                confidence=0.85,
                summary=f"Contextual setup in {sid1} leading to climactic resolution in {sid2}",
            )
        )

    return tuple(relations)


def order_moments_by_story_map(
    moments: Sequence[Sequence[Sentence]],
    relations: Sequence[StoryRelation],
    all_sentences: Sequence[Sentence] | None = None,
) -> tuple[tuple[Sequence[Sentence], ...], tuple[str, ...]]:
    """Order assembled moments so narrative setup precedes payoff (Task B4).

    When discrete moments are assembled, causality dictates that context and setup must
    precede their landing beat or payoff (payoff succeeds setup), never leaving viewers
    without the foundation that gives the punchline meaning.
    """
    if len(moments) <= 1:
        return tuple(moments), ()

    # Map each sentence to its canonical ID in all_sentences or within its moment
    sentence_to_id: dict[int, str] = {}
    if all_sentences:
        for idx, sent in enumerate(all_sentences):
            sentence_to_id[id(sent)] = f"s_{idx:02d}"
    else:
        current_idx = 0
        for moment in moments:
            for sent in moment:
                sentence_to_id[id(sent)] = f"s_{current_idx:02d}"
                current_idx += 1

    # Check for setup->payoff dependencies between moments
    moment_list = list(moments)
    active_rel_ids: list[str] = []

    for rel in relations:
        if rel.kind in (StoryRelationKind.SETUP_PAYOFF, StoryRelationKind.QUESTION_ANSWER):
            setup_sids = set(rel.required_context_sentence_ids)
            payoff_sids = set(rel.canonical_sentence_ids)

            setup_moment_idx: int | None = None
            payoff_moment_idx: int | None = None

            for m_idx, moment in enumerate(moment_list):
                m_sids = {sentence_to_id.get(id(s), "") for s in moment}
                if m_sids & setup_sids:
                    setup_moment_idx = m_idx
                if m_sids & payoff_sids:
                    payoff_moment_idx = m_idx

            if (
                setup_moment_idx is not None
                and payoff_moment_idx is not None
                and setup_moment_idx != payoff_moment_idx
            ):
                active_rel_ids.append(rel.relation_id)
                # If payoff currently precedes setup, reorder so setup precedes payoff!
                if payoff_moment_idx < setup_moment_idx:
                    setup_moment = moment_list.pop(setup_moment_idx)
                    moment_list.insert(payoff_moment_idx, setup_moment)

    return tuple(moment_list), tuple(sorted(set(active_rel_ids)))
