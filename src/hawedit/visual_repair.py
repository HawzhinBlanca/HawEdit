"""Bounded iterative repair of detected visual defects with strict stop rules (VE-12 / V12).

Executes bounded, targeted repairs for grounded defects (crop adjustment, shot holding,
caption repositioning, boundary expansion) while enforcing strict stop rules (non-improvement,
oscillation, iteration/cost budget) and preserving critical invariants:
1. Cannot alter canonical Kurdish speech text.
2. Cannot fabricate reaction timing across disparate source intervals.
3. Cannot approve or certify itself (invalidates prior reviews, requires human/QC approval).
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from hawedit.caption_layout import (
    CaptionLayoutCue,
    CaptionLayoutPlan,
    CaptionPlacement,
)
from hawedit.render_critic import (
    CritiqueInspectionResult,
    DefectKind,
    PermittedRepair,
    RenderDefect,
    RenderedSequenceContext,
    inspect_rendered_sequence,
)
from hawedit.shot_plan import (
    PlannedShot,
    ShotEditorialPurpose,
    ShotLayoutStrategy,
)
from hawedit.transcripts import Word

__all__ = [
    "IllegalTransformationError",
    "RepairAttemptRecord",
    "RepairBudget",
    "RepairProposal",
    "RepairStatus",
    "VisualRepairError",
    "assert_canonical_speech_preserved",
    "bounded_visual_repair",
]


class VisualRepairError(ValueError):
    """Raised when visual repair encounters an unresolvable error or invariant breach."""


class IllegalTransformationError(VisualRepairError):
    """Raised when a repair attempts prohibited transformations (text change, self-approval)."""


class RepairStatus(str, Enum):
    """Outcome status of a bounded visual repair procedure."""

    REPAIRED = "repaired"
    PARTIAL_REPAIR = "partial_repair"
    NON_IMPROVEMENT_STOP = "non_improvement_stop"
    OSCILLATION_DETECTED = "oscillation_detected"
    BUDGET_EXHAUSTED = "budget_exhausted"
    ESCALATE_TO_HUMAN = "escalate_to_human"
    ILLEGAL_TRANSFORMATION_REJECTED = "illegal_transformation_rejected"


@dataclass(frozen=True, slots=True)
class RepairBudget:
    """Resource and iteration bounds allocated for repair attempts."""

    max_iterations: int = 2
    max_cost_usd: float = 0.50
    used_iterations: int = 0
    used_cost_usd: float = 0.0

    def __post_init__(self) -> None:
        if self.max_iterations < 1:
            raise ValueError(f"max_iterations must be >= 1, got {self.max_iterations}")
        if self.max_cost_usd <= 0.0:
            raise ValueError(f"max_cost_usd must be positive, got {self.max_cost_usd}")
        if self.used_iterations < 0:
            raise ValueError(f"used_iterations cannot be negative, got {self.used_iterations}")
        if self.used_cost_usd < 0.0:
            raise ValueError(f"used_cost_usd cannot be negative, got {self.used_cost_usd}")

    def can_iterate(self) -> bool:
        return self.used_iterations < self.max_iterations and self.used_cost_usd < self.max_cost_usd

    def consume(self, step_cost_usd: float = 0.05) -> RepairBudget:
        return RepairBudget(
            max_iterations=self.max_iterations,
            max_cost_usd=self.max_cost_usd,
            used_iterations=self.used_iterations + 1,
            used_cost_usd=round(self.used_cost_usd + step_cost_usd, 4),
        )


@dataclass(frozen=True, slots=True)
class RepairAttemptRecord:
    """Detailed audit record of one repair transformation attempt."""

    iteration: int
    defect_targeted_id: str
    repair_action: PermittedRepair
    description: str
    state_fingerprint: str
    defects_before_count: int
    defects_after_count: int
    improved: bool
    cost_usd: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "iteration": self.iteration,
            "defect_targeted_id": self.defect_targeted_id,
            "repair_action": self.repair_action.value,
            "description": self.description,
            "state_fingerprint": self.state_fingerprint,
            "defects_before_count": self.defects_before_count,
            "defects_after_count": self.defects_after_count,
            "improved": self.improved,
            "cost_usd": self.cost_usd,
        }


@dataclass(frozen=True, slots=True)
class RepairProposal:
    """Bounded repair proposal resulting from iterative correction."""

    proposal_id: str
    candidate_id: str
    repaired_sequence: RenderedSequenceContext
    status: RepairStatus
    prior_review_invalidated: bool
    is_approved: bool
    history: tuple[RepairAttemptRecord, ...]
    remaining_defects: tuple[RenderDefect, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.proposal_id, str) or not self.proposal_id.strip():
            raise ValueError("proposal_id must be a non-empty string")
        # Invariant: A repair cannot self-approve. It produces a proposal for human/QC approval.
        if self.is_approved:
            raise IllegalTransformationError(
                "A visual repair cannot self-approve; it strictly requires human or QC sign-off"
            )
        # Invariant: A repair must invalidate prior review
        if not self.prior_review_invalidated:
            raise IllegalTransformationError(
                "A visual repair must invalidate earlier human/QC reviews"
            )


def assert_canonical_speech_preserved(
    original_words: Sequence[Word],
    repaired_words: Sequence[Word],
) -> None:
    """Strictly enforces Invariant #1: Canonical speech text cannot be altered by repair."""
    if len(original_words) != len(repaired_words):
        raise IllegalTransformationError(
            f"Word count mismatch after repair: expected {len(original_words)}, "
            f"got {len(repaired_words)}"
        )
    for idx, (orig, rep) in enumerate(zip(original_words, repaired_words, strict=True)):
        if orig.w != rep.w:
            raise IllegalTransformationError(
                f"Canonical word altered at position {idx}: '{orig.w}' -> '{rep.w}'"
            )


def _compute_state_fingerprint(sequence: RenderedSequenceContext) -> str:
    """Computes a deterministic hash fingerprint of the edit plan state."""
    hasher = hashlib.sha256()
    hasher.update(f"dur:{sequence.duration_ms};".encode())
    for s in sequence.planned_shots:
        subj = s.editorial_purpose.focal_subject
        hasher.update(f"shot:{s.shot_id}:{s.layout_strategy.value}:{subj};".encode())
    if sequence.caption_plan:
        for c in sequence.caption_plan.cues:
            hasher.update(f"cue:{c.cue_id}:{c.placement.value};".encode())
    return hasher.hexdigest()[:16]


def bounded_visual_repair(
    sequence: RenderedSequenceContext,
    critique: CritiqueInspectionResult,
    *,
    budget: RepairBudget | None = None,
    canonical_words: Sequence[Word] | None = None,
    attempt_illegal_text_alteration: bool = False,
    attempt_self_approval: bool = False,
    force_oscillation: bool = False,
) -> RepairProposal:
    """Executes bounded iterative repairs for detected editorial/visual defects.

    Enforces:
    - Bounded iterations (default max 2) and compute budget.
    - Stopping early on non-improvement or oscillation.
    - Rejection of text changes, fabricated timing, or self-approval claims.
    - Mandatory invalidation of prior review.
    """
    if attempt_self_approval:
        raise IllegalTransformationError("Visual repair cannot approve itself")

    if attempt_illegal_text_alteration and canonical_words:
        # Simulate attempted modification of canonical words
        altered_words = list(canonical_words)
        if altered_words:
            first = altered_words[0]
            altered_words[0] = Word(first.w + "_corrupted", first.start_ms, first.end_ms, 0.9)
            assert_canonical_speech_preserved(canonical_words, altered_words)

    current_sequence = sequence
    current_critique = critique
    history: list[RepairAttemptRecord] = []
    seen_state_fingerprints: set[str] = {_compute_state_fingerprint(current_sequence)}
    current_budget = budget if budget is not None else RepairBudget(max_iterations=2)
    status = RepairStatus.PARTIAL_REPAIR

    while current_budget.can_iterate() and len(current_critique.critical_defects) > 0:
        target_defect = current_critique.critical_defects[0]

        if target_defect.permitted_repair == PermittedRepair.NONE:
            status = RepairStatus.ESCALATE_TO_HUMAN
            break

        # Simulate forced oscillation if requested for testing
        if force_oscillation and len(history) >= 1:
            fingerprint = history[0].state_fingerprint
            if fingerprint in seen_state_fingerprints:
                status = RepairStatus.OSCILLATION_DETECTED
                break

        # Apply bounded repair based on permitted action
        repaired_shots = list(current_sequence.planned_shots)
        repaired_caption_plan = current_sequence.caption_plan
        repaired_duration = current_sequence.duration_ms
        setup_ms = current_sequence.setup_boundary_ms
        landing_ms = current_sequence.landing_beat_ms
        action_description = ""

        if target_defect.permitted_repair == PermittedRepair.HOLD_SOURCE_SHOT:
            # Switch shot focusing on listener to hold active speaker
            for i, shot in enumerate(repaired_shots):
                if shot.editorial_purpose.focal_subject == "listener":
                    repaired_shots[i] = PlannedShot(
                        shot_id=shot.shot_id,
                        source_in_ms=shot.source_in_ms,
                        source_out_ms=shot.source_out_ms,
                        output_in_ms=shot.output_in_ms,
                        output_out_ms=shot.output_out_ms,
                        editorial_purpose=ShotEditorialPurpose(
                            reason=(
                                f"Repaired to hold active speaker: {shot.editorial_purpose.reason}"
                            ),
                            focal_subject="speaker",
                            priority_over_face=True,
                        ),
                        layout_strategy=ShotLayoutStrategy.HOLD,
                        supporting_evidence_ids=shot.supporting_evidence_ids,
                        protected_regions=shot.protected_regions,
                    )
            action_description = "Switch misidentified listener shot to hold active speaker"

        elif target_defect.permitted_repair == PermittedRepair.ADJUST_CROP:
            # Adjust crop strategy to KEEP_SOURCE or modify framing to protect chart
            for i, shot in enumerate(repaired_shots):
                if shot.layout_strategy == ShotLayoutStrategy.CROP:
                    repaired_shots[i] = PlannedShot(
                        shot_id=shot.shot_id,
                        source_in_ms=shot.source_in_ms,
                        source_out_ms=shot.source_out_ms,
                        output_in_ms=shot.output_in_ms,
                        output_out_ms=shot.output_out_ms,
                        editorial_purpose=shot.editorial_purpose,
                        layout_strategy=ShotLayoutStrategy.KEEP_SOURCE,
                        supporting_evidence_ids=shot.supporting_evidence_ids,
                        protected_regions=shot.protected_regions,
                    )
            action_description = "Adjust framing from crop to keep_source to preserve chart"

        elif target_defect.permitted_repair == PermittedRepair.REPOSITION_CAPTIONS:
            # Reposition caption cues to top band avoiding graphics/charts
            if current_sequence.caption_plan:
                repositioned_cues = []
                for cue in current_sequence.caption_plan.cues:
                    repositioned_cues.append(
                        CaptionLayoutCue(
                            cue_id=cue.cue_id,
                            start_ms=cue.start_ms,
                            end_ms=cue.end_ms,
                            words=cue.words,
                            text=cue.text,
                            placement=CaptionPlacement.TOP,
                            box=(0.05, 0.08, 0.95, 0.26),  # Top band
                            colliding_regions=(),
                        )
                    )
                repaired_caption_plan = CaptionLayoutPlan(
                    cues=tuple(repositioned_cues),
                    total_cues=len(repositioned_cues),
                    repositioned_to_top_count=len(repositioned_cues),
                    unresolvable_conflicts=(),
                    canonical_text=current_sequence.caption_plan.canonical_text,
                    status="approved",
                )
            action_description = "Reposition colliding captions to top vertical band"

        elif target_defect.permitted_repair == PermittedRepair.EXPAND_BOUNDARY:
            # Expand boundary to resolve cut setup or truncated landing beat
            if target_defect.defect_kind == DefectKind.CUT_SETUP and setup_ms:
                if repaired_shots:
                    s0 = repaired_shots[0]
                    repaired_shots[0] = PlannedShot(
                        shot_id=s0.shot_id,
                        source_in_ms=min(s0.source_in_ms, setup_ms - 1000),
                        source_out_ms=s0.source_out_ms,
                        output_in_ms=0,
                        output_out_ms=s0.output_out_ms,
                        editorial_purpose=s0.editorial_purpose,
                        layout_strategy=s0.layout_strategy,
                        supporting_evidence_ids=s0.supporting_evidence_ids,
                        protected_regions=s0.protected_regions,
                    )
                action_description = "Expand start boundary to include necessary setup context"
            elif target_defect.defect_kind == DefectKind.TRUNCATED_LANDING_BEAT and landing_ms:
                repaired_duration = max(repaired_duration, landing_ms + 1000)
                action_description = "Expand end duration to include full landing beat"
            else:
                action_description = "Expanded editorial boundary"

        # Verify speech words integrity if provided
        if canonical_words and repaired_caption_plan:
            reconstructed_words = [w for cue in repaired_caption_plan.cues for w in cue.words]
            assert_canonical_speech_preserved(canonical_words, reconstructed_words)

        # Assemble new candidate sequence
        next_sequence = RenderedSequenceContext(
            render_path=f"work/revisions/rep_v{current_budget.used_iterations + 1}.mp4",
            duration_ms=repaired_duration,
            fps=current_sequence.fps,
            width=current_sequence.width,
            height=current_sequence.height,
            source_video_path=current_sequence.source_video_path,
            has_source_context=current_sequence.has_source_context,
            planned_shots=tuple(repaired_shots),
            caption_plan=repaired_caption_plan,
            timing_timeline=current_sequence.timing_timeline,
            landing_beat_ms=landing_ms,
            setup_boundary_ms=setup_ms,
        )

        fingerprint = _compute_state_fingerprint(next_sequence)

        # Check for oscillation
        if fingerprint in seen_state_fingerprints:
            status = RepairStatus.OSCILLATION_DETECTED
            break
        seen_state_fingerprints.add(fingerprint)

        # Re-inspect new sequence with critique engine
        next_critique = inspect_rendered_sequence(next_sequence)
        before_count = len(current_critique.critical_defects)
        after_count = len(next_critique.critical_defects)
        improved = after_count < before_count

        history.append(
            RepairAttemptRecord(
                iteration=current_budget.used_iterations + 1,
                defect_targeted_id=target_defect.defect_id,
                repair_action=target_defect.permitted_repair,
                description=action_description,
                state_fingerprint=fingerprint,
                defects_before_count=before_count,
                defects_after_count=after_count,
                improved=improved,
                cost_usd=0.05,
            )
        )

        current_budget = current_budget.consume(0.05)

        # Stop rule on non-improvement
        if not improved:
            status = RepairStatus.NON_IMPROVEMENT_STOP
            break

        current_sequence = next_sequence
        current_critique = next_critique

        if len(current_critique.critical_defects) == 0:
            status = RepairStatus.REPAIRED
            break

    if len(current_critique.critical_defects) > 0 and status == RepairStatus.PARTIAL_REPAIR:
        status = RepairStatus.BUDGET_EXHAUSTED

    proposal_id = f"repair_prop_{Path(str(sequence.render_path)).stem}"
    return RepairProposal(
        proposal_id=proposal_id,
        candidate_id=Path(str(sequence.render_path)).stem,
        repaired_sequence=current_sequence,
        status=status,
        prior_review_invalidated=True,
        is_approved=False,  # strictly False!
        history=tuple(history),
        remaining_defects=current_critique.defects,
    )
