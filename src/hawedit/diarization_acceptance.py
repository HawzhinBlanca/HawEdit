"""Signed real-media acceptance packets for diarization and speaker-aware reframing.

The production pipeline deliberately exposes diarizer and speaker-tracker protocols without
pretending that the gated Community-1 checkpoint or human multi-speaker references are present.
This coordinator closes the autonomous part of BLUEPRINT §8.1: it prepares content-bound inputs,
then compares the production model with the non-routable 3.1 control after a human has supplied
real references, runs, rights assertions, gated-access acceptance, and one detached signature.

No threshold is invented here.  The result reports raw DER components, word-boundary error,
speaker/face association error, crop-centre error and crop-motion error for both systems.  A
fallback is preserved as a fallback and is never scored as successful speaker tracking.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path, PurePosixPath
from typing import Any, Final, cast

from hawedit.atomic_fs import rename_directory_noreplace
from hawedit.cli import machine_readable_stdout, program_name, use_utf8_streams
from hawedit.diarization import (
    BoundaryReconciliation,
    DiarizationError,
    Segment,
    assert_exclusive,
    boundary_reconciliation,
    diarization_error_rate,
    overlap_aware_diarization_error_rate,
)
from hawedit.ingest import IngestError, probe_duration_ms, probe_stream
from hawedit.reframe import (
    SpeakerAssociationError,
    SpeakerFocusPoint,
    validate_speaker_focus_points,
)
from hawedit.registry import BENCHMARK_CONTROLS, REGISTRY
from hawedit.transcripts import Word

__all__ = [
    "COMMUNITY_MODEL_ID",
    "COMMUNITY_REVISION",
    "CONTROL_MODEL_ID",
    "SIGNATURE_NAMESPACE",
    "DiarizationAcceptanceError",
    "PreparedDiarizationStudy",
    "VerifiedDiarizationStudy",
    "evaluate_diarization_study",
    "main",
    "prepare_diarization_study",
]

COMMUNITY_MODEL_ID: Final = "pyannote/speaker-diarization-community-1"
COMMUNITY_REVISION: Final = "3533c8cf8e369892e6b79ff1bf80f7b0286a54ee"
CONTROL_MODEL_ID: Final = "pyannote/speaker-diarization-3.1"
SIGNATURE_NAMESPACE: Final = "hawedit-diarization-study-v1"
_SCHEMA: Final = 1
_MAX_JSON_BYTES: Final = 64 * 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_REVISION = re.compile(r"[0-9a-f]{40}\Z")
_RFC3339_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_SIGNER_FINGERPRINT = re.compile(rb"\bkey (SHA256:[A-Za-z0-9+/=]{20,})\b")
_PLACEHOLDERS: Final = frozenset(
    {"", "unknown", "tbd", "todo", "none", "n/a", "unrecorded", "placeholder"}
)
_PREPARED_FILES: Final = frozenset(
    {
        "INSTRUCTIONS.txt",
        "approval.template.json",
        "community-run.template.json",
        "control-run.template.json",
        "study-manifest.json",
    }
)
_RESULT_FILES: Final = frozenset({"ATTRIBUTION.txt", "INSTRUCTIONS.txt", "diarization-report.json"})


class DiarizationAcceptanceError(ValueError):
    """The proposed acceptance evidence is incomplete, mutable, or unauthenticated."""


def _one_line(value: object, field: str, *, allow_placeholder: bool = False) -> str:
    if not isinstance(value, str):
        raise DiarizationAcceptanceError(f"{field} must be a string")
    if (
        not value
        or value.strip() != value
        or not value.isprintable()
        or value.splitlines() != [value]
    ):
        raise DiarizationAcceptanceError(
            f"{field} must be non-empty, trimmed, printable, and one line"
        )
    if not allow_placeholder and value.casefold() in _PLACEHOLDERS:
        raise DiarizationAcceptanceError(f"{field} is placeholder text, not acceptance evidence")
    return value


def _exact_bool(value: object, field: str) -> bool:
    if type(value) is not bool:
        raise DiarizationAcceptanceError(f"{field} must be a JSON boolean")
    return value


def _exact_int(value: object, field: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise DiarizationAcceptanceError(f"{field} must be an integer >= {minimum}")
    return value


def _digest(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise DiarizationAcceptanceError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _revision(value: object, field: str) -> str:
    if not isinstance(value, str) or _REVISION.fullmatch(value) is None:
        raise DiarizationAcceptanceError(f"{field} must be a lowercase 40-hex revision")
    return value


def _strict_object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise DiarizationAcceptanceError(f"{field} must be a JSON object")
    return value


def _exact_fields(value: Mapping[str, Any], expected: set[str], field: str) -> None:
    actual = set(value)
    if actual != expected:
        raise DiarizationAcceptanceError(
            f"{field} fields do not match schema; "
            f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise DiarizationAcceptanceError(f"duplicate JSON key {key!r}")
        document[key] = value
    return document


def _canonical_json(document: Mapping[str, Any]) -> bytes:
    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _is_reparse(info: os.stat_result) -> bool:
    flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(getattr(info, "st_file_attributes", 0) & flag)


def _identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_nlink)


def _read_bound_file(path: Path, label: str, maximum: int | None) -> bytes:
    try:
        before_path = os.lstat(path)
    except OSError as exc:
        raise DiarizationAcceptanceError(f"cannot inspect {label} {path}: {exc}") from exc
    if stat.S_ISLNK(before_path.st_mode) or _is_reparse(before_path):
        raise DiarizationAcceptanceError(f"{label} must not be a link or reparse point: {path}")
    if not stat.S_ISREG(before_path.st_mode) or before_path.st_nlink != 1:
        raise DiarizationAcceptanceError(
            f"{label} must be one regular, non-hardlinked file: {path}"
        )
    if maximum is not None and before_path.st_size > maximum:
        raise DiarizationAcceptanceError(f"{label} exceeds its {maximum}-byte limit: {path}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise DiarizationAcceptanceError(f"cannot open {label} {path}: {exc}") from exc
    chunks: list[bytes] = []
    try:
        before_fd = os.fstat(descriptor)
        if _identity(before_fd) != _identity(before_path):
            raise DiarizationAcceptanceError(f"{label} changed while opening: {path}")
        total = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if maximum is not None and total > maximum:
                raise DiarizationAcceptanceError(
                    f"{label} exceeds its {maximum}-byte limit: {path}"
                )
            chunks.append(chunk)
        after_fd = os.fstat(descriptor)
        if (
            _identity(after_fd) != _identity(before_fd)
            or after_fd.st_ctime_ns != before_fd.st_ctime_ns
        ):
            raise DiarizationAcceptanceError(f"{label} changed while being read: {path}")
    finally:
        os.close(descriptor)
    try:
        after_path = os.lstat(path)
    except OSError as exc:
        raise DiarizationAcceptanceError(f"cannot re-inspect {label} {path}: {exc}") from exc
    if (
        _identity(after_path) != _identity(before_path)
        or after_path.st_ctime_ns != before_path.st_ctime_ns
    ):
        raise DiarizationAcceptanceError(f"{label} path changed while being read: {path}")
    return b"".join(chunks)


def _load_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    payload = _read_bound_file(path, label, _MAX_JSON_BYTES)
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DiarizationAcceptanceError(f"{label} is not strict UTF-8 JSON: {exc}") from exc
    return _strict_object(value, label), payload


def _relative_path(value: object, field: str) -> str:
    text = _one_line(value, field)
    if "\\" in text:
        raise DiarizationAcceptanceError(f"{field} must use forward slashes")
    relative = PurePosixPath(text)
    if relative.is_absolute() or any(
        part in {"", ".", ".."} or ":" in part for part in relative.parts
    ):
        raise DiarizationAcceptanceError(f"{field} must be one contained relative path")
    return text


def _bound_directory(path: Path, label: str) -> tuple[Path, tuple[int, int]]:
    absolute = Path(os.path.abspath(path))
    try:
        info = os.lstat(absolute)
    except OSError as exc:
        raise DiarizationAcceptanceError(f"cannot inspect {label} {absolute}: {exc}") from exc
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or _is_reparse(info):
        raise DiarizationAcceptanceError(f"{label} must be one real directory: {absolute}")
    return absolute, (info.st_dev, info.st_ino)


def _assert_directory(path: Path, identity: tuple[int, int], label: str) -> None:
    _, current = _bound_directory(path, label)
    if current != identity:
        raise DiarizationAcceptanceError(f"{label} identity changed: {path}")


def _contained_file(root: Path, relative: str) -> Path:
    current = root
    parts = PurePosixPath(_relative_path(relative, "media path")).parts
    for index, part in enumerate(parts):
        current /= part
        try:
            info = os.lstat(current)
        except OSError as exc:
            raise DiarizationAcceptanceError(
                f"cannot inspect study media {current}: {exc}"
            ) from exc
        if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
            raise DiarizationAcceptanceError(f"study media path contains a link: {current}")
        if index < len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise DiarizationAcceptanceError(f"study media parent is not a directory: {current}")
    return current


def _video_identity(path: Path, duration_ms: int, frame_width: int) -> str:
    before = hashlib.sha256(_read_bound_file(path, "study video", None)).hexdigest()
    try:
        dimensions = probe_stream(path, "stream=width,height", video_only=True)
        measured_duration = probe_duration_ms(path)
    except (IngestError, OSError, ValueError) as exc:
        raise DiarizationAcceptanceError(f"study media is not probeable video: {exc}") from exc
    try:
        measured_width = int(dimensions.split("x", 1)[0])
    except (IndexError, ValueError) as exc:
        raise DiarizationAcceptanceError(
            f"study video returned malformed dimensions {dimensions!r}"
        ) from exc
    after = hashlib.sha256(_read_bound_file(path, "study video", None)).hexdigest()
    if after != before:
        raise DiarizationAcceptanceError("study video changed while ffprobe inspected it")
    if measured_duration != duration_ms:
        raise DiarizationAcceptanceError(
            f"study video duration is {measured_duration} ms, not declared {duration_ms} ms"
        )
    if measured_width != frame_width:
        raise DiarizationAcceptanceError(
            f"study video width is {measured_width}, not declared {frame_width}"
        )
    return before


def _write_private(path: Path, payload: bytes) -> None:
    try:
        with path.open("xb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
    except OSError as exc:
        raise DiarizationAcceptanceError(
            f"cannot stage diarization evidence {path}: {exc}"
        ) from exc


def _discard_private(staging: Path, identity: tuple[int, int], expected: frozenset[str]) -> None:
    if not os.path.lexists(staging):
        return
    _assert_directory(staging, identity, "private diarization-evidence directory")
    try:
        children = tuple(staging.iterdir())
        unexpected = sorted(child.name for child in children if child.name not in expected)
        if unexpected:
            raise DiarizationAcceptanceError(
                "refusing to clean unexpected private evidence: " + ", ".join(unexpected)
            )
        for child in children:
            info = os.lstat(child)
            if (
                not stat.S_ISREG(info.st_mode)
                or stat.S_ISLNK(info.st_mode)
                or _is_reparse(info)
                or info.st_nlink != 1
            ):
                raise DiarizationAcceptanceError(f"refusing to clean unsafe evidence file {child}")
            child.unlink()
        staging.rmdir()
    except DiarizationAcceptanceError:
        raise
    except OSError as exc:
        raise DiarizationAcceptanceError(f"cannot clean private evidence {staging}: {exc}") from exc


def _publish_exact(output_dir: Path, payloads: Mapping[str, bytes]) -> Path:
    expected = frozenset(payloads)
    if expected not in {_PREPARED_FILES, _RESULT_FILES}:
        raise DiarizationAcceptanceError("diarization evidence is not an exact supported file set")
    destination = Path(os.path.abspath(output_dir))
    parent, parent_identity = _bound_directory(destination.parent, "diarization output parent")
    if os.path.lexists(destination):
        raise DiarizationAcceptanceError(
            f"refusing to overwrite diarization evidence {destination}"
        )
    try:
        staging = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.", suffix=".staging", dir=parent)
        )
    except OSError as exc:
        raise DiarizationAcceptanceError(
            f"cannot create private evidence under {parent}: {exc}"
        ) from exc
    _, staging_identity = _bound_directory(staging, "private diarization-evidence directory")
    try:
        for name in sorted(expected):
            _write_private(staging / name, payloads[name])
        _assert_directory(parent, parent_identity, "diarization output parent")
        _assert_directory(staging, staging_identity, "private diarization-evidence directory")
        if frozenset(path.name for path in staging.iterdir()) != expected:
            raise DiarizationAcceptanceError("private diarization evidence set changed")
        rename_directory_noreplace(staging, destination)
        _assert_directory(destination, staging_identity, "published diarization evidence")
        _assert_directory(parent, parent_identity, "diarization output parent")
    except BaseException as primary:
        try:
            _discard_private(staging, staging_identity, expected)
        except DiarizationAcceptanceError as cleanup:
            primary.add_note(f"HawEdit diarization-evidence cleanup also failed: {cleanup}")
        if isinstance(primary, FileExistsError):
            raise DiarizationAcceptanceError(
                f"refusing to overwrite diarization evidence {destination}; another publisher won"
            ) from primary
        if isinstance(primary, OSError):
            raise DiarizationAcceptanceError(
                f"cannot atomically publish diarization evidence {destination}: {primary}"
            ) from primary
        raise
    return destination


def _segment(value: object, field: str) -> Segment:
    raw = _strict_object(value, field)
    _exact_fields(raw, {"end_ms", "speaker", "start_ms"}, field)
    try:
        return Segment(
            start_ms=_exact_int(raw["start_ms"], f"{field}.start_ms"),
            end_ms=_exact_int(raw["end_ms"], f"{field}.end_ms", minimum=1),
            speaker=_one_line(raw["speaker"], f"{field}.speaker"),
        )
    except (TypeError, ValueError) as exc:
        raise DiarizationAcceptanceError(f"invalid {field}: {exc}") from exc


def _word(value: object, field: str) -> Word:
    raw = _strict_object(value, field)
    _exact_fields(raw, {"end_ms", "start_ms", "w"}, field)
    try:
        return Word(
            w=_one_line(raw["w"], f"{field}.w", allow_placeholder=True),
            start_ms=_exact_int(raw["start_ms"], f"{field}.start_ms"),
            end_ms=_exact_int(raw["end_ms"], f"{field}.end_ms", minimum=1),
            conf=1.0,
        )
    except ValueError as exc:
        raise DiarizationAcceptanceError(f"invalid {field}: {exc}") from exc


def _focus(value: object, field: str) -> SpeakerFocusPoint:
    raw = _strict_object(value, field)
    _exact_fields(raw, {"at_ms", "center_x", "speaker"}, field)
    try:
        return SpeakerFocusPoint(
            at_ms=_exact_int(raw["at_ms"], f"{field}.at_ms"),
            center_x=_exact_int(raw["center_x"], f"{field}.center_x"),
            speaker=_one_line(raw["speaker"], f"{field}.speaker"),
        )
    except (TypeError, ValueError) as exc:
        raise DiarizationAcceptanceError(f"invalid {field}: {exc}") from exc


def _array(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise DiarizationAcceptanceError(f"{field} must be a JSON array")
    return value


def _turns(value: object, field: str, *, exclusive: bool = True) -> tuple[Segment, ...]:
    turns = tuple(
        _segment(item, f"{field}[{index}]") for index, item in enumerate(_array(value, field))
    )
    if exclusive:
        try:
            assert_exclusive(turns)
        except ValueError as exc:
            raise DiarizationAcceptanceError(f"invalid {field}: {exc}") from exc
    return turns


def _words(value: object, field: str) -> tuple[Word, ...]:
    words = tuple(
        _word(item, f"{field}[{index}]") for index, item in enumerate(_array(value, field))
    )
    if not words:
        raise DiarizationAcceptanceError(f"{field} must contain aligned reference words")
    for previous, current in pairwise(words):
        if current.start_ms < previous.end_ms:
            raise DiarizationAcceptanceError(f"{field} words overlap or are not chronological")
    return words


def _focus_points(value: object, field: str) -> tuple[SpeakerFocusPoint, ...]:
    return tuple(
        _focus(item, f"{field}[{index}]") for index, item in enumerate(_array(value, field))
    )


def _segments_dict(turns: Sequence[Segment]) -> list[dict[str, object]]:
    return [
        {"end_ms": turn.end_ms, "speaker": turn.speaker, "start_ms": turn.start_ms}
        for turn in turns
    ]


def _words_dict(words: Sequence[Word]) -> list[dict[str, object]]:
    return [{"end_ms": word.end_ms, "start_ms": word.start_ms, "w": word.w} for word in words]


def _focus_dict(points: Sequence[SpeakerFocusPoint]) -> list[dict[str, object]]:
    return [
        {"at_ms": point.at_ms, "center_x": point.center_x, "speaker": point.speaker}
        for point in points
    ]


@dataclass(frozen=True, slots=True)
class _ReferenceItem:
    media_id: str
    media_path: str
    duration_ms: int
    frame_width: int
    turns: tuple[Segment, ...]
    words: tuple[Word, ...]
    focus_points: tuple[SpeakerFocusPoint, ...]

    @staticmethod
    def from_dict(value: object, field: str) -> _ReferenceItem:
        raw = _strict_object(value, field)
        _exact_fields(
            raw,
            {
                "duration_ms",
                "frame_width",
                "media_id",
                "media_path",
                "reference_focus_points",
                "reference_turns",
                "reference_words",
            },
            field,
        )
        item = _ReferenceItem(
            media_id=_one_line(raw["media_id"], f"{field}.media_id"),
            media_path=_relative_path(raw["media_path"], f"{field}.media_path"),
            duration_ms=_exact_int(raw["duration_ms"], f"{field}.duration_ms", minimum=1),
            frame_width=_exact_int(raw["frame_width"], f"{field}.frame_width", minimum=1),
            turns=_turns(raw["reference_turns"], f"{field}.reference_turns"),
            words=_words(raw["reference_words"], f"{field}.reference_words"),
            focus_points=_focus_points(
                raw["reference_focus_points"], f"{field}.reference_focus_points"
            ),
        )
        speakers = {turn.speaker for turn in item.turns}
        if len(speakers) < 2:
            raise DiarizationAcceptanceError(
                f"{field} must contain at least two reference speakers"
            )
        if not item.focus_points:
            raise DiarizationAcceptanceError(
                f"{field} must contain human face/crop reference points"
            )
        for turn in item.turns:
            if turn.end_ms > item.duration_ms:
                raise DiarizationAcceptanceError(f"{field} turn exceeds the media duration")
        for word in item.words:
            if word.end_ms > item.duration_ms:
                raise DiarizationAcceptanceError(f"{field} word exceeds the media duration")
        for point in item.focus_points:
            if point.center_x >= item.frame_width:
                raise DiarizationAcceptanceError(f"{field} focus centre is outside the video width")
        try:
            validate_speaker_focus_points(item.focus_points, item.turns, 0, item.duration_ms)
        except (SpeakerAssociationError, TypeError, ValueError) as exc:
            raise DiarizationAcceptanceError(f"invalid {field} reference focus: {exc}") from exc
        return item

    def to_dict(self, media_sha256: str) -> dict[str, object]:
        return {
            "duration_ms": self.duration_ms,
            "frame_width": self.frame_width,
            "media_id": self.media_id,
            "media_path": self.media_path,
            "media_sha256": media_sha256,
            "reference_focus_points": _focus_dict(self.focus_points),
            "reference_turns": _segments_dict(self.turns),
            "reference_words": _words_dict(self.words),
        }


@dataclass(frozen=True, slots=True)
class _ReferenceStudy:
    study_id: str
    authorized_by: str
    media_authorization: str
    consent_basis: str
    use_scope: str
    items: tuple[_ReferenceItem, ...]


def _reference_study(document: object) -> _ReferenceStudy:
    raw = _strict_object(document, "reference manifest")
    _exact_fields(
        raw,
        {
            "authorized_by",
            "consent_basis",
            "interim",
            "items",
            "media_authorization",
            "schema",
            "study_id",
            "use_scope",
        },
        "reference manifest",
    )
    if _exact_int(raw["schema"], "reference schema", minimum=1) != _SCHEMA:
        raise DiarizationAcceptanceError("unsupported reference schema")
    if _exact_bool(raw["interim"], "reference interim"):
        raise DiarizationAcceptanceError("interim references cannot become acceptance evidence")
    items = tuple(
        _ReferenceItem.from_dict(item, f"reference items[{index}]")
        for index, item in enumerate(_array(raw["items"], "reference items"))
    )
    if not items:
        raise DiarizationAcceptanceError("reference manifest must contain real multi-speaker items")
    media_ids = [item.media_id for item in items]
    media_paths = [item.media_path for item in items]
    if len(media_ids) != len(set(media_ids)) or len(media_paths) != len(set(media_paths)):
        raise DiarizationAcceptanceError("reference items contain duplicate media ids or paths")
    return _ReferenceStudy(
        study_id=_one_line(raw["study_id"], "study id"),
        authorized_by=_one_line(raw["authorized_by"], "media authorizer"),
        media_authorization=_one_line(raw["media_authorization"], "media authorization"),
        consent_basis=_one_line(raw["consent_basis"], "consent basis"),
        use_scope=_one_line(raw["use_scope"], "media use scope"),
        items=items,
    )


def _prepared_manifest(
    reference: _ReferenceStudy,
    reference_sha256: str,
    media_root: Path,
) -> dict[str, object]:
    root, root_identity = _bound_directory(media_root, "diarization media root")
    prepared_items: list[dict[str, object]] = []
    seen_digests: set[str] = set()
    for item in reference.items:
        source = _contained_file(root, item.media_path)
        media_sha256 = _video_identity(source, item.duration_ms, item.frame_width)
        _assert_directory(root, root_identity, "diarization media root")
        if media_sha256 in seen_digests:
            raise DiarizationAcceptanceError("reference manifest reuses identical video bytes")
        seen_digests.add(media_sha256)
        prepared_items.append(item.to_dict(media_sha256))
    return {
        "authorized_by": reference.authorized_by,
        "consent_basis": reference.consent_basis,
        "items": prepared_items,
        "media_authorization": reference.media_authorization,
        "reference_manifest_sha256": reference_sha256,
        "schema": _SCHEMA,
        "study_id": reference.study_id,
        "use_scope": reference.use_scope,
    }


def _run_template(manifest_sha256: str, system: str, item_ids: Sequence[str]) -> dict[str, object]:
    model_id = COMMUNITY_MODEL_ID if system == "community" else CONTROL_MODEL_ID
    licence = (
        REGISTRY[COMMUNITY_MODEL_ID].licence.name
        if system == "community"
        else BENCHMARK_CONTROLS[CONTROL_MODEL_ID].licence.name
    )
    revision = COMMUNITY_REVISION if system == "community" else None
    return {
        "checkpoint_manifest_sha256": None,
        "items": [
            {
                "fallback_reason": None,
                "focus_points": [],
                "media_id": media_id,
                "mode": None,
                "turns": [],
            }
            for media_id in item_ids
        ],
        "licence": licence,
        "model_id": model_id,
        "revision": revision,
        "run_at_utc": None,
        "run_by": None,
        "runtime_identity": None,
        "schema": _SCHEMA,
        "study_manifest_sha256": manifest_sha256,
        "system": system,
    }


@dataclass(frozen=True, slots=True)
class PreparedDiarizationStudy:
    directory: Path
    study_manifest_path: Path
    community_run_template_path: Path
    control_run_template_path: Path
    approval_template_path: Path


def prepare_diarization_study(
    *, reference_manifest_path: Path, media_root: Path, output_dir: Path
) -> PreparedDiarizationStudy:
    """Bind human references and real videos, then publish only unsigned templates."""
    document, source_bytes = _load_json(reference_manifest_path, "diarization reference manifest")
    reference = _reference_study(document)
    manifest = _prepared_manifest(
        reference,
        hashlib.sha256(source_bytes).hexdigest(),
        media_root,
    )
    manifest_bytes = _canonical_json(manifest)
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    item_ids = [item.media_id for item in reference.items]
    approval = {
        "approved_at_utc": None,
        "approved_by": reference.authorized_by,
        "community_run_sha256": None,
        "control_run_sha256": None,
        "crop_reviewed": False,
        "gated_repo_access_accepted": False,
        "media_rights_confirmed": False,
        "schema": _SCHEMA,
        "statement": None,
        "study_manifest_sha256": manifest_sha256,
    }
    instructions = (
        "HAWEDIT DIARIZATION/REFRAME ACCEPTANCE — HUMAN INPUT REQUIRED\n\n"
        "1. Run the pinned Community-1 production model and the separate 3.1 benchmark control.\n"
        "2. Fill each run template without changing study_manifest_sha256 or media ids.\n"
        "3. Record speaker_tracked only when every focus point is produced from that run's turns; "
        "otherwise use fallback with a concrete reason and no points.\n"
        "4. Review the gated licence/access and media/crop assertions, fill "
        "approval.template.json, "
        f"then sign it with: ssh-keygen -Y sign -n {SIGNATURE_NAMESPACE} -f KEY approval.json\n"
        "5. Evaluate with the original reference manifest and media root. Templates are unset and "
        "are not acceptance evidence.\n"
    ).encode()
    directory = _publish_exact(
        output_dir,
        {
            "INSTRUCTIONS.txt": instructions,
            "approval.template.json": _canonical_json(approval),
            "community-run.template.json": _canonical_json(
                _run_template(manifest_sha256, "community", item_ids)
            ),
            "control-run.template.json": _canonical_json(
                _run_template(manifest_sha256, "control", item_ids)
            ),
            "study-manifest.json": manifest_bytes,
        },
    )
    return PreparedDiarizationStudy(
        directory=directory,
        study_manifest_path=directory / "study-manifest.json",
        community_run_template_path=directory / "community-run.template.json",
        control_run_template_path=directory / "control-run.template.json",
        approval_template_path=directory / "approval.template.json",
    )


@dataclass(frozen=True, slots=True)
class _RunItem:
    media_id: str
    mode: str
    fallback_reason: str | None
    turns: tuple[Segment, ...]
    focus_points: tuple[SpeakerFocusPoint, ...]


@dataclass(frozen=True, slots=True)
class _SystemRun:
    system: str
    model_id: str
    revision: str
    licence: str
    checkpoint_manifest_sha256: str
    run_by: str
    run_at_utc: str
    runtime_identity: str
    study_manifest_sha256: str
    items: tuple[_RunItem, ...]


def _timestamp(value: object, field: str) -> str:
    text = _one_line(value, field)
    if _RFC3339_UTC.fullmatch(text) is None:
        raise DiarizationAcceptanceError(f"{field} must be exact UTC YYYY-MM-DDTHH:MM:SSZ")
    return text


def _run(document: object, expected_system: str, manifest_sha256: str) -> _SystemRun:
    raw = _strict_object(document, f"{expected_system} run")
    _exact_fields(
        raw,
        {
            "checkpoint_manifest_sha256",
            "items",
            "licence",
            "model_id",
            "revision",
            "run_at_utc",
            "run_by",
            "runtime_identity",
            "schema",
            "study_manifest_sha256",
            "system",
        },
        f"{expected_system} run",
    )
    if _exact_int(raw["schema"], "run schema", minimum=1) != _SCHEMA:
        raise DiarizationAcceptanceError("unsupported run schema")
    system = _one_line(raw["system"], "run system")
    if system != expected_system:
        raise DiarizationAcceptanceError(f"expected {expected_system} run, got {system!r}")
    expected_model = COMMUNITY_MODEL_ID if system == "community" else CONTROL_MODEL_ID
    expected_licence = (
        REGISTRY[COMMUNITY_MODEL_ID].licence.name
        if system == "community"
        else BENCHMARK_CONTROLS[CONTROL_MODEL_ID].licence.name
    )
    model_id = _one_line(raw["model_id"], "run model_id")
    licence = _one_line(raw["licence"], "run licence")
    revision = _revision(raw["revision"], "run revision")
    if model_id != expected_model or licence != expected_licence:
        raise DiarizationAcceptanceError(
            f"{system} run must use {expected_model} under {expected_licence}"
        )
    if system == "community" and revision != COMMUNITY_REVISION:
        raise DiarizationAcceptanceError(
            f"Community-1 run must use pinned revision {COMMUNITY_REVISION}"
        )
    bound_manifest = _digest(raw["study_manifest_sha256"], "run study manifest digest")
    if bound_manifest != manifest_sha256:
        raise DiarizationAcceptanceError(f"{system} run is bound to another study manifest")
    items: list[_RunItem] = []
    for index, value in enumerate(_array(raw["items"], "run items")):
        item = _strict_object(value, f"run items[{index}]")
        _exact_fields(
            item,
            {"fallback_reason", "focus_points", "media_id", "mode", "turns"},
            f"run items[{index}]",
        )
        mode = _one_line(item["mode"], f"run items[{index}].mode")
        if mode not in {"speaker_tracked", "fallback"}:
            raise DiarizationAcceptanceError("run item mode must be speaker_tracked or fallback")
        turns = _turns(
            item["turns"],
            f"run items[{index}].turns",
            exclusive=system == "community",
        )
        points = _focus_points(item["focus_points"], f"run items[{index}].focus_points")
        fallback_raw = item["fallback_reason"]
        fallback = (
            None
            if fallback_raw is None
            else _one_line(fallback_raw, f"run items[{index}].fallback_reason")
        )
        if mode == "speaker_tracked" and (fallback is not None or not points):
            raise DiarizationAcceptanceError(
                "speaker_tracked output requires points and cannot carry a fallback reason"
            )
        if mode == "fallback" and (fallback is None or points):
            raise DiarizationAcceptanceError(
                "fallback output requires a concrete reason and must not carry focus points"
            )
        items.append(
            _RunItem(
                media_id=_one_line(item["media_id"], f"run items[{index}].media_id"),
                mode=mode,
                fallback_reason=fallback,
                turns=turns,
                focus_points=points,
            )
        )
    return _SystemRun(
        system=system,
        model_id=model_id,
        revision=revision,
        licence=licence,
        checkpoint_manifest_sha256=_digest(
            raw["checkpoint_manifest_sha256"], "checkpoint manifest digest"
        ),
        run_by=_one_line(raw["run_by"], "run operator"),
        run_at_utc=_timestamp(raw["run_at_utc"], "run timestamp"),
        runtime_identity=_one_line(raw["runtime_identity"], "run runtime identity"),
        study_manifest_sha256=bound_manifest,
        items=tuple(items),
    )


@dataclass(frozen=True, slots=True)
class _SignatureEvidence:
    document_sha256: str
    signature_sha256: str
    key_fingerprint: str


def _verify_signature(
    document_bytes: bytes,
    signature_path: Path,
    allowed_signers_bytes: bytes,
    identity: str,
    ssh_keygen: str,
) -> _SignatureEvidence:
    signature = _read_bound_file(signature_path, "diarization approval signature", 1024 * 1024)
    executable = shutil.which(ssh_keygen)
    if executable is None:
        raise DiarizationAcceptanceError(f"OpenSSH verifier {ssh_keygen!r} is unavailable")
    with tempfile.TemporaryDirectory(prefix="hawedit-diarization-signature-") as temporary:
        directory = Path(temporary)
        signature_snapshot = directory / "approval.sig"
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
            raise DiarizationAcceptanceError(
                f"approval signature verification failed: {exc}"
            ) from exc
    if result.returncode != 0:
        raise DiarizationAcceptanceError("approval signature verification failed")
    output = result.stdout + b"\n" + result.stderr
    if len(output) > 8192:
        raise DiarizationAcceptanceError("signature verifier output exceeded 8192 bytes")
    fingerprints = {
        match.group(1).decode("ascii") for match in _SIGNER_FINGERPRINT.finditer(output)
    }
    if len(fingerprints) != 1:
        raise DiarizationAcceptanceError(
            "OpenSSH signature verification did not identify exactly one signing key"
        )
    return _SignatureEvidence(
        document_sha256=hashlib.sha256(document_bytes).hexdigest(),
        signature_sha256=hashlib.sha256(signature).hexdigest(),
        key_fingerprint=fingerprints.pop(),
    )


def _approval(
    document: object,
    manifest_sha256: str,
    community_sha256: str,
    control_sha256: str,
    authorized_by: str,
) -> tuple[str, str]:
    raw = _strict_object(document, "diarization approval")
    _exact_fields(
        raw,
        {
            "approved_at_utc",
            "approved_by",
            "community_run_sha256",
            "control_run_sha256",
            "crop_reviewed",
            "gated_repo_access_accepted",
            "media_rights_confirmed",
            "schema",
            "statement",
            "study_manifest_sha256",
        },
        "diarization approval",
    )
    if _exact_int(raw["schema"], "approval schema", minimum=1) != _SCHEMA:
        raise DiarizationAcceptanceError("unsupported approval schema")
    approved_by = _one_line(raw["approved_by"], "approval identity")
    if approved_by != authorized_by:
        raise DiarizationAcceptanceError("approval identity is not the recorded media authorizer")
    bindings = {
        "study_manifest_sha256": manifest_sha256,
        "community_run_sha256": community_sha256,
        "control_run_sha256": control_sha256,
    }
    for field, expected in bindings.items():
        if _digest(raw[field], field) != expected:
            raise DiarizationAcceptanceError(f"approval {field} is bound to other evidence")
    for field in ("crop_reviewed", "gated_repo_access_accepted", "media_rights_confirmed"):
        if not _exact_bool(raw[field], field):
            raise DiarizationAcceptanceError(f"approval {field} must be explicitly true")
    _one_line(raw["statement"], "approval statement")
    return approved_by, _timestamp(raw["approved_at_utc"], "approval timestamp")


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _der_dict(value: DiarizationError) -> dict[str, object]:
    return {
        "confusion_ms": value.confusion_ms,
        "der": value.der,
        "false_alarm_ms": value.false_alarm_ms,
        "missed_ms": value.missed_ms,
        "speaker_mapping": [list(pair) for pair in value.speaker_mapping],
        "total_speech_ms": value.total_speech_ms,
    }


def _boundary_dict(value: BoundaryReconciliation) -> dict[str, object]:
    return {
        "boundaries": value.boundaries,
        "mean_abs_error_ms": value.mean_abs_error_ms,
        "tolerance_ms": value.tolerance_ms,
        "within_tolerance_rate": value.within_tolerance_rate,
    }


def _item_metrics(
    reference: _ReferenceItem, run: _RunItem, *, overlap_aware: bool
) -> dict[str, object]:
    if run.media_id != reference.media_id:
        raise DiarizationAcceptanceError("run item order or media identity drifted")
    for turn in run.turns:
        if turn.end_ms > reference.duration_ms:
            raise DiarizationAcceptanceError(f"run turn exceeds {run.media_id} duration")
    error = (
        overlap_aware_diarization_error_rate(reference.turns, run.turns)
        if overlap_aware
        else diarization_error_rate(reference.turns, run.turns)
    )
    reconciliation = boundary_reconciliation(run.turns, reference.words)
    if error is None:
        raise DiarizationAcceptanceError("multi-speaker reference unexpectedly has no speech")
    result: dict[str, object] = {
        "boundary": _boundary_dict(reconciliation) if reconciliation is not None else None,
        "der": _der_dict(error),
        "fallback_reason": run.fallback_reason,
        "media_id": run.media_id,
        "mode": run.mode,
    }
    if run.mode == "fallback":
        result.update(
            {
                "association_error_count": None,
                "association_error_rate": None,
                "center_mae_normalized": None,
                "center_mae_px": None,
                "crop_step_error_mae_px": None,
                "predicted_mean_step_px": None,
                "reference_mean_step_px": None,
                "tracked_points": 0,
            }
        )
        return result
    try:
        validate_speaker_focus_points(run.focus_points, run.turns, 0, reference.duration_ms)
    except (SpeakerAssociationError, TypeError, ValueError) as exc:
        raise DiarizationAcceptanceError(f"invalid speaker-tracked evidence: {exc}") from exc
    for point in run.focus_points:
        if point.center_x >= reference.frame_width:
            raise DiarizationAcceptanceError("run focus centre is outside the video width")
    predicted = {point.at_ms: point for point in run.focus_points}
    expected = {point.at_ms: point for point in reference.focus_points}
    if len(predicted) != len(run.focus_points) or len(expected) != len(reference.focus_points):
        raise DiarizationAcceptanceError("focus timestamps must be unique")
    if set(predicted) != set(expected):
        raise DiarizationAcceptanceError(
            "speaker-tracked run must report the exact human-reference focus timestamps"
        )
    mapping = dict(error.speaker_mapping)
    ordered_times = sorted(expected)
    association_errors = sum(
        mapping.get(predicted[at].speaker) != expected[at].speaker for at in ordered_times
    )
    centre_errors = [abs(predicted[at].center_x - expected[at].center_x) for at in ordered_times]
    predicted_steps = [
        abs(predicted[current].center_x - predicted[previous].center_x)
        for previous, current in pairwise(ordered_times)
    ]
    expected_steps = [
        abs(expected[current].center_x - expected[previous].center_x)
        for previous, current in pairwise(ordered_times)
    ]
    step_errors = [
        abs(predicted_step - expected_step)
        for predicted_step, expected_step in zip(predicted_steps, expected_steps, strict=True)
    ]
    center_mae = _mean([float(value) for value in centre_errors])
    result.update(
        {
            "association_error_count": association_errors,
            "association_error_rate": association_errors / len(ordered_times),
            "center_mae_normalized": (
                center_mae / reference.frame_width if center_mae is not None else None
            ),
            "center_mae_px": center_mae,
            "crop_step_error_mae_px": _mean([float(value) for value in step_errors]),
            "predicted_mean_step_px": _mean([float(value) for value in predicted_steps]),
            "reference_mean_step_px": _mean([float(value) for value in expected_steps]),
            "tracked_points": len(ordered_times),
        }
    )
    return result


def _aggregate(
    system: str, model: _SystemRun, items: Sequence[dict[str, object]]
) -> dict[str, object]:
    der_rows = [item["der"] for item in items]
    boundary_rows = [item["boundary"] for item in items if item["boundary"] is not None]
    if not all(isinstance(row, dict) for row in der_rows + boundary_rows):
        raise AssertionError("non-null metric rows must be objects")
    typed_der = [row for row in der_rows if isinstance(row, dict)]
    typed_boundary = [row for row in boundary_rows if isinstance(row, dict)]
    speech = sum(int(row["total_speech_ms"]) for row in typed_der)
    errors = sum(
        int(row["missed_ms"]) + int(row["false_alarm_ms"]) + int(row["confusion_ms"])
        for row in typed_der
    )
    boundary_count = sum(int(row["boundaries"]) for row in typed_boundary)
    boundary_abs = sum(
        float(row["mean_abs_error_ms"]) * int(row["boundaries"]) for row in typed_boundary
    )
    boundary_within = sum(
        float(row["within_tolerance_rate"]) * int(row["boundaries"]) for row in typed_boundary
    )
    tracked = [item for item in items if item["mode"] == "speaker_tracked"]
    association_points = sum(cast(int, item["tracked_points"]) for item in tracked)
    association_errors = sum(cast(int, item["association_error_count"]) for item in tracked)
    return {
        "association_error_count": association_errors,
        "association_error_rate": (
            association_errors / association_points if association_points else None
        ),
        "boundary_mean_abs_error_ms": (boundary_abs / boundary_count if boundary_count else None),
        "boundary_within_tolerance_rate": (
            boundary_within / boundary_count if boundary_count else None
        ),
        "checkpoint_manifest_sha256": model.checkpoint_manifest_sha256,
        "der": errors / speech,
        "fallback_items": len(items) - len(tracked),
        "items": list(items),
        "licence": model.licence,
        "model_id": model.model_id,
        "revision": model.revision,
        "run_at_utc": model.run_at_utc,
        "run_by": model.run_by,
        "runtime_identity": model.runtime_identity,
        "system": system,
        "tracked_items": len(tracked),
        "tracked_points": association_points,
    }


@dataclass(frozen=True, slots=True)
class VerifiedDiarizationStudy:
    directory: Path
    report_path: Path
    attribution_path: Path


def evaluate_diarization_study(
    *,
    reference_manifest_path: Path,
    media_root: Path,
    study_manifest_path: Path,
    community_run_path: Path,
    control_run_path: Path,
    approval_path: Path,
    approval_signature_path: Path,
    allowed_signers_path: Path,
    output_dir: Path,
    ssh_keygen: str = "ssh-keygen",
) -> VerifiedDiarizationStudy:
    """Verify all human/model evidence and atomically publish a threshold-free report."""
    reference_document, reference_bytes = _load_json(
        reference_manifest_path, "diarization reference manifest"
    )
    reference = _reference_study(reference_document)
    expected_manifest = _prepared_manifest(
        reference, hashlib.sha256(reference_bytes).hexdigest(), media_root
    )
    expected_manifest_bytes = _canonical_json(expected_manifest)
    manifest_document, manifest_bytes = _load_json(study_manifest_path, "prepared study manifest")
    if manifest_bytes != expected_manifest_bytes or manifest_document != expected_manifest:
        raise DiarizationAcceptanceError(
            "prepared study manifest does not recompute from references"
        )
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    community_document, community_bytes = _load_json(community_run_path, "Community-1 run")
    control_document, control_bytes = _load_json(control_run_path, "3.1 control run")
    community = _run(community_document, "community", manifest_sha256)
    control = _run(control_document, "control", manifest_sha256)
    expected_ids = [item.media_id for item in reference.items]
    if [item.media_id for item in community.items] != expected_ids:
        raise DiarizationAcceptanceError("Community-1 run item inventory or order drifted")
    if [item.media_id for item in control.items] != expected_ids:
        raise DiarizationAcceptanceError("3.1 control run item inventory or order drifted")
    approval_document, approval_bytes = _load_json(approval_path, "diarization approval")
    community_sha256 = hashlib.sha256(community_bytes).hexdigest()
    control_sha256 = hashlib.sha256(control_bytes).hexdigest()
    approved_by, approved_at = _approval(
        approval_document,
        manifest_sha256,
        community_sha256,
        control_sha256,
        reference.authorized_by,
    )
    if approved_at <= max(community.run_at_utc, control.run_at_utc):
        raise DiarizationAcceptanceError("approval timestamp must be later than both model runs")
    allowed_signers_bytes = _read_bound_file(
        allowed_signers_path, "diarization allowed signers", 1024 * 1024
    )
    signature = _verify_signature(
        approval_bytes,
        approval_signature_path,
        allowed_signers_bytes,
        approved_by,
        ssh_keygen,
    )
    system_reports: dict[str, object] = {}
    for system, run in (("community", community), ("control", control)):
        metrics = [
            _item_metrics(reference_item, run_item, overlap_aware=system == "control")
            for reference_item, run_item in zip(reference.items, run.items, strict=True)
        ]
        system_reports[system] = _aggregate(system, run, metrics)
    report: dict[str, object] = {
        "acceptance_boundary": (
            "raw measurements only; no pass threshold or production acceptance is inferred"
        ),
        "approval": {
            "allowed_signers_sha256": hashlib.sha256(allowed_signers_bytes).hexdigest(),
            "approved_at_utc": approved_at,
            "approved_by": approved_by,
            "document_sha256": signature.document_sha256,
            "key_fingerprint": signature.key_fingerprint,
            "signature_sha256": signature.signature_sha256,
        },
        "community_run_sha256": community_sha256,
        "control_run_sha256": control_sha256,
        "reference_manifest_sha256": hashlib.sha256(reference_bytes).hexdigest(),
        "schema": _SCHEMA,
        "study_id": reference.study_id,
        "study_manifest_sha256": manifest_sha256,
        "systems": system_reports,
    }
    attribution = (
        "HawEdit diarization acceptance attribution\n"
        f"Production: {COMMUNITY_MODEL_ID} @ {COMMUNITY_REVISION} "
        f"({REGISTRY[COMMUNITY_MODEL_ID].licence.name}; attribution required)\n"
        f"Benchmark control: {CONTROL_MODEL_ID} "
        f"({BENCHMARK_CONTROLS[CONTROL_MODEL_ID].licence.name}; "
        "measurement only, never production-routable)\n"
        f"Study: {reference.study_id}\n"
        f"Study manifest SHA-256: {manifest_sha256}\n"
    ).encode()
    instructions = (
        b"VERIFIED DIARIZATION/REFRAME MEASUREMENT\n\n"
        b"This directory is signed, content-bound measurement evidence. It reports no guessed "
        b"pass threshold and does not by itself approve Community-1 for production. Review "
        b"diarization-report.json together with the human authorization and retained private "
        b"inputs.\n"
    )
    directory = _publish_exact(
        output_dir,
        {
            "ATTRIBUTION.txt": attribution,
            "INSTRUCTIONS.txt": instructions,
            "diarization-report.json": _canonical_json(report),
        },
    )
    return VerifiedDiarizationStudy(
        directory=directory,
        report_path=directory / "diarization-report.json",
        attribution_path=directory / "ATTRIBUTION.txt",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=program_name("hawedit-diarization-acceptance"),
        description="Prepare or evaluate signed diarization/reframe acceptance evidence.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--reference-manifest", type=Path, required=True)
    prepare.add_argument("--media-root", type=Path, required=True)
    prepare.add_argument("--output-dir", type=Path, required=True)
    evaluate = subparsers.add_parser("evaluate")
    evaluate.add_argument("--reference-manifest", type=Path, required=True)
    evaluate.add_argument("--media-root", type=Path, required=True)
    evaluate.add_argument("--study-manifest", type=Path, required=True)
    evaluate.add_argument("--community-run", type=Path, required=True)
    evaluate.add_argument("--control-run", type=Path, required=True)
    evaluate.add_argument("--approval", type=Path, required=True)
    evaluate.add_argument("--approval-signature", type=Path, required=True)
    evaluate.add_argument("--allowed-signers", type=Path, required=True)
    evaluate.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    use_utf8_streams()
    args = _parser().parse_args(argv)
    try:
        with machine_readable_stdout() as stdout:
            if args.command == "prepare":
                prepared = prepare_diarization_study(
                    reference_manifest_path=args.reference_manifest,
                    media_root=args.media_root,
                    output_dir=args.output_dir,
                )
                payload = {"directory": str(prepared.directory), "status": "prepared"}
            else:
                verified = evaluate_diarization_study(
                    reference_manifest_path=args.reference_manifest,
                    media_root=args.media_root,
                    study_manifest_path=args.study_manifest,
                    community_run_path=args.community_run,
                    control_run_path=args.control_run,
                    approval_path=args.approval,
                    approval_signature_path=args.approval_signature,
                    allowed_signers_path=args.allowed_signers,
                    output_dir=args.output_dir,
                )
                payload = {"directory": str(verified.directory), "status": "verified"}
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=stdout)
        return 0
    except DiarizationAcceptanceError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
