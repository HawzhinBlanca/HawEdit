"""Comparison kit for blind pairwise human evaluation (Task T5.1, H7).

Versioned A/B ratings and descriptive comparisons between system and human editor cuts.
Legacy overall scores cannot identify option differences. Pooled Wilson references do
not establish episode/reviewer independence or authorize superiority. Preference is not
fidelity QC or authenticated approval. Staging is currently deterministic and unsealed;
it must not be used as an independently blinded release study.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import shutil
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from statistics import NormalDist
from typing import Any, Final

from hawedit.clip import QcRecord

__all__ = [
    "BlindedItem",
    "BlindedStudy",
    "ComparisonKitError",
    "OptionRating",
    "PairCandidate",
    "PairRating",
    "RaterSubmission",
    "StudyMetrics",
    "analyze_study",
    "export_to_qc_records",
    "format_kurdish_form_markdown",
    "generate_kurdish_rating_form",
    "prepare_blind_study",
    "validate_ratings",
    "wilson_score_interval",
]

Z_95: Final[float] = 1.959963984540054


class ComparisonKitError(ValueError):
    """Raised when comparison kit operations or inputs violate validation constraints."""


def wilson_score_interval(p_hat: float, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Calculate the two-sided Wilson score confidence interval for a binomial proportion.

    Args:
        p_hat: Sample proportion in [0.0, 1.0].
        n: Total number of trials / comparisons (must be >= 1).
        confidence: Confidence level (default 0.95).

    Returns:
        (ci_lower, ci_upper) clamped strictly to [0.0, 1.0].
    """
    if type(n) is not int or n <= 0:
        raise ComparisonKitError(f"Sample size n must be positive, got {n}")
    if isinstance(p_hat, bool) or not isinstance(p_hat, int | float) or not (0.0 <= p_hat <= 1.0):
        raise ComparisonKitError(f"p_hat must be within [0.0, 1.0], got {p_hat}")
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, int | float)
        or not 0.0 < confidence < 1.0
    ):
        raise ComparisonKitError("confidence must be finite and strictly between 0 and 1")

    # The lower tail avoids rounding (1 + confidence) / 2 to one near confidence=1.
    z = Z_95 if confidence == 0.95 else -NormalDist().inv_cdf((1.0 - confidence) / 2.0)
    z2 = z * z
    denominator = 1.0 + z2 / n
    center = (p_hat + z2 / (2.0 * n)) / denominator
    std_err = math.sqrt((p_hat * (1.0 - p_hat) / n) + (z2 / (4.0 * n * n)))
    margin = (z / denominator) * std_err
    lower = max(0.0, center - margin)
    upper = min(1.0, center + margin)
    return (lower, upper)


@dataclass(frozen=True, slots=True)
class PairCandidate:
    """One pair of clips for blind evaluation (system vs human editor)."""

    pair_id: str
    system_path: Path
    human_path: Path
    topic_ckb: str
    duration_s: float

    def __post_init__(self) -> None:
        if not self.pair_id.strip():
            raise ComparisonKitError("pair_id must be non-empty")
        if not self.topic_ckb.strip():
            raise ComparisonKitError("topic_ckb must be non-empty")
        if self.duration_s <= 0:
            raise ComparisonKitError("duration_s must be positive")


@dataclass(frozen=True, slots=True)
class BlindedItem:
    """A single blinded pair presented to raters as Option A and Option B."""

    pair_id: str
    blinded_path_a: Path
    blinded_path_b: Path
    sha256_a: str
    sha256_b: str
    topic_ckb: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "pair_id": self.pair_id,
            "blinded_path_a": str(self.blinded_path_a),
            "blinded_path_b": str(self.blinded_path_b),
            "sha256_a": self.sha256_a,
            "sha256_b": self.sha256_b,
            "topic_ckb": self.topic_ckb,
        }


@dataclass(frozen=True, slots=True)
class BlindedStudy:
    """A prepared blinded evaluation study with sealed unblinding key."""

    study_id: str
    items: tuple[BlindedItem, ...]
    unblinding_map: dict[str, dict[str, str]]
    seed: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "study_id": self.study_id,
            "seed": self.seed,
            "items": [item.to_dict() for item in self.items],
        }


def prepare_blind_study(
    pairs: Sequence[PairCandidate],
    output_dir: Path,
    seed: int = 42,
    copy_media: bool = True,
) -> BlindedStudy:
    """Prepare a deterministic blinded evaluation study from clip pairs.

    For each pair, Option A and Option B are randomized using a deterministic PRNG seed.
    Blinded copies are staged with sanitized names, and an unblinding key is generated.

    Args:
        pairs: Sequence of PairCandidate items.
        output_dir: Directory where blinded artifacts and manifest are saved.
        seed: Random seed for deterministic blinding.
        copy_media: If True, copies media files; if False, creates placeholder files.

    Returns:
        BlindedStudy containing blinded items and the unblinding map.
    """
    if not pairs:
        raise ComparisonKitError("Cannot prepare study with zero pairs")

    output_dir.mkdir(parents=True, exist_ok=True)
    media_dir = output_dir / "blinded_media"
    media_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(seed)
    items: list[BlindedItem] = []
    unblinding_map: dict[str, dict[str, str]] = {}

    for pair in pairs:
        # 0 = A is system, B is human; 1 = A is human, B is system
        flip = rng.randint(0, 1) == 1
        path_a_src = pair.human_path if flip else pair.system_path
        path_b_src = pair.system_path if flip else pair.human_path

        dest_a = media_dir / f"{pair.pair_id}_option_A.mp4"
        dest_b = media_dir / f"{pair.pair_id}_option_B.mp4"

        if copy_media:
            if not path_a_src.is_file() or not path_b_src.is_file():
                raise ComparisonKitError(
                    f"Source files missing for {pair.pair_id}: {path_a_src} or {path_b_src}"
                )
            shutil.copyfile(path_a_src, dest_a)
            shutil.copyfile(path_b_src, dest_b)
            sha256_a = hashlib.sha256(dest_a.read_bytes()).hexdigest()
            sha256_b = hashlib.sha256(dest_b.read_bytes()).hexdigest()
        else:
            dest_a.write_bytes(f"mock_media_a_{pair.pair_id}".encode())
            dest_b.write_bytes(f"mock_media_b_{pair.pair_id}".encode())
            sha256_a = hashlib.sha256(dest_a.read_bytes()).hexdigest()
            sha256_b = hashlib.sha256(dest_b.read_bytes()).hexdigest()

        items.append(
            BlindedItem(
                pair_id=pair.pair_id,
                blinded_path_a=dest_a,
                blinded_path_b=dest_b,
                sha256_a=sha256_a,
                sha256_b=sha256_b,
                topic_ckb=pair.topic_ckb,
            )
        )
        unblinding_map[pair.pair_id] = {
            "A": "human" if flip else "system",
            "B": "system" if flip else "human",
        }

    study = BlindedStudy(
        study_id=f"study_seed_{seed}",
        items=tuple(items),
        unblinding_map=unblinding_map,
        seed=seed,
    )

    # Persist blinded manifest and sealed unblinding key
    manifest_path = output_dir / "blinded_manifest.json"
    manifest_path.write_text(json.dumps(study.to_dict(), indent=2), encoding="utf-8")

    unblinding_path = output_dir / "unblinding_key.json"
    unblinding_path.write_text(json.dumps(unblinding_map, indent=2), encoding="utf-8")

    return study


@dataclass(frozen=True, slots=True)
class OptionRating:
    """Self-reported observations for one option, not an authenticated QC record."""

    hook_score: int
    clarity_score: int
    shareability_score: int
    misleading_flag: bool
    seconds_watched: float | None = None
    correction_seconds: float | None = None

    def __post_init__(self) -> None:
        for name in ("hook_score", "clarity_score", "shareability_score"):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= 5:
                raise ComparisonKitError(f"{name} must be an integer between 1 and 5")
        if type(self.misleading_flag) is not bool:
            raise ComparisonKitError("misleading_flag must be boolean")
        for name in ("seconds_watched", "correction_seconds"):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, int | float)
                or not math.isfinite(value)
                or value < 0
            ):
                raise ComparisonKitError(f"{name} must be unknown or finite nonnegative seconds")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PairRating:
    """Version 1 overall scores or version 2 separate A/B observations."""

    pair_id: str
    hook_score: int | None
    clarity_score: int | None
    shareability_score: int | None
    misleading_flag: bool | None
    preferred_option: str
    notes: str = ""
    option_a: OptionRating | None = field(default=None, kw_only=True)
    option_b: OptionRating | None = field(default=None, kw_only=True)

    def __post_init__(self) -> None:
        if not isinstance(self.pair_id, str) or not self.pair_id.strip():
            raise ComparisonKitError("pair_id must be non-empty")
        if self.pair_id != self.pair_id.strip():
            raise ComparisonKitError("pair_id must not have surrounding whitespace")
        overall = (
            self.hook_score,
            self.clarity_score,
            self.shareability_score,
            self.misleading_flag,
        )
        if self.option_a is None and self.option_b is None:
            for name, value in zip(
                ("hook_score", "clarity_score", "shareability_score"), overall[:3], strict=True
            ):
                if type(value) is not int or not 1 <= value <= 5:
                    raise ComparisonKitError(f"{name} must be an integer between 1 and 5")
            if type(self.misleading_flag) is not bool:
                raise ComparisonKitError("misleading_flag must be boolean")
        elif (
            not isinstance(self.option_a, OptionRating)
            or not isinstance(self.option_b, OptionRating)
            or any(value is not None for value in overall)
        ):
            raise ComparisonKitError(
                "Paired schema requires A/B observations without overall scores"
            )
        if self.preferred_option not in ("A", "B", "tie"):
            raise ComparisonKitError(
                f"preferred_option must be 'A', 'B', or 'tie', got {self.preferred_option!r}"
            )
        if not isinstance(self.notes, str):
            raise ComparisonKitError("notes must be a string")

    @property
    def schema(self) -> int:
        return 2 if self.option_a is not None else 1

    @classmethod
    def from_options(
        cls,
        pair_id: str,
        option_a: OptionRating,
        option_b: OptionRating,
        preferred_option: str,
        notes: str = "",
    ) -> PairRating:
        return cls(
            pair_id,
            None,
            None,
            None,
            None,
            preferred_option,
            notes,
            option_a=option_a,
            option_b=option_b,
        )

    def to_dict(self) -> dict[str, Any]:
        if self.option_a is not None and self.option_b is not None:
            return {
                "pair_id": self.pair_id,
                "option_a": self.option_a.to_dict(),
                "option_b": self.option_b.to_dict(),
                "preferred_option": self.preferred_option,
                "notes": self.notes,
            }
        return {
            "pair_id": self.pair_id,
            "hook_score": self.hook_score,
            "clarity_score": self.clarity_score,
            "shareability_score": self.shareability_score,
            "misleading_flag": self.misleading_flag,
            "preferred_option": self.preferred_option,
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class RaterSubmission:
    """Distinct observations under a self-declared label, not trusted reviewer identity."""

    reviewer_name: str
    submitted_at_iso: str
    ratings: tuple[PairRating, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.reviewer_name, str) or not self.reviewer_name.strip():
            raise ComparisonKitError("reviewer_name must be a non-empty string")
        if self.reviewer_name != self.reviewer_name.strip():
            raise ComparisonKitError("reviewer_name must not have surrounding whitespace")
        if not isinstance(self.submitted_at_iso, str):
            raise ComparisonKitError("submitted_at_iso must be a timezone-aware ISO datetime")
        try:
            timestamp = datetime.fromisoformat(self.submitted_at_iso)
            if timestamp.utcoffset() is None:
                raise ValueError("timezone missing")
        except ValueError as exc:
            raise ComparisonKitError(
                "submitted_at_iso must be a timezone-aware ISO datetime"
            ) from exc
        if (
            not isinstance(self.ratings, tuple)
            or not self.ratings
            or any(not isinstance(r, PairRating) for r in self.ratings)
        ):
            raise ComparisonKitError("ratings must be a non-empty tuple of PairRating")
        if len({r.pair_id for r in self.ratings}) != len(self.ratings):
            raise ComparisonKitError("Duplicate rating for reviewer/pair")
        if len({r.schema for r in self.ratings}) != 1:
            raise ComparisonKitError("Submission cannot mix rating schemas")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.ratings[0].schema,
            "reviewer_name": self.reviewer_name,
            "submitted_at_iso": self.submitted_at_iso,
            "ratings": [r.to_dict() for r in self.ratings],
        }


def generate_kurdish_rating_form(study: BlindedStudy) -> dict[str, Any]:
    """Generate structured rating template in Kurdish Sorani (ckb)."""
    return {
        "schema": 2,
        "title_ckb": "فۆڕمی هەڵسەنگاندنی کوالێتی ڤیدیۆ — بەراوردی کوێرانە",
        "instructions_ckb": (
            "تکایە هەر جووتە ڤیدیۆیەک بە وردی تەماشا بکە (بژاردەی A و بژاردەی B). "
            "هەڵسەنگاندن بۆ هەر بڕگەیەک بکە لەسەر پێوەری ۱ تا ۵. "
            "لە کۆتاییدا ئەو بژاردەیە دیاری بکە کە بە پەسەندتری دەزانیت."
        ),
        "dimensions": [
            {
                "id": "hook_score",
                "scope": "per_option",
                "label_ckb": "سەرنجڕاکێشی لە ۳ چرکەی یەکەمدا (Hook)",
                "scale": "1 (زۆر لاواز) تا 5 (زۆر سەرنجڕاکێش)",
            },
            {
                "id": "clarity_score",
                "scope": "per_option",
                "label_ckb": "ڕوونی پەیام و پاراستنی مانای دەق (Clarity)",
                "scale": "1 (ناڕوون/پچڕاو) تا 5 (تەواو ڕوون و بەسوود)",
            },
            {
                "id": "shareability_score",
                "scope": "per_option",
                "label_ckb": "ئارەزووی بڵاوکردنەوە لە تۆڕە کۆمەڵایەتییەکان (Shareability)",
                "scale": "1 (هەرگیز بڵاوی ناکەمەوە) تا 5 (بە دڵنیاییەوە بڵاوی دەکەمەوە)",
            },
            {
                "id": "misleading_flag",
                "scope": "per_option",
                "label_ckb": "ئایا دەستکارییەکە چەواشەکارانەیە یان واتاکەی شێواندووە؟ (Misleading)",
                "type": "بەڵێ / نەخێر",
            },
            {
                "id": "preferred_option",
                "scope": "pair",
                "label_ckb": "هەڵبژاردنی گشتیی پەسەندکراو (Overall Preference)",
                "options": ["A", "B", "tie (یەکسان)"],
            },
        ],
        "items": [
            {
                "pair_id": item.pair_id,
                "topic_ckb": item.topic_ckb,
                "option_a": str(item.blinded_path_a.name),
                "option_b": str(item.blinded_path_b.name),
                "rating_options": ["A", "B"],
            }
            for item in study.items
        ],
    }


def format_kurdish_form_markdown(study: BlindedStudy) -> str:
    """Format the Kurdish evaluation sheet as a readable Markdown document."""
    form = generate_kurdish_rating_form(study)
    lines: list[str] = [
        f"# {form['title_ckb']}",
        "",
        form["instructions_ckb"],
        "",
        "## پێوەرەکانی هەڵسەنگاندن",
    ]
    for dim in form["dimensions"]:
        desc = dim.get("scale") or dim.get("type") or ", ".join(dim.get("options", []))
        lines.append(f"- **{dim['label_ckb']}**: {desc}")
    lines.append("")
    lines.append("## جووتە ڤیدیۆکان")
    for item in form["items"]:
        lines.append(f"### {item['pair_id']} — {item['topic_ckb']}")
        lines.append(f"- پەڕگەی A: `{item['option_a']}`")
        lines.append(f"- پەڕگەی B: `{item['option_b']}`")
        for option in item["rating_options"]:
            lines.append(f"### {option}")
            for dim in form["dimensions"][:4]:
                lines.append(f"- {dim['label_ckb']}: ______")
        lines.append(f"- {form['dimensions'][4]['label_ckb']}: A / B / tie")
        lines.append("")
    return "\n".join(lines)


def validate_ratings(payload: dict[str, Any], expected_pair_ids: set[str]) -> RaterSubmission:
    """Validate submitted ratings against the expected study schema and pairs.

    Raises:
        ComparisonKitError: If schema is invalid, pairs are missing/duplicate,
            or scores out of bounds.
    """
    if not isinstance(payload, dict):
        raise ComparisonKitError("Submission must be a dictionary")
    schema = payload.get("schema", 1)
    if type(schema) is not int or schema not in (1, 2):
        raise ComparisonKitError("Unsupported rating schema")
    required = {"reviewer_name", "submitted_at_iso", "ratings"}
    if not required <= payload.keys() or payload.keys() - required - {"schema"}:
        raise ComparisonKitError("Submission fields are missing or unknown")
    reviewer = payload.get("reviewer_name")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ComparisonKitError("reviewer_name must be a non-empty string")

    time_str = payload.get("submitted_at_iso")
    if not isinstance(time_str, str) or not time_str.strip():
        raise ComparisonKitError("submitted_at_iso must be a non-empty string")

    raw_ratings = payload.get("ratings")
    if not isinstance(raw_ratings, list) or not raw_ratings:
        raise ComparisonKitError("ratings must be a non-empty list")

    seen_pairs: set[str] = set()
    validated_ratings: list[PairRating] = []

    for r in raw_ratings:
        if not isinstance(r, dict):
            raise ComparisonKitError("Each rating entry must be a dictionary")
        pid = r.get("pair_id")
        if not isinstance(pid, str) or pid not in expected_pair_ids:
            raise ComparisonKitError(f"Unexpected or invalid pair_id: {pid}")
        if pid in seen_pairs:
            raise ComparisonKitError(f"Duplicate rating for pair: {pid}")
        seen_pairs.add(pid)

        fields = {"pair_id", "preferred_option"}
        fields |= (
            {"hook_score", "clarity_score", "shareability_score", "misleading_flag"}
            if schema == 1
            else {"option_a", "option_b"}
        )
        if not fields <= r.keys() or r.keys() - fields - {"notes"}:
            raise ComparisonKitError(f"Rating fields are missing or unknown for pair {pid}")
        if schema == 1:
            rating = PairRating(
                pair_id=pid,
                hook_score=r["hook_score"],
                clarity_score=r["clarity_score"],
                shareability_score=r["shareability_score"],
                misleading_flag=r["misleading_flag"],
                preferred_option=r["preferred_option"],
                notes=r.get("notes", ""),
            )
        else:
            options: list[OptionRating] = []
            for option_name in ("option_a", "option_b"):
                raw = r[option_name]
                required_option = {
                    "hook_score",
                    "clarity_score",
                    "shareability_score",
                    "misleading_flag",
                }
                if (
                    not isinstance(raw, dict)
                    or not required_option <= raw.keys()
                    or raw.keys() - required_option - {"seconds_watched", "correction_seconds"}
                ):
                    raise ComparisonKitError(f"Invalid {option_name} fields for pair {pid}")
                options.append(OptionRating(**raw))
            rating = PairRating.from_options(
                pid, options[0], options[1], r["preferred_option"], r.get("notes", "")
            )
        validated_ratings.append(rating)

    if seen_pairs != expected_pair_ids:
        missing = expected_pair_ids - seen_pairs
        raise ComparisonKitError(f"Submission is missing ratings for pairs: {sorted(missing)}")

    return RaterSubmission(
        reviewer_name=reviewer,
        submitted_at_iso=time_str,
        ratings=tuple(validated_ratings),
    )


@dataclass(frozen=True, slots=True)
class StudyMetrics:
    """Descriptive outcomes; independent reference bounds are not clustered inference."""

    total_comparisons: int
    system_wins: int
    human_wins: int
    ties: int
    system_win_rate: float
    ci_lower: float | None
    ci_upper: float | None
    better_than_a_team: bool
    hook_mean_diff: float | None
    clarity_mean_diff: float | None
    shareability_mean_diff: float | None
    misleading_rate_system: float | None
    misleading_rate_human: float | None
    independent_reference_ci_lower: float
    independent_reference_ci_upper: float
    nominal_reviewers: int
    distinct_pairs: int
    paired_comparisons: int
    independent_reference_method: str = (
        "independent-Bernoulli Wilson 95%; ties half-counted; reference only"
    )
    inference_status: str = "unavailable-unverified-study"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def analyze_study(
    submissions: Sequence[RaterSubmission],
    unblinding_map: dict[str, dict[str, str]],
) -> StudyMetrics:
    """Compute descriptive votes and option differences without authorizing H7.

    This input lacks verified episode/reviewer design, provenance and signed review.
    Its pooled reference interval cannot be substituted for independent study inference.
    """
    if not submissions:
        raise ComparisonKitError("Cannot analyze study with zero submissions")

    total_comparisons = 0
    system_wins = 0
    human_wins = 0
    ties = 0

    hook_diffs: list[float] = []
    clarity_diffs: list[float] = []
    share_diffs: list[float] = []

    misleading_system_count = 0
    misleading_human_count = 0
    observations: set[tuple[str, str]] = set()
    pair_ids: set[str] = set()
    reviewers: set[str] = set()
    paired_count = 0
    if not isinstance(unblinding_map, dict) or not unblinding_map:
        raise ComparisonKitError("Unblinding map must be non-empty")
    for pid, entry in unblinding_map.items():
        if (
            not isinstance(pid, str)
            or not isinstance(entry, dict)
            or set(entry) != {"A", "B"}
            or (entry["A"], entry["B"]) not in (("human", "system"), ("system", "human"))
        ):
            raise ComparisonKitError("Unblinding map must have bijective A/B system/human entries")

    for sub in submissions:
        if not isinstance(sub, RaterSubmission):
            raise ComparisonKitError("Each submission must be a RaterSubmission")
        reviewers.add(sub.reviewer_name)
        for r in sub.ratings:
            observation = (sub.reviewer_name, r.pair_id)
            if observation in observations:
                raise ComparisonKitError("Duplicate reviewer/pair observation")
            observations.add(observation)
            pair_ids.add(r.pair_id)
            key = unblinding_map.get(r.pair_id)
            if not key:
                raise ComparisonKitError(f"Pair {r.pair_id} not found in unblinding map")

            total_comparisons += 1
            choice = r.preferred_option

            if choice == "tie":
                ties += 1
            else:
                winner = key.get(choice)
                if winner == "system":
                    system_wins += 1
                elif winner == "human":
                    human_wins += 1
                else:
                    raise ComparisonKitError(f"Invalid option {choice} for pair {r.pair_id}")

            if r.option_a is not None and r.option_b is not None:
                system, human = (
                    (r.option_a, r.option_b) if key["A"] == "system" else (r.option_b, r.option_a)
                )
                paired_count += 1
                hook_diffs.append(float(system.hook_score - human.hook_score))
                clarity_diffs.append(float(system.clarity_score - human.clarity_score))
                share_diffs.append(float(system.shareability_score - human.shareability_score))
                misleading_system_count += int(system.misleading_flag)
                misleading_human_count += int(human.misleading_flag)

    if pair_ids != set(unblinding_map):
        raise ComparisonKitError("Unblinding map contains unrated pairs; incomplete accounting")

    # Calculate effective win rate: (wins + 0.5 * ties) / total
    p_hat = (system_wins + 0.5 * ties) / total_comparisons
    ci_lower, ci_upper = wilson_score_interval(p_hat, total_comparisons, confidence=0.95)

    # Do not report a selected paired subset as the whole study's measurements.
    fully_paired = paired_count == total_comparisons

    return StudyMetrics(
        total_comparisons=total_comparisons,
        system_wins=system_wins,
        human_wins=human_wins,
        ties=ties,
        system_win_rate=round(p_hat, 4),
        ci_lower=None,
        ci_upper=None,
        better_than_a_team=False,
        hook_mean_diff=round(math.fsum(hook_diffs) / total_comparisons, 3)
        if fully_paired
        else None,
        clarity_mean_diff=round(math.fsum(clarity_diffs) / total_comparisons, 3)
        if fully_paired
        else None,
        shareability_mean_diff=round(math.fsum(share_diffs) / total_comparisons, 3)
        if fully_paired
        else None,
        misleading_rate_system=round(misleading_system_count / total_comparisons, 4)
        if fully_paired
        else None,
        misleading_rate_human=round(misleading_human_count / total_comparisons, 4)
        if fully_paired
        else None,
        independent_reference_ci_lower=round(ci_lower, 4),
        independent_reference_ci_upper=round(ci_upper, 4),
        nominal_reviewers=len(reviewers),
        distinct_pairs=len(pair_ids),
        paired_comparisons=paired_count,
    )


def export_to_qc_records(
    submission: RaterSubmission,
    study: BlindedStudy,
) -> tuple[QcRecord, ...]:
    """Retained migration entry point; preferences cannot become fidelity approval."""
    raise ComparisonKitError(
        "Comparative preference cannot produce QC approval: use separate fidelity review "
        "with observed watched time, exact-byte evidence and authenticated signatures"
    )
