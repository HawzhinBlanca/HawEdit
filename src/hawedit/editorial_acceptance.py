"""Content-bound, blinded human acceptance studies for BLUEPRINT §8.2.

The existing :mod:`hawedit.editorial_bench` is the 20-item judge-regression gate.  This module
owns the larger 200–500-item study: deterministic sampling, concealed A/B order, a frozen
training/holdout split, signed independent reviews, exact disagreement adjudication, and the
complete per-split metric report.  It prepares human work; it never fabricates human labels.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Final

from hawedit.atomic_fs import rename_directory_noreplace
from hawedit.cli import machine_readable_stdout, program_name, use_utf8_streams
from hawedit.clip import DiscoveryPath
from hawedit.corpus import Dialect
from hawedit.ingest import IngestError, probe_duration_ms, probe_stream
from hawedit.judge import (
    JUDGE_SHADOW,
    KURDISH_EDITORIAL_JUDGE,
    JudgeVerdict,
    decide_judge,
)
from hawedit.repurposing import (
    GoldCandidate,
    RetrievedCandidate,
    cost_per_source_hour,
    misleading_edit_rate,
    pairwise_preference,
    path_unique_wins,
    recall_at_k_by_path,
    sentence_completeness_rate,
    temporal_iou,
    wallclock_per_source_hour,
)

__all__ = [
    "MAX_STUDY_ITEMS",
    "MIN_STUDY_ITEMS",
    "SIGNATURE_NAMESPACE",
    "EditorialAcceptanceError",
    "PreparedEditorialStudy",
    "VerifiedEditorialStudy",
    "evaluate_editorial_study",
    "main",
    "prepare_editorial_study",
]

MIN_STUDY_ITEMS: Final = 200
MAX_STUDY_ITEMS: Final = 500
SIGNATURE_NAMESPACE: Final = "hawedit-editorial-study-v1"
_SCHEMA: Final = 1
_MAX_JSON_BYTES: Final = 64 * 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_RFC3339_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_SIGNER_FINGERPRINT = re.compile(rb"\bkey (SHA256:[A-Za-z0-9+/=]{20,})\b")
_PLACEHOLDERS: Final = frozenset(
    {"", "unknown", "tbd", "todo", "none", "n/a", "unrecorded", "placeholder"}
)
_VERDICT_FIELDS: Final = {
    "candidate_id",
    "clip_in_ms",
    "clip_out_ms",
    "cultural_landing",
    "description_ckb",
    "hashtags_ckb",
    "hook_score",
    "judge",
    "meaning_fidelity",
    "misleading_edit_risk",
    "narrative_role",
    "payoff_at_ms",
    "self_contained",
    "sv6d",
    "title_ckb",
}
_PREPARED_FILES: Final = (
    "INSTRUCTIONS.txt",
    "adjudication.template.json",
    "coordinator-approval.template.json",
    "review-packet.json",
    "reviewer.template.json",
    "study-manifest.json",
)
_RESULT_FILES: Final = (
    "INSTRUCTIONS.txt",
    "holdout-labels.json",
    "study-report.json",
    "training-labels.json",
)


class EditorialAcceptanceError(ValueError):
    """The proposed §8.2 study is incomplete, mutable, unblinded, or unauthenticated."""


def _one_line(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise EditorialAcceptanceError(f"{field} must be a string")
    if (
        not value
        or value.strip() != value
        or not value.isprintable()
        or value.splitlines() != [value]
    ):
        raise EditorialAcceptanceError(
            f"{field} must be non-empty, trimmed, printable, and one line"
        )
    if value.casefold() in _PLACEHOLDERS:
        raise EditorialAcceptanceError(f"{field} is placeholder text, not acceptance evidence")
    return value


def _exact_bool(value: object, field: str) -> bool:
    if type(value) is not bool:
        raise EditorialAcceptanceError(f"{field} must be a JSON boolean")
    return value


def _exact_int(value: object, field: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise EditorialAcceptanceError(f"{field} must be an integer >= {minimum}")
    return value


def _finite_number(value: object, field: str, *, positive: bool = False) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not math.isfinite(float(value))
    ):
        raise EditorialAcceptanceError(f"{field} must be a finite JSON number")
    numeric = float(value)
    if (positive and numeric <= 0.0) or (not positive and numeric < 0.0):
        comparison = "> 0" if positive else ">= 0"
        raise EditorialAcceptanceError(f"{field} must be {comparison}")
    return numeric


def _digest(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise EditorialAcceptanceError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _strict_object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise EditorialAcceptanceError(f"{field} must be a JSON object")
    return value


def _exact_fields(value: Mapping[str, Any], expected: set[str], field: str) -> None:
    actual = set(value)
    if actual != expected:
        raise EditorialAcceptanceError(
            f"{field} fields do not match schema; "
            f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EditorialAcceptanceError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _canonical_json(document: Mapping[str, Any]) -> bytes:
    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _is_reparse(info: os.stat_result) -> bool:
    flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(getattr(info, "st_file_attributes", 0) & flag)


def _file_identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_nlink)


def _read_bound_file(path: Path, label: str, *, maximum: int | None) -> bytes:
    try:
        before_path = os.lstat(path)
    except OSError as exc:
        raise EditorialAcceptanceError(f"cannot inspect {label} {path}: {exc}") from exc
    if stat.S_ISLNK(before_path.st_mode) or _is_reparse(before_path):
        raise EditorialAcceptanceError(f"{label} must not be a link or reparse point: {path}")
    if not stat.S_ISREG(before_path.st_mode) or before_path.st_nlink != 1:
        raise EditorialAcceptanceError(f"{label} must be one regular, non-hardlinked file: {path}")
    if maximum is not None and before_path.st_size > maximum:
        raise EditorialAcceptanceError(f"{label} exceeds its {maximum}-byte limit: {path}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise EditorialAcceptanceError(f"cannot open {label} {path}: {exc}") from exc
    try:
        before_fd = os.fstat(descriptor)
        if _file_identity(before_fd) != _file_identity(before_path):
            raise EditorialAcceptanceError(f"{label} changed while it was being opened: {path}")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if maximum is not None and total > maximum:
                raise EditorialAcceptanceError(f"{label} exceeds its {maximum}-byte limit: {path}")
            chunks.append(chunk)
        after_fd = os.fstat(descriptor)
        if (
            _file_identity(after_fd) != _file_identity(before_fd)
            or after_fd.st_ctime_ns != before_fd.st_ctime_ns
        ):
            raise EditorialAcceptanceError(f"{label} changed while it was being read: {path}")
    finally:
        os.close(descriptor)
    try:
        after_path = os.lstat(path)
    except OSError as exc:
        raise EditorialAcceptanceError(f"cannot re-inspect {label} {path}: {exc}") from exc
    if (
        _file_identity(after_path) != _file_identity(before_path)
        or after_path.st_ctime_ns != before_path.st_ctime_ns
    ):
        raise EditorialAcceptanceError(f"{label} path changed while it was being read: {path}")
    return b"".join(chunks)


def _stable_digest(path: Path, label: str) -> str:
    return hashlib.sha256(_read_bound_file(path, label, maximum=None)).hexdigest()


def _verified_video_identity(path: Path, label: str, expected_duration_ms: int) -> str:
    before = _stable_digest(path, label)
    try:
        video_stream = probe_stream(path, "stream=index", video_only=True)
        actual_duration_ms = probe_duration_ms(path)
    except (IngestError, OSError, ValueError) as exc:
        raise EditorialAcceptanceError(f"{label} is not probeable video: {exc}") from exc
    if not video_stream:
        raise EditorialAcceptanceError(f"{label} has no video stream")
    after = _stable_digest(path, label)
    if after != before:
        raise EditorialAcceptanceError(f"{label} changed while ffprobe inspected it")
    if actual_duration_ms != expected_duration_ms:
        raise EditorialAcceptanceError(
            f"{label} duration is {actual_duration_ms} ms, not declared {expected_duration_ms} ms"
        )
    return before


def _load_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    payload = _read_bound_file(path, label, maximum=_MAX_JSON_BYTES)
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EditorialAcceptanceError(f"{label} is not strict UTF-8 JSON: {exc}") from exc
    return _strict_object(value, label), payload


def _relative_path(value: object, field: str) -> str:
    text = _one_line(value, field)
    if "\\" in text:
        raise EditorialAcceptanceError(f"{field} must use forward slashes")
    relative = PurePosixPath(text)
    if relative.is_absolute() or any(
        part in {"", ".", ".."} or ":" in part for part in relative.parts
    ):
        raise EditorialAcceptanceError(f"{field} must be one contained relative path")
    return text


def _bound_directory(path: Path, label: str) -> tuple[Path, tuple[int, int]]:
    absolute = Path(os.path.abspath(path))
    try:
        info = os.lstat(absolute)
    except OSError as exc:
        raise EditorialAcceptanceError(f"cannot inspect {label} {absolute}: {exc}") from exc
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or _is_reparse(info):
        raise EditorialAcceptanceError(f"{label} must be one real directory: {absolute}")
    return absolute, (info.st_dev, info.st_ino)


def _assert_directory(path: Path, identity: tuple[int, int], label: str) -> None:
    _, actual = _bound_directory(path, label)
    if actual != identity:
        raise EditorialAcceptanceError(f"{label} identity changed: {path}")


def _contained_media(root: Path, relative: str) -> Path:
    current = root
    parts = PurePosixPath(_relative_path(relative, "media path")).parts
    for index, part in enumerate(parts):
        current /= part
        try:
            info = os.lstat(current)
        except OSError as exc:
            raise EditorialAcceptanceError(f"cannot inspect study media {current}: {exc}") from exc
        if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
            raise EditorialAcceptanceError(f"study media path contains a link: {current}")
        if index < len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise EditorialAcceptanceError(f"study media parent is not a directory: {current}")
    return current


def _write_private_file(path: Path, payload: bytes) -> None:
    try:
        with path.open("xb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
    except OSError as exc:
        raise EditorialAcceptanceError(f"cannot stage editorial evidence {path}: {exc}") from exc


def _discard_private_directory(
    staging: Path, identity: tuple[int, int], expected: frozenset[str]
) -> None:
    if not os.path.lexists(staging):
        return
    _assert_directory(staging, identity, "private editorial-evidence directory")
    try:
        children = tuple(staging.iterdir())
    except OSError as exc:
        raise EditorialAcceptanceError(f"cannot inspect private evidence {staging}: {exc}") from exc
    unexpected = sorted(path.name for path in children if path.name not in expected)
    if unexpected:
        raise EditorialAcceptanceError(
            "refusing to clean unexpected private editorial evidence: " + ", ".join(unexpected)
        )
    try:
        for path in children:
            info = os.lstat(path)
            if (
                not stat.S_ISREG(info.st_mode)
                or stat.S_ISLNK(info.st_mode)
                or _is_reparse(info)
                or info.st_nlink != 1
            ):
                raise EditorialAcceptanceError(f"refusing to clean unsafe evidence file {path}")
            path.unlink()
        staging.rmdir()
    except EditorialAcceptanceError:
        raise
    except OSError as exc:
        raise EditorialAcceptanceError(f"cannot clean private evidence {staging}: {exc}") from exc


def _publish_exact_directory(output_dir: Path, payloads: Mapping[str, bytes]) -> Path:
    expected = frozenset(payloads)
    if expected not in {frozenset(_PREPARED_FILES), frozenset(_RESULT_FILES)}:
        raise EditorialAcceptanceError("editorial evidence is not an exact supported file set")
    destination = Path(os.path.abspath(output_dir))
    parent, parent_identity = _bound_directory(destination.parent, "editorial output parent")
    if os.path.lexists(destination):
        raise EditorialAcceptanceError(f"refusing to overwrite editorial evidence {destination}")
    try:
        staging = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.", suffix=".staging", dir=parent)
        )
    except OSError as exc:
        raise EditorialAcceptanceError(
            f"cannot create private evidence under {parent}: {exc}"
        ) from exc
    _, staging_identity = _bound_directory(staging, "private editorial-evidence directory")
    try:
        for filename in sorted(expected):
            _write_private_file(staging / filename, payloads[filename])
        _assert_directory(parent, parent_identity, "editorial output parent")
        _assert_directory(staging, staging_identity, "private editorial-evidence directory")
        actual = frozenset(path.name for path in staging.iterdir())
        if actual != expected:
            raise EditorialAcceptanceError(
                f"private editorial evidence set changed; expected={sorted(expected)}, "
                f"actual={sorted(actual)}"
            )
        rename_directory_noreplace(staging, destination)
        _assert_directory(parent, parent_identity, "editorial output parent")
        _assert_directory(destination, staging_identity, "published editorial evidence")
    except BaseException as primary:
        try:
            _discard_private_directory(staging, staging_identity, expected)
        except EditorialAcceptanceError as cleanup:
            primary.add_note(f"HawEdit editorial-evidence cleanup also failed: {cleanup}")
        if isinstance(primary, FileExistsError):
            raise EditorialAcceptanceError(
                f"refusing to overwrite editorial evidence {destination}; another publisher won"
            ) from primary
        if isinstance(primary, OSError):
            raise EditorialAcceptanceError(
                f"cannot atomically publish editorial evidence {destination}: {primary}"
            ) from primary
        raise
    return destination


def _verdict(document: object, field: str) -> JudgeVerdict:
    raw = _strict_object(document, field)
    _exact_fields(raw, set(_VERDICT_FIELDS), field)
    try:
        return JudgeVerdict.from_dict(raw)
    except (KeyError, TypeError, ValueError) as exc:
        raise EditorialAcceptanceError(f"invalid {field}: {exc}") from exc


@dataclass(frozen=True, slots=True)
class _CandidateRecord:
    item_id: str
    media_id: str
    media_path: str
    media_duration_ms: int
    dialect: Dialect
    discovery_path: DiscoveryPath
    rank: int
    incumbent: JudgeVerdict
    shadow: JudgeVerdict

    @staticmethod
    def from_dict(value: object) -> _CandidateRecord:
        raw = _strict_object(value, "candidate inventory item")
        _exact_fields(
            raw,
            {
                "dialect",
                "discovery_path",
                "incumbent",
                "item_id",
                "media_duration_ms",
                "media_id",
                "media_path",
                "rank",
                "shadow",
            },
            "candidate inventory item",
        )
        if not isinstance(raw["dialect"], str):
            raise EditorialAcceptanceError("candidate dialect must be a string")
        if not isinstance(raw["discovery_path"], str):
            raise EditorialAcceptanceError("candidate discovery_path must be a string")
        try:
            dialect = Dialect(raw["dialect"])
            discovery_path = DiscoveryPath(raw["discovery_path"])
        except ValueError as exc:
            raise EditorialAcceptanceError(f"invalid candidate enum: {exc}") from exc
        incumbent = _verdict(raw["incumbent"], "incumbent verdict")
        shadow = _verdict(raw["shadow"], "shadow verdict")
        if incumbent.judge != KURDISH_EDITORIAL_JUDGE:
            raise EditorialAcceptanceError("incumbent verdict is not from the pinned judge")
        if shadow.judge != JUDGE_SHADOW:
            raise EditorialAcceptanceError("shadow verdict is not from the registered shadow")
        incumbent_span = (
            incumbent.candidate_id,
            incumbent.clip_in_ms,
            incumbent.clip_out_ms,
        )
        shadow_span = (shadow.candidate_id, shadow.clip_in_ms, shadow.clip_out_ms)
        if incumbent_span != shadow_span:
            raise EditorialAcceptanceError("incumbent and shadow evaluated different footage")
        duration = _exact_int(raw["media_duration_ms"], "media_duration_ms", minimum=1)
        if not 0 <= incumbent.clip_in_ms < incumbent.clip_out_ms <= duration:
            raise EditorialAcceptanceError(
                "candidate clip falls outside its declared media duration"
            )
        rank = _exact_int(raw["rank"], "candidate rank", minimum=1)
        if rank > 20:
            raise EditorialAcceptanceError("§8.2 inventory ranks must be within Recall@20")
        return _CandidateRecord(
            item_id=_one_line(raw["item_id"], "candidate item_id"),
            media_id=_one_line(raw["media_id"], "candidate media_id"),
            media_path=_relative_path(raw["media_path"], "candidate media_path"),
            media_duration_ms=duration,
            dialect=dialect,
            discovery_path=discovery_path,
            rank=rank,
            incumbent=incumbent,
            shadow=shadow,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "dialect": self.dialect.value,
            "discovery_path": self.discovery_path.value,
            "incumbent": self.incumbent.to_dict(),
            "item_id": self.item_id,
            "media_duration_ms": self.media_duration_ms,
            "media_id": self.media_id,
            "media_path": self.media_path,
            "rank": self.rank,
            "shadow": self.shadow.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class _Economics:
    total_cost_usd: float
    total_wallclock_s: float

    @staticmethod
    def from_dict(value: object, field: str) -> _Economics:
        raw = _strict_object(value, field)
        _exact_fields(raw, {"total_cost_usd", "total_wallclock_s"}, field)
        return _Economics(
            _finite_number(raw["total_cost_usd"], f"{field}.total_cost_usd"),
            _finite_number(raw["total_wallclock_s"], f"{field}.total_wallclock_s"),
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "total_cost_usd": self.total_cost_usd,
            "total_wallclock_s": self.total_wallclock_s,
        }


@dataclass(frozen=True, slots=True)
class _Inventory:
    study_id: str
    authorized_by: str
    media_authorization: str
    source_duration_s: float
    systems: Mapping[str, _Economics]
    items: tuple[_CandidateRecord, ...]
    sha256: str


def _load_inventory(path: Path) -> _Inventory:
    raw, payload = _load_json(path, "editorial candidate inventory")
    _exact_fields(
        raw,
        {
            "authorized_by",
            "interim",
            "items",
            "media_authorization",
            "schema",
            "source_duration_s",
            "study_id",
            "systems",
        },
        "editorial candidate inventory",
    )
    if _exact_int(raw["schema"], "inventory schema", minimum=1) != _SCHEMA:
        raise EditorialAcceptanceError("unsupported editorial inventory schema")
    if _exact_bool(raw["interim"], "inventory interim"):
        raise EditorialAcceptanceError("an interim inventory cannot become AC-8 evidence")
    systems = _strict_object(raw["systems"], "inventory systems")
    _exact_fields(systems, {"incumbent", "shadow"}, "inventory systems")
    if not isinstance(raw["items"], list):
        raise EditorialAcceptanceError("inventory items must be a JSON array")
    items = tuple(_CandidateRecord.from_dict(value) for value in raw["items"])
    ids = [item.item_id for item in items]
    candidate_ids = [item.incumbent.candidate_id for item in items]
    ranks = [(item.media_id, item.discovery_path, item.rank) for item in items]
    if len(ids) != len(set(ids)):
        raise EditorialAcceptanceError("candidate inventory contains duplicate item ids")
    if len(candidate_ids) != len(set(candidate_ids)):
        raise EditorialAcceptanceError("candidate inventory contains duplicate candidate ids")
    if len(ranks) != len(set(ranks)):
        raise EditorialAcceptanceError("candidate inventory repeats a media/path rank")
    media_by_id: dict[str, tuple[str, int]] = {}
    media_ids_by_path: dict[str, str] = {}
    for item in items:
        identity = (item.media_path, item.media_duration_ms)
        previous = media_by_id.setdefault(item.media_id, identity)
        if previous != identity:
            raise EditorialAcceptanceError(
                f"media id {item.media_id!r} maps to conflicting paths or durations"
            )
        previous_id = media_ids_by_path.setdefault(item.media_path, item.media_id)
        if previous_id != item.media_id:
            raise EditorialAcceptanceError(
                f"media path {item.media_path!r} maps to multiple media ids"
            )
    source_duration_s = _finite_number(raw["source_duration_s"], "source_duration_s", positive=True)
    measured_source_ms = sum(duration for _, duration in media_by_id.values())
    if round(source_duration_s * 1000) != measured_source_ms:
        raise EditorialAcceptanceError(
            f"source_duration_s covers {round(source_duration_s * 1000)} ms, not the "
            f"{measured_source_ms} ms represented by unique media ids"
        )
    return _Inventory(
        study_id=_one_line(raw["study_id"], "study id"),
        authorized_by=_one_line(raw["authorized_by"], "media authorizer"),
        media_authorization=_one_line(raw["media_authorization"], "media authorization"),
        source_duration_s=source_duration_s,
        systems={
            "incumbent": _Economics.from_dict(systems["incumbent"], "incumbent economics"),
            "shadow": _Economics.from_dict(systems["shadow"], "shadow economics"),
        },
        items=items,
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def _rank_digest(namespace: str, inventory: _Inventory, item: _CandidateRecord) -> str:
    payload = b"\0".join(
        (
            namespace.encode("ascii"),
            inventory.sha256.encode("ascii"),
            inventory.study_id.encode("utf-8"),
            item.item_id.encode("utf-8"),
            hashlib.sha256(_canonical_json(item.to_dict())).hexdigest().encode("ascii"),
        )
    )
    return hashlib.sha256(payload).hexdigest()


def _stratified_sample(inventory: _Inventory, sample_size: int) -> tuple[_CandidateRecord, ...]:
    if type(sample_size) is not int or not MIN_STUDY_ITEMS <= sample_size <= MAX_STUDY_ITEMS:
        raise EditorialAcceptanceError(
            f"sample_size must be an integer in [{MIN_STUDY_ITEMS}, {MAX_STUDY_ITEMS}]"
        )
    if len(inventory.items) < sample_size:
        raise EditorialAcceptanceError(
            f"inventory has {len(inventory.items)} candidates, fewer than requested {sample_size}"
        )
    dialects = tuple(Dialect)
    base, remainder = divmod(sample_size, len(dialects))
    selected: list[_CandidateRecord] = []
    for index, dialect in enumerate(dialects):
        quota = base + (1 if index < remainder else 0)
        choices = sorted(
            (item for item in inventory.items if item.dialect is dialect),
            key=lambda item: (
                _rank_digest("hawedit-editorial-sample-v1", inventory, item),
                item.item_id,
            ),
        )
        if len(choices) < quota:
            raise EditorialAcceptanceError(
                f"inventory has {len(choices)} {dialect.value} candidates; deterministic "
                f"stratification requires {quota}"
            )
        selected.extend(choices[:quota])
    return tuple(sorted(selected, key=lambda item: item.item_id))


def _visible_verdict(verdict: JudgeVerdict) -> dict[str, object]:
    return {
        "description_ckb": verdict.description_ckb,
        "hashtags_ckb": list(verdict.hashtags_ckb),
        "title_ckb": verdict.title_ckb,
    }


@dataclass(frozen=True, slots=True)
class _StudyItem:
    review_id: str
    split: str
    option_a: str
    media_sha256: str
    source: _CandidateRecord

    def to_dict(self) -> dict[str, object]:
        return {
            "media_sha256": self.media_sha256,
            "option_a": self.option_a,
            "review_id": self.review_id,
            "source": self.source.to_dict(),
            "source_item_sha256": hashlib.sha256(
                _canonical_json(self.source.to_dict())
            ).hexdigest(),
            "split": self.split,
        }

    @staticmethod
    def from_dict(value: object) -> _StudyItem:
        raw = _strict_object(value, "study item")
        _exact_fields(
            raw,
            {
                "media_sha256",
                "option_a",
                "review_id",
                "source",
                "source_item_sha256",
                "split",
            },
            "study item",
        )
        source = _CandidateRecord.from_dict(raw["source"])
        expected = hashlib.sha256(_canonical_json(source.to_dict())).hexdigest()
        if _digest(raw["source_item_sha256"], "source item SHA-256") != expected:
            raise EditorialAcceptanceError("study item source digest does not match its content")
        split = _one_line(raw["split"], "study split")
        if split not in {"training", "holdout"}:
            raise EditorialAcceptanceError("study split must be training or holdout")
        option_a = _one_line(raw["option_a"], "study option A identity")
        if option_a not in {"incumbent", "shadow"}:
            raise EditorialAcceptanceError("study option A identity must be incumbent or shadow")
        review_id = _one_line(raw["review_id"], "study review id")
        if re.fullmatch(r"review-[0-9a-f]{24}", review_id) is None:
            raise EditorialAcceptanceError("study review id is not a generated opaque id")
        return _StudyItem(
            review_id=review_id,
            split=split,
            option_a=option_a,
            media_sha256=_digest(raw["media_sha256"], "study media SHA-256"),
            source=source,
        )


def _review_item(item: _StudyItem) -> dict[str, object]:
    source = item.source
    option_a = source.incumbent if item.option_a == "incumbent" else source.shadow
    option_b = source.shadow if item.option_a == "incumbent" else source.incumbent
    return {
        "clip_in_ms": source.incumbent.clip_in_ms,
        "clip_out_ms": source.incumbent.clip_out_ms,
        "dialect": source.dialect.value,
        "media_path": source.media_path,
        "option_a": _visible_verdict(option_a),
        "option_b": _visible_verdict(option_b),
        "review_id": item.review_id,
    }


def _review_packet(
    study_id: str, manifest_sha256: str, items: Sequence[_StudyItem]
) -> dict[str, Any]:
    return {
        "items": [_review_item(item) for item in items],
        "manifest_sha256": manifest_sha256,
        "schema": _SCHEMA,
        "study_id": study_id,
    }


def _freeze_study_items(
    inventory: _Inventory,
    media_root: Path,
    media_root_identity: tuple[int, int],
    sample_size: int,
) -> tuple[_StudyItem, ...]:
    selected = _stratified_sample(inventory, sample_size)
    by_dialect: dict[Dialect, list[_CandidateRecord]] = defaultdict(list)
    for item in selected:
        by_dialect[item.dialect].append(item)
    holdout_ids: set[str] = set()
    for dialect in Dialect:
        choices = sorted(
            by_dialect[dialect],
            key=lambda item: (
                _rank_digest("hawedit-editorial-holdout-v1", inventory, item),
                item.item_id,
            ),
        )
        holdout_count = max(1, len(choices) // 5)
        holdout_ids.update(item.item_id for item in choices[:holdout_count])

    media_hashes: dict[str, tuple[str, int]] = {}
    digest_paths: dict[str, str] = {}
    study_items: list[_StudyItem] = []
    review_ids: set[str] = set()
    for source in selected:
        media_identity = media_hashes.get(source.media_path)
        if media_identity is None:
            media = _contained_media(media_root, source.media_path)
            media_sha256 = _verified_video_identity(
                media,
                f"{source.item_id} editorial media",
                source.media_duration_ms,
            )
            duplicate_path = digest_paths.get(media_sha256)
            if duplicate_path is not None and duplicate_path != source.media_path:
                raise EditorialAcceptanceError(
                    f"identical media bytes appear under {duplicate_path!r} and "
                    f"{source.media_path!r}"
                )
            digest_paths[media_sha256] = source.media_path
            media_hashes[source.media_path] = (media_sha256, source.media_duration_ms)
        else:
            media_sha256, measured_duration_ms = media_identity
            if measured_duration_ms != source.media_duration_ms:
                raise EditorialAcceptanceError(
                    f"{source.item_id}: one media path declares conflicting durations"
                )
        rank = _rank_digest("hawedit-editorial-review-id-v1", inventory, source)
        review_id = f"review-{rank[:24]}"
        if review_id in review_ids:
            raise EditorialAcceptanceError("generated editorial review ids collided")
        review_ids.add(review_id)
        blind = _rank_digest("hawedit-editorial-blind-v1", inventory, source)
        study_items.append(
            _StudyItem(
                review_id=review_id,
                split="holdout" if source.item_id in holdout_ids else "training",
                option_a="incumbent" if int(blind[-1], 16) % 2 == 0 else "shadow",
                media_sha256=media_sha256,
                source=source,
            )
        )
    _assert_directory(media_root, media_root_identity, "editorial media root")
    return tuple(sorted(study_items, key=lambda item: item.review_id))


def _study_manifest(
    inventory: _Inventory, items: Sequence[_StudyItem], sample_size: int
) -> dict[str, object]:
    return {
        "authorized_by": inventory.authorized_by,
        "inventory_sha256": inventory.sha256,
        "items": [item.to_dict() for item in items],
        "media_authorization": inventory.media_authorization,
        "sample_size": sample_size,
        "schema": _SCHEMA,
        "selection_policy": "sha256-content-ranked-near-equal-dialect-v1",
        "source_duration_s": inventory.source_duration_s,
        "split_policy": "sha256-content-ranked-per-dialect-floor-20-percent-v1",
        "study_id": inventory.study_id,
        "systems": {name: value.to_dict() for name, value in inventory.systems.items()},
    }


@dataclass(frozen=True, slots=True)
class PreparedEditorialStudy:
    output_dir: Path
    manifest_path: Path
    review_packet_path: Path
    coordinator_approval_template_path: Path
    reviewer_template_path: Path
    adjudication_template_path: Path
    manifest_sha256: str
    review_packet_sha256: str


def prepare_editorial_study(
    *, inventory_path: Path, media_root: Path, output_dir: Path, sample_size: int
) -> PreparedEditorialStudy:
    """Freeze a deterministic, blinded, unsigned human-study packet."""
    inventory = _load_inventory(inventory_path)
    root, root_identity = _bound_directory(media_root, "editorial media root")
    study_items = _freeze_study_items(inventory, root, root_identity, sample_size)
    manifest = _study_manifest(inventory, study_items, sample_size)
    manifest_bytes = _canonical_json(manifest)
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    packet = _review_packet(inventory.study_id, manifest_sha256, study_items)
    packet_bytes = _canonical_json(packet)
    packet_sha256 = hashlib.sha256(packet_bytes).hexdigest()
    approval = {
        "approved_at_utc": "",
        "approved_by": "",
        "manifest_sha256": manifest_sha256,
        "media_rights_attested": False,
        "review_packet_sha256": packet_sha256,
        "role": "coordinator",
        "schema": _SCHEMA,
    }
    labels = [
        {
            "gold_in_ms": None,
            "gold_out_ms": None,
            "is_winner": None,
            "misleading": None,
            "preference": None,
            "review_id": item.review_id,
            "sentence_complete": None,
        }
        for item in study_items
    ]
    reviewer = {
        "completed_at_utc": "",
        "labels": labels,
        "manifest_sha256": manifest_sha256,
        "review_packet_sha256": packet_sha256,
        "reviewer_id": "",
        "role": "reviewer",
        "schema": _SCHEMA,
    }
    adjudication = {
        "adjudicator_id": "",
        "completed_at_utc": "",
        "manifest_sha256": manifest_sha256,
        "resolutions": [],
        "review_packet_sha256": packet_sha256,
        "role": "adjudicator",
        "schema": _SCHEMA,
    }
    instructions = (
        "HawEdit blinded editorial acceptance study\n\n"
        "Coordinator: keep study-manifest.json private; it contains the A/B answer key and "
        "training/holdout split. Distribute only review-packet.json and one independently copied "
        "reviewer.template.json to each reviewer.\n"
        "Fill and OpenSSH-sign coordinator approval, both reviewer files, and the distinct "
        f"adjudicator file with namespace {SIGNATURE_NAMESPACE}. Reviewers must label every item "
        "without seeing the manifest. The adjudicator must resolve exactly the fields on which "
        "the two signed reviews disagree.\n"
        "Run `python -m hawedit.editorial_acceptance evaluate --help` for the exact "
        "import command. "
        "Private keys, trust files, signatures, client media, and completed human labels stay "
        "outside Git.\n"
    )
    published = _publish_exact_directory(
        output_dir,
        {
            "INSTRUCTIONS.txt": instructions.encode("utf-8"),
            "adjudication.template.json": _canonical_json(adjudication),
            "coordinator-approval.template.json": _canonical_json(approval),
            "review-packet.json": packet_bytes,
            "reviewer.template.json": _canonical_json(reviewer),
            "study-manifest.json": manifest_bytes,
        },
    )
    return PreparedEditorialStudy(
        output_dir=published,
        manifest_path=published / "study-manifest.json",
        review_packet_path=published / "review-packet.json",
        coordinator_approval_template_path=published / "coordinator-approval.template.json",
        reviewer_template_path=published / "reviewer.template.json",
        adjudication_template_path=published / "adjudication.template.json",
        manifest_sha256=manifest_sha256,
        review_packet_sha256=packet_sha256,
    )


@dataclass(frozen=True, slots=True)
class _Study:
    study_id: str
    authorized_by: str
    media_authorization: str
    source_duration_s: float
    systems: Mapping[str, _Economics]
    items: tuple[_StudyItem, ...]


def _parse_study(raw: Mapping[str, Any]) -> _Study:
    _exact_fields(
        raw,
        {
            "authorized_by",
            "inventory_sha256",
            "items",
            "media_authorization",
            "sample_size",
            "schema",
            "selection_policy",
            "source_duration_s",
            "split_policy",
            "study_id",
            "systems",
        },
        "editorial study manifest",
    )
    if _exact_int(raw["schema"], "study schema", minimum=1) != _SCHEMA:
        raise EditorialAcceptanceError("unsupported editorial study schema")
    _digest(raw["inventory_sha256"], "inventory SHA-256")
    if raw["selection_policy"] != "sha256-content-ranked-near-equal-dialect-v1":
        raise EditorialAcceptanceError("editorial selection policy drifted")
    if raw["split_policy"] != "sha256-content-ranked-per-dialect-floor-20-percent-v1":
        raise EditorialAcceptanceError("editorial split policy drifted")
    if not isinstance(raw["items"], list):
        raise EditorialAcceptanceError("study items must be a JSON array")
    items = tuple(_StudyItem.from_dict(value) for value in raw["items"])
    sample_size = _exact_int(raw["sample_size"], "study sample_size", minimum=1)
    if sample_size != len(items) or not MIN_STUDY_ITEMS <= sample_size <= MAX_STUDY_ITEMS:
        raise EditorialAcceptanceError("study sample size is outside 200–500 or mismatches items")
    review_ids = [item.review_id for item in items]
    source_ids = [item.source.item_id for item in items]
    if len(review_ids) != len(set(review_ids)) or len(source_ids) != len(set(source_ids)):
        raise EditorialAcceptanceError("study manifest contains duplicate item identities")
    counts = Counter(item.source.dialect for item in items)
    if max(counts.values()) - min(counts.values()) > 1 or set(counts) != set(Dialect):
        raise EditorialAcceptanceError("study dialect sample is not near-equally stratified")
    for dialect in Dialect:
        dialect_items = [item for item in items if item.source.dialect is dialect]
        expected_holdout = max(1, len(dialect_items) // 5)
        actual_holdout = sum(item.split == "holdout" for item in dialect_items)
        if actual_holdout != expected_holdout:
            raise EditorialAcceptanceError(f"{dialect.value} holdout count drifted")
    systems = _strict_object(raw["systems"], "study systems")
    _exact_fields(systems, {"incumbent", "shadow"}, "study systems")
    return _Study(
        study_id=_one_line(raw["study_id"], "study id"),
        authorized_by=_one_line(raw["authorized_by"], "media authorizer"),
        media_authorization=_one_line(raw["media_authorization"], "media authorization"),
        source_duration_s=_finite_number(
            raw["source_duration_s"], "source_duration_s", positive=True
        ),
        systems={
            "incumbent": _Economics.from_dict(systems["incumbent"], "incumbent economics"),
            "shadow": _Economics.from_dict(systems["shadow"], "shadow economics"),
        },
        items=items,
    )


@dataclass(frozen=True, slots=True)
class _SignatureEvidence:
    document_sha256: str
    signature_sha256: str
    key_fingerprint: str


def _verify_signature(
    *,
    document_bytes: bytes,
    signature_path: Path,
    allowed_signers_bytes: bytes,
    identity: str,
    ssh_keygen: str,
) -> _SignatureEvidence:
    signature = _read_bound_file(signature_path, "editorial signature", maximum=1024 * 1024)
    executable = shutil.which(ssh_keygen)
    if executable is None:
        raise EditorialAcceptanceError(f"OpenSSH verifier {ssh_keygen!r} is unavailable")
    with tempfile.TemporaryDirectory(prefix="hawedit-editorial-signature-") as temporary:
        directory = Path(temporary)
        signature_snapshot = directory / "document.sig"
        signers_snapshot = directory / "allowed_signers"
        signature_snapshot.write_bytes(signature)
        signers_snapshot.write_bytes(allowed_signers_bytes)
        try:
            result = subprocess.run(
                [
                    executable,
                    "-Y",
                    "verify",
                    "-f",
                    str(signers_snapshot),
                    "-I",
                    identity,
                    "-n",
                    SIGNATURE_NAMESPACE,
                    "-s",
                    str(signature_snapshot),
                ],
                input=document_bytes,
                capture_output=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise EditorialAcceptanceError(
                f"editorial signature verification failed: {exc}"
            ) from exc
    if result.returncode != 0:
        raise EditorialAcceptanceError("editorial signature verification failed")
    verifier_output = result.stdout + b"\n" + result.stderr
    if len(verifier_output) > 8192:
        raise EditorialAcceptanceError("OpenSSH signature-verifier output exceeded 8192 bytes")
    fingerprints = {
        match.group(1).decode("ascii") for match in _SIGNER_FINGERPRINT.finditer(verifier_output)
    }
    if len(fingerprints) != 1:
        raise EditorialAcceptanceError(
            "OpenSSH signature verification did not identify exactly one signing key"
        )
    return _SignatureEvidence(
        hashlib.sha256(document_bytes).hexdigest(),
        hashlib.sha256(signature).hexdigest(),
        fingerprints.pop(),
    )


def _timestamp(value: object, field: str) -> str:
    timestamp = _one_line(value, field)
    if _RFC3339_UTC.fullmatch(timestamp) is None:
        raise EditorialAcceptanceError(f"{field} must be exact UTC YYYY-MM-DDTHH:MM:SSZ")
    return timestamp


@dataclass(frozen=True, slots=True)
class _HumanLabel:
    review_id: str
    preference: str
    is_winner: bool
    misleading: bool
    sentence_complete: bool
    gold_in_ms: int | None
    gold_out_ms: int | None

    @staticmethod
    def from_dict(value: object, item: _StudyItem) -> _HumanLabel:
        raw = _strict_object(value, "human editorial label")
        _exact_fields(
            raw,
            {
                "gold_in_ms",
                "gold_out_ms",
                "is_winner",
                "misleading",
                "preference",
                "review_id",
                "sentence_complete",
            },
            "human editorial label",
        )
        review_id = _one_line(raw["review_id"], "label review_id")
        if review_id != item.review_id:
            raise EditorialAcceptanceError("human label names the wrong review item")
        preference = _one_line(raw["preference"], "human preference")
        if preference not in {"a", "b", "tie"}:
            raise EditorialAcceptanceError("human preference must be a, b, or tie")
        is_winner = _exact_bool(raw["is_winner"], "is_winner")
        gold_in_raw = raw["gold_in_ms"]
        gold_out_raw = raw["gold_out_ms"]
        if is_winner:
            gold_in = _exact_int(gold_in_raw, "gold_in_ms")
            gold_out = _exact_int(gold_out_raw, "gold_out_ms", minimum=1)
            if not 0 <= gold_in < gold_out <= item.source.media_duration_ms:
                raise EditorialAcceptanceError("human gold span falls outside source media")
        else:
            if gold_in_raw is not None or gold_out_raw is not None:
                raise EditorialAcceptanceError("a non-winner must have null gold span bounds")
            gold_in = None
            gold_out = None
        return _HumanLabel(
            review_id=review_id,
            preference=preference,
            is_winner=is_winner,
            misleading=_exact_bool(raw["misleading"], "misleading"),
            sentence_complete=_exact_bool(raw["sentence_complete"], "sentence_complete"),
            gold_in_ms=gold_in,
            gold_out_ms=gold_out,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "gold_in_ms": self.gold_in_ms,
            "gold_out_ms": self.gold_out_ms,
            "is_winner": self.is_winner,
            "misleading": self.misleading,
            "preference": self.preference,
            "review_id": self.review_id,
            "sentence_complete": self.sentence_complete,
        }


@dataclass(frozen=True, slots=True)
class _Review:
    reviewer_id: str
    completed_at_utc: str
    labels: Mapping[str, _HumanLabel]
    evidence: _SignatureEvidence


def _load_review(
    *,
    path: Path,
    signature_path: Path,
    allowed_signers_bytes: bytes,
    manifest_sha256: str,
    packet_sha256: str,
    items: Mapping[str, _StudyItem],
    ssh_keygen: str,
) -> _Review:
    raw, payload = _load_json(path, "signed editorial review")
    _exact_fields(
        raw,
        {
            "completed_at_utc",
            "labels",
            "manifest_sha256",
            "review_packet_sha256",
            "reviewer_id",
            "role",
            "schema",
        },
        "signed editorial review",
    )
    if _exact_int(raw["schema"], "review schema", minimum=1) != _SCHEMA:
        raise EditorialAcceptanceError("unsupported editorial review schema")
    if raw["role"] != "reviewer":
        raise EditorialAcceptanceError("signed editorial review has the wrong role")
    if _digest(raw["manifest_sha256"], "review manifest SHA-256") != manifest_sha256:
        raise EditorialAcceptanceError("review names a different study manifest")
    if _digest(raw["review_packet_sha256"], "review packet SHA-256") != packet_sha256:
        raise EditorialAcceptanceError("review names a different blinded packet")
    reviewer_id = _one_line(raw["reviewer_id"], "reviewer id")
    if not isinstance(raw["labels"], list):
        raise EditorialAcceptanceError("review labels must be a JSON array")
    labels: dict[str, _HumanLabel] = {}
    for value in raw["labels"]:
        value_object = _strict_object(value, "human editorial label")
        review_id = value_object.get("review_id")
        if not isinstance(review_id, str) or review_id not in items:
            raise EditorialAcceptanceError("review contains an unknown review id")
        if review_id in labels:
            raise EditorialAcceptanceError("review contains duplicate labels")
        labels[review_id] = _HumanLabel.from_dict(value_object, items[review_id])
    if set(labels) != set(items):
        raise EditorialAcceptanceError("review does not label the exact sampled item set")
    evidence = _verify_signature(
        document_bytes=payload,
        signature_path=signature_path,
        allowed_signers_bytes=allowed_signers_bytes,
        identity=reviewer_id,
        ssh_keygen=ssh_keygen,
    )
    return _Review(
        reviewer_id, _timestamp(raw["completed_at_utc"], "review timestamp"), labels, evidence
    )


def _load_approval(
    *,
    path: Path,
    signature_path: Path,
    allowed_signers_bytes: bytes,
    study: _Study,
    manifest_sha256: str,
    packet_sha256: str,
    ssh_keygen: str,
) -> tuple[str, str, _SignatureEvidence]:
    raw, payload = _load_json(path, "signed editorial coordinator approval")
    _exact_fields(
        raw,
        {
            "approved_at_utc",
            "approved_by",
            "manifest_sha256",
            "media_rights_attested",
            "review_packet_sha256",
            "role",
            "schema",
        },
        "signed editorial coordinator approval",
    )
    if _exact_int(raw["schema"], "approval schema", minimum=1) != _SCHEMA:
        raise EditorialAcceptanceError("unsupported coordinator approval schema")
    if raw["role"] != "coordinator":
        raise EditorialAcceptanceError("coordinator approval has the wrong role")
    identity = _one_line(raw["approved_by"], "coordinator identity")
    if identity != study.authorized_by:
        raise EditorialAcceptanceError("coordinator identity does not match media authorization")
    if not _exact_bool(raw["media_rights_attested"], "media_rights_attested"):
        raise EditorialAcceptanceError("coordinator did not attest media rights")
    if _digest(raw["manifest_sha256"], "approval manifest SHA-256") != manifest_sha256:
        raise EditorialAcceptanceError("coordinator approved a different study manifest")
    if _digest(raw["review_packet_sha256"], "approval packet SHA-256") != packet_sha256:
        raise EditorialAcceptanceError("coordinator approved a different review packet")
    evidence = _verify_signature(
        document_bytes=payload,
        signature_path=signature_path,
        allowed_signers_bytes=allowed_signers_bytes,
        identity=identity,
        ssh_keygen=ssh_keygen,
    )
    return identity, _timestamp(raw["approved_at_utc"], "approval timestamp"), evidence


def _load_adjudication(
    *,
    path: Path,
    signature_path: Path,
    allowed_signers_bytes: bytes,
    manifest_sha256: str,
    packet_sha256: str,
    disagreements: set[str],
    items: Mapping[str, _StudyItem],
    ssh_keygen: str,
) -> tuple[
    str,
    str,
    Mapping[str, _HumanLabel],
    Mapping[str, str],
    _SignatureEvidence,
]:
    raw, payload = _load_json(path, "signed editorial adjudication")
    _exact_fields(
        raw,
        {
            "adjudicator_id",
            "completed_at_utc",
            "manifest_sha256",
            "resolutions",
            "review_packet_sha256",
            "role",
            "schema",
        },
        "signed editorial adjudication",
    )
    if _exact_int(raw["schema"], "adjudication schema", minimum=1) != _SCHEMA:
        raise EditorialAcceptanceError("unsupported adjudication schema")
    if raw["role"] != "adjudicator":
        raise EditorialAcceptanceError("editorial adjudication has the wrong role")
    if _digest(raw["manifest_sha256"], "adjudication manifest SHA-256") != manifest_sha256:
        raise EditorialAcceptanceError("adjudication names a different study manifest")
    if _digest(raw["review_packet_sha256"], "adjudication packet SHA-256") != packet_sha256:
        raise EditorialAcceptanceError("adjudication names a different review packet")
    identity = _one_line(raw["adjudicator_id"], "adjudicator id")
    if not isinstance(raw["resolutions"], list):
        raise EditorialAcceptanceError("adjudication resolutions must be a JSON array")
    resolutions: dict[str, _HumanLabel] = {}
    reasons: dict[str, str] = {}
    for entry in raw["resolutions"]:
        resolution = _strict_object(entry, "adjudication resolution")
        _exact_fields(
            resolution,
            {
                "gold_in_ms",
                "gold_out_ms",
                "is_winner",
                "misleading",
                "preference",
                "reason",
                "review_id",
                "sentence_complete",
            },
            "adjudication resolution",
        )
        review_id = resolution.get("review_id")
        if not isinstance(review_id, str) or review_id not in items:
            raise EditorialAcceptanceError("adjudication contains an unknown review id")
        if review_id in resolutions:
            raise EditorialAcceptanceError("adjudication repeats a resolution")
        reasons[review_id] = _one_line(resolution["reason"], "adjudication reason")
        label_payload = {key: value for key, value in resolution.items() if key != "reason"}
        resolutions[review_id] = _HumanLabel.from_dict(label_payload, items[review_id])
    if set(resolutions) != disagreements:
        raise EditorialAcceptanceError(
            "adjudication must resolve exactly the reviewer disagreements; "
            f"expected={sorted(disagreements)}, actual={sorted(resolutions)}"
        )
    evidence = _verify_signature(
        document_bytes=payload,
        signature_path=signature_path,
        allowed_signers_bytes=allowed_signers_bytes,
        identity=identity,
        ssh_keygen=ssh_keygen,
    )
    return (
        identity,
        _timestamp(raw["completed_at_utc"], "adjudication timestamp"),
        resolutions,
        reasons,
        evidence,
    )


def _system_preference(item: _StudyItem, preference: str) -> str | None:
    if preference == "tie":
        return None
    if preference == "a":
        return item.option_a
    return "shadow" if item.option_a == "incumbent" else "incumbent"


def _labels_document(
    *,
    split: str,
    manifest_sha256: str,
    items: Sequence[_StudyItem],
    labels: Mapping[str, _HumanLabel],
) -> dict[str, object]:
    return {
        "items": [
            {
                "candidate_id": item.source.incumbent.candidate_id,
                "dialect": item.source.dialect.value,
                "discovery_path": item.source.discovery_path.value,
                "label": labels[item.review_id].to_dict(),
                "media_id": item.source.media_id,
                "media_sha256": item.media_sha256,
                "rank": item.source.rank,
                "source_item_id": item.source.item_id,
            }
            for item in items
        ],
        "manifest_sha256": manifest_sha256,
        "schema": _SCHEMA,
        "split": split,
    }


def _slice_report(
    items: Sequence[_StudyItem], labels: Mapping[str, _HumanLabel]
) -> dict[str, object]:
    preferences: Counter[str] = Counter()
    comparisons: list[tuple[str, str, str | None]] = []
    gold: list[GoldCandidate] = []
    retrieved: list[RetrievedCandidate] = []
    overlaps: list[float] = []
    shipped_complete: list[bool] = []
    for item in items:
        label = labels[item.review_id]
        winner = _system_preference(item, label.preference)
        preferences[winner or "tie"] += 1
        comparisons.append(("incumbent", "shadow", winner))
        gold_span = (
            (label.gold_in_ms, label.gold_out_ms)
            if label.gold_in_ms is not None and label.gold_out_ms is not None
            else (item.source.incumbent.clip_in_ms, item.source.incumbent.clip_out_ms)
        )
        gold.append(
            GoldCandidate(
                candidate_id=item.source.item_id,
                media_id=item.source.media_id,
                in_ms=gold_span[0],
                out_ms=gold_span[1],
                discovery_path=item.source.discovery_path,
                is_winner=label.is_winner,
                misleading=label.misleading,
            )
        )
        retrieved.append(
            RetrievedCandidate(
                media_id=item.source.media_id,
                in_ms=item.source.incumbent.clip_in_ms,
                out_ms=item.source.incumbent.clip_out_ms,
                discovery_path=item.source.discovery_path,
                rank=item.source.rank,
            )
        )
        if label.is_winner:
            overlaps.append(
                temporal_iou(
                    (item.source.incumbent.clip_in_ms, item.source.incumbent.clip_out_ms),
                    gold_span,
                )
            )
            shipped_complete.append(label.sentence_complete)
    decision = decide_judge(
        incumbent_wins=preferences["incumbent"],
        shadow_wins=preferences["shadow"],
        ties=preferences["tie"],
    )
    recall = recall_at_k_by_path(retrieved, gold)
    unique = path_unique_wins(retrieved, gold)
    return {
        "decision": {
            "challenger": decision.challenger,
            "incumbent": decision.incumbent,
            "reasons": list(decision.reasons),
            "switch": decision.switch,
        },
        "items_by_dialect": {
            dialect.value: sum(item.source.dialect is dialect for item in items)
            for dialect in Dialect
        },
        "mean_temporal_iou": sum(overlaps) / len(overlaps) if overlaps else None,
        "misleading_edit_rate": misleading_edit_rate([item for item in gold if item.is_winner]),
        "pairwise_preference": dict(pairwise_preference(comparisons)),
        "path_unique_wins": {path.value: count for path, count in unique.items()},
        "preference_counts": {
            "incumbent": preferences["incumbent"],
            "shadow": preferences["shadow"],
            "tie": preferences["tie"],
        },
        "recall_at_20_by_path": {path.value: score for path, score in recall.items()},
        "sentence_completeness_rate": sentence_completeness_rate(shipped_complete),
        "total_items": len(items),
        "winner_count": sum(
            label.is_winner for label in (labels[item.review_id] for item in items)
        ),
    }


@dataclass(frozen=True, slots=True)
class VerifiedEditorialStudy:
    output_dir: Path
    report_path: Path
    training_labels_path: Path
    holdout_labels_path: Path
    manifest_sha256: str
    review_packet_sha256: str
    reviewer_ids: tuple[str, str]
    adjudicator_id: str


def evaluate_editorial_study(
    *,
    inventory_path: Path,
    manifest_path: Path,
    review_packet_path: Path,
    media_root: Path,
    approval_path: Path,
    approval_signature_path: Path,
    reviewer_one_path: Path,
    reviewer_one_signature_path: Path,
    reviewer_two_path: Path,
    reviewer_two_signature_path: Path,
    adjudication_path: Path,
    adjudication_signature_path: Path,
    allowed_signers_path: Path,
    output_dir: Path,
    ssh_keygen: str = "ssh-keygen",
) -> VerifiedEditorialStudy:
    """Verify all human evidence and atomically publish separate train/holdout reports."""
    manifest_raw, manifest_bytes = _load_json(manifest_path, "editorial study manifest")
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    study = _parse_study(manifest_raw)
    inventory = _load_inventory(inventory_path)
    if manifest_raw["inventory_sha256"] != inventory.sha256:
        raise EditorialAcceptanceError("editorial inventory changed after study preparation")
    root, root_identity = _bound_directory(media_root, "editorial media root")
    expected_items = _freeze_study_items(inventory, root, root_identity, len(study.items))
    expected_media = {item.review_id: item.media_sha256 for item in expected_items}
    for item in study.items:
        if expected_media.get(item.review_id) != item.media_sha256:
            raise EditorialAcceptanceError(
                f"{item.source.item_id}: media changed after the study was frozen"
            )
    expected_manifest = _canonical_json(
        _study_manifest(inventory, expected_items, len(study.items))
    )
    if manifest_bytes != expected_manifest:
        raise EditorialAcceptanceError(
            "editorial study manifest was not produced by the deterministic sampler"
        )
    packet_raw, packet_bytes = _load_json(review_packet_path, "blinded review packet")
    packet_sha256 = hashlib.sha256(packet_bytes).hexdigest()
    expected_packet = _canonical_json(_review_packet(study.study_id, manifest_sha256, study.items))
    if packet_bytes != expected_packet:
        raise EditorialAcceptanceError("blinded review packet does not match the study manifest")
    if packet_raw.get("manifest_sha256") != manifest_sha256:
        raise EditorialAcceptanceError("blinded review packet names a different manifest")
    allowed_signers_bytes = _read_bound_file(
        allowed_signers_path, "editorial allowed signers", maximum=1024 * 1024
    )
    allowed_signers_sha256 = hashlib.sha256(allowed_signers_bytes).hexdigest()
    coordinator_id, approval_at, approval_evidence = _load_approval(
        path=approval_path,
        signature_path=approval_signature_path,
        allowed_signers_bytes=allowed_signers_bytes,
        study=study,
        manifest_sha256=manifest_sha256,
        packet_sha256=packet_sha256,
        ssh_keygen=ssh_keygen,
    )
    items_by_review = {item.review_id: item for item in study.items}
    review_one = _load_review(
        path=reviewer_one_path,
        signature_path=reviewer_one_signature_path,
        allowed_signers_bytes=allowed_signers_bytes,
        manifest_sha256=manifest_sha256,
        packet_sha256=packet_sha256,
        items=items_by_review,
        ssh_keygen=ssh_keygen,
    )
    review_two = _load_review(
        path=reviewer_two_path,
        signature_path=reviewer_two_signature_path,
        allowed_signers_bytes=allowed_signers_bytes,
        manifest_sha256=manifest_sha256,
        packet_sha256=packet_sha256,
        items=items_by_review,
        ssh_keygen=ssh_keygen,
    )
    if review_one.reviewer_id == review_two.reviewer_id:
        raise EditorialAcceptanceError("the two independent reviews have the same identity")
    if coordinator_id in {review_one.reviewer_id, review_two.reviewer_id}:
        raise EditorialAcceptanceError(
            "the coordinator must be distinct from both independent reviewers"
        )
    disagreements = {
        review_id
        for review_id in items_by_review
        if review_one.labels[review_id] != review_two.labels[review_id]
    }
    (
        adjudicator_id,
        adjudicated_at,
        resolutions,
        adjudication_reasons,
        adjudication_evidence,
    ) = _load_adjudication(
        path=adjudication_path,
        signature_path=adjudication_signature_path,
        allowed_signers_bytes=allowed_signers_bytes,
        manifest_sha256=manifest_sha256,
        packet_sha256=packet_sha256,
        disagreements=disagreements,
        items=items_by_review,
        ssh_keygen=ssh_keygen,
    )
    if adjudicator_id in {review_one.reviewer_id, review_two.reviewer_id, coordinator_id}:
        raise EditorialAcceptanceError(
            "the adjudicator must be distinct from both reviewers and the coordinator"
        )
    signing_keys = {
        "adjudicator": adjudication_evidence.key_fingerprint,
        "coordinator": approval_evidence.key_fingerprint,
        "reviewer_one": review_one.evidence.key_fingerprint,
        "reviewer_two": review_two.evidence.key_fingerprint,
    }
    if len(set(signing_keys.values())) != len(signing_keys):
        raise EditorialAcceptanceError(
            "coordinator, reviewers, and adjudicator must use four distinct signing keys"
        )
    if approval_at > min(review_one.completed_at_utc, review_two.completed_at_utc):
        raise EditorialAcceptanceError("coordinator approval must not postdate either review")
    if adjudicated_at < max(review_one.completed_at_utc, review_two.completed_at_utc):
        raise EditorialAcceptanceError("adjudication must not predate either review")
    final_labels = {
        review_id: (
            resolutions[review_id] if review_id in disagreements else review_one.labels[review_id]
        )
        for review_id in items_by_review
    }
    training = tuple(item for item in study.items if item.split == "training")
    holdout = tuple(item for item in study.items if item.split == "holdout")
    training_document = _labels_document(
        split="training",
        manifest_sha256=manifest_sha256,
        items=training,
        labels=final_labels,
    )
    holdout_document = _labels_document(
        split="holdout",
        manifest_sha256=manifest_sha256,
        items=holdout,
        labels=final_labels,
    )
    report = {
        "adjudication": {
            "adjudicated_at_utc": adjudicated_at,
            "adjudicator_id": adjudicator_id,
            "disagreement_count": len(disagreements),
            "disagreement_rate": len(disagreements) / len(study.items),
            "resolutions": [
                {
                    "adjudicated_label": resolutions[review_id].to_dict(),
                    "reason": adjudication_reasons[review_id],
                    "review_id": review_id,
                    "reviewer_one_label": review_one.labels[review_id].to_dict(),
                    "reviewer_two_label": review_two.labels[review_id].to_dict(),
                }
                for review_id in sorted(disagreements)
            ],
        },
        "approval": {
            "approved_at_utc": approval_at,
            "approved_by": coordinator_id,
            "media_authorization": study.media_authorization,
        },
        "economics": {
            name: {
                "cost_per_source_hour": cost_per_source_hour(
                    economics.total_cost_usd, study.source_duration_s / 3600.0
                ),
                "wallclock_seconds_per_source_hour": wallclock_per_source_hour(
                    economics.total_wallclock_s, study.source_duration_s / 3600.0
                ),
            }
            for name, economics in study.systems.items()
        },
        "evidence": {
            "adjudication_sha256": adjudication_evidence.document_sha256,
            "adjudication_signature_sha256": adjudication_evidence.signature_sha256,
            "allowed_signers_sha256": allowed_signers_sha256,
            "approval_sha256": approval_evidence.document_sha256,
            "approval_signature_sha256": approval_evidence.signature_sha256,
            "manifest_sha256": manifest_sha256,
            "review_packet_sha256": packet_sha256,
            "reviewer_one_sha256": review_one.evidence.document_sha256,
            "reviewer_one_signature_sha256": review_one.evidence.signature_sha256,
            "reviewer_two_sha256": review_two.evidence.document_sha256,
            "reviewer_two_signature_sha256": review_two.evidence.signature_sha256,
        },
        "holdout": _slice_report(holdout, final_labels),
        "reviewers": [review_one.reviewer_id, review_two.reviewer_id],
        "schema": _SCHEMA,
        "signing_keys": signing_keys,
        "study_id": study.study_id,
        "training": _slice_report(training, final_labels),
    }
    instructions = (
        "Training and holdout labels were published as separate content-bound files. Tune only "
        "against training-labels.json. Do not open holdout-labels.json until the tuning rule, "
        "model, and thresholds are frozen. study-report.json reports both slices separately and "
        "does not claim a threshold was tuned or a model was promoted.\n"
    )
    published = _publish_exact_directory(
        output_dir,
        {
            "INSTRUCTIONS.txt": instructions.encode("utf-8"),
            "holdout-labels.json": _canonical_json(holdout_document),
            "study-report.json": _canonical_json(report),
            "training-labels.json": _canonical_json(training_document),
        },
    )
    return VerifiedEditorialStudy(
        output_dir=published,
        report_path=published / "study-report.json",
        training_labels_path=published / "training-labels.json",
        holdout_labels_path=published / "holdout-labels.json",
        manifest_sha256=manifest_sha256,
        review_packet_sha256=packet_sha256,
        reviewer_ids=(review_one.reviewer_id, review_two.reviewer_id),
        adjudicator_id=adjudicator_id,
    )


def main(argv: Sequence[str] | None = None) -> int:
    use_utf8_streams()
    parser = argparse.ArgumentParser(
        prog=program_name("hawedit.editorial_acceptance"),
        description="Prepare or evaluate a signed, blinded 200–500-item Sorani editorial study",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare", help="freeze an unsigned blinded study packet")
    prepare.add_argument("inventory", type=Path)
    prepare.add_argument("--media-root", type=Path, required=True)
    prepare.add_argument("--output-dir", type=Path, required=True)
    prepare.add_argument("--sample-size", type=int, required=True)

    evaluate = subparsers.add_parser("evaluate", help="verify signatures and publish split reports")
    evaluate.add_argument("manifest", type=Path)
    evaluate.add_argument("review_packet", type=Path)
    evaluate.add_argument("--inventory", type=Path, required=True)
    evaluate.add_argument("--media-root", type=Path, required=True)
    evaluate.add_argument("--approval", type=Path, required=True)
    evaluate.add_argument("--approval-signature", type=Path, required=True)
    evaluate.add_argument("--reviewer-one", type=Path, required=True)
    evaluate.add_argument("--reviewer-one-signature", type=Path, required=True)
    evaluate.add_argument("--reviewer-two", type=Path, required=True)
    evaluate.add_argument("--reviewer-two-signature", type=Path, required=True)
    evaluate.add_argument("--adjudication", type=Path, required=True)
    evaluate.add_argument("--adjudication-signature", type=Path, required=True)
    evaluate.add_argument("--allowed-signers", type=Path, required=True)
    evaluate.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        with machine_readable_stdout() as report_stream:
            if args.command == "prepare":
                prepared = prepare_editorial_study(
                    inventory_path=args.inventory,
                    media_root=args.media_root,
                    output_dir=args.output_dir,
                    sample_size=args.sample_size,
                )
                document: dict[str, object] = {
                    "manifest": str(prepared.manifest_path),
                    "manifest_sha256": prepared.manifest_sha256,
                    "review_packet": str(prepared.review_packet_path),
                    "review_packet_sha256": prepared.review_packet_sha256,
                    "status": "prepared-not-reviewed",
                }
            else:
                verified = evaluate_editorial_study(
                    inventory_path=args.inventory,
                    manifest_path=args.manifest,
                    review_packet_path=args.review_packet,
                    media_root=args.media_root,
                    approval_path=args.approval,
                    approval_signature_path=args.approval_signature,
                    reviewer_one_path=args.reviewer_one,
                    reviewer_one_signature_path=args.reviewer_one_signature,
                    reviewer_two_path=args.reviewer_two,
                    reviewer_two_signature_path=args.reviewer_two_signature,
                    adjudication_path=args.adjudication,
                    adjudication_signature_path=args.adjudication_signature,
                    allowed_signers_path=args.allowed_signers,
                    output_dir=args.output_dir,
                )
                document = {
                    "adjudicator_id": verified.adjudicator_id,
                    "manifest_sha256": verified.manifest_sha256,
                    "output_dir": str(verified.output_dir),
                    "review_packet_sha256": verified.review_packet_sha256,
                    "reviewer_ids": list(verified.reviewer_ids),
                    "status": "signed-reviewed-and-split",
                }
            print(json.dumps(document, ensure_ascii=False, sort_keys=True), file=report_stream)
    except (EditorialAcceptanceError, OSError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
