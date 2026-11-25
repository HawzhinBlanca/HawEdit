"""§3 Stage 4 — the final editorial judge. The contract around someone else's model.

    KURDISH_EDITORIAL_JUDGE = gemini-2.5-pro     # pinned, today
    SHADOW                  = gemini-3.1-pro     # evaluated, not routed
    …
    All routing goes through the `KURDISH_EDITORIAL_JUDGE` interface. Swapping providers
    must be a config change, never a refactor.

Stage 4 is entirely a hosted model, so nothing here calls it — that needs credentials and the
governance decision in §3 Stage 3's warning box (`BLOCKED.md` #3). What is buildable is the
contract, and §3 puts most of its warnings there rather than in the call.

**"Evaluated, not routed."** `route()` refuses `gemini-3.1-pro`, and `ShadowVerdict` is a
distinct type from `JudgeVerdict` so a shadow result cannot reach §5's editorial block through
a loosely annotated function. A shadow that can score a shipped clip is an incumbent nobody
chose.

**"Empirical beats newer."** §3 pins 2.5 Pro on tested evidence for Hawa's Sorani and none for
3.1 Pro. `decide_judge` promotes only on a clear win over a regression set of real size —
never on a tie, never on an empty set, and it deliberately takes no date argument, because §3
says the October 2026 Vertex date is "a managed migration with a shadow test, not a deadline".

**The 200K ceiling is arithmetic, not advice.** §3's own with-video figure is ~360K tokens per
source hour against a "keep each request under 200K" ceiling, so the most expensive mode is
also the one that cannot be a single request. §3 prescribes the fix — 20 × 60 s segments — and
`assert_within_tier` makes skipping it loud. A request whose size is unknown is refused too:
"unmeasured is None", and None is not "small enough".

**"Don't pay the judge twice."** A survivor Path A already scored arrives with its verbal
judgment attached (§3 Stage 3). `JudgeRequest.for_survivor` carries it forward and refuses to
re-run discovery on it. That failure mode is a bill rather than an error, which is precisely
why nothing else would catch it.

**One discrepancy inside the blueprint, recorded rather than resolved.** §3 Stage 4 lists
*payoff location* and *hashtags* among the judge's outputs; §5's frozen JSON contract has no
cell for either. §5 is frozen and is not edited here. `JudgeVerdict` carries both, and
`to_editorial()` drops them explicitly — the loss is in one place with a name on it, instead
of being a field nobody noticed was missing. See D-030.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, Final, Protocol, runtime_checkable

from hawedit.boundary import json_object_fields, strict_bool
from hawedit.clip import Editorial, Output, Sv6d, sv6d_from_json
from hawedit.discovery import MergedCandidate
from hawedit.normalize import normalize_sorani
from hawedit.registry import ModelEntry, resolve_role
from hawedit.repurposing import pairwise_preference

__all__ = [
    "CANDIDATE_SLICE_TOKENS_PER_HOUR",
    "DEFAULT_PAIRWISE_ROUNDS",
    "FULL_TRANSCRIPT_TOKENS_PER_HOUR",
    "HOOK_TYPES",
    "JUDGE_ROLES",
    "KURDISH_EDITORIAL_JUDGE",
    "MAX_JUDGE_FRAME_BYTES",
    "MAX_PAIRWISE_CANDIDATES",
    "MAX_PERSISTED_VERDICT_BYTES",
    "MIN_REGRESSION_ITEMS",
    "NARRATIVE_ROLES",
    "PAIRWISE_SCHEMA",
    "PRO_TIER_TOKEN_CEILING",
    "USD_PER_MILLION_TOKENS",
    "VIDEO_TOKENS_PER_SECOND",
    "WITH_VIDEO_TOKENS_PER_HOUR",
    "BilledCall",
    "EditorialJudge",
    "GeminiPairwiseJudge",
    "InputMode",
    "JudgeDecision",
    "JudgeFrame",
    "JudgeRequest",
    "JudgeVerdict",
    "NotRoutable",
    "PairwiseComparator",
    "PairwiseMatch",
    "RequestTooLarge",
    "ShadowVerdict",
    "StructuredJsonClient",
    "assert_model_agreement_cannot_bypass_human_qc",
    "compute_repeat_k_agreement",
    "decide_judge",
    "estimate_cost_usd",
    "is_verdict_eligible",
    "pairwise_rank_verdicts",
    "route",
    "tournament_rank_verdicts",
    "video_tokens",
]

# §3 Stage 4's pinned judge (upgraded per D-339 from deprecated gemini-2.5-pro). Named here
# so a caller states the incumbent rather than hard-coding a string, and so the
# shadow-promotion rule has something to compare against.
KURDISH_EDITORIAL_JUDGE: Final = "gemini-4-carbon"
JUDGE_SHADOW: Final = "gemini-4-argon"
JUDGE_ROLES: Final = frozenset({"kurdish_editorial_judge", "judge_shadow"})
MAX_JUDGE_FRAME_BYTES: Final = 5 * 1024 * 1024
# The live provider response is capped at the same one-mebibyte boundary in `gemini.py`.
# A persisted stand-in is the same schema and earns no larger parser/memory budget.
MAX_PERSISTED_VERDICT_BYTES: Final = 1 << 20

# §3 Stage 4's input-mode table, verbatim.
FULL_TRANSCRIPT_TOKENS_PER_HOUR: Final = 20_000  # Path A discovery
CANDIDATE_SLICE_TOKENS_PER_HOUR: Final = 20_000  # Stage 4, transcript-first
WITH_VIDEO_TOKENS_PER_HOUR: Final = 360_000  # Stage 4, with video — above the ceiling

# "Keep each request under 200K tokens to stay on the lower Pro price tier."
PRO_TIER_TOKEN_CEILING: Final = 200_000

# "Video bills at ~300 tokens/sec at default media resolution, ~100 at low."
VIDEO_TOKENS_PER_SECOND: Final = {"default": 300, "low": 100}

# Back-solved from §3's own table — 20K tokens costs ~$0.04, 360K costs ~$0.72 — rather than
# from a published price list, so the two cannot drift apart. §3's figures are what this
# project's cost claims are accountable to.
USD_PER_MILLION_TOKENS: Final = 2.0

# A promotion decided on a handful of items is noise wearing a decision's clothes. §3 asks for
# tested evidence on Hawa's Sorani; the floor is a judgment recorded in D-030, not a blueprint
# figure, and it is a parameter so §8.2 can raise it against real data.
MIN_REGRESSION_ITEMS: Final = 20


NARRATIVE_ROLES: Final = frozenset({"setup", "escalation", "payoff", "aside"})
HOOK_TYPES: Final = frozenset({"question", "claim", "contrast", "story_open", "confession"})

_VERDICT_REQUIRED_FIELDS: Final = frozenset(
    {
        "candidate_id",
        "hook_score",
        "self_contained",
        "payoff_at_ms",
        "meaning_fidelity",
        "misleading_edit_risk",
        "cultural_landing",
        "narrative_role",
        "title_ckb",
        "description_ckb",
        "hashtags_ckb",
        "judge",
        "clip_in_ms",
        "clip_out_ms",
    }
)


def _reject_duplicate_verdict_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    decoded: dict[str, Any] = {}
    for key, value in pairs:
        if key in decoded:
            raise ValueError(f"duplicate JSON key {key!r} in persisted verdict")
        decoded[key] = value
    return decoded


def _reject_verdict_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON numeric constant {value!r} in persisted verdict")


class NotRoutable(ValueError):
    """Raised when a model §7 keeps out of the path is asked to score client output."""


class RequestTooLarge(ValueError):
    """Raised when a request would leave the lower Pro price tier, or cannot be shown not to."""


def _is_kurdish(text: str) -> bool:
    """Does this text contain Arabic-script letters at all?

    Deliberately weak — it asks "is this plausibly Kurdish", not "is this good Kurdish". The
    failure it exists to catch is total: a judge answering in English produces a clip that
    renders, uploads and reads as finished work in the wrong language, and every type
    downstream accepts a `str`.
    """
    return any("؀" <= character <= "ۿ" for character in text)


def _kurdish_field(value: str, field: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field} is empty — §3 Stage 4 lists it among the judge's outputs")
    # §4.1 governs text this system *produces* as well as text it receives: an unnormalized
    # title makes the clip unfindable by its own name in the §2 index (Kurdish invariant #3's
    # reasoning, one step downstream).
    normalized = normalize_sorani(stripped)
    # Checked on the NORMALIZED text, not the raw. The check used to run first, and §4.1
    # normalization can remove the very characters that satisfied it: `٠١٢` is Arabic-Indic,
    # so it is inside the block `_is_kurdish` tests, and `unify_numeral` rewrites it to `012`.
    # Measured — `_kurdish_field('٠١٢', 'title_ckb')` returned `'012'`, a title with no Kurdish
    # script at all, past a guard whose whole purpose is to refuse exactly that. Checking after
    # is strictly stronger than checking before, because normalization never *adds* Kurdish
    # script, so anything the late check accepts the early one would have too. D-076.
    if not _is_kurdish(normalized):
        raise ValueError(
            f"{field} {stripped!r} contains no Kurdish script"
            + (f" once §4.1-normalized to {normalized!r}" if normalized != stripped else "")
            + ". The judge answered in another language and every type downstream would accept "
            "it as finished work."
        )
    return normalized


@dataclass(frozen=True, slots=True)
class JudgeVerdict:
    """Everything §3 Stage 4 says the judge outputs, for one candidate.

        hook strength · self-containment · payoff location · meaning fidelity ·
        misleading-edit risk · cultural landing · Kurdish title, description, hashtags

    Two of those — payoff location and hashtags — have no cell in §5's frozen contract. They
    live here and are dropped by `to_editorial()`, explicitly (D-030).
    """

    candidate_id: str
    hook_score: float
    self_contained: bool
    payoff_at_ms: int
    meaning_fidelity: float
    misleading_edit_risk: float
    cultural_landing: float
    narrative_role: str
    title_ckb: str
    description_ckb: str
    hashtags_ckb: tuple[str, ...]
    judge: str
    clip_in_ms: int
    clip_out_ms: int
    sv6d: Sv6d | None = None
    hook_type: str = "claim"
    payoff_strength: float = 0.5
    ends_on_a_beat: bool = True
    reason_ckb: str = "پەسەندکراوە لەسەر بنەمای بەهێزی دەربڕین."
    title_variants_ckb: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.self_contained, bool):
            raise ValueError(
                "self_contained must be a JSON boolean, got "
                f"{self.self_contained!r} ({type(self.self_contained).__name__})"
            )
        for field in (
            "candidate_id",
            "narrative_role",
            "title_ckb",
            "description_ckb",
            "judge",
        ):
            value = getattr(self, field)
            if not isinstance(value, str):
                raise ValueError(
                    f"{field} must be a JSON string, got {value!r} ({type(value).__name__})"
                )
        if not isinstance(self.hashtags_ckb, tuple) or not all(
            isinstance(tag, str) for tag in self.hashtags_ckb
        ):
            raise ValueError("hashtags_ckb must be a tuple of strings")
        if not isinstance(self.title_variants_ckb, tuple) or not all(
            isinstance(variant, str) for variant in self.title_variants_ckb
        ):
            raise ValueError("title_variants_ckb must be a tuple of strings")
        if self.sv6d is not None and not isinstance(self.sv6d, Sv6d):
            raise ValueError("sv6d must be an Sv6d value or None")

        for field in (
            "hook_score",
            "meaning_fidelity",
            "misleading_edit_risk",
            "cultural_landing",
        ):
            value = getattr(self, field)
            if (
                isinstance(value, bool)
                or not isinstance(value, int | float)
                or (isinstance(value, float) and not math.isfinite(value))
            ):
                raise ValueError(
                    f"{field} must be a finite JSON number, got {value!r} ({type(value).__name__})"
                )
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{field} must be within [0, 1], got {value}")

        for field in ("payoff_at_ms", "clip_in_ms", "clip_out_ms"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(
                    f"{field} must be a JSON integer, got {value!r} ({type(value).__name__})"
                )

        if not self.clip_in_ms <= self.payoff_at_ms <= self.clip_out_ms:
            raise ValueError(
                f"payoff_at_ms {self.payoff_at_ms} falls outside the clip "
                f"({self.clip_in_ms}..{self.clip_out_ms}). The judge scored a different span "
                f"than the one being cut, and shipping this would put the punchline past the "
                f"out point."
            )

        if self.narrative_role not in NARRATIVE_ROLES:
            raise ValueError(
                f"narrative_role {self.narrative_role!r} is not one of "
                f"{sorted(NARRATIVE_ROLES)}. The prompt asks for exactly these four, and §5's "
                f"contract carries the value to the client — an unconstrained string means the "
                f"field says whatever the model felt like saying."
            )

        object.__setattr__(self, "title_ckb", _kurdish_field(self.title_ckb, "title_ckb"))
        object.__setattr__(
            self, "description_ckb", _kurdish_field(self.description_ckb, "description_ckb")
        )
        object.__setattr__(
            self,
            "hashtags_ckb",
            tuple(_kurdish_field(tag, "hashtag") for tag in self.hashtags_ckb),
        )

        if self.hook_type not in HOOK_TYPES:
            raise ValueError(
                f"hook_type {self.hook_type!r} is not one of {sorted(HOOK_TYPES)}. "
                f"Blueprint §4 taxonomy requires one of the 5 canonical hook types."
            )
        if not isinstance(self.ends_on_a_beat, bool):
            raise ValueError("ends_on_a_beat must be a JSON boolean")
        if (
            isinstance(self.payoff_strength, bool)
            or not isinstance(self.payoff_strength, int | float)
            or not 0.0 <= self.payoff_strength <= 1.0
        ):
            raise ValueError(
                f"payoff_strength must be a JSON number within [0, 1], got {self.payoff_strength}"
            )
        object.__setattr__(self, "reason_ckb", _kurdish_field(self.reason_ckb, "reason_ckb"))

        # Role-checked, not routability-checked. The shadow is *evaluated*, so its verdicts
        # have to exist — refusing to construct one would make the shadow test impossible and
        # leave "switch only when 3.1 Pro beats 2.5 Pro" unenforceable for want of a 3.1 Pro
        # result to compare. Routability is a question about shipping, and it is asked at the
        # two places shipping happens: `route()` and `to_editorial()`.
        resolve_role(self.judge, JUDGE_ROLES, "the editorial judge")

    def to_editorial(self) -> Editorial:
        """Project onto §5's frozen `editorial` block.

        No longer lossy. D-030 recorded that §5 had no cell for `payoff_at_ms` or
        `hashtags_ckb` while §3 Stage 4 lists both among the judge's outputs, and left the
        question open. D-033 answers it: both are carried, as *optional* fields, so every §5
        document written before now still deserializes. `payoff_at_ms` lands in `editorial`
        because it is a judgment; `hashtags_ckb` lands in `output` beside the title and
        description because it is a delivery artifact.

        Raises:
            NotRoutable: a shadow model produced this verdict. This is the boundary where
                "evaluated, not routed" is enforced — the point where an opinion becomes part
                of a clip. `Editorial` refuses it a second time, because a verdict can also
                arrive there as deserialized JSON that never passed through here.
        """
        entry = resolve_role(self.judge, JUDGE_ROLES, "the editorial judge")
        if not entry.routable:
            raise NotRoutable(
                f"{self.judge!r} is marked 'evaluated, not routed' in §3 Stage 4, so its "
                f"verdict cannot become a clip's editorial block. Keep it as a ShadowVerdict "
                f"and compare it with decide_judge()."
            )
        return Editorial(
            hook_score=self.hook_score,
            self_contained=self.self_contained,
            meaning_fidelity=self.meaning_fidelity,
            misleading_edit_risk=self.misleading_edit_risk,
            cultural_landing=self.cultural_landing,
            narrative_role=self.narrative_role,
            judge=self.judge,
            sv6d=self.sv6d,
            payoff_at_ms=self.payoff_at_ms,
            hook_type=self.hook_type,
            payoff_strength=self.payoff_strength,
            ends_on_a_beat=self.ends_on_a_beat,
            reason_ckb=self.reason_ckb,
        )

    def to_output(
        self,
        crop_target: str,
        durations: tuple[int, ...],
        caption_style: str = "word_highlight",
    ) -> Output:
        """Fill §5's `output` block with the judge's Kurdish title and description.

        `crop_target` and `durations` are not the judge's to decide — they are delivery
        settings — so they are the caller's arguments rather than invented here.
        """
        return Output(
            title_ckb=self.title_ckb,
            description_ckb=self.description_ckb,
            crop_target=crop_target,
            caption_style=caption_style,
            durations=durations,
            hashtags_ckb=self.hashtags_ckb,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "hook_score": self.hook_score,
            "self_contained": self.self_contained,
            "payoff_at_ms": self.payoff_at_ms,
            "meaning_fidelity": self.meaning_fidelity,
            "misleading_edit_risk": self.misleading_edit_risk,
            "cultural_landing": self.cultural_landing,
            "narrative_role": self.narrative_role,
            "title_ckb": self.title_ckb,
            "description_ckb": self.description_ckb,
            "hashtags_ckb": list(self.hashtags_ckb),
            "judge": self.judge,
            "clip_in_ms": self.clip_in_ms,
            "clip_out_ms": self.clip_out_ms,
            "sv6d": self.sv6d.to_dict() if self.sv6d else None,
            "hook_type": self.hook_type,
            "payoff_strength": self.payoff_strength,
            "ends_on_a_beat": self.ends_on_a_beat,
            "reason_ckb": self.reason_ckb,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> JudgeVerdict:
        fields = json_object_fields(
            data,
            field="persisted verdict",
            required=_VERDICT_REQUIRED_FIELDS,
            optional=frozenset(
                {"sv6d", "hook_type", "payoff_strength", "ends_on_a_beat", "reason_ckb"}
            ),
        )
        raw_hashtags = fields["hashtags_ckb"]
        if not isinstance(raw_hashtags, list) or not all(
            isinstance(tag, str) for tag in raw_hashtags
        ):
            raise ValueError(
                "hashtags_ckb must be a JSON array of strings; a scalar string would be "
                "split into one hashtag per character"
            )
        return JudgeVerdict(
            candidate_id=fields["candidate_id"],
            hook_score=fields["hook_score"],
            self_contained=strict_bool(fields["self_contained"], "self_contained"),
            payoff_at_ms=fields["payoff_at_ms"],
            meaning_fidelity=fields["meaning_fidelity"],
            misleading_edit_risk=fields["misleading_edit_risk"],
            cultural_landing=fields["cultural_landing"],
            narrative_role=fields["narrative_role"],
            title_ckb=fields["title_ckb"],
            description_ckb=fields["description_ckb"],
            hashtags_ckb=tuple(raw_hashtags),
            judge=fields["judge"],
            clip_in_ms=fields["clip_in_ms"],
            clip_out_ms=fields["clip_out_ms"],
            sv6d=sv6d_from_json(fields.get("sv6d"), "persisted verdict.sv6d"),
            hook_type=str(fields.get("hook_type", "claim")),
            payoff_strength=float(fields.get("payoff_strength", 0.5)),
            ends_on_a_beat=strict_bool(fields.get("ends_on_a_beat", True), "ends_on_a_beat"),
            reason_ckb=str(fields.get("reason_ckb", "پەسەندکراوە لەسەر بنەمای بەهێزی دەربڕین.")),
        )

    @staticmethod
    def from_json(payload: str) -> JudgeVerdict:
        """Decode one unambiguous persisted verdict instead of Python's permissive JSON."""
        if not isinstance(payload, str):
            raise ValueError("persisted verdict payload must be text")
        try:
            decoded: object = json.loads(
                payload,
                object_pairs_hook=_reject_duplicate_verdict_keys,
                parse_constant=_reject_verdict_constant,
            )
        except json.JSONDecodeError as exc:
            raise ValueError(f"persisted verdict is not valid JSON: {exc.msg}") from exc
        except RecursionError as exc:
            raise ValueError("persisted verdict exceeds the JSON nesting limit") from exc
        if not isinstance(decoded, dict):
            raise ValueError("persisted verdict must be a JSON object")
        return JudgeVerdict.from_dict(decoded)


@dataclass(frozen=True, slots=True)
class ShadowVerdict:
    """A shadow model's opinion, kept for comparison and structurally unable to ship.

    A separate type rather than a flag on `JudgeVerdict`: a flag is checked where someone
    remembered to check it, whereas a type that `to_editorial()` does not exist on cannot
    reach §5's editorial block at all.
    """

    verdict: JudgeVerdict
    incumbent: str = KURDISH_EDITORIAL_JUDGE

    def __post_init__(self) -> None:
        if self.verdict.judge == self.incumbent:
            raise ValueError(
                f"a shadow run recorded {self.incumbent!r} as its judge, which is the "
                f"incumbent. Comparing a model against itself always ties and would read as "
                f"'the shadow did not win' forever."
            )

    def to_dict(self) -> dict[str, Any]:
        """Added for `promotion.py`'s shadow-verdict ledger (D-A14) — a shadow opinion nobody
        can read back is a shadow opinion `decide_judge`'s tally cannot be reconstructed from."""
        return {"verdict": self.verdict.to_dict(), "incumbent": self.incumbent}

    @staticmethod
    def from_dict(data: dict[str, Any]) -> ShadowVerdict:
        return ShadowVerdict(
            verdict=JudgeVerdict.from_dict(data["verdict"]), incumbent=str(data["incumbent"])
        )


class _RoutableModel(Protocol):
    model_id: str


@runtime_checkable
class EditorialJudge(Protocol):
    """§3 Stage 4's routing interface. Two members, so a swap is a config change."""

    model_id: str

    def judge(self, request: JudgeRequest) -> JudgeVerdict: ...


def route(judge: _RoutableModel) -> ModelEntry:
    """Resolve a judge against §7, refusing anything the blueprint keeps out of the path.

    Raises:
        ModelNotInRegistry / ModelExcluded: the model is not §7-permitted.
        WrongRole: it is in §7 but is not a judge (audit finding #8).
        NotRoutable: it is the shadow — "evaluated, not routed".
    """
    entry = resolve_role(judge.model_id, JUDGE_ROLES, "the editorial judge")
    if not entry.routable:
        raise NotRoutable(
            f"{judge.model_id!r} is marked 'evaluated, not routed' in §3 Stage 4. §3 pins "
            f"{KURDISH_EDITORIAL_JUDGE} on tested evidence for Sorani and has none for this "
            f"model — switch only when it beats the incumbent on the regression set."
        )
    return entry


class InputMode(Enum):
    """§3 Stage 4's three payload shapes, with the cost each implies."""

    PATH_A_DISCOVERY = "path_a_discovery"
    STAGE_4_TRANSCRIPT_FIRST = "stage_4_transcript_first"
    STAGE_4_WITH_VIDEO = "stage_4_with_video"


@dataclass(frozen=True, slots=True)
class JudgeFrame:
    """One source-timestamped image sent to the multimodal editorial judge."""

    timestamp_ms: int
    mime_type: str
    data: bytes

    def __post_init__(self) -> None:
        if self.timestamp_ms < 0:
            raise ValueError("judge keyframe timestamp must be non-negative")
        if self.mime_type not in {"image/jpeg", "image/png"}:
            raise ValueError(f"unsupported judge keyframe MIME type {self.mime_type!r}")
        if not isinstance(self.data, bytes) or not self.data:
            raise ValueError("judge keyframe data must be non-empty bytes")
        if len(self.data) > MAX_JUDGE_FRAME_BYTES:
            raise ValueError("one judge keyframe exceeds the 5 MiB inline-data ceiling")


def video_tokens(seconds: float, resolution: str = "default") -> int:
    """§3: "~300 tokens/sec at default media resolution, ~100 at low."."""
    if resolution not in VIDEO_TOKENS_PER_SECOND:
        raise ValueError(f"unknown resolution {resolution!r}; §3 names 'default' and 'low'")
    return round(seconds * VIDEO_TOKENS_PER_SECOND[resolution])


def estimate_cost_usd(tokens: int, batched: bool = False, cached: bool = False) -> float:
    """What a request of this size costs, from §3's own table.

    §3: "Batch API takes 50% off; cached input reads at 10% of base." An estimate, and named
    as one — the authority on the bill is the bill.
    """
    cost = tokens / 1_000_000 * USD_PER_MILLION_TOKENS
    if cached:
        cost *= 0.1
    if batched:
        cost *= 0.5
    return cost


@dataclass(frozen=True, slots=True)
class BilledCall:
    """Record of a foundation-model call that incurs billing.

    Every billed call carries:
    - model: the provider model identifier (e.g. "gemini-4-carbon")
    - tokens: provider-counted input tokens
    - cost_usd_estimate: calculated from USD_PER_MILLION_TOKENS
    - stage: the pipeline stage making the call ("discovery", "editorial", etc.)
    - candidate_id: the candidate or slice id being evaluated (optional)
    """

    model: str
    tokens: int
    cost_usd_estimate: float
    stage: str
    candidate_id: str | None = None

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("BilledCall.model cannot be empty")
        if self.tokens < 0:
            raise ValueError(f"BilledCall.tokens must be non-negative, got {self.tokens}")
        if self.cost_usd_estimate < 0.0:
            raise ValueError(
                f"BilledCall.cost_usd_estimate cannot be negative, got {self.cost_usd_estimate}"
            )
        if not self.stage.strip():
            raise ValueError("BilledCall.stage cannot be empty")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "model": self.model,
            "tokens": self.tokens,
            "cost_usd_estimate": round(self.cost_usd_estimate, 6),
            "stage": self.stage,
        }
        if self.candidate_id is not None:
            result["candidate_id"] = self.candidate_id
        return result


@dataclass(frozen=True, slots=True)
class JudgeRequest:
    """One call to the judge: what is being sent, how big it is, and what it already knows."""

    candidate_id: str
    mode: InputMode
    # `None` means nobody counted. It is not zero and it is not "probably fine" — see
    # assert_within_tier.
    tokens: int | None = None
    carried_verbal_score: float | None = None
    # Stage 4 is not a second text-only Path A pass. Path B's timestamped SV6D evidence is
    # carried into the final judgment so a reaction/gesture/visual beat is not reduced to the
    # transcript that could not see it. This is the evidence the local visual reader produced.
    visual_context: tuple[str, ...] = ()
    # Actual source pixels. Textual SV6D does not make a multimodal request by itself.
    keyframes: tuple[JudgeFrame, ...] = ()
    # What the judge actually reads. Normalized Sorani (Kurdish invariant #3) — the judge is a
    # model input, so it reads transcript.norm.json and never the raw artifact.
    text_ckb: str = ""
    clip_in_ms: int = 0
    clip_out_ms: int = 0

    def __post_init__(self) -> None:
        if len(self.keyframes) > 20:
            raise ValueError(f"Stage 4 accepts at most 20 keyframes, got {len(self.keyframes)}")
        outside = [
            frame.timestamp_ms
            for frame in self.keyframes
            if not self.clip_in_ms <= frame.timestamp_ms <= self.clip_out_ms
        ]
        if outside:
            raise ValueError(
                f"judge keyframes {outside!r} fall outside candidate "
                f"{self.clip_in_ms}..{self.clip_out_ms}ms"
            )

    def assert_within_tier(self) -> None:
        """Refuse a request that would leave the lower Pro price tier (§3 Stage 4).

        Raises:
            RequestTooLarge: the request exceeds the ceiling, or its size is unknown.
        """
        if self.tokens is None:
            raise RequestTooLarge(
                f"request for {self.candidate_id!r} has an unknown token count, so it cannot "
                f"be shown to stay under {PRO_TIER_TOKEN_CEILING:,}. Count it — an uncounted "
                f"request is not a small one."
            )
        if self.tokens >= PRO_TIER_TOKEN_CEILING:
            raise RequestTooLarge(
                f"request for {self.candidate_id!r} is {self.tokens:,} tokens, at or over §3 "
                f"Stage 4's {PRO_TIER_TOKEN_CEILING:,} ceiling for the lower Pro price tier. "
                f"§3 already prescribes the fix for the with-video mode: 20 × 60 s segments, "
                f"not one call per source hour."
            )

    @property
    def estimated_cost_usd(self) -> float | None:
        return None if self.tokens is None else estimate_cost_usd(self.tokens)

    @staticmethod
    def for_survivor(
        candidate: MergedCandidate,
        tokens: int | None = None,
        mode: InputMode = InputMode.STAGE_4_TRANSCRIPT_FIRST,
        text_ckb: str = "",
        keyframes: tuple[JudgeFrame, ...] = (),
    ) -> JudgeRequest:
        """Build a Stage 4 request for a candidate that survived Stage 3's union.

        §3 Stage 3: "Path A already scores its candidates. Stage 4 should add *visual* context
        to survivors, not re-derive verbal judgment. Don't pay the judge twice for the same
        reasoning." So the verbal score travels with the request, and asking for Path A
        discovery on a candidate that already has one is refused — that mistake produces a
        larger bill and a correct-looking result, which is why nothing else would catch it.

        Raises:
            ValueError: `mode` re-runs discovery on an already-scored candidate.
        """
        if mode is InputMode.PATH_A_DISCOVERY and candidate.verbal_score is not None:
            raise ValueError(
                f"candidate {candidate.candidate_id!r} was already scored by Path A "
                f"({candidate.verbal_score}). Re-running discovery pays the judge twice for "
                f"the same reasoning (§3 Stage 3) — use a Stage 4 mode, which adds visual "
                f"context to what Path A already concluded."
            )
        return JudgeRequest(
            candidate_id=candidate.candidate_id,
            mode=mode,
            tokens=tokens,
            carried_verbal_score=candidate.verbal_score,
            visual_context=(
                tuple(
                    f"{dimension}: {getattr(candidate.sv6d, dimension)}"
                    for dimension in candidate.sv6d.DIMENSIONS
                )
                if candidate.sv6d is not None
                else ()
            ),
            keyframes=keyframes,
            text_ckb=text_ckb,
            clip_in_ms=candidate.in_ms,
            clip_out_ms=candidate.out_ms,
        )


@dataclass(frozen=True, slots=True)
class JudgeDecision:
    """What the shadow test concluded, and why. As in §8.1, the reasons are the point."""

    incumbent: str
    challenger: str | None
    switch: bool
    reasons: tuple[str, ...]


def decide_judge(
    incumbent_wins: int,
    shadow_wins: int,
    ties: int = 0,
    incumbent: str = KURDISH_EDITORIAL_JUDGE,
    shadow: str = JUDGE_SHADOW,
    min_items: int = MIN_REGRESSION_ITEMS,
) -> JudgeDecision:
    """§3 Stage 4's switch rule: promote the shadow only if it beats the incumbent.

    Takes no date. §3 is explicit that the October 2026 deprecation applies to Vertex AI
    rather than the Developer API, and that this is "a managed migration with a shadow test,
    not a deadline" — a signature with a date in it would encode the reading §3 rejects.

    "Empirical beats newer" resolves to three refusals: an empty regression set decides
    nothing, a tie is not beating, and a win on a handful of items is noise.
    """
    total = incumbent_wins + shadow_wins + ties
    reasons: list[str] = [
        f"regression set: {total} items — {incumbent} {incumbent_wins}, "
        f"{shadow} {shadow_wins}, ties {ties}"
    ]

    if total == 0:
        reasons.append(
            f"no regression set was run. §3 pins {incumbent} because there is tested evidence "
            f"for it on Hawa's Sorani and none for {shadow}; promoting on nothing is the "
            f"'newer is better' reasoning §3 exists to prevent."
        )
        return JudgeDecision(incumbent, None, False, tuple(reasons))

    if total < min_items:
        reasons.append(
            f"{total} items is below the {min_items}-item floor. A win this size is noise, and "
            f"§3 asks for evidence on your Sorani, not for a coin flip that landed twice."
        )
        return JudgeDecision(incumbent, shadow, False, tuple(reasons))

    if shadow_wins <= incumbent_wins:
        verdict = "tied with" if shadow_wins == incumbent_wins else "lost to"
        reasons.append(
            f"{shadow} {verdict} the incumbent and so did not beat it. §3: switch only when "
            f"{shadow} beats {incumbent} on your Sorani regression set."
        )
        return JudgeDecision(incumbent, shadow, False, tuple(reasons))

    reasons.append(
        f"{shadow} beat {incumbent} on {total} items. §3 treats this as a managed migration: "
        f"switching is a config change to KURDISH_EDITORIAL_JUDGE, and §7's routable flag "
        f"moves with it."
    )
    return JudgeDecision(incumbent, shadow, True, tuple(reasons))


MAX_PAIRWISE_CANDIDATES: Final = 12
DEFAULT_PAIRWISE_ROUNDS: Final = 3
_MIN_PAIRWISE_ROUNDS: Final = 2
_HOOK_PRIORITY: Final[dict[str, int]] = {
    "question": 5,
    "claim": 4,
    "contrast": 3,
    "confession": 2,
    "story_open": 1,
}

PAIRWISE_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "winner": {"type": "string", "enum": ["A", "B", "TIE"]},
        "reason_ckb": {"type": "string"},
    },
    "required": ["winner", "reason_ckb"],
}

_PAIRWISE_PROMPT: Final = (
    "Compare Candidate A and Candidate B as short-form Sorani Kurdish clips.\n"
    "Which candidate would a Kurdish viewer keep watching through its payoff?\n"
    "Reward a compelling opening backed by clear meaning fidelity and complete resolution; "
    "reject clickbait or misleading edits.\n"
    "Return JSON only matching the schema with winner ('A', 'B', or 'TIE') and a concise "
    "Sorani Kurdish explanation in reason_ckb.\n\n"
    "Candidate A ({id_a}) | hook={hook_a} | role={role_a}\n"
    "Title: {title_a}\n"
    "Transcript/Context:\n{text_a}\n\n"
    "Candidate B ({id_b}) | hook={hook_b} | role={role_b}\n"
    "Title: {title_b}\n"
    "Transcript/Context:\n{text_b}\n"
)


@dataclass(frozen=True, slots=True)
class PairwiseMatch:
    """One head-to-head comparison outcome between two eligible candidates."""

    candidate_a: str
    candidate_b: str
    winner: str | None
    reason_ckb: str
    billed_call: BilledCall | None = None

    def __post_init__(self) -> None:
        if self.winner is not None and self.winner not in (self.candidate_a, self.candidate_b):
            raise ValueError(
                f"pairwise winner {self.winner!r} must be {self.candidate_a!r}, "
                f"{self.candidate_b!r}, or None for tie"
            )
        object.__setattr__(self, "reason_ckb", _kurdish_field(self.reason_ckb, "reason_ckb"))


@runtime_checkable
class StructuredJsonClient(Protocol):
    """Minimal JSON-generation client interface satisfied by GeminiJudge/VertexGeminiJudge."""

    model_id: str

    def count_parts(self, parts: list[dict[str, Any]]) -> int: ...

    def generate_json(self, parts: list[dict[str, Any]], schema: Mapping[str, Any]) -> str: ...


@runtime_checkable
class PairwiseComparator(Protocol):
    """Head-to-head comparison interface for editorial candidate ranking."""

    def compare(
        self,
        verdict_a: JudgeVerdict,
        verdict_b: JudgeVerdict,
        *,
        text_a_ckb: str = "",
        text_b_ckb: str = "",
    ) -> PairwiseMatch: ...


class GeminiPairwiseJudge:
    """Pairwise editorial comparator backed by §3 Stage 4's routed Gemini client."""

    def __init__(self, client: StructuredJsonClient, *, model_id: str | None = None) -> None:
        self._client = client
        self.model_id = model_id or client.model_id

    def compare(
        self,
        verdict_a: JudgeVerdict,
        verdict_b: JudgeVerdict,
        *,
        text_a_ckb: str = "",
        text_b_ckb: str = "",
    ) -> PairwiseMatch:
        from hawedit.gemini import JudgeUnusable, extract_response_text

        route(self)

        context_a = normalize_sorani(
            text_a_ckb.strip() or f"{verdict_a.title_ckb} — {verdict_a.description_ckb}"
        )
        context_b = normalize_sorani(
            text_b_ckb.strip() or f"{verdict_b.title_ckb} — {verdict_b.description_ckb}"
        )
        prompt = _PAIRWISE_PROMPT.format(
            id_a=verdict_a.candidate_id,
            hook_a=verdict_a.hook_type,
            role_a=verdict_a.narrative_role,
            title_a=verdict_a.title_ckb,
            text_a=context_a,
            id_b=verdict_b.candidate_id,
            hook_b=verdict_b.hook_type,
            role_b=verdict_b.narrative_role,
            title_b=verdict_b.title_ckb,
            text_b=context_b,
        )
        parts = [{"text": prompt}]
        tokens = self._client.count_parts(parts)
        if tokens >= PRO_TIER_TOKEN_CEILING:
            raise RequestTooLarge(
                f"pairwise comparison {verdict_a.candidate_id!r} vs {verdict_b.candidate_id!r} "
                f"is {tokens:,} tokens, at or over {PRO_TIER_TOKEN_CEILING:,}."
            )

        raw = self._client.generate_json(parts, PAIRWISE_SCHEMA)
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and "candidates" in parsed:
                parsed = json.loads(extract_response_text(raw))
            fields = json_object_fields(
                parsed,
                field="pairwise verdict",
                required=frozenset({"winner", "reason_ckb"}),
            )
            winner_token = fields["winner"]
            if not isinstance(winner_token, str) or winner_token not in {"A", "B", "TIE"}:
                raise ValueError(
                    f"pairwise winner must be 'A', 'B', or 'TIE', got {winner_token!r}"
                )
            raw_reason = fields["reason_ckb"]
            if not isinstance(raw_reason, str):
                raise ValueError("pairwise reason_ckb must be a string")
            reason_ckb = _kurdish_field(raw_reason, "reason_ckb")
        except (ValueError, json.JSONDecodeError, TypeError, KeyError, IndexError) as exc:
            raise JudgeUnusable(f"pairwise comparison returned unusable JSON: {exc}") from exc

        winner_id: str | None
        if winner_token == "A":
            winner_id = verdict_a.candidate_id
        elif winner_token == "B":
            winner_id = verdict_b.candidate_id
        else:
            winner_id = None

        return PairwiseMatch(
            candidate_a=verdict_a.candidate_id,
            candidate_b=verdict_b.candidate_id,
            winner=winner_id,
            reason_ckb=reason_ckb,
            billed_call=BilledCall(
                model=self.model_id,
                tokens=tokens,
                cost_usd_estimate=estimate_cost_usd(tokens),
                stage="editorial",
                candidate_id=f"{verdict_a.candidate_id}_vs_{verdict_b.candidate_id}",
            ),
        )


def is_verdict_eligible(verdict: JudgeVerdict) -> bool:
    """Enforce §2 hard eligibility floors before any candidate can compete or ship."""
    return (
        verdict.meaning_fidelity >= 0.70
        and verdict.misleading_edit_risk <= 0.10
        and verdict.self_contained
    )


def _unweighted_tiebreak(verdict: JudgeVerdict) -> tuple[float, float, float, float, bool, int]:
    """Deterministic unweighted preference tuple used only to cap >12 or break ties."""
    return (
        verdict.hook_score,
        verdict.meaning_fidelity,
        verdict.cultural_landing,
        float(getattr(verdict, "payoff_strength", 0.5)),
        bool(getattr(verdict, "ends_on_a_beat", False)),
        _HOOK_PRIORITY.get(getattr(verdict, "hook_type", ""), 0),
    )


def _pairwise_standings(
    candidate_ids: Sequence[str],
    matches: Sequence[PairwiseMatch],
) -> tuple[dict[str, float], dict[str, float]]:
    """Return `(win_rates, buchholz_sums)` using `hawedit.repurposing.pairwise_preference`."""
    if not matches:
        zeros = {cid: 0.0 for cid in candidate_ids}
        return zeros, dict(zeros)
    win_rates = dict(
        pairwise_preference([(m.candidate_a, m.candidate_b, m.winner) for m in matches])
    )
    opponents: dict[str, list[str]] = {cid: [] for cid in candidate_ids}
    for match in matches:
        if match.candidate_a in opponents:
            opponents[match.candidate_a].append(match.candidate_b)
        if match.candidate_b in opponents:
            opponents[match.candidate_b].append(match.candidate_a)
    for cid in candidate_ids:
        win_rates.setdefault(cid, 0.0)
    buchholz = {
        cid: sum(win_rates.get(opp, 0.0) for opp in opponents[cid]) for cid in candidate_ids
    }
    return win_rates, buchholz


def _pair_without_rematches(
    active_ids: Sequence[str],
    played_pairs: set[frozenset[str]],
) -> list[tuple[str, str]]:
    """Find a disjoint Swiss pairing avoiding already-played unordered pairs when possible."""

    def _search(remaining: list[str], allow_rematch: bool) -> list[tuple[str, str]] | None:
        if not remaining:
            return []
        first = remaining[0]
        rest = remaining[1:]
        for idx, opp in enumerate(rest):
            if not allow_rematch and frozenset({first, opp}) in played_pairs:
                continue
            sub = _search(rest[:idx] + rest[idx + 1 :], allow_rematch)
            if sub is not None:
                return [(first, opp), *sub]
        return None

    unseen = _search(list(active_ids), allow_rematch=False)
    if unseen is not None:
        return unseen
    fallback = _search(list(active_ids), allow_rematch=True)
    assert fallback is not None
    return fallback


def pairwise_rank_verdicts(
    verdicts: Sequence[JudgeVerdict],
    *,
    comparator: PairwiseComparator | None = None,
    candidate_texts: Mapping[str, str] | None = None,
    rounds: int = DEFAULT_PAIRWISE_ROUNDS,
    max_candidates: int = MAX_PAIRWISE_CANDIDATES,
    require_eligible: bool = True,
    matches_out: list[PairwiseMatch] | None = None,
) -> tuple[tuple[JudgeVerdict, float], ...]:
    """Rank eligible verdicts via a bounded Swiss pairwise tournament (no weighted sum).

    - Excludes ineligible verdicts before scheduling any bouts (`require_eligible=True`).
    - Caps pools larger than `max_candidates` (`<= 12`) deterministically before bouts.
    - Runs 0 comparator calls when `<= 1` eligible verdict remains.
    - Runs `2..3` Swiss rounds alternating A/B positions and breaking ties via Buchholz.
    """
    if not _MIN_PAIRWISE_ROUNDS <= rounds <= DEFAULT_PAIRWISE_ROUNDS:
        raise ValueError(f"rounds must be between 2 and 3, got {rounds}")
    if not 1 <= max_candidates <= MAX_PAIRWISE_CANDIDATES:
        raise ValueError(
            f"max_candidates must be between 1 and {MAX_PAIRWISE_CANDIDATES}, got {max_candidates}"
        )

    filtered = [v for v in verdicts if not require_eligible or is_verdict_eligible(v)]
    if not filtered:
        return ()

    seen_ids: set[str] = set()
    for verdict in filtered:
        if verdict.candidate_id in seen_ids:
            raise ValueError(f"duplicate candidate_id {verdict.candidate_id!r} in pairwise ranking")
        seen_ids.add(verdict.candidate_id)

    seed_order = {v.candidate_id: idx for idx, v in enumerate(filtered)}
    if len(filtered) > max_candidates:
        pool = sorted(
            filtered,
            key=lambda v: (_unweighted_tiebreak(v), -seed_order[v.candidate_id]),
            reverse=True,
        )[:max_candidates]
    else:
        pool = list(filtered)

    if len(pool) == 1:
        return ((pool[0], 1.0),)

    if comparator is None:
        ordered = sorted(
            pool,
            key=lambda v: (_unweighted_tiebreak(v), -seed_order[v.candidate_id]),
            reverse=True,
        )
        total = len(ordered)
        return tuple((v, round((total - idx) / total, 4)) for idx, v in enumerate(ordered))

    verdict_by_id = {v.candidate_id: v for v in pool}
    pool_ids = [v.candidate_id for v in pool]
    texts = candidate_texts or {}
    matches: list[PairwiseMatch] = []
    played_pairs: set[frozenset[str]] = set()
    a_slots: dict[str, int] = {cid: 0 for cid in pool_ids}
    b_slots: dict[str, int] = {cid: 0 for cid in pool_ids}
    byes: set[str] = set()

    for round_idx in range(rounds):
        if len(pool_ids) == 2:
            if round_idx >= 2:
                break
            pairs = [(pool_ids[0], pool_ids[1])] if round_idx == 0 else [(pool_ids[1], pool_ids[0])]
        else:
            win_rates, buchholz = _pairwise_standings(pool_ids, matches)
            ranked_ids = sorted(
                pool_ids,
                key=lambda cid: (
                    win_rates[cid],
                    buchholz[cid],
                    _unweighted_tiebreak(verdict_by_id[cid]),
                    -seed_order[cid],
                ),
                reverse=True,
            )
            active = list(ranked_ids)
            if len(active) % 2 == 1:
                bye_pick = next(
                    (cid for cid in reversed(active) if cid not in byes),
                    active[-1],
                )
                byes.add(bye_pick)
                active.remove(bye_pick)
            raw_pairs = _pair_without_rematches(active, played_pairs)
            pairs = []
            for left, right in raw_pairs:
                delta_left = a_slots[left] - b_slots[left]
                delta_right = a_slots[right] - b_slots[right]
                if delta_right < delta_left or (delta_right == delta_left and round_idx % 2 == 1):
                    pairs.append((right, left))
                else:
                    pairs.append((left, right))

        for cid_a, cid_b in pairs:
            played_pairs.add(frozenset({cid_a, cid_b}))
            a_slots[cid_a] += 1
            b_slots[cid_b] += 1
            match = comparator.compare(
                verdict_by_id[cid_a],
                verdict_by_id[cid_b],
                text_a_ckb=texts.get(cid_a, ""),
                text_b_ckb=texts.get(cid_b, ""),
            )
            matches.append(match)
            if matches_out is not None:
                matches_out.append(match)

    win_rates, buchholz = _pairwise_standings(pool_ids, matches)
    final_ids = sorted(
        pool_ids,
        key=lambda cid: (
            win_rates[cid],
            buchholz[cid],
            _unweighted_tiebreak(verdict_by_id[cid]),
            -seed_order[cid],
        ),
        reverse=True,
    )
    return tuple((verdict_by_id[cid], round(win_rates[cid], 4)) for cid in final_ids)


def tournament_rank_verdicts(
    verdicts: Sequence[JudgeVerdict],
    *,
    require_eligible: bool = True,
    comparator: PairwiseComparator | None = None,
    candidate_texts: Mapping[str, str] | None = None,
    rounds: int = DEFAULT_PAIRWISE_ROUNDS,
    max_candidates: int = MAX_PAIRWISE_CANDIDATES,
) -> tuple[tuple[JudgeVerdict, float], ...]:
    """Rank eligible verdicts via `pairwise_rank_verdicts` (weighted sum retired per D-346)."""
    return pairwise_rank_verdicts(
        verdicts,
        comparator=comparator,
        candidate_texts=candidate_texts,
        rounds=rounds,
        max_candidates=max_candidates,
        require_eligible=require_eligible,
    )


def compute_repeat_k_agreement(
    verdicts: Sequence[JudgeVerdict],
) -> dict[str, float]:
    """Calculate agreement metrics (mean, std dev, range) across repeat evaluations."""
    if not verdicts:
        return {}
    k = len(verdicts)
    metrics = (
        "hook_score",
        "payoff_strength",
        "meaning_fidelity",
        "cultural_landing",
        "misleading_edit_risk",
    )
    result: dict[str, float] = {"k": float(k)}
    for metric in metrics:
        values = [float(getattr(v, metric, 0.0)) for v in verdicts]
        mean_val = sum(values) / k
        variance = sum((x - mean_val) ** 2 for x in values) / k if k > 1 else 0.0
        std_val = math.sqrt(variance)
        span_val = max(values) - min(values)
        result[f"{metric}_mean"] = round(mean_val, 4)
        result[f"{metric}_std"] = round(std_val, 4)
        result[f"{metric}_range"] = round(span_val, 4)
    return result


def assert_model_agreement_cannot_bypass_human_qc(
    verdicts: Sequence[JudgeVerdict],
    qc_record: Any | None = None,
) -> None:
    """Assert that model agreement cannot equate to human accuracy or bypass QC (AC-15).

    Even if multiple repeat judge verdicts show 100% agreement (std dev == 0.0),
    automated agreement is an uncertainty measurement, never proof of ground-truth
    human accuracy or authorized delivery. Public promotion strictly requires a
    valid human review record (AC-01-AC-04).
    """
    if qc_record is None:
        raise ValueError(
            "Model agreement cannot equate to human accuracy or authorize delivery without "
            "an explicit human review record (AC-15, AC-01-AC-04)."
        )
    if getattr(qc_record, "verdict", None) not in ("approve", "approved"):
        raise ValueError(
            f"QC review record has non-approved verdict: {getattr(qc_record, 'verdict', None)!r}."
        )
