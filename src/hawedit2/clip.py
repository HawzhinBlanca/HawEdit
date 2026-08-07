"""§5's data contract — the clip record every stage emits and consumes.

§1: "Every stage emits and consumes JSON. Stages are independently testable, replaceable,
re-runnable." A contract that is only a shape in a document gets violated the first time two
stages disagree about a field, and nothing notices until a client sees the output. So this is
a validated structure with the §5 rules enforced at construction:

* **The span must agree with its own boundary.** `in_ms`/`out_ms` are the boundary's final
  points. A record whose top-level span contradicts its boundary block is a lie the renderer
  would act on.
* **Rejection is first-class.** §5: "Every rejected candidate keeps a `reject_reason` and its
  `discovery_path`. That set is your only measure of recall." So it is a type with both
  fields required, not an absent clip.
* **SV6D labels must cite a timestamp.** §3 Stage 3: "Every label must cite a timestamp.
  Reject output where a claim has no timeline evidence."
* **The judge must be routable.** §4 pins `gemini-2.5-pro` and marks `gemini-3.1-pro`
  "evaluated, not routed". A clip recording the shadow as its judge would mean a model the
  blueprint keeps out of the path scored a client's output.

`assert_renderable()` is the gate §2's diagram puts before every output: Kurdish invariant #2,
plus the human QC gate that diagram marks "(always)".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Final

from hawedit2.boundary import Boundary, assert_boundary_invariant
from hawedit2.registry import resolve
from hawedit2.transcripts import AsrProvenance, Word

__all__ = [
    "Clip",
    "ClipTranscript",
    "DiscoveryPath",
    "Editorial",
    "Output",
    "Qc",
    "RejectedCandidate",
    "Sv6d",
]

# A timestamp citation in an SV6D label. Accepts `84.6s`, `84600ms`, `1:24` and `00:01:52`,
# which is the range of forms a judge plausibly emits; the requirement §3 Stage 3 makes is
# that *some* timeline evidence is present, not that it is in one house format.
_TIMESTAMP = re.compile(r"\d+(?:\.\d+)?\s*(?:ms|s)\b|\d{1,2}:\d{2}(?::\d{2})?")

_SCORE_FIELDS: Final = (
    "hook_score",
    "meaning_fidelity",
    "misleading_edit_risk",
    "cultural_landing",
)


class DiscoveryPath(Enum):
    """§5: which path found this candidate. §3 Stage 3 unions the two, never intersects."""

    VERBAL = "verbal"
    VISUAL = "visual"
    BOTH = "both"


@dataclass(frozen=True, slots=True)
class Sv6d:
    """§3 Stage 3's six-dimension schema. Every label must cite a timestamp."""

    subject: str
    aesthetics: str
    camera: str
    editing: str
    narrative: str
    retention: str

    def __post_init__(self) -> None:
        for dimension in ("subject", "aesthetics", "camera", "editing", "narrative", "retention"):
            label: str = getattr(self, dimension)
            if not _TIMESTAMP.search(label):
                raise ValueError(
                    f"SV6D {dimension} label {label!r} cites no timestamp. §3 Stage 3: "
                    f"'Every label must cite a timestamp. Reject output where a claim has no "
                    f"timeline evidence.'"
                )

    def to_dict(self) -> dict[str, str]:
        return {
            "subject": self.subject,
            "aesthetics": self.aesthetics,
            "camera": self.camera,
            "editing": self.editing,
            "narrative": self.narrative,
            "retention": self.retention,
        }


@dataclass(frozen=True, slots=True)
class Editorial:
    """§4's judge output for one candidate."""

    hook_score: float
    self_contained: bool
    meaning_fidelity: float
    misleading_edit_risk: float
    cultural_landing: float
    narrative_role: str
    judge: str
    sv6d: Sv6d | None = None

    def __post_init__(self) -> None:
        for name in _SCORE_FIELDS:
            value: float = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be within [0, 1], got {value}")
        entry = resolve(self.judge)
        if not entry.routable:
            raise ValueError(
                f"{self.judge!r} is not routable. §4 marks it 'evaluated, not routed' — a "
                f"clip recording it as its judge would mean a model the blueprint keeps out "
                f"of the path scored client output."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "hook_score": self.hook_score,
            "self_contained": self.self_contained,
            "meaning_fidelity": self.meaning_fidelity,
            "misleading_edit_risk": self.misleading_edit_risk,
            "cultural_landing": self.cultural_landing,
            "narrative_role": self.narrative_role,
            "judge": self.judge,
            "sv6d": self.sv6d.to_dict() if self.sv6d else None,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Editorial:
        raw_sv6d = data.get("sv6d")
        return Editorial(
            hook_score=data["hook_score"],
            self_contained=data["self_contained"],
            meaning_fidelity=data["meaning_fidelity"],
            misleading_edit_risk=data["misleading_edit_risk"],
            cultural_landing=data["cultural_landing"],
            narrative_role=data["narrative_role"],
            judge=data["judge"],
            sv6d=Sv6d(**raw_sv6d) if raw_sv6d else None,
        )


@dataclass(frozen=True, slots=True)
class ClipTranscript:
    """§5's `transcript` block. `raw_ckb` is canonical and ships to the client (invariant #1)."""

    raw_ckb: str
    norm_ckb: str
    en_aux: str | None
    words: tuple[Word, ...]
    asr: AsrProvenance

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_ckb": self.raw_ckb,
            "norm_ckb": self.norm_ckb,
            "en_aux": self.en_aux,
            "words": [
                {"w": w.w, "start_ms": w.start_ms, "end_ms": w.end_ms, "conf": w.conf}
                for w in self.words
            ],
            "asr": {
                "canonical": self.asr.canonical,
                "aligner": self.asr.aligner,
                "validated_by": self.asr.validated_by,
                "mean_logprob": self.asr.mean_logprob,
            },
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> ClipTranscript:
        return ClipTranscript(
            raw_ckb=data["raw_ckb"],
            norm_ckb=data["norm_ckb"],
            en_aux=data.get("en_aux"),
            words=tuple(Word(**w) for w in data.get("words", ())),
            asr=AsrProvenance(**data["asr"]),
        )


@dataclass(frozen=True, slots=True)
class Output:
    """§5's `output` block — the deliverable settings."""

    title_ckb: str
    description_ckb: str
    crop_target: str
    caption_style: str
    durations: tuple[int, ...]

    def __post_init__(self) -> None:
        if any(duration <= 0 for duration in self.durations):
            raise ValueError("output durations must be positive seconds")

    def to_dict(self) -> dict[str, Any]:
        return {
            "title_ckb": self.title_ckb,
            "description_ckb": self.description_ckb,
            "crop_target": self.crop_target,
            "caption_style": self.caption_style,
            "durations": list(self.durations),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Output:
        return Output(
            title_ckb=data["title_ckb"],
            description_ckb=data["description_ckb"],
            crop_target=data["crop_target"],
            caption_style=data["caption_style"],
            durations=tuple(data["durations"]),
        )


@dataclass(frozen=True, slots=True)
class Qc:
    """§5's `qc` block. §2's diagram puts a human QC gate before output, always."""

    auto_pass: bool
    flags: tuple[str, ...] = ()
    human_reviewed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "auto_pass": self.auto_pass,
            "flags": list(self.flags),
            "human_reviewed": self.human_reviewed,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Qc:
        return Qc(
            auto_pass=data["auto_pass"],
            flags=tuple(data.get("flags", ())),
            human_reviewed=data.get("human_reviewed", False),
        )


@dataclass(frozen=True, slots=True)
class RejectedCandidate:
    """§5: "Rejection is a first-class outcome."

    "Every rejected candidate keeps a `reject_reason` and its `discovery_path`. That set is
    your only measure of recall." Per-path recall is also what §8.2 uses to decide whether
    the dual-path cost is justified, so a rejection with no path recorded destroys the
    measurement the whole discovery design rests on.
    """

    media_id: str
    in_ms: int
    out_ms: int
    discovery_path: DiscoveryPath
    reject_reason: str

    def __post_init__(self) -> None:
        if not self.reject_reason.strip():
            raise ValueError(
                "reject_reason must not be empty: the rejection set is the only measure of "
                "recall there is, and a blank reason measures nothing."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "media_id": self.media_id,
            "in_ms": self.in_ms,
            "out_ms": self.out_ms,
            "discovery_path": self.discovery_path.value,
            "reject_reason": self.reject_reason,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> RejectedCandidate:
        return RejectedCandidate(
            media_id=data["media_id"],
            in_ms=data["in_ms"],
            out_ms=data["out_ms"],
            discovery_path=DiscoveryPath(data["discovery_path"]),
            reject_reason=data["reject_reason"],
        )


@dataclass(frozen=True, slots=True)
class Clip:
    """§5's clip record.

    `editorial` and `output` are optional because Stage 5 produces boundaries before Stage 4
    has scored anything — a clip mid-pipeline is a real state, not an incomplete record.
    """

    clip_id: str
    media_id: str
    in_ms: int
    out_ms: int
    discovery_path: DiscoveryPath
    boundary: Boundary
    transcript: ClipTranscript
    speaker: str | None = None
    editorial: Editorial | None = None
    output: Output | None = None
    qc: Qc | None = None

    def __post_init__(self) -> None:
        if self.in_ms != self.boundary.final_in_ms:
            raise ValueError(
                f"in_ms ({self.in_ms}) does not match the boundary's final_in_ms "
                f"({self.boundary.final_in_ms}). A span that contradicts its own boundary "
                f"block is a lie the renderer would act on."
            )
        if self.out_ms != self.boundary.final_out_ms:
            raise ValueError(
                f"out_ms ({self.out_ms}) does not match the boundary's final_out_ms "
                f"({self.boundary.final_out_ms})."
            )

    def assert_renderable(self) -> None:
        """The gate before Stage 6. §8.3 requires this on every shipped clip.

        Raises:
            BoundaryInvariantViolated: Kurdish invariant #2 fails.
            ValueError: the clip has not cleared QC.
        """
        assert_boundary_invariant(self.boundary)
        if self.qc is not None and not (self.qc.auto_pass or self.qc.human_reviewed):
            raise ValueError(
                f"clip {self.clip_id!r} has not cleared QC (flags: {list(self.qc.flags)}). "
                f"§2 puts a human QC gate before output, always — low confidence routes to "
                f"review, never to silent acceptance."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "clip_id": self.clip_id,
            "media_id": self.media_id,
            "in_ms": self.in_ms,
            "out_ms": self.out_ms,
            "discovery_path": self.discovery_path.value,
            "boundary": self.boundary.to_dict(),
            "transcript": self.transcript.to_dict(),
            "speaker": self.speaker,
            "editorial": self.editorial.to_dict() if self.editorial else None,
            "output": self.output.to_dict() if self.output else None,
            "qc": self.qc.to_dict() if self.qc else None,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Clip:
        editorial = data.get("editorial")
        output = data.get("output")
        qc = data.get("qc")
        return Clip(
            clip_id=data["clip_id"],
            media_id=data["media_id"],
            in_ms=data["in_ms"],
            out_ms=data["out_ms"],
            discovery_path=DiscoveryPath(data["discovery_path"]),
            boundary=Boundary.from_dict(data["boundary"]),
            transcript=ClipTranscript.from_dict(data["transcript"]),
            speaker=data.get("speaker"),
            editorial=Editorial.from_dict(editorial) if editorial else None,
            output=Output.from_dict(output) if output else None,
            qc=Qc.from_dict(qc) if qc else None,
        )
