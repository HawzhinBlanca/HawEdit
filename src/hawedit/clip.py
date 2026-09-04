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

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, ClassVar, Final

from hawedit.boundary import (
    Boundary,
    _json_object_fields,
    _strict_bool,
    _strict_json_array,
    _strict_json_int,
    _strict_json_number,
    _strict_json_string,
    _strict_optional_json_string,
    assert_boundary_invariant,
)
from hawedit.registry import resolve_role
from hawedit.transcripts import AsrProvenance, Word, validate_media_id, validate_media_sha256

_SHA256_HEX_RE: Final = re.compile(r"^[0-9a-f]{64}$")
_ISO_TIMESTAMP_RE: Final = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)

__all__ = [
    "HOOK_TYPES",
    "MAX_CANDIDATE_SPAN_MS",
    "MAX_MISLEADING_EDIT_RISK",
    "MIN_CANDIDATE_SPAN_MS",
    "MIN_CULTURAL_LANDING",
    "MIN_HOOK_SCORE",
    "MIN_MEANING_FIDELITY",
    "Clip",
    "ClipTranscript",
    "DiscoveryPath",
    "Editorial",
    "EditorialBelowThreshold",
    "Output",
    "Provenance",
    "Qc",
    "QcRecord",
    "RejectedCandidate",
    "Sv6d",
    "assert_sv6d_within_window",
    "parse_timestamps_ms",
    "sv6d_from_json",
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

HOOK_TYPES: Final = frozenset({"question", "claim", "contrast", "story_open", "confession"})


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
            label = _strict_json_string(getattr(self, dimension), f"sv6d.{dimension}")
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


def sv6d_from_json(value: object, field: str) -> Sv6d | None:
    if value is None:
        return None
    fields = _json_object_fields(
        value,
        field=field,
        required=frozenset(Sv6d.DIMENSIONS),
    )
    return Sv6d(
        **{
            dimension: _strict_json_string(fields[dimension], f"{field}.{dimension}")
            for dimension in Sv6d.DIMENSIONS
        }
    )


_sv6d_from_json = sv6d_from_json


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
        # the window itself, which is the longest duration anything inside it can have. D-098.
        window_ms = out_ms - in_ms
        implausible = [t for t in cited if not (in_ms <= t <= out_ms) and t >= window_ms]
        if implausible:
            raise ValueError(
                f"SV6D {dimension} label {label!r} cites {implausible} ms, outside the scene "
                f"({in_ms}..{out_ms} ms) and too large to be a duration of anything within it "
                f"({window_ms} ms long). A label may name a length as well as a moment, but a "
                f"time this far outside is a claim about footage the model was never shown."
            )


# Set by Hawa on 2026-08-26, after the first genuinely judged run measured what their absence
# costs. Live Gemini scored the auto-selected clip hook **0.20**, `self_contained` **False** and
# misleading-edit risk **0.40**, and Stage 6 rendered it anyway: `assert_renderable` checked that
# an editorial block *existed* and never read a number out of it, while the message three lines
# below it said "§8.2 calls the misleading-edit rate the metric that matters for a media
# organisation". The judge had already done its job. Nothing acted on the answer.
#
# Numbers, not judgement calls dressed as constants: these are the owner's, recorded with the
# date they were set, so changing either is a visible change to a decision.
#
# The ceiling moved from 0.05 to 0.10 on 2026-08-27, and the move is a measurement rather than a
# relaxation: **ten of ten** verdicts across two unrelated episodes came back at exactly 0.10,
# on spans of 32 to 102 seconds in nine different parts of the footage. The metric does move —
# ep10's pre-fix run produced 0.00, 0.10, 0.20, 0.85 and 0.90 — so 0.10 is the floor
# `gemini-2.5-pro` settles on for a well-formed excerpt of a conversation, not a value it always
# emits. At 0.05 this pipeline refuses every clip it can cut from a podcast, whatever its
# quality: ep01's best scored hook 0.90, self-contained, meaning fidelity 1.00, and was refused
# on one hundredth of a point. D-257, amending D-253.
MIN_HOOK_SCORE: Final = 0.75
MAX_MISLEADING_EDIT_RISK: Final = 0.10
MIN_MEANING_FIDELITY: Final = 0.70
MIN_CULTURAL_LANDING: Final = 0.70

# Set by Hawa on 2026-08-27, and a *decision* rather than a derivation: `BLUEPRINT.md` states no
# clip duration anywhere. Its only fixed duration is `max_speech_duration_s=38`, which governs
# ASR input. The 20-55 s figure quoted around this project comes from the pro-kurdish-reel
# operator runbook, not from §3, so this range stands on the same footing as `MIN_HOOK_SCORE`
# and changing it should read as a changed decision.
#
# Why the wide, long window rather than the runbook's: a grown span is likelier to contain a
# whole argument, and that is the entire mechanism. Measured on the real 75-minute episode, the
# strongest candidate scored hook 0.90 with misleading-edit **0.85** across 5.3 seconds — a
# five-second cut of a conversation is close to definitionally not self-contained, which is
# exactly what that risk score measures.
#
# The minimum is an eligibility bar in both directions: a seed that cannot reach it on complete
# sentence boundaries becomes ineligible where today it might have been judged. Whether
# eligibility rises or falls overall is measured in T5, not assumed.
MIN_CANDIDATE_SPAN_MS: Final = 30_000
MAX_CANDIDATE_SPAN_MS: Final = 90_000


class EditorialBelowThreshold(ValueError):
    """The judge scored this clip below what §8.2 permits to ship.

    Separate from the QC refusals it sits beside because it is a different claim: QC is about
    whether a human looked, and this is about what the model said when it did. A caller that
    wants to ship anyway has to say so in a way that appears in a diff.
    """


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
    hook_type: str | None = None
    payoff_strength: float | None = None
    ends_on_a_beat: bool | None = None
    reason_ckb: str | None = None

    def __post_init__(self) -> None:
        _strict_bool(self.self_contained, "editorial.self_contained")
        for name in _SCORE_FIELDS:
            _strict_json_number(getattr(self, name), f"editorial.{name}", minimum=0.0, maximum=1.0)
        for name in ("narrative_role", "judge"):
            _strict_json_string(getattr(self, name), f"editorial.{name}")
        if self.payoff_at_ms is not None:
            _strict_json_int(self.payoff_at_ms, "editorial.payoff_at_ms", minimum=0)
        if self.sv6d is not None and not isinstance(self.sv6d, Sv6d):
            raise ValueError("editorial.sv6d must be an Sv6d value or None")
        if self.hook_type is not None and self.hook_type not in HOOK_TYPES:
            raise ValueError(
                f"editorial.hook_type must be one of {sorted(HOOK_TYPES)}, got {self.hook_type!r}"
            )
        if self.payoff_strength is not None:
            _strict_json_number(
                self.payoff_strength, "editorial.payoff_strength", minimum=0.0, maximum=1.0
            )
        if self.ends_on_a_beat is not None:
            _strict_bool(self.ends_on_a_beat, "editorial.ends_on_a_beat")
        if self.reason_ckb is not None:
            _strict_json_string(self.reason_ckb, "editorial.reason_ckb")
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
            "hook_type": self.hook_type,
            "payoff_strength": self.payoff_strength,
            "ends_on_a_beat": self.ends_on_a_beat,
            "reason_ckb": self.reason_ckb,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Editorial:
        fields = _json_object_fields(
            data,
            field="editorial",
            required=frozenset(
                {
                    "hook_score",
                    "self_contained",
                    "meaning_fidelity",
                    "misleading_edit_risk",
                    "cultural_landing",
                    "narrative_role",
                    "judge",
                }
            ),
            optional=frozenset(
                {
                    "sv6d",
                    "payoff_at_ms",
                    "hook_type",
                    "payoff_strength",
                    "ends_on_a_beat",
                    "reason_ckb",
                }
            ),
        )
        raw_payoff = fields.get("payoff_at_ms")
        return Editorial(
            hook_score=_strict_json_number(
                fields["hook_score"], "editorial.hook_score", minimum=0.0, maximum=1.0
            ),
            self_contained=_strict_bool(fields["self_contained"], "editorial.self_contained"),
            meaning_fidelity=_strict_json_number(
                fields["meaning_fidelity"],
                "editorial.meaning_fidelity",
                minimum=0.0,
                maximum=1.0,
            ),
            misleading_edit_risk=_strict_json_number(
                fields["misleading_edit_risk"],
                "editorial.misleading_edit_risk",
                minimum=0.0,
                maximum=1.0,
            ),
            cultural_landing=_strict_json_number(
                fields["cultural_landing"],
                "editorial.cultural_landing",
                minimum=0.0,
                maximum=1.0,
            ),
            narrative_role=_strict_json_string(
                fields["narrative_role"], "editorial.narrative_role"
            ),
            judge=_strict_json_string(fields["judge"], "editorial.judge"),
            sv6d=_sv6d_from_json(fields.get("sv6d"), "editorial.sv6d"),
            payoff_at_ms=(
                None
                if raw_payoff is None
                else _strict_json_int(raw_payoff, "editorial.payoff_at_ms", minimum=0)
            ),
            hook_type=(
                None
                if fields.get("hook_type") is None
                else _strict_json_string(fields["hook_type"], "editorial.hook_type")
            ),
            payoff_strength=(
                None
                if fields.get("payoff_strength") is None
                else _strict_json_number(
                    fields["payoff_strength"], "editorial.payoff_strength", minimum=0.0, maximum=1.0
                )
            ),
            ends_on_a_beat=(
                None
                if fields.get("ends_on_a_beat") is None
                else _strict_bool(fields["ends_on_a_beat"], "editorial.ends_on_a_beat")
            ),
            reason_ckb=(
                None
                if fields.get("reason_ckb") is None
                else _strict_json_string(fields["reason_ckb"], "editorial.reason_ckb")
            ),
        )


@dataclass(frozen=True, slots=True)
class ClipTranscript:
    """§5's `transcript` block. `raw_ckb` is canonical and ships to the client (invariant #1)."""

    raw_ckb: str
    norm_ckb: str
    en_aux: str | None
    words: tuple[Word, ...]
    asr: AsrProvenance

    def __post_init__(self) -> None:
        _strict_json_string(self.raw_ckb, "transcript.raw_ckb")
        _strict_json_string(self.norm_ckb, "transcript.norm_ckb")
        _strict_optional_json_string(self.en_aux, "transcript.en_aux")
        if not isinstance(self.words, tuple) or not all(
            isinstance(word, Word) for word in self.words
        ):
            raise ValueError("transcript.words must be a tuple of Word values")
        if not isinstance(self.asr, AsrProvenance):
            raise ValueError("transcript.asr must be AsrProvenance")

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
        fields = _json_object_fields(
            data,
            field="transcript",
            required=frozenset({"raw_ckb", "norm_ckb", "asr"}),
            optional=frozenset({"en_aux", "words"}),
        )
        raw_words = _strict_json_array(fields.get("words", []), "transcript.words")
        words: list[Word] = []
        for index, raw_word in enumerate(raw_words):
            word = _json_object_fields(
                raw_word,
                field=f"transcript.words[{index}]",
                required=frozenset({"w", "start_ms", "end_ms", "conf"}),
            )
            words.append(
                Word(
                    w=_strict_json_string(word["w"], f"transcript.words[{index}].w"),
                    start_ms=_strict_json_int(
                        word["start_ms"], f"transcript.words[{index}].start_ms", minimum=0
                    ),
                    end_ms=_strict_json_int(
                        word["end_ms"], f"transcript.words[{index}].end_ms", minimum=0
                    ),
                    conf=_strict_json_number(
                        word["conf"],
                        f"transcript.words[{index}].conf",
                        minimum=0.0,
                        maximum=1.0,
                    ),
                )
            )
        asr = _json_object_fields(
            fields["asr"],
            field="transcript.asr",
            required=frozenset({"canonical"}),
            optional=frozenset({"adapter", "aligner", "validated_by", "mean_logprob"}),
        )
        return ClipTranscript(
            raw_ckb=_strict_json_string(fields["raw_ckb"], "transcript.raw_ckb"),
            norm_ckb=_strict_json_string(fields["norm_ckb"], "transcript.norm_ckb"),
            en_aux=_strict_optional_json_string(fields.get("en_aux"), "transcript.en_aux"),
            words=tuple(words),
            asr=AsrProvenance(
                canonical=_strict_json_string(asr["canonical"], "transcript.asr.canonical"),
                adapter=_strict_optional_json_string(asr.get("adapter"), "transcript.asr.adapter"),
                aligner=_strict_optional_json_string(asr.get("aligner"), "transcript.asr.aligner"),
                validated_by=_strict_optional_json_string(
                    asr.get("validated_by"), "transcript.asr.validated_by"
                ),
                mean_logprob=asr.get("mean_logprob"),
            ),
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
    silence_removed_ms: int = 0
    loudness: dict[str, Any] | None = None
    title_variants_ckb: tuple[str, ...] = ()
    cover_frame_ms: int | None = None

    def __post_init__(self) -> None:
        for name in ("title_ckb", "description_ckb", "crop_target", "caption_style"):
            _strict_json_string(getattr(self, name), f"output.{name}")
        if not isinstance(self.durations, tuple):
            raise ValueError("output durations must be a tuple of JSON integers")
        for duration in self.durations:
            _strict_json_int(duration, "output duration")
            if duration <= 0:
                raise ValueError("output durations must be positive seconds")
        if not isinstance(self.hashtags_ckb, tuple) or not all(
            isinstance(tag, str) for tag in self.hashtags_ckb
        ):
            raise ValueError("output.hashtags_ckb must be a tuple of strings")
        _strict_json_int(self.silence_removed_ms, "output.silence_removed_ms", minimum=0)
        if self.loudness is not None and not isinstance(self.loudness, dict):
            raise ValueError("output.loudness must be a dictionary or None")
        if not isinstance(self.title_variants_ckb, tuple) or not all(
            isinstance(variant, str) for variant in self.title_variants_ckb
        ):
            raise ValueError("output.title_variants_ckb must be a tuple of strings")
        if self.cover_frame_ms is not None:
            _strict_json_int(self.cover_frame_ms, "output.cover_frame_ms", minimum=0)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "title_ckb": self.title_ckb,
            "description_ckb": self.description_ckb,
            "crop_target": self.crop_target,
            "caption_style": self.caption_style,
            "durations": list(self.durations),
            "hashtags_ckb": list(self.hashtags_ckb),
            "silence_removed_ms": self.silence_removed_ms,
            "title_variants_ckb": list(self.title_variants_ckb),
            "cover_frame_ms": self.cover_frame_ms,
        }
        if self.loudness is not None:
            data["loudness"] = dict(self.loudness)
        return data

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Output:
        fields = _json_object_fields(
            data,
            field="output",
            required=frozenset(
                {"title_ckb", "description_ckb", "crop_target", "caption_style", "durations"}
            ),
            optional=frozenset(
                {
                    "hashtags_ckb",
                    "silence_removed_ms",
                    "loudness",
                    "title_variants_ckb",
                    "cover_frame_ms",
                }
            ),
        )
        raw_durations = _strict_json_array(fields["durations"], "output.durations")
        raw_hashtags = _strict_json_array(fields.get("hashtags_ckb", []), "output.hashtags_ckb")
        raw_silence = fields.get("silence_removed_ms", 0)
        raw_loudness = fields.get("loudness")
        raw_variants = _strict_json_array(
            fields.get("title_variants_ckb", []), "output.title_variants_ckb"
        )
        raw_cover = fields.get("cover_frame_ms")
        return Output(
            title_ckb=_strict_json_string(fields["title_ckb"], "output.title_ckb"),
            description_ckb=_strict_json_string(
                fields["description_ckb"], "output.description_ckb"
            ),
            crop_target=_strict_json_string(fields["crop_target"], "output.crop_target"),
            caption_style=_strict_json_string(fields["caption_style"], "output.caption_style"),
            durations=tuple(
                _strict_json_int(duration, "output duration") for duration in raw_durations
            ),
            hashtags_ckb=tuple(
                _strict_json_string(tag, "output.hashtags_ckb member") for tag in raw_hashtags
            ),
            silence_removed_ms=_strict_json_int(
                raw_silence, "output.silence_removed_ms", minimum=0
            ),
            loudness=dict(raw_loudness) if isinstance(raw_loudness, dict) else None,
            title_variants_ckb=tuple(
                _strict_json_string(variant, "output.title_variants_ckb member")
                for variant in raw_variants
            ),
            cover_frame_ms=(
                None
                if raw_cover is None
                else _strict_json_int(raw_cover, "output.cover_frame_ms", minimum=0)
            ),
        )


@dataclass(frozen=True, slots=True)
class QcRecord:
    """A verified, signed human QC review record (§2 / Task T1.3)."""

    reviewer: str
    reviewed_at: str
    mp4_sha256: str
    seconds_watched: float
    verdict: str
    notes: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.reviewer, str) or not self.reviewer.strip():
            raise ValueError("qc_record.reviewer must be a non-empty string")
        if not isinstance(self.reviewed_at, str) or not _ISO_TIMESTAMP_RE.match(self.reviewed_at):
            raise ValueError(
                f"qc_record.reviewed_at must be an ISO-8601 timestamp: {self.reviewed_at!r}"
            )
        if not isinstance(self.mp4_sha256, str) or not _SHA256_HEX_RE.match(
            self.mp4_sha256.lower()
        ):
            raise ValueError(
                f"qc_record.mp4_sha256 must be a 64-char lowercase hex SHA-256: {self.mp4_sha256!r}"
            )
        if not isinstance(self.seconds_watched, int | float) or self.seconds_watched <= 0:
            raise ValueError(
                f"qc_record.seconds_watched must be a positive number: {self.seconds_watched!r}"
            )
        if not isinstance(self.verdict, str) or not self.verdict.strip():
            raise ValueError("qc_record.verdict must be a non-empty string")
        if not isinstance(self.notes, str):
            raise ValueError("qc_record.notes must be a string")

    def to_dict(self) -> dict[str, Any]:
        return {
            "reviewer": self.reviewer,
            "reviewed_at": self.reviewed_at,
            "mp4_sha256": self.mp4_sha256.lower(),
            "seconds_watched": float(self.seconds_watched),
            "verdict": self.verdict,
            "notes": self.notes,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> QcRecord:
        fields = _json_object_fields(
            data,
            field="qc_record",
            required=frozenset(
                {"reviewer", "reviewed_at", "mp4_sha256", "seconds_watched", "verdict"}
            ),
            optional=frozenset({"notes"}),
        )
        return QcRecord(
            reviewer=_strict_json_string(fields["reviewer"], "qc_record.reviewer"),
            reviewed_at=_strict_json_string(fields["reviewed_at"], "qc_record.reviewed_at"),
            mp4_sha256=_strict_json_string(fields["mp4_sha256"], "qc_record.mp4_sha256"),
            seconds_watched=_strict_json_number(
                fields["seconds_watched"], "qc_record.seconds_watched", minimum=0.001
            ),
            verdict=_strict_json_string(fields["verdict"], "qc_record.verdict"),
            notes=_strict_optional_json_string(fields.get("notes"), "qc_record.notes") or "",
        )

    @classmethod
    def from_json(cls, text: str) -> QcRecord:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON in qc_record: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("qc_record must be a JSON object")
        return cls.from_dict(parsed)


@dataclass(frozen=True, slots=True)
class Qc:
    """§5's `qc` block. §2's diagram puts a human QC gate before output, always."""

    auto_pass: bool
    flags: tuple[str, ...] = ()
    human_reviewed: bool = False
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    reviewed_sha256: str | None = None

    def __post_init__(self) -> None:
        _strict_bool(self.auto_pass, "qc.auto_pass")
        _strict_bool(self.human_reviewed, "qc.human_reviewed")
        if not isinstance(self.flags, tuple) or any(
            not isinstance(flag, str) or not flag.strip() for flag in self.flags
        ):
            raise ValueError("qc.flags must be a tuple of non-empty strings")
        if self.human_reviewed:
            if not isinstance(self.reviewed_by, str) or not self.reviewed_by.strip():
                raise ValueError("qc.human_reviewed requires a non-empty reviewed_by string")
            if not isinstance(self.reviewed_at, str) or not _ISO_TIMESTAMP_RE.match(
                self.reviewed_at
            ):
                raise ValueError(
                    "qc.human_reviewed requires a valid ISO-8601 reviewed_at timestamp: "
                    f"{self.reviewed_at!r}"
                )
            if not isinstance(self.reviewed_sha256, str) or not _SHA256_HEX_RE.match(
                self.reviewed_sha256.lower()
            ):
                raise ValueError(
                    "qc.human_reviewed requires a 64-character lowercase hex reviewed_sha256: "
                    f"{self.reviewed_sha256!r}"
                )
        else:
            if (
                self.reviewed_by is not None
                or self.reviewed_at is not None
                or self.reviewed_sha256 is not None
            ):
                raise ValueError("qc review metadata requires human_reviewed=True")

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "auto_pass": self.auto_pass,
            "flags": list(self.flags),
            "human_reviewed": self.human_reviewed,
        }
        if self.reviewed_by is not None:
            data["reviewed_by"] = self.reviewed_by
        if self.reviewed_at is not None:
            data["reviewed_at"] = self.reviewed_at
        if self.reviewed_sha256 is not None:
            data["reviewed_sha256"] = self.reviewed_sha256.lower()
        return data

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Qc:
        fields = _json_object_fields(
            data,
            field="qc",
            required=frozenset({"auto_pass"}),
            optional=frozenset(
                {"flags", "human_reviewed", "reviewed_by", "reviewed_at", "reviewed_sha256"}
            ),
        )
        raw_flags = _strict_json_array(fields.get("flags", []), "qc.flags")
        if not all(isinstance(flag, str) for flag in raw_flags):
            raise ValueError("qc.flags must be a JSON array of strings")
        human_rev = _strict_bool(fields.get("human_reviewed", False), "qc.human_reviewed")
        rev_by = _strict_optional_json_string(fields.get("reviewed_by"), "qc.reviewed_by")
        rev_at = _strict_optional_json_string(fields.get("reviewed_at"), "qc.reviewed_at")
        rev_sha = _strict_optional_json_string(fields.get("reviewed_sha256"), "qc.reviewed_sha256")
        return Qc(
            auto_pass=_strict_bool(fields["auto_pass"], "qc.auto_pass"),
            flags=tuple(raw_flags),
            human_reviewed=human_rev,
            reviewed_by=rev_by,
            reviewed_at=rev_at,
            reviewed_sha256=rev_sha,
        )

    @classmethod
    def from_record(
        cls, record: QcRecord, auto_pass: bool = False, flags: tuple[str, ...] = ()
    ) -> Qc:
        """Construct a valid human-reviewed Qc block from a verified QcRecord."""
        return cls(
            auto_pass=auto_pass,
            flags=flags,
            human_reviewed=True,
            reviewed_by=record.reviewer,
            reviewed_at=record.reviewed_at,
            reviewed_sha256=record.mp4_sha256.lower(),
        )


def _probe_ffmpeg_version() -> str:
    from shutil import which

    configured = os.environ.get("HAWEDIT_FFMPEG")
    bin_path = Path(configured) if configured and Path(configured).is_file() else None
    if bin_path is None:
        vendored = Path(__file__).resolve().parents[2] / ".ffmpeg"
        for name in ("ffmpeg", "ffmpeg.exe"):
            if (vendored / name).is_file():
                bin_path = vendored / name
                break
    if bin_path is None:
        located = which("ffmpeg")
        if located:
            bin_path = Path(located)
    if bin_path is not None:
        try:
            proc = subprocess.run(
                [str(bin_path), "-version"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            if proc.stdout:
                line = proc.stdout.splitlines()[0].strip()
                if line:
                    return line
        except Exception:
            pass
    return "7.1"


def _probe_revisions_digest() -> str:
    for candidate in (
        Path("models/revisions.json"),
        Path(__file__).resolve().parents[2] / "models" / "revisions.json",
    ):
        if candidate.is_file():
            try:
                return hashlib.sha256(candidate.read_bytes()).hexdigest()
            except Exception:
                pass
    return "0" * 64


def _probe_git_commit() -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        sha = proc.stdout.strip()
        if len(sha) == 40 and all(c in "0123456789abcdefABCDEF" for c in sha):
            return sha
    except Exception:
        pass
    return "unknown"


@dataclass(frozen=True, slots=True)
class Provenance:
    """§7.6 / Task T1.6: A clip must say what made it.

    Names the exact renderer commit, model checkpoint revisions digest, judge prompt
    hash and response ID, threshold values in force, VAD/scene cut guards, crop geometry
    constants, FFmpeg runtime version and build configuration, and execution profile.
    """

    git_commit: str
    revisions_digest: str
    judge_prompt_sha256: str
    judge_response_id: str
    thresholds: dict[str, float]
    vad_scene: dict[str, float | int]
    crop_constants: dict[str, float | int]
    ffmpeg: dict[str, str]
    profile: str = "production"

    def __post_init__(self) -> None:
        _strict_json_string(self.git_commit, "provenance.git_commit")
        _strict_json_string(self.revisions_digest, "provenance.revisions_digest")
        _strict_json_string(self.judge_prompt_sha256, "provenance.judge_prompt_sha256")
        _strict_json_string(self.judge_response_id, "provenance.judge_response_id")
        _strict_json_string(self.profile, "provenance.profile")
        if not isinstance(self.thresholds, dict) or not self.thresholds:
            raise ValueError("provenance.thresholds must be a non-empty dictionary of floats")
        if not isinstance(self.vad_scene, dict) or not self.vad_scene:
            raise ValueError("provenance.vad_scene must be a non-empty dictionary of numbers")
        if not isinstance(self.crop_constants, dict) or not self.crop_constants:
            raise ValueError("provenance.crop_constants must be a non-empty dictionary of numbers")
        if not isinstance(self.ffmpeg, dict) or not self.ffmpeg:
            raise ValueError("provenance.ffmpeg must be a non-empty dictionary of strings")

    def to_dict(self) -> dict[str, Any]:
        return {
            "git_commit": self.git_commit,
            "revisions_digest": self.revisions_digest,
            "judge_prompt_sha256": self.judge_prompt_sha256,
            "judge_response_id": self.judge_response_id,
            "thresholds": dict(self.thresholds),
            "vad_scene": dict(self.vad_scene),
            "crop_constants": dict(self.crop_constants),
            "ffmpeg": dict(self.ffmpeg),
            "profile": self.profile,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Provenance:
        fields = _json_object_fields(
            data,
            field="provenance",
            required=frozenset(
                {
                    "git_commit",
                    "revisions_digest",
                    "judge_prompt_sha256",
                    "judge_response_id",
                    "thresholds",
                    "vad_scene",
                    "crop_constants",
                    "ffmpeg",
                }
            ),
            optional=frozenset({"profile"}),
        )
        raw_thresholds = fields["thresholds"]
        if not isinstance(raw_thresholds, dict) or not raw_thresholds:
            raise ValueError("provenance.thresholds must be a non-empty dictionary")
        raw_vad = fields["vad_scene"]
        if not isinstance(raw_vad, dict) or not raw_vad:
            raise ValueError("provenance.vad_scene must be a non-empty dictionary")
        raw_crop = fields["crop_constants"]
        if not isinstance(raw_crop, dict) or not raw_crop:
            raise ValueError("provenance.crop_constants must be a non-empty dictionary")
        raw_ffmpeg = fields["ffmpeg"]
        if not isinstance(raw_ffmpeg, dict) or not raw_ffmpeg:
            raise ValueError("provenance.ffmpeg must be a non-empty dictionary")

        return Provenance(
            git_commit=_strict_json_string(fields["git_commit"], "provenance.git_commit"),
            revisions_digest=_strict_json_string(
                fields["revisions_digest"], "provenance.revisions_digest"
            ),
            judge_prompt_sha256=_strict_json_string(
                fields["judge_prompt_sha256"], "provenance.judge_prompt_sha256"
            ),
            judge_response_id=_strict_json_string(
                fields["judge_response_id"], "provenance.judge_response_id"
            ),
            thresholds={k: float(v) for k, v in raw_thresholds.items()},
            vad_scene=dict(raw_vad),
            crop_constants=dict(raw_crop),
            ffmpeg={k: str(v) for k, v in raw_ffmpeg.items()},
            profile=_strict_optional_json_string(fields.get("profile"), "provenance.profile")
            or "production",
        )

    @classmethod
    def current(
        cls,
        git_commit: str | None = None,
        revisions_digest: str | None = None,
        judge_prompt_sha256: str = "0" * 64,
        judge_response_id: str = "resp-default",
        profile: str = "production",
        ffmpeg_version: str | None = None,
        ffmpeg_buildconf_hash: str = "0" * 64,
    ) -> Provenance:
        return cls(
            git_commit=git_commit if git_commit is not None else _probe_git_commit(),
            revisions_digest=revisions_digest
            if revisions_digest is not None
            else _probe_revisions_digest(),
            judge_prompt_sha256=judge_prompt_sha256,
            judge_response_id=judge_response_id,
            thresholds={
                "min_hook_score": MIN_HOOK_SCORE,
                "max_misleading_edit_risk": MAX_MISLEADING_EDIT_RISK,
                "min_meaning_fidelity": 0.70,
                "min_cultural_landing": 0.70,
            },
            vad_scene={
                "scene_threshold": 0.30,
                "vad_onset_ms": 300,
                "shot_cut_guard_ms": 400,
            },
            crop_constants={
                "target_width": 1080,
                "target_height": 1920,
                "face_composition_line": 0.38,
                "max_vertical_zoom": 1.20,
            },
            ffmpeg={
                "version": ffmpeg_version
                if ffmpeg_version is not None
                else _probe_ffmpeg_version(),
                "buildconf_hash": ffmpeg_buildconf_hash,
            },
            profile=profile,
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
        validate_media_id(self.media_id)
        _strict_json_int(self.in_ms, "rejected candidate in_ms", minimum=0)
        _strict_json_int(self.out_ms, "rejected candidate out_ms", minimum=0)
        if self.out_ms <= self.in_ms:
            raise ValueError("rejected candidate out_ms must be after in_ms")
        if not isinstance(self.discovery_path, DiscoveryPath):
            raise ValueError("rejected candidate discovery_path must be a DiscoveryPath")
        _strict_json_string(self.reject_reason, "rejected candidate reject_reason")
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
        fields = _json_object_fields(
            data,
            field="rejected candidate",
            required=frozenset({"media_id", "in_ms", "out_ms", "discovery_path", "reject_reason"}),
        )
        return RejectedCandidate(
            media_id=_strict_json_string(fields["media_id"], "rejected candidate.media_id"),
            in_ms=_strict_json_int(fields["in_ms"], "rejected candidate.in_ms", minimum=0),
            out_ms=_strict_json_int(fields["out_ms"], "rejected candidate.out_ms", minimum=0),
            discovery_path=DiscoveryPath(
                _strict_json_string(fields["discovery_path"], "rejected candidate.discovery_path")
            ),
            reject_reason=_strict_json_string(
                fields["reject_reason"], "rejected candidate.reject_reason"
            ),
        )


@dataclass(frozen=True, slots=True)
class Clip:
    """§5's clip record.

    `editorial` and `output` are optional because Stage 5 produces boundaries before Stage 4
    has scored anything — a clip mid-pipeline is a real state, not an incomplete record.
    """

    clip_id: str
    media_id: str
    # ``None`` reads legacy editing JSON, but cannot clear the render gate.
    media_sha256: str | None
    in_ms: int
    out_ms: int
    discovery_path: DiscoveryPath
    boundary: Boundary
    transcript: ClipTranscript
    speaker: str | None = None
    editorial: Editorial | None = None
    output: Output | None = None
    qc: Qc | None = None
    provenance: Provenance | None = None

    def __post_init__(self) -> None:
        validate_media_id(self.clip_id)
        validate_media_id(self.media_id)
        validate_media_sha256(self.media_sha256)
        _strict_json_int(self.in_ms, "clip.in_ms", minimum=0)
        _strict_json_int(self.out_ms, "clip.out_ms", minimum=0)
        if self.out_ms <= self.in_ms:
            raise ValueError("clip.out_ms must be after clip.in_ms")
        if not isinstance(self.discovery_path, DiscoveryPath):
            raise ValueError("clip.discovery_path must be a DiscoveryPath")
        if not isinstance(self.boundary, Boundary):
            raise ValueError("clip.boundary must be a Boundary")
        if not isinstance(self.transcript, ClipTranscript):
            raise ValueError("clip.transcript must be a ClipTranscript")
        _strict_optional_json_string(self.speaker, "clip.speaker")
        if self.editorial is not None and not isinstance(self.editorial, Editorial):
            raise ValueError("clip.editorial must be Editorial or None")
        if self.output is not None and not isinstance(self.output, Output):
            raise ValueError("clip.output must be Output or None")
        if self.qc is not None and not isinstance(self.qc, Qc):
            raise ValueError("clip.qc must be Qc or None")
        if self.provenance is not None and not isinstance(self.provenance, Provenance):
            raise ValueError("clip.provenance must be Provenance or None")
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
        if self.media_sha256 is None:
            raise ValueError(
                f"clip {self.clip_id!r} has no source-media SHA-256 binding; legacy "
                "editing JSON cannot be rendered safely"
            )
        # A clip with no QC record has not passed QC — it has skipped it. §2's diagram puts
        # the gate before output "(always)", so absence is refusal, not permission. The
        # same for the judge: an unjudged clip has no meaning-fidelity or misleading-edit
        # score, which are the numbers §8.2 says matter most. Audit finding #3.
        if self.qc is None:
            raise ValueError(
                f"clip {self.clip_id!r} carries no QC record. §2 puts a human QC gate before "
                f"output, always — a missing record is not a pass."
            )
        if not self.qc.human_reviewed:
            raise ValueError(
                f"clip {self.clip_id!r} has not cleared human QC "
                f"(auto_pass={self.qc.auto_pass}, flags: {list(self.qc.flags)}). "
                f"§2 puts a human QC gate before output, always — automation may inform "
                f"review, but it cannot replace it."
            )
        if self.editorial is None:
            raise ValueError(
                f"clip {self.clip_id!r} has no editorial block: it was never judged, so its "
                f"meaning fidelity and misleading-edit risk are unknown. §8.2 calls the "
                f"misleading-edit rate the metric that matters for a media organisation."
            )
        # The scores, not merely their presence. Each is checked separately and named in the
        # refusal: an operator who is told only "editorial gate" has to re-run to find out
        # which number, and the run that produced it cost a billed model call.
        if self.editorial.hook_score < MIN_HOOK_SCORE:
            raise EditorialBelowThreshold(
                f"clip {self.clip_id!r} scored hook {self.editorial.hook_score:.2f}, below the "
                f"{MIN_HOOK_SCORE:.2f} floor. §3 Stage 4 judged this clip and said it does not "
                f"open well enough to ship; rendering it spends an encode to publish something "
                f"the judge already rejected."
            )
        if self.editorial.misleading_edit_risk > MAX_MISLEADING_EDIT_RISK:
            raise EditorialBelowThreshold(
                f"clip {self.clip_id!r} scored misleading-edit risk "
                f"{self.editorial.misleading_edit_risk:.2f}, over the "
                f"{MAX_MISLEADING_EDIT_RISK:.2f} ceiling. §8.2 calls this the metric that "
                f"matters for a media organisation — an edit that changes what someone is "
                f"understood to have said is the one failure no amount of polish redeems."
            )
        if not self.editorial.self_contained:
            raise EditorialBelowThreshold(
                f"clip {self.clip_id!r} was judged not self-contained: it needs the rest of the "
                f"episode to make sense, which a viewer scrolling past it does not have."
            )
        if self.editorial.meaning_fidelity < MIN_MEANING_FIDELITY:
            raise EditorialBelowThreshold(
                f"clip {self.clip_id!r} scored meaning fidelity "
                f"{self.editorial.meaning_fidelity:.2f}, below the "
                f"{MIN_MEANING_FIDELITY:.2f} floor. §8.2 calls meaning preservation "
                f"the invariant an edit must not break."
            )
        if self.editorial.cultural_landing < MIN_CULTURAL_LANDING:
            raise EditorialBelowThreshold(
                f"clip {self.clip_id!r} scored cultural landing "
                f"{self.editorial.cultural_landing:.2f}, below the "
                f"{MIN_CULTURAL_LANDING:.2f} floor. §8.2 requires content to resonate "
                f"with Kurdish cultural sensibilities."
            )
        if self.output is None:
            raise ValueError(
                f"clip {self.clip_id!r} has no output block — no title, crop target or "
                f"caption style to render with."
            )
        if self.provenance is None:
            raise ValueError(
                f"clip {self.clip_id!r} carries no provenance block. §7.6 requires every "
                "shipped clip to name renderer git SHA, revisions digest, judge prompt hash, "
                "thresholds, crop constants, and ffmpeg buildconf that shaped it."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "clip_id": self.clip_id,
            "media_id": self.media_id,
            "media_sha256": self.media_sha256,
            "in_ms": self.in_ms,
            "out_ms": self.out_ms,
            "discovery_path": self.discovery_path.value,
            "boundary": self.boundary.to_dict(),
            "transcript": self.transcript.to_dict(),
            "speaker": self.speaker,
            "editorial": self.editorial.to_dict() if self.editorial else None,
            "output": self.output.to_dict() if self.output else None,
            "qc": self.qc.to_dict() if self.qc else None,
            "provenance": self.provenance.to_dict() if self.provenance else None,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Clip:
        fields = _json_object_fields(
            data,
            field="clip",
            required=frozenset(
                {
                    "clip_id",
                    "media_id",
                    "in_ms",
                    "out_ms",
                    "discovery_path",
                    "boundary",
                    "transcript",
                }
            ),
            optional=frozenset(
                {"media_sha256", "speaker", "editorial", "output", "qc", "provenance"}
            ),
        )

        def object_value(name: str, value: object) -> dict[str, Any]:
            if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
                raise ValueError(f"clip.{name} must be a JSON object with string keys")
            return value

        boundary = object_value("boundary", fields["boundary"])
        transcript = object_value("transcript", fields["transcript"])

        def optional_object(name: str) -> dict[str, Any] | None:
            value = fields.get(name)
            if value is None:
                return None
            return object_value(name, value)

        editorial = optional_object("editorial")
        output = optional_object("output")
        qc = optional_object("qc")
        prov = optional_object("provenance")
        return Clip(
            clip_id=_strict_json_string(fields["clip_id"], "clip.clip_id"),
            media_id=_strict_json_string(fields["media_id"], "clip.media_id"),
            media_sha256=fields.get("media_sha256"),
            in_ms=_strict_json_int(fields["in_ms"], "clip.in_ms", minimum=0),
            out_ms=_strict_json_int(fields["out_ms"], "clip.out_ms", minimum=0),
            discovery_path=DiscoveryPath(
                _strict_json_string(fields["discovery_path"], "clip.discovery_path")
            ),
            boundary=Boundary.from_dict(boundary),
            transcript=ClipTranscript.from_dict(transcript),
            speaker=_strict_optional_json_string(fields.get("speaker"), "clip.speaker"),
            editorial=Editorial.from_dict(editorial) if editorial is not None else None,
            output=Output.from_dict(output) if output is not None else None,
            qc=Qc.from_dict(qc) if qc is not None else None,
            provenance=Provenance.from_dict(prov) if prov is not None else None,
        )
