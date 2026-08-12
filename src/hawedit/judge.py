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

from dataclasses import dataclass
from enum import Enum
from typing import Any, Final, Protocol, runtime_checkable

from hawedit.boundary import _strict_bool
from hawedit.clip import Editorial, Output, Sv6d
from hawedit.discovery import MergedCandidate
from hawedit.normalize import normalize_sorani
from hawedit.registry import ModelEntry, resolve_role

__all__ = [
    "CANDIDATE_SLICE_TOKENS_PER_HOUR",
    "FULL_TRANSCRIPT_TOKENS_PER_HOUR",
    "JUDGE_ROLES",
    "KURDISH_EDITORIAL_JUDGE",
    "MIN_REGRESSION_ITEMS",
    "NARRATIVE_ROLES",
    "PRO_TIER_TOKEN_CEILING",
    "USD_PER_MILLION_TOKENS",
    "VIDEO_TOKENS_PER_SECOND",
    "WITH_VIDEO_TOKENS_PER_HOUR",
    "EditorialJudge",
    "InputMode",
    "JudgeDecision",
    "JudgeFrame",
    "JudgeRequest",
    "JudgeVerdict",
    "NotRoutable",
    "RequestTooLarge",
    "ShadowVerdict",
    "decide_judge",
    "estimate_cost_usd",
    "route",
    "video_tokens",
]

# §3 Stage 4's pinned judge. Named here so a caller states the incumbent rather than
# hard-coding a string, and so the shadow-promotion rule has something to compare against.
KURDISH_EDITORIAL_JUDGE: Final = "gemini-2.5-pro"
JUDGE_SHADOW: Final = "gemini-3.1-pro"
JUDGE_ROLES: Final = frozenset({"kurdish_editorial_judge", "judge_shadow"})

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

    def __post_init__(self) -> None:
        for field in (
            "hook_score",
            "meaning_fidelity",
            "misleading_edit_risk",
            "cultural_landing",
        ):
            value: float = getattr(self, field)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{field} must be within [0, 1], got {value}")

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
        )

    def to_output(self, crop_target: str, durations: tuple[int, ...]) -> Output:
        """Fill §5's `output` block with the judge's Kurdish title and description.

        `crop_target` and `durations` are not the judge's to decide — they are delivery
        settings — so they are the caller's arguments rather than invented here.
        """
        return Output(
            title_ckb=self.title_ckb,
            description_ckb=self.description_ckb,
            crop_target=crop_target,
            caption_style="word_highlight",
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
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> JudgeVerdict:
        raw_sv6d = data.get("sv6d")
        raw_hashtags = data["hashtags_ckb"]
        if not isinstance(raw_hashtags, list) or not all(
            isinstance(tag, str) for tag in raw_hashtags
        ):
            raise ValueError(
                "hashtags_ckb must be a JSON array of strings; a scalar string would be "
                "split into one hashtag per character"
            )
        if raw_sv6d is not None and not isinstance(raw_sv6d, dict):
            raise ValueError("sv6d must be a JSON object or null")
        return JudgeVerdict(
            candidate_id=data["candidate_id"],
            hook_score=data["hook_score"],
            self_contained=_strict_bool(data["self_contained"], "self_contained"),
            payoff_at_ms=data["payoff_at_ms"],
            meaning_fidelity=data["meaning_fidelity"],
            misleading_edit_risk=data["misleading_edit_risk"],
            cultural_landing=data["cultural_landing"],
            narrative_role=data["narrative_role"],
            title_ckb=data["title_ckb"],
            description_ckb=data["description_ckb"],
            hashtags_ckb=tuple(raw_hashtags),
            judge=data["judge"],
            clip_in_ms=data["clip_in_ms"],
            clip_out_ms=data["clip_out_ms"],
            sv6d=Sv6d(**raw_sv6d) if raw_sv6d is not None else None,
        )


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


@runtime_checkable
class EditorialJudge(Protocol):
    """§3 Stage 4's routing interface. Two members, so a swap is a config change."""

    model_id: str

    def judge(self, request: JudgeRequest) -> JudgeVerdict: ...


def route(judge: EditorialJudge) -> ModelEntry:
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
        if len(self.data) > 5 * 1024 * 1024:
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
