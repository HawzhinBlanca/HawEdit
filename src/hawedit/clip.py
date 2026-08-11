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
from typing import Any, ClassVar, Final

from hawedit.boundary import Boundary, _strict_bool, assert_boundary_invariant
from hawedit.registry import resolve_role
from hawedit.transcripts import AsrProvenance, Word

__all__ = [
    "Clip",
    "ClipTranscript",
    "DiscoveryPath",
    "Editorial",
    "Output",
    "Qc",
    "RejectedCandidate",
    "Sv6d",
    "assert_sv6d_within_window",
    "parse_timestamps_ms",
]

# A timestamp citation in an SV6D label. Accepts `84.6s`, `84600ms`, `1:24` and `00:01:52`,
# which is the range of forms a judge plausibly emits; the requirement §3 Stage 3 makes is
# that *some* timeline evidence is present, not that it is in one house format.
#
# `Sv6d` checks presence, which is all it can do: it does not know which scene the label is
# about. Presence alone accepts `speaker at 9999s` on a twelve-second scene — two and three-
# quarter hours away, regex satisfied, claim anchored to a moment the model never saw.
# `assert_sv6d_within_window` is the other half, and it needs the window as an argument, so it
# is a function beside the type rather than a check inside it — the same split as
# `assert_boundary_invariant` beside `Boundary`.
_TIMESTAMP = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>ms|s)\b"
    r"|(?P<first>\d{1,2}):(?P<second>\d{2})(?::(?P<third>\d{2}))?"
)

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

    DIMENSIONS: ClassVar[tuple[str, ...]] = (
        "subject",
        "aesthetics",
        "camera",
        "editing",
        "narrative",
        "retention",
    )

    def __post_init__(self) -> None:
        for dimension in self.DIMENSIONS:
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


def parse_timestamps_ms(label: str) -> tuple[int, ...]:
    """Every time this label cites, in milliseconds, in the order they appear.

    A two-part clock is minutes and seconds — `1:24` in a note about a video is a minute and
    24 seconds, never an hour and 24 minutes. Three parts are hours, minutes, seconds.
    """
    found: list[int] = []
    for match in _TIMESTAMP.finditer(label):
        if match.group("value") is not None:
            value = float(match.group("value"))
            found.append(round(value if match.group("unit") == "ms" else value * 1000))
            continue
        first, second, third = match.group("first", "second", "third")
        if third is None:
            found.append((int(first) * 60 + int(second)) * 1000)
        else:
            found.append((int(first) * 3600 + int(second) * 60 + int(third)) * 1000)
    return tuple(found)


def assert_sv6d_within_window(sv6d: Sv6d, in_ms: int, out_ms: int) -> None:
    """Refuse SV6D labels whose timeline evidence is not in the scene they describe.

    §3 Stage 3: "Every label must cite a timestamp. Reject output where a claim has no timeline
    evidence." `Sv6d` enforces the first sentence and can only enforce the first, because it
    does not know which scene it belongs to. Read together the two sentences ask for something
    stronger than a well-formed string: a claim citing `9999s` on a twelve-second scene has a
    timestamp and no evidence, since the model was never shown that moment.

    The rule is that **some** cited time falls inside the window, not that every number does.
    A label may legitimately mention a length as well as a moment — "slow push-in over 3s,
    starting 5:04" cites 3 000 ms and 304 000 ms, and only the second is a point on the
    timeline. Requiring all of them would reject honest labels; requiring none is what let
    `9999s` through.

    Raises:
        ValueError: a dimension cites no time inside `[in_ms, out_ms]`.
    """
    for dimension in Sv6d.DIMENSIONS:
        label: str = getattr(sv6d, dimension)
        cited = parse_timestamps_ms(label)
        if not any(in_ms <= t <= out_ms for t in cited):
            raise ValueError(
                f"SV6D {dimension} label {label!r} cites {list(cited)} ms, all outside the "
                f"scene it describes ({in_ms}..{out_ms} ms). §3 Stage 3: 'Reject output where "
                f"a claim has no timeline evidence' — a timestamp pointing somewhere the model "
                f"was never shown is a well-formed string, not evidence."
            )
        # "Some cited time is in the window" alone let the original defect back in. Pair
        # `9999s` with a duration the window happens to contain and the claim rides through:
        # measured on the three windows Stage 0 actually plans for the fixture,
        # 'speaker gestures at 9999s, held over 1s' was ACCEPTED on 0..1400 ms, and the same
        # trick works on 1400..2800 ("over 2s") and 2800..4162 ("over 3s"). The cited tests
        # used only a 300000..312000 window, the one distance from zero where 1000 ms falls
        # outside — so the rule bit there and nowhere this pipeline runs.
        #
        # The discriminator needs no invented constant. In the legitimate case this guard was
        # written to permit — "slow push-in over 3s, starting 5:04" — the out-of-window number
        # is a small *duration* (3 000 ms) and the in-window one is the *moment* (304 000 ms).
        # In the defect it is reversed: the out-of-window number is vastly larger than the
        # scene. So a cited time outside the window is admissible only if it is shorter than
        # the window itself, which is the longest duration anything inside it can have. D-088.
        window_ms = out_ms - in_ms
        implausible = [t for t in cited if not (in_ms <= t <= out_ms) and t >= window_ms]
        if implausible:
            raise ValueError(
                f"SV6D {dimension} label {label!r} cites {implausible} ms, outside the scene "
                f"({in_ms}..{out_ms} ms) and too large to be a duration of anything within it "
                f"({window_ms} ms long). A label may name a length as well as a moment, but a "
                f"time this far outside is a claim about footage the model was never shown."
            )


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
    # §3 Stage 4 lists "payoff location" among the judge's outputs; §5's contract cell for it
    # did not exist. Added as an OPTIONAL field so every §5 document written before this still
    # deserializes — see D-033. `None` means unmeasured, not "at zero".
    payoff_at_ms: int | None = None

    def __post_init__(self) -> None:
        for name in _SCORE_FIELDS:
            value: float = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be within [0, 1], got {value}")
        entry = resolve_role(
            self.judge,
            frozenset({"kurdish_editorial_judge", "judge_shadow"}),
            "the editorial judge",
        )
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
            "payoff_at_ms": self.payoff_at_ms,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Editorial:
        raw_sv6d = data.get("sv6d")
        return Editorial(
            hook_score=data["hook_score"],
            self_contained=_strict_bool(data["self_contained"], "editorial.self_contained"),
            meaning_fidelity=data["meaning_fidelity"],
            misleading_edit_risk=data["misleading_edit_risk"],
            cultural_landing=data["cultural_landing"],
            narrative_role=data["narrative_role"],
            judge=data["judge"],
            sv6d=Sv6d(**raw_sv6d) if raw_sv6d else None,
            payoff_at_ms=data.get("payoff_at_ms"),
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
                # Hand-enumerated, so a field added to `AsrProvenance` is dropped here unless it
                # is named — and this dict is what §2 ships. Without `adapter` the delivered clip
                # says stock weights read these words whichever weights actually did. D-181.
                "adapter": self.asr.adapter,
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
    # §3 Stage 4 lists hashtags among the judge's outputs and §5 had no cell. Optional and
    # additive for the same reason as `Editorial.payoff_at_ms` — see D-033. An empty tuple
    # here genuinely means "none", because a post with no hashtags is a real deliverable.
    hashtags_ckb: tuple[str, ...] = ()

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
            "hashtags_ckb": list(self.hashtags_ckb),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Output:
        return Output(
            title_ckb=data["title_ckb"],
            description_ckb=data["description_ckb"],
            crop_target=data["crop_target"],
            caption_style=data["caption_style"],
            durations=tuple(data["durations"]),
            hashtags_ckb=tuple(data.get("hashtags_ckb", ())),
        )


@dataclass(frozen=True, slots=True)
class Qc:
    """§5's `qc` block. §2's diagram puts a human QC gate before output, always."""

    auto_pass: bool
    flags: tuple[str, ...] = ()
    human_reviewed: bool = False

    def __post_init__(self) -> None:
        _strict_bool(self.auto_pass, "qc.auto_pass")
        _strict_bool(self.human_reviewed, "qc.human_reviewed")
        if not isinstance(self.flags, tuple) or any(
            not isinstance(flag, str) or not flag.strip() for flag in self.flags
        ):
            raise ValueError("qc.flags must be a tuple of non-empty strings")

    def to_dict(self) -> dict[str, Any]:
        return {
            "auto_pass": self.auto_pass,
            "flags": list(self.flags),
            "human_reviewed": self.human_reviewed,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Qc:
        raw_flags = data.get("flags", [])
        if not isinstance(raw_flags, list) or not all(isinstance(flag, str) for flag in raw_flags):
            raise ValueError("qc.flags must be a JSON array of strings")
        return Qc(
            auto_pass=_strict_bool(data["auto_pass"], "qc.auto_pass"),
            flags=tuple(raw_flags),
            human_reviewed=_strict_bool(data.get("human_reviewed", False), "qc.human_reviewed"),
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
        # A clip with no QC record has not passed QC — it has skipped it. §2's diagram puts
        # the gate before output "(always)", so absence is refusal, not permission. The
        # same for the judge: an unjudged clip has no meaning-fidelity or misleading-edit
        # score, which are the numbers §8.2 says matter most. Audit finding #3.
        if self.qc is None:
            raise ValueError(
                f"clip {self.clip_id!r} carries no QC record. §2 puts a human QC gate before "
                f"output, always — a missing record is not a pass."
            )
        if not (self.qc.auto_pass or self.qc.human_reviewed):
            raise ValueError(
                f"clip {self.clip_id!r} has not cleared QC (flags: {list(self.qc.flags)}). "
                f"§2 puts a human QC gate before output, always — low confidence routes to "
                f"review, never to silent acceptance."
            )
        if self.editorial is None:
            raise ValueError(
                f"clip {self.clip_id!r} has no editorial block: it was never judged, so its "
                f"meaning fidelity and misleading-edit risk are unknown. §8.2 calls the "
                f"misleading-edit rate the metric that matters for a media organisation."
            )
        if self.output is None:
            raise ValueError(
                f"clip {self.clip_id!r} has no output block — no title, crop target or "
                f"caption style to render with."
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
