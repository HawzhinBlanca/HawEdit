"""One-shot, signed and content-bound confidential Vertex acceptance.

Preparation is deliberately offline. Execution proves the signed private inputs again, checks
the live ADC project, Vertex API and billing state, and only then reserves one attempt before
delegating the sole counted generation to :class:`hawedit.gemini.VertexGeminiJudge`.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
import shutil
import stat
import subprocess
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Final, Protocol

from hawedit.atomic_fs import rename_directory_noreplace
from hawedit.gemini import Governance, VertexGeminiJudge
from hawedit.http_transport import open_without_redirects
from hawedit.ingest import IngestError, probe_duration_ms, probe_stream
from hawedit.judge import (
    KURDISH_EDITORIAL_JUDGE,
    PRO_TIER_TOKEN_CEILING,
    USD_PER_MILLION_TOKENS,
    InputMode,
    JudgeFrame,
    JudgeRequest,
    JudgeVerdict,
    estimate_cost_usd,
)
from hawedit.keyframes import KeyframeError, extract_judge_frames
from hawedit.normalize import normalize_sorani
from hawedit.transcripts import NormalizedTranscript, Word
from hawedit.windows_security import (
    WindowsSecurityError,
    assert_private_windows_path,
    create_private_directory,
)

__all__ = [
    "SIGNATURE_NAMESPACE",
    "PreparedVertexAcceptance",
    "VerifiedVertexAcceptance",
    "VertexAcceptanceError",
    "VertexEnvironment",
    "prepare_vertex_acceptance",
    "probe_vertex_environment",
    "run_vertex_acceptance",
]

SIGNATURE_NAMESPACE: Final = "hawedit-vertex-acceptance-v1"
_SCHEMA: Final = 1
_MAX_JSON_BYTES: Final = 16 * 1024 * 1024
_MAX_POLICY_BYTES: Final = 16 * 1024 * 1024
_MAX_CLOUD_RESPONSE_BYTES: Final = 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_RFC3339_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_PROJECT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*\Z")
_LOCATION = re.compile(r"[a-z][a-z0-9-]*\Z")
_SIGNER_FINGERPRINT = re.compile(rb"SHA256:([A-Za-z0-9+/]+={0,2})")
_PREPARED_FILES: Final = frozenset(
    {"INSTRUCTIONS.txt", "approval.template.json", "vertex-acceptance.json"}
)
_RESULT_FILES: Final = frozenset({"INSTRUCTIONS.txt", "vertex-evidence.json"})
_ATTEMPT_FILES: Final = frozenset({"attempt.json"})
_PLACEHOLDERS: Final = frozenset(
    {"", "unknown", "tbd", "todo", "none", "n/a", "unrecorded", "placeholder"}
)


class VertexAcceptanceError(ValueError):
    """The purported confidential acceptance is incomplete, unsafe or no longer authentic."""


def _one_line(value: object, field_name: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str):
        raise VertexAcceptanceError(f"{field_name} must be a string")
    if (
        not value
        or value.strip() != value
        or not value.isprintable()
        or value.splitlines() != [value]
        or len(value) > maximum
    ):
        raise VertexAcceptanceError(
            f"{field_name} must be non-empty, trimmed, printable, one line, and at most "
            f"{maximum} characters"
        )
    if value.casefold() in _PLACEHOLDERS:
        raise VertexAcceptanceError(f"{field_name} is placeholder text")
    return value


def _exact_bool(value: object, field_name: str) -> bool:
    if type(value) is not bool:
        raise VertexAcceptanceError(f"{field_name} must be a JSON boolean")
    return value


def _exact_int(
    value: object, field_name: str, *, minimum: int = 0, maximum: int | None = None
) -> int:
    if type(value) is not int:
        raise VertexAcceptanceError(f"{field_name} must be a JSON integer")
    if value < minimum or (maximum is not None and value > maximum):
        suffix = f"..{maximum}" if maximum is not None else " or greater"
        raise VertexAcceptanceError(f"{field_name} must be {minimum}{suffix}")
    return value


def _number(value: object, field_name: str, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise VertexAcceptanceError(f"{field_name} must be a JSON number")
    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise VertexAcceptanceError(f"{field_name} must be in {minimum}..{maximum}")
    return result


def _digest(value: object, field_name: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise VertexAcceptanceError(f"{field_name} must be a lowercase SHA-256 digest")
    return value


def _timestamp(value: object, field_name: str) -> str:
    text = _one_line(value, field_name, maximum=20)
    if _RFC3339_UTC.fullmatch(text) is None:
        raise VertexAcceptanceError(f"{field_name} must be RFC3339 UTC seconds")
    try:
        datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise VertexAcceptanceError(f"{field_name} is not a real UTC timestamp") from exc
    return text


def _strict_object(value: object, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise VertexAcceptanceError(f"{field_name} must be a JSON object")
    return value


def _exact_fields(value: Mapping[str, Any], expected: set[str], field_name: str) -> None:
    actual = set(value)
    if actual != expected:
        raise VertexAcceptanceError(
            f"{field_name} fields do not match schema; "
            f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )


def _array(value: object, field_name: str) -> list[object]:
    if not isinstance(value, list):
        raise VertexAcceptanceError(f"{field_name} must be a JSON array")
    return value


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise VertexAcceptanceError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _canonical_json(document: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _is_reparse(info: os.stat_result) -> bool:
    attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(getattr(info, "st_file_attributes", 0) & attribute)


def _identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_nlink)


def _read_bound_file(path: Path, label: str, maximum: int | None) -> bytes:
    try:
        before_path = os.lstat(path)
    except OSError as exc:
        raise VertexAcceptanceError(f"cannot inspect {label} {path}: {exc}") from exc
    if stat.S_ISLNK(before_path.st_mode) or _is_reparse(before_path):
        raise VertexAcceptanceError(f"{label} must not be a symlink or reparse point: {path}")
    if not stat.S_ISREG(before_path.st_mode):
        raise VertexAcceptanceError(f"{label} must be a regular file: {path}")
    if before_path.st_nlink != 1:
        raise VertexAcceptanceError(f"{label} must not be a hardlink: {path}")
    if maximum is not None and before_path.st_size > maximum:
        raise VertexAcceptanceError(f"{label} exceeds its {maximum}-byte limit: {path}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise VertexAcceptanceError(f"cannot open {label} {path}: {exc}") from exc
    try:
        before_fd = os.fstat(descriptor)
        if _identity(before_fd) != _identity(before_path):
            raise VertexAcceptanceError(f"{label} changed while opening: {path}")
        chunks: list[bytes] = []
        total = 0
        while chunk := os.read(descriptor, 1024 * 1024):
            total += len(chunk)
            if maximum is not None and total > maximum:
                raise VertexAcceptanceError(f"{label} exceeds its byte limit: {path}")
            chunks.append(chunk)
        after_fd = os.fstat(descriptor)
        if (
            _identity(after_fd) != _identity(before_fd)
            or after_fd.st_ctime_ns != before_fd.st_ctime_ns
        ):
            raise VertexAcceptanceError(f"{label} changed while being read: {path}")
    finally:
        os.close(descriptor)
    try:
        after_path = os.lstat(path)
    except OSError as exc:
        raise VertexAcceptanceError(f"cannot re-inspect {label} {path}: {exc}") from exc
    if (
        _identity(after_path) != _identity(before_path)
        or after_path.st_ctime_ns != before_path.st_ctime_ns
    ):
        raise VertexAcceptanceError(f"{label} path changed while being read: {path}")
    return b"".join(chunks)


def _stable_digest(path: Path, label: str) -> str:
    digest = hashlib.sha256()
    try:
        before_path = os.lstat(path)
    except OSError as exc:
        raise VertexAcceptanceError(f"cannot inspect {label} {path}: {exc}") from exc
    if stat.S_ISLNK(before_path.st_mode) or _is_reparse(before_path):
        raise VertexAcceptanceError(f"{label} must not be a symlink or reparse point: {path}")
    if not stat.S_ISREG(before_path.st_mode):
        raise VertexAcceptanceError(f"{label} must be a regular file: {path}")
    if before_path.st_nlink != 1:
        raise VertexAcceptanceError(f"{label} must not be a hardlink: {path}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise VertexAcceptanceError(f"cannot open {label} {path}: {exc}") from exc
    try:
        before_fd = os.fstat(descriptor)
        if _identity(before_fd) != _identity(before_path):
            raise VertexAcceptanceError(f"{label} changed while opening: {path}")
        while chunk := os.read(descriptor, 1024 * 1024):
            digest.update(chunk)
        after_fd = os.fstat(descriptor)
        if (
            _identity(after_fd) != _identity(before_fd)
            or after_fd.st_ctime_ns != before_fd.st_ctime_ns
        ):
            raise VertexAcceptanceError(f"{label} changed while hashing: {path}")
    finally:
        os.close(descriptor)
    try:
        after_path = os.lstat(path)
    except OSError as exc:
        raise VertexAcceptanceError(f"cannot re-inspect {label} {path}: {exc}") from exc
    if (
        _identity(after_path) != _identity(before_path)
        or after_path.st_ctime_ns != before_path.st_ctime_ns
    ):
        raise VertexAcceptanceError(f"{label} path changed while hashing: {path}")
    return digest.hexdigest()


def _load_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    payload = _read_bound_file(path, label, _MAX_JSON_BYTES)
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VertexAcceptanceError(f"{label} is not strict UTF-8 JSON: {exc}") from exc
    return _strict_object(value, label), payload


def _relative_path(value: object, field_name: str) -> str:
    text = _one_line(value, field_name)
    if "\\" in text:
        raise VertexAcceptanceError(f"{field_name} must use forward slashes")
    relative = PurePosixPath(text)
    if relative.is_absolute() or any(
        part in {"", ".", ".."} or ":" in part for part in relative.parts
    ):
        raise VertexAcceptanceError(f"{field_name} must be one contained relative path")
    return text


def _bound_directory(path: Path, label: str) -> tuple[Path, tuple[int, int]]:
    absolute = Path(os.path.abspath(path))
    try:
        info = os.lstat(absolute)
    except OSError as exc:
        raise VertexAcceptanceError(f"cannot inspect {label} {absolute}: {exc}") from exc
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or _is_reparse(info):
        raise VertexAcceptanceError(f"{label} must be one real directory: {absolute}")
    return absolute, (info.st_dev, info.st_ino)


def _assert_directory(path: Path, identity: tuple[int, int], label: str) -> None:
    _, current = _bound_directory(path, label)
    if current != identity:
        raise VertexAcceptanceError(f"{label} identity changed: {path}")


def _assert_private_directory(
    path: Path, identity: tuple[int, int], label: str, *, require_protected: bool = True
) -> None:
    _assert_directory(path, identity, label)
    try:
        info = os.lstat(path)
        if os.name == "nt":
            assert_private_windows_path(path, require_protected=require_protected)
        elif (info.st_mode & 0o077) != 0 or (
            hasattr(os, "geteuid") and info.st_uid != os.geteuid()
        ):
            raise VertexAcceptanceError(f"{label} is not private to the current user: {path}")
    except WindowsSecurityError as exc:
        raise VertexAcceptanceError(f"{label} does not have a private Windows ACL: {path}") from exc
    except OSError as exc:
        raise VertexAcceptanceError(f"cannot inspect private {label} {path}: {exc}") from exc


def _create_private_directory(
    parent: Path, *, prefix: str, suffix: str = ""
) -> tuple[Path, tuple[int, int]]:
    for _ in range(32):
        candidate = parent / f"{prefix}{secrets.token_hex(16)}{suffix}"
        try:
            if os.name == "nt":
                create_private_directory(candidate)
            else:
                os.mkdir(candidate, 0o700)
        except FileExistsError:
            continue
        except (OSError, WindowsSecurityError) as exc:
            raise VertexAcceptanceError(
                f"cannot create private Vertex directory under {parent}"
            ) from exc
        _, identity = _bound_directory(candidate, "private Vertex directory")
        _assert_private_directory(candidate, identity, "private Vertex directory")
        return candidate, identity
    raise VertexAcceptanceError("could not allocate a unique private Vertex directory")


def _contained_file(root: Path, relative: str, label: str) -> Path:
    current = root
    parts = PurePosixPath(_relative_path(relative, f"{label} path")).parts
    for index, part in enumerate(parts):
        current /= part
        try:
            info = os.lstat(current)
        except OSError as exc:
            raise VertexAcceptanceError(f"cannot inspect {label} {current}: {exc}") from exc
        if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
            raise VertexAcceptanceError(f"{label} path contains a link: {current}")
        if index < len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise VertexAcceptanceError(f"{label} parent is not a directory: {current}")
    return current


def _write_private(path: Path, payload: bytes) -> None:
    try:
        with path.open("xb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
    except OSError as exc:
        raise VertexAcceptanceError(f"cannot stage Vertex evidence {path}: {exc}") from exc


@contextmanager
def _private_frame_directory(parent: Path) -> Iterator[Path]:
    temporary, identity = _create_private_directory(parent, prefix=".hawedit-vertex-frames-")
    try:
        yield temporary
    except BaseException as primary:
        try:
            _discard_private_tree(temporary, identity)
        except (OSError, VertexAcceptanceError) as cleanup:
            primary.add_note(
                "HawEdit could not remove confidential Vertex frame bytes: "
                f"{type(cleanup).__name__}: {cleanup}"
            )
        raise
    else:
        try:
            _discard_private_tree(temporary, identity)
        except (OSError, VertexAcceptanceError) as exc:
            raise VertexAcceptanceError(
                "confidential Vertex frame cleanup failed after the request; the no-replay "
                "reservation was retained"
            ) from exc


def _discard_private_tree(
    directory: Path, identity: tuple[int, int], *, require_protected: bool = True
) -> None:
    """Remove only regular, single-link files inside one still-bound private directory."""
    _assert_private_directory(
        directory,
        identity,
        "confidential Vertex frame workspace",
        require_protected=require_protected,
    )
    try:
        entries = tuple(os.scandir(directory))
    except OSError as exc:
        raise VertexAcceptanceError(
            f"cannot enumerate confidential Vertex frame workspace {directory}: {exc}"
        ) from exc
    for entry in entries:
        child = Path(entry.path)
        try:
            # Windows' DirEntry.stat() can report synthetic zero device/inode values even
            # though os.lstat() exposes the stable file identity used by _bound_directory.
            info = os.lstat(child)
        except OSError as exc:
            raise VertexAcceptanceError(f"cannot inspect confidential frame path {child}") from exc
        if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
            raise VertexAcceptanceError(f"refusing to clean linked confidential frame path {child}")
        if stat.S_ISREG(info.st_mode):
            if info.st_nlink != 1:
                raise VertexAcceptanceError(
                    f"refusing to clean hardlinked confidential frame path {child}"
                )
            child.unlink()
        elif stat.S_ISDIR(info.st_mode):
            _discard_private_tree(child, (info.st_dev, info.st_ino), require_protected=False)
        else:
            raise VertexAcceptanceError(
                f"refusing to clean unsupported confidential frame path {child}"
            )
    _assert_private_directory(
        directory,
        identity,
        "confidential Vertex frame workspace",
        require_protected=require_protected,
    )
    directory.rmdir()


def _discard_private(staging: Path, identity: tuple[int, int], expected: frozenset[str]) -> None:
    if not os.path.lexists(staging):
        return
    _assert_private_directory(staging, identity, "private Vertex-evidence directory")
    children = tuple(staging.iterdir())
    unexpected = sorted(child.name for child in children if child.name not in expected)
    if unexpected:
        raise VertexAcceptanceError(
            "refusing to clean unexpected private Vertex evidence: " + ", ".join(unexpected)
        )
    for child in children:
        info = os.lstat(child)
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or _is_reparse(info)
            or info.st_nlink != 1
        ):
            raise VertexAcceptanceError(f"refusing to clean unsafe evidence file {child}")
        child.unlink()
    staging.rmdir()


def _publish_exact(
    output_dir: Path, payloads: Mapping[str, bytes], expected: frozenset[str]
) -> Path:
    if frozenset(payloads) != expected:
        raise VertexAcceptanceError("Vertex evidence is not an exact supported file set")
    destination = Path(os.path.abspath(output_dir))
    parent, parent_identity = _bound_directory(destination.parent, "Vertex output parent")
    if os.path.lexists(destination):
        raise VertexAcceptanceError(f"Vertex evidence already exists at {destination}")
    staging, staging_identity = _create_private_directory(
        parent, prefix=f".{destination.name}.", suffix=".staging"
    )
    try:
        for name in sorted(expected):
            _write_private(staging / name, payloads[name])
        _assert_directory(parent, parent_identity, "Vertex output parent")
        _assert_private_directory(staging, staging_identity, "private Vertex-evidence directory")
        if frozenset(path.name for path in staging.iterdir()) != expected:
            raise VertexAcceptanceError("private Vertex evidence set changed")
        rename_directory_noreplace(staging, destination)
        _assert_private_directory(destination, staging_identity, "published Vertex evidence")
        _assert_directory(parent, parent_identity, "Vertex output parent")
    except BaseException as primary:
        try:
            _discard_private(staging, staging_identity, expected)
        except (OSError, VertexAcceptanceError) as cleanup:
            primary.add_note(f"HawEdit Vertex-evidence cleanup also failed: {cleanup}")
        if isinstance(primary, FileExistsError):
            raise VertexAcceptanceError(
                f"Vertex evidence already exists at {destination}; another publisher won"
            ) from primary
        if isinstance(primary, OSError):
            raise VertexAcceptanceError(
                f"cannot atomically publish Vertex evidence {destination}: {primary}"
            ) from primary
        raise
    return destination


def _default_media_probe(path: Path) -> tuple[int, int]:
    try:
        duration = probe_duration_ms(path)
        dimensions = probe_stream(path, "stream=width,height", video_only=True)
        width = int(dimensions.split("x", 1)[0])
    except (IngestError, OSError, ValueError, IndexError) as exc:
        raise VertexAcceptanceError(f"Vertex media is not probeable video: {exc}") from exc
    return duration, width


@dataclass(frozen=True, slots=True)
class _Study:
    study_id: str
    project: str
    location: str
    model_id: str
    source_manifest_sha256: str
    media_path: Path
    media_sha256: str
    media_duration_ms: int
    media_width: int
    authorized_by: str
    billing_account_reference: str
    billing_confirmed_at: str
    billing_confirmed_by: str
    policy_sha256: str
    retention_confirmed_at: str
    retention_confirmed_by: str
    transcript_sha256: str
    transcript: NormalizedTranscript
    candidate_id: str
    clip_in_ms: int
    clip_out_ms: int
    request_text: str
    visual_context: tuple[str, ...]
    carried_verbal_score: float | None
    request_sha256: str
    expected_adc_project: str
    expected_credential_type: str
    expected_principal: str
    max_input_tokens: int
    max_estimated_input_cost_usd: float

    @property
    def effective_max_tokens(self) -> int:
        cost_ceiling = math.floor(
            self.max_estimated_input_cost_usd * 1_000_000 / USD_PER_MILLION_TOKENS
        )
        return min(self.max_input_tokens, cost_ceiling)


def _normalised_transcript(payload: bytes, expected_media_id: str) -> NormalizedTranscript:
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VertexAcceptanceError(
            f"normalised transcript is not strict UTF-8 JSON: {exc}"
        ) from exc
    raw = _strict_object(value, "normalised transcript")
    _exact_fields(raw, {"media_id", "source_sha256", "text_ckb", "words"}, "normalised transcript")
    words: list[Word] = []
    previous_end = 0
    for index, item in enumerate(_array(raw["words"], "normalised transcript words")):
        word = _strict_object(item, f"normalised transcript words[{index}]")
        _exact_fields(
            word, {"conf", "end_ms", "start_ms", "w"}, f"normalised transcript words[{index}]"
        )
        try:
            parsed_word = Word(
                w=_one_line(word["w"], f"word {index}"),
                start_ms=_exact_int(word["start_ms"], f"word {index} start"),
                end_ms=_exact_int(word["end_ms"], f"word {index} end", minimum=1),
                conf=_number(word["conf"], f"word {index} confidence", minimum=0.0, maximum=1.0),
            )
        except ValueError as exc:
            raise VertexAcceptanceError(
                f"invalid normalised transcript word {index}: {exc}"
            ) from exc
        if parsed_word.start_ms < previous_end:
            raise VertexAcceptanceError(
                "normalised transcript words must be chronological and non-overlapping"
            )
        words.append(parsed_word)
        previous_end = parsed_word.end_ms
    try:
        transcript = NormalizedTranscript(
            media_id=_one_line(raw["media_id"], "transcript media_id"),
            text_ckb=_one_line(raw["text_ckb"], "normalised transcript text", maximum=8_000_000),
            source_sha256=_digest(raw["source_sha256"], "normalised transcript source_sha256"),
            words=tuple(words),
        )
    except ValueError as exc:
        raise VertexAcceptanceError(f"invalid normalised transcript identity: {exc}") from exc
    if transcript.media_id != expected_media_id:
        raise VertexAcceptanceError("normalised transcript belongs to a different media id")
    if normalize_sorani(transcript.text_ckb) != transcript.text_ckb:
        raise VertexAcceptanceError("transcript is not in the §4.1 normal form")
    return transcript


def _study(
    document: Mapping[str, Any],
    source_bytes: bytes,
    private_root: Path,
    media_probe: Callable[[Path], tuple[int, int]],
) -> _Study:
    _exact_fields(
        document,
        {
            "billing",
            "environment",
            "limits",
            "location",
            "media",
            "model_id",
            "project",
            "request",
            "retention",
            "schema",
            "study_id",
            "transcript",
        },
        "Vertex source manifest",
    )
    if _exact_int(document["schema"], "source schema", minimum=1) != _SCHEMA:
        raise VertexAcceptanceError("unsupported Vertex source schema")
    study_id = _one_line(document["study_id"], "study_id")
    project = _one_line(document["project"], "project")
    location = _one_line(document["location"], "location")
    model_id = _one_line(document["model_id"], "model_id")
    if _PROJECT.fullmatch(project) is None:
        raise VertexAcceptanceError("project is not a valid Vertex project identifier")
    if _LOCATION.fullmatch(location) is None:
        raise VertexAcceptanceError("location is not a valid Vertex location")
    if model_id != KURDISH_EDITORIAL_JUDGE:
        raise VertexAcceptanceError(
            f"Vertex acceptance must use pinned judge {KURDISH_EDITORIAL_JUDGE!r}"
        )

    billing = _strict_object(document["billing"], "billing")
    _exact_fields(
        billing,
        {"billing_account_reference", "billing_enabled", "confirmed_at_utc", "confirmed_by"},
        "billing",
    )
    if not _exact_bool(billing["billing_enabled"], "billing.billing_enabled"):
        raise VertexAcceptanceError("billing.billing_enabled must be true")
    billing_account = _one_line(billing["billing_account_reference"], "billing account reference")
    billing_at = _timestamp(billing["confirmed_at_utc"], "billing confirmation timestamp")
    billing_by = _one_line(billing["confirmed_by"], "billing confirmer")

    retention = _strict_object(document["retention"], "retention")
    _exact_fields(
        retention,
        {
            "confirmed_at_utc",
            "confirmed_by",
            "policy_path",
            "policy_sha256",
            "zero_data_retention",
        },
        "retention",
    )
    if not _exact_bool(retention["zero_data_retention"], "retention.zero_data_retention"):
        raise VertexAcceptanceError("retention.zero_data_retention must be true")
    policy_path = _contained_file(
        private_root,
        _relative_path(retention["policy_path"], "retention.policy_path"),
        "retained ZDR policy",
    )
    policy_bytes = _read_bound_file(policy_path, "retained ZDR policy", _MAX_POLICY_BYTES)
    policy_sha = _digest(retention["policy_sha256"], "retention.policy_sha256")
    if hashlib.sha256(policy_bytes).hexdigest() != policy_sha:
        raise VertexAcceptanceError("retained ZDR policy digest does not match")
    retention_at = _timestamp(retention["confirmed_at_utc"], "retention confirmation timestamp")
    retention_by = _one_line(retention["confirmed_by"], "retention confirmer")

    media = _strict_object(document["media"], "media")
    _exact_fields(
        media,
        {
            "authorized_by",
            "consent_authorization_basis",
            "duration_ms",
            "licence",
            "path",
            "rights_owner",
            "sha256",
            "use_scope",
        },
        "media",
    )
    for field_name in (
        "authorized_by",
        "consent_authorization_basis",
        "licence",
        "rights_owner",
        "use_scope",
    ):
        _one_line(media[field_name], f"media.{field_name}")
    media_path = _contained_file(
        private_root, _relative_path(media["path"], "media.path"), "client media"
    )
    declared_media_sha = _digest(media["sha256"], "media.sha256")
    before_media_sha = _stable_digest(media_path, "client media")
    if before_media_sha != declared_media_sha:
        raise VertexAcceptanceError("client media digest does not match")
    declared_duration = _exact_int(media["duration_ms"], "media.duration_ms", minimum=1)
    try:
        measured_duration, measured_width = media_probe(media_path)
    except VertexAcceptanceError:
        raise
    except (OSError, ValueError) as exc:
        raise VertexAcceptanceError(f"client media probe failed: {exc}") from exc
    if measured_duration != declared_duration:
        raise VertexAcceptanceError(
            f"client media duration is {measured_duration} ms, not declared {declared_duration} ms"
        )
    if measured_width <= 0:
        raise VertexAcceptanceError("client media returned a non-positive frame width")
    if _stable_digest(media_path, "client media") != before_media_sha:
        raise VertexAcceptanceError("client media changed while being probed")

    transcript_record = _strict_object(document["transcript"], "transcript")
    _exact_fields(transcript_record, {"media_id", "path", "sha256"}, "transcript")
    transcript_media_id = _one_line(transcript_record["media_id"], "transcript.media_id")
    transcript_path = _contained_file(
        private_root,
        _relative_path(transcript_record["path"], "transcript.path"),
        "normalised transcript",
    )
    transcript_bytes = _read_bound_file(transcript_path, "normalised transcript", _MAX_JSON_BYTES)
    transcript_sha = _digest(transcript_record["sha256"], "transcript.sha256")
    if hashlib.sha256(transcript_bytes).hexdigest() != transcript_sha:
        raise VertexAcceptanceError("normalised transcript digest does not match")
    transcript = _normalised_transcript(transcript_bytes, transcript_media_id)

    request = _strict_object(document["request"], "request")
    _exact_fields(
        request,
        {
            "candidate_id",
            "carried_verbal_score",
            "clip_in_ms",
            "clip_out_ms",
            "text_ckb",
            "visual_context",
        },
        "request",
    )
    candidate_id = _one_line(request["candidate_id"], "request.candidate_id")
    clip_in = _exact_int(request["clip_in_ms"], "request.clip_in_ms")
    clip_out = _exact_int(request["clip_out_ms"], "request.clip_out_ms", minimum=1)
    if clip_out <= clip_in or clip_out > declared_duration:
        raise VertexAcceptanceError("request clip must be non-empty and contained in client media")
    request_text = _one_line(request["text_ckb"], "request.text_ckb", maximum=1_000_000)
    if normalize_sorani(request_text) != request_text:
        raise VertexAcceptanceError("request text is not in the §4.1 normal form")
    aligned_request_text = normalize_sorani(
        " ".join(
            word.w
            for word in transcript.words
            if word.start_ms < clip_out and word.end_ms > clip_in
        )
    )
    if not aligned_request_text or request_text != aligned_request_text:
        raise VertexAcceptanceError(
            "request text does not exactly match the bound aligned words overlapping the clip"
        )
    context_items = _array(request["visual_context"], "request.visual_context")
    if len(context_items) > 20:
        raise VertexAcceptanceError("request.visual_context accepts at most 20 entries")
    visual_context = tuple(
        _one_line(item, f"request.visual_context[{index}]", maximum=2_000)
        for index, item in enumerate(context_items)
    )
    score_value = request["carried_verbal_score"]
    carried_score = (
        None
        if score_value is None
        else _number(score_value, "request.carried_verbal_score", minimum=0.0, maximum=1.0)
    )

    environment = _strict_object(document["environment"], "environment")
    _exact_fields(
        environment,
        {"expected_adc_project", "expected_credential_type", "expected_principal"},
        "environment",
    )
    expected_project = _one_line(environment["expected_adc_project"], "expected ADC project")
    if expected_project != project:
        raise VertexAcceptanceError("expected ADC project must equal the approved Vertex project")
    credential_type = _one_line(environment["expected_credential_type"], "expected credential type")
    principal = _one_line(environment["expected_principal"], "expected ADC principal")

    limits = _strict_object(document["limits"], "limits")
    _exact_fields(limits, {"max_estimated_input_cost_usd", "max_input_tokens"}, "limits")
    max_tokens = _exact_int(limits["max_input_tokens"], "limits.max_input_tokens", minimum=1)
    if max_tokens >= PRO_TIER_TOKEN_CEILING:
        raise VertexAcceptanceError(
            f"limits.max_input_tokens must be below {PRO_TIER_TOKEN_CEILING}"
        )
    max_cost = _number(
        limits["max_estimated_input_cost_usd"],
        "limits.max_estimated_input_cost_usd",
        minimum=estimate_cost_usd(1),
        maximum=estimate_cost_usd(PRO_TIER_TOKEN_CEILING - 1),
    )
    request_binding = {
        "candidate_id": candidate_id,
        "carried_verbal_score": carried_score,
        "clip_in_ms": clip_in,
        "clip_out_ms": clip_out,
        "text_ckb": request_text,
        "visual_context": list(visual_context),
    }
    return _Study(
        study_id=study_id,
        project=project,
        location=location,
        model_id=model_id,
        source_manifest_sha256=hashlib.sha256(source_bytes).hexdigest(),
        media_path=media_path,
        media_sha256=declared_media_sha,
        media_duration_ms=declared_duration,
        media_width=measured_width,
        authorized_by=_one_line(media["authorized_by"], "media.authorized_by"),
        billing_account_reference=billing_account,
        billing_confirmed_at=billing_at,
        billing_confirmed_by=billing_by,
        policy_sha256=policy_sha,
        retention_confirmed_at=retention_at,
        retention_confirmed_by=retention_by,
        transcript_sha256=transcript_sha,
        transcript=transcript,
        candidate_id=candidate_id,
        clip_in_ms=clip_in,
        clip_out_ms=clip_out,
        request_text=request_text,
        visual_context=visual_context,
        carried_verbal_score=carried_score,
        request_sha256=hashlib.sha256(_canonical_json(request_binding)).hexdigest(),
        expected_adc_project=expected_project,
        expected_credential_type=credential_type,
        expected_principal=principal,
        max_input_tokens=max_tokens,
        max_estimated_input_cost_usd=max_cost,
    )


def _prepared_manifest(study: _Study) -> dict[str, object]:
    return {
        "authorized_by": study.authorized_by,
        "billing_confirmation_sha256": hashlib.sha256(
            _canonical_json(
                {
                    "billing_account_reference": study.billing_account_reference,
                    "confirmed_at_utc": study.billing_confirmed_at,
                    "confirmed_by": study.billing_confirmed_by,
                }
            )
        ).hexdigest(),
        "clip_in_ms": study.clip_in_ms,
        "clip_out_ms": study.clip_out_ms,
        "expected_adc_project": study.expected_adc_project,
        "expected_credential_type": study.expected_credential_type,
        "expected_principal_sha256": hashlib.sha256(study.expected_principal.encode()).hexdigest(),
        "location": study.location,
        "max_estimated_input_cost_usd": study.max_estimated_input_cost_usd,
        "max_input_tokens": study.max_input_tokens,
        "media_duration_ms": study.media_duration_ms,
        "media_sha256": study.media_sha256,
        "media_width": study.media_width,
        "model_id": study.model_id,
        "policy_sha256": study.policy_sha256,
        "project": study.project,
        "request_sha256": study.request_sha256,
        "schema": _SCHEMA,
        "source_manifest_sha256": study.source_manifest_sha256,
        "study_id": study.study_id,
        "transcript_sha256": study.transcript_sha256,
    }


@dataclass(frozen=True, slots=True)
class PreparedVertexAcceptance:
    directory: Path
    manifest_path: Path
    approval_template_path: Path


def prepare_vertex_acceptance(
    *,
    source_manifest_path: Path,
    private_root: Path,
    output_dir: Path,
    media_probe: Callable[[Path], tuple[int, int]] = _default_media_probe,
) -> PreparedVertexAcceptance:
    """Validate private inputs and publish a transport-free approval packet."""
    root, root_identity = _bound_directory(private_root, "Vertex private root")
    source_document, source_bytes = _load_json(source_manifest_path, "Vertex source manifest")
    study = _study(source_document, source_bytes, root, media_probe)
    _assert_directory(root, root_identity, "Vertex private root")
    manifest = _prepared_manifest(study)
    manifest_bytes = _canonical_json(manifest)
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    approval = {
        "approved_at_utc": None,
        "approved_by": None,
        "billing_confirmed": False,
        "media_rights_confirmed": False,
        "one_paid_request_approved": False,
        "schema": _SCHEMA,
        "statement": None,
        "study_manifest_sha256": manifest_sha,
        "zero_data_retention_confirmed": False,
    }
    instructions = (
        "CONFIDENTIAL VERTEX ACCEPTANCE — NO REQUEST HAS BEEN SENT\n\n"
        "Review the retained private source manifest, media, normalized transcript, billing "
        "link and contractual zero-data-retention policy. Fill approval.template.json without "
        "changing study_manifest_sha256, sign its exact bytes with OpenSSH namespace "
        f"{SIGNATURE_NAMESPACE}, and retain private inputs outside the repository. Execution "
        "will reserve exactly one paid generation attempt; a failed or ambiguous attempt is not "
        "replayed.\n"
    ).encode()
    directory = _publish_exact(
        output_dir,
        {
            "INSTRUCTIONS.txt": instructions,
            "approval.template.json": _canonical_json(approval),
            "vertex-acceptance.json": manifest_bytes,
        },
        _PREPARED_FILES,
    )
    return PreparedVertexAcceptance(
        directory=directory,
        manifest_path=directory / "vertex-acceptance.json",
        approval_template_path=directory / "approval.template.json",
    )


@dataclass(frozen=True, slots=True)
class VertexEnvironment:
    project: str
    credential_type: str
    principal: str
    billing_enabled: bool
    billing_account_reference: str
    aiplatform_enabled: bool
    checked_at_utc: str
    access_token: str = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        _one_line(self.project, "live ADC project")
        _one_line(self.credential_type, "live credential type")
        _one_line(self.principal, "live ADC principal")
        _exact_bool(self.billing_enabled, "live billing state")
        _one_line(self.billing_account_reference, "live billing account reference")
        _exact_bool(self.aiplatform_enabled, "live Vertex API state")
        _timestamp(self.checked_at_utc, "live environment timestamp")
        _one_line(self.access_token, "live ADC access token", maximum=16_384)


def _cloud_get_json(url: str, access_token: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        method="GET",
    )
    try:
        with open_without_redirects(request, timeout=30) as response:
            payload = response.read(_MAX_CLOUD_RESPONSE_BYTES + 1)
            status = response.status
    except urllib.error.HTTPError as exc:
        payload = exc.read(_MAX_CLOUD_RESPONSE_BYTES + 1)
        status = exc.code
    except OSError as exc:
        raise VertexAcceptanceError(
            "Vertex environment preflight could not reach Google Cloud; no client content was sent"
        ) from exc
    if len(payload) > _MAX_CLOUD_RESPONSE_BYTES:
        raise VertexAcceptanceError("Google Cloud preflight response exceeded 1 MiB")
    if status != 200:
        raise VertexAcceptanceError(
            f"Google Cloud preflight returned HTTP {status}; no client content was sent"
        )
    try:
        document = json.loads(payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VertexAcceptanceError("Google Cloud preflight returned malformed JSON") from exc
    return _strict_object(document, "Google Cloud preflight response")


def _credential_identity(credentials: object) -> tuple[str, str]:
    module = type(credentials).__module__
    if module.startswith("google.oauth2.service_account"):
        kind = "service_account"
    elif module.startswith("google.oauth2.credentials"):
        kind = "authorized_user"
    else:
        kind = f"{module}.{type(credentials).__name__}"
    principal = next(
        (
            value
            for name in ("service_account_email", "signer_email", "account")
            if isinstance((value := getattr(credentials, name, None)), str) and value.strip()
        ),
        "",
    )
    if not principal:
        raise VertexAcceptanceError(
            "Application Default Credentials do not expose an attributable principal"
        )
    return kind, principal


def probe_vertex_environment(project: str) -> VertexEnvironment:
    """Refresh ADC and verify live billing plus Vertex API enablement without client content."""
    if _PROJECT.fullmatch(project) is None:
        raise VertexAcceptanceError("invalid Vertex project identifier")
    try:
        import google.auth
        from google.auth.exceptions import GoogleAuthError
        from google.auth.transport.requests import Request
    except ImportError as exc:
        raise VertexAcceptanceError("Vertex preflight requires the cloud extra") from exc
    try:
        credentials, adc_project = google.auth.default(
            scopes=("https://www.googleapis.com/auth/cloud-platform",)
        )
        credentials.refresh(Request())
    except (GoogleAuthError, OSError, UnicodeError) as exc:
        raise VertexAcceptanceError(
            "Application Default Credentials could not be acquired or refreshed"
        ) from exc
    token = getattr(credentials, "token", None)
    if not isinstance(token, str) or not token:
        raise VertexAcceptanceError("Application Default Credentials returned no access token")
    if not isinstance(adc_project, str) or not adc_project:
        raise VertexAcceptanceError("Application Default Credentials returned no project")
    billing = _cloud_get_json(
        f"https://cloudbilling.googleapis.com/v1/projects/{project}/billingInfo", token
    )
    service = _cloud_get_json(
        "https://serviceusage.googleapis.com/v1/projects/"
        f"{project}/services/aiplatform.googleapis.com",
        token,
    )
    kind, principal = _credential_identity(credentials)
    return VertexEnvironment(
        project=adc_project,
        credential_type=kind,
        principal=principal,
        billing_enabled=_exact_bool(billing.get("billingEnabled"), "Cloud Billing state"),
        billing_account_reference=_one_line(
            billing.get("billingAccountName"), "Cloud Billing account"
        ),
        aiplatform_enabled=service.get("state") == "ENABLED",
        checked_at_utc=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        access_token=token,
    )


@dataclass(frozen=True, slots=True)
class _SignatureEvidence:
    document_sha256: str
    signature_sha256: str
    allowed_signers_sha256: str
    key_fingerprint: str


def _verify_signature(
    document_bytes: bytes,
    signature_path: Path,
    allowed_signers_path: Path,
    identity: str,
    ssh_keygen: str,
) -> _SignatureEvidence:
    signature = _read_bound_file(signature_path, "Vertex approval signature", 1024 * 1024)
    signers = _read_bound_file(allowed_signers_path, "Vertex allowed signers", 1024 * 1024)
    executable = shutil.which(ssh_keygen)
    if executable is None:
        raise VertexAcceptanceError(f"OpenSSH verifier {ssh_keygen!r} is unavailable")
    with tempfile.TemporaryDirectory(prefix="hawedit-vertex-signature-") as temporary:
        directory = Path(temporary)
        signature_snapshot = directory / "approval.sig"
        signers_snapshot = directory / "allowed_signers"
        signature_snapshot.write_bytes(signature)
        signers_snapshot.write_bytes(signers)
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
            raise VertexAcceptanceError(f"approval signature verification failed: {exc}") from exc
    if result.returncode != 0:
        raise VertexAcceptanceError("approval signature verification failed")
    output = result.stdout + b"\n" + result.stderr
    if len(output) > 8192:
        raise VertexAcceptanceError("signature verifier output exceeded 8192 bytes")
    fingerprints = {
        match.group(1).decode("ascii") for match in _SIGNER_FINGERPRINT.finditer(output)
    }
    if len(fingerprints) != 1:
        raise VertexAcceptanceError(
            "OpenSSH signature verification did not identify exactly one signing key"
        )
    return _SignatureEvidence(
        document_sha256=hashlib.sha256(document_bytes).hexdigest(),
        signature_sha256=hashlib.sha256(signature).hexdigest(),
        allowed_signers_sha256=hashlib.sha256(signers).hexdigest(),
        key_fingerprint=fingerprints.pop(),
    )


def _approval(document: Mapping[str, Any], manifest_sha: str, study: _Study) -> tuple[str, str]:
    _exact_fields(
        document,
        {
            "approved_at_utc",
            "approved_by",
            "billing_confirmed",
            "media_rights_confirmed",
            "one_paid_request_approved",
            "schema",
            "statement",
            "study_manifest_sha256",
            "zero_data_retention_confirmed",
        },
        "Vertex approval",
    )
    if _exact_int(document["schema"], "approval schema", minimum=1) != _SCHEMA:
        raise VertexAcceptanceError("unsupported Vertex approval schema")
    approved_by = _one_line(document["approved_by"], "approval identity")
    if approved_by != study.authorized_by:
        raise VertexAcceptanceError("approval identity is not the recorded media authorizer")
    if _digest(document["study_manifest_sha256"], "approval study manifest") != manifest_sha:
        raise VertexAcceptanceError("approval is bound to another study manifest")
    for field_name in (
        "billing_confirmed",
        "media_rights_confirmed",
        "one_paid_request_approved",
        "zero_data_retention_confirmed",
    ):
        if not _exact_bool(document[field_name], field_name):
            raise VertexAcceptanceError(f"{field_name} must be explicitly true")
    _one_line(document["statement"], "approval statement")
    approved_at = _timestamp(document["approved_at_utc"], "approval timestamp")
    if approved_at <= max(study.billing_confirmed_at, study.retention_confirmed_at):
        raise VertexAcceptanceError(
            "approval timestamp must follow billing and retention confirmations"
        )
    return approved_by, approved_at


def _assert_environment(study: _Study, environment: VertexEnvironment) -> None:
    if environment.project != study.expected_adc_project:
        raise VertexAcceptanceError("live ADC project does not match the approved project")
    if environment.credential_type != study.expected_credential_type:
        raise VertexAcceptanceError("live ADC credential type does not match approval")
    if environment.principal != study.expected_principal:
        raise VertexAcceptanceError("live ADC principal does not match approval")
    if not environment.billing_enabled:
        raise VertexAcceptanceError("Cloud billing is not enabled for the approved project")
    if environment.billing_account_reference != study.billing_account_reference:
        raise VertexAcceptanceError("live billing account does not match approval")
    if not environment.aiplatform_enabled:
        raise VertexAcceptanceError("Vertex AI API is not enabled for the approved project")


class _CountedJudge(Protocol):
    def judge_with_count(
        self, request: JudgeRequest, *, max_tokens: int | None = None
    ) -> tuple[int, JudgeVerdict]: ...


JudgeFactory = Callable[[str, str, Governance, str], _CountedJudge]


def _default_judge_factory(
    project: str, location: str, governance: Governance, token: str
) -> VertexGeminiJudge:
    return VertexGeminiJudge(
        project,
        location=location,
        governance=governance,
        token_provider=lambda: token,
    )


@dataclass(frozen=True, slots=True)
class VerifiedVertexAcceptance:
    directory: Path
    evidence_path: Path
    attempt_path: Path


def run_vertex_acceptance(
    *,
    source_manifest_path: Path,
    private_root: Path,
    prepared_manifest_path: Path,
    approval_path: Path,
    approval_signature_path: Path,
    allowed_signers_path: Path,
    output_dir: Path,
    environment_probe: Callable[[str], VertexEnvironment] = probe_vertex_environment,
    judge_factory: JudgeFactory = _default_judge_factory,
    frame_extractor: Callable[..., tuple[JudgeFrame, ...]] = extract_judge_frames,
    media_probe: Callable[[Path], tuple[int, int]] = _default_media_probe,
    now_utc: Callable[[], str] = lambda: datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    ssh_keygen: str = "ssh-keygen",
) -> VerifiedVertexAcceptance:
    """Verify every local/live prerequisite and spend at most one generation attempt."""
    destination = Path(os.path.abspath(output_dir))
    output_parent, output_parent_identity = _bound_directory(
        destination.parent, "Vertex output parent"
    )
    attempt_path = destination.parent / f".{destination.name}.vertex-attempt"
    if os.path.lexists(destination):
        raise VertexAcceptanceError(f"Vertex evidence already exists at {destination}")
    if os.path.lexists(attempt_path):
        raise VertexAcceptanceError(
            f"Vertex attempt already exists at {attempt_path}; refusing a replay"
        )
    root, root_identity = _bound_directory(private_root, "Vertex private root")
    source_document, source_bytes = _load_json(source_manifest_path, "Vertex source manifest")
    study = _study(source_document, source_bytes, root, media_probe)
    expected_manifest = _prepared_manifest(study)
    expected_manifest_bytes = _canonical_json(expected_manifest)
    prepared_document, prepared_bytes = _load_json(
        prepared_manifest_path, "prepared Vertex manifest"
    )
    if prepared_document != expected_manifest or prepared_bytes != expected_manifest_bytes:
        raise VertexAcceptanceError(
            "prepared Vertex manifest does not recompute from the private source"
        )
    manifest_sha = hashlib.sha256(prepared_bytes).hexdigest()
    approval_document, approval_bytes = _load_json(approval_path, "Vertex approval")
    approved_by, approved_at = _approval(approval_document, manifest_sha, study)
    signature = _verify_signature(
        approval_bytes,
        approval_signature_path,
        allowed_signers_path,
        approved_by,
        ssh_keygen,
    )
    _assert_directory(root, root_identity, "Vertex private root")
    environment = environment_probe(study.project)
    _assert_environment(study, environment)
    if environment.checked_at_utc < approved_at:
        raise VertexAcceptanceError("live ADC/billing check predates the signed approval")
    _assert_directory(root, root_identity, "Vertex private root")
    _assert_directory(output_parent, output_parent_identity, "Vertex output parent")
    with _private_frame_directory(output_parent) as workspace:
        try:
            frames = frame_extractor(
                study.media_path,
                study.clip_in_ms,
                study.clip_out_ms,
                workspace,
            )
        except VertexAcceptanceError:
            raise
        except (KeyframeError, OSError, ValueError) as exc:
            raise VertexAcceptanceError(
                f"cannot extract Vertex acceptance keyframes: {exc}"
            ) from exc
        if not frames or len(frames) > 20:
            raise VertexAcceptanceError("Vertex acceptance requires 1..20 real source keyframes")
        _assert_directory(root, root_identity, "Vertex private root")
        _assert_directory(output_parent, output_parent_identity, "Vertex output parent")
        if _stable_digest(study.media_path, "client media") != study.media_sha256:
            raise VertexAcceptanceError("client media changed before Vertex transport")
        attempt_started = _timestamp(now_utc(), "attempt start timestamp")
        if environment.checked_at_utc > attempt_started:
            raise VertexAcceptanceError("live ADC/billing check is later than the attempt start")
        attempt_document = {
            "approved_document_sha256": signature.document_sha256,
            "intended_output_name_sha256": hashlib.sha256(destination.name.encode()).hexdigest(),
            "schema": _SCHEMA,
            "started_at_utc": attempt_started,
            "study_manifest_sha256": manifest_sha,
        }
        _publish_exact(
            attempt_path,
            {"attempt.json": _canonical_json(attempt_document)},
            _ATTEMPT_FILES,
        )
        governance = Governance(
            confidential=True,
            zero_data_retention=True,
            confirmed_by=study.retention_confirmed_by,
        )
        request = JudgeRequest(
            candidate_id=study.candidate_id,
            mode=InputMode.STAGE_4_TRANSCRIPT_FIRST,
            carried_verbal_score=study.carried_verbal_score,
            visual_context=study.visual_context,
            keyframes=frames,
            text_ckb=study.request_text,
            clip_in_ms=study.clip_in_ms,
            clip_out_ms=study.clip_out_ms,
        )
        judge = judge_factory(study.project, study.location, governance, environment.access_token)
        counted_tokens, verdict = judge.judge_with_count(
            request, max_tokens=study.effective_max_tokens
        )
        if type(counted_tokens) is not int or counted_tokens <= 0:
            raise VertexAcceptanceError("counted Vertex input tokens are not a positive integer")
        estimated_cost = estimate_cost_usd(counted_tokens)
        if (
            counted_tokens > study.max_input_tokens
            or estimated_cost > study.max_estimated_input_cost_usd
        ):
            raise VertexAcceptanceError("Vertex judge violated the signed token or cost ceiling")
        finished_at = _timestamp(now_utc(), "attempt completion timestamp")
        if finished_at < attempt_started:
            raise VertexAcceptanceError("attempt completion timestamp precedes its start")
        frame_hashes = [hashlib.sha256(frame.data).hexdigest() for frame in frames]
        frame_timestamps = [frame.timestamp_ms for frame in frames]
    _assert_directory(output_parent, output_parent_identity, "Vertex output parent")
    evidence: dict[str, object] = {
        "acceptance_boundary": (
            "one live content-bound Vertex measurement; contractual ZDR, rights and spend "
            "approval remain signed human assertions"
        ),
        "approval": {
            "allowed_signers_sha256": signature.allowed_signers_sha256,
            "approved_at_utc": approved_at,
            "approved_by": approved_by,
            "document_sha256": signature.document_sha256,
            "key_fingerprint": signature.key_fingerprint,
            "signature_sha256": signature.signature_sha256,
        },
        "content": {
            "frame_sha256": frame_hashes,
            "frame_timestamps_ms": frame_timestamps,
            "media_sha256": study.media_sha256,
            "policy_sha256": study.policy_sha256,
            "request_sha256": study.request_sha256,
            "transcript_sha256": study.transcript_sha256,
        },
        "environment": {
            "aiplatform_enabled": environment.aiplatform_enabled,
            "billing_account_sha256": hashlib.sha256(
                environment.billing_account_reference.encode()
            ).hexdigest(),
            "billing_enabled": environment.billing_enabled,
            "checked_at_utc": environment.checked_at_utc,
            "credential_type": environment.credential_type,
            "principal_sha256": hashlib.sha256(environment.principal.encode()).hexdigest(),
            "project": environment.project,
        },
        "request": {
            "candidate_id_sha256": hashlib.sha256(study.candidate_id.encode()).hexdigest(),
            "clip_in_ms": study.clip_in_ms,
            "clip_out_ms": study.clip_out_ms,
            "completed_at_utc": finished_at,
            "counted_input_tokens": counted_tokens,
            "estimated_input_cost_usd": estimated_cost,
            "effective_max_input_tokens": study.effective_max_tokens,
            "max_estimated_input_cost_usd": study.max_estimated_input_cost_usd,
            "max_input_tokens": study.max_input_tokens,
            "paid_generate_attempts": 1,
            "started_at_utc": attempt_started,
        },
        "route": {
            "location": study.location,
            "model_id": study.model_id,
            "project": study.project,
        },
        "schema": _SCHEMA,
        "source_manifest_sha256": study.source_manifest_sha256,
        "study_id": study.study_id,
        "study_manifest_sha256": manifest_sha,
        "verdict": {
            "cultural_landing": verdict.cultural_landing,
            "hook_score": verdict.hook_score,
            "meaning_fidelity": verdict.meaning_fidelity,
            "misleading_edit_risk": verdict.misleading_edit_risk,
            "narrative_role": verdict.narrative_role,
            "payoff_at_ms": verdict.payoff_at_ms,
            "self_contained": verdict.self_contained,
        },
    }
    instructions = (
        b"VERIFIED CONFIDENTIAL VERTEX ACCEPTANCE\n\n"
        b"This directory intentionally omits client transcript text, frame bytes, generated "
        b"editorial copy, access tokens, billing-account names and retained policy text. Verify "
        b"their SHA-256 bindings against the private signed inputs. The sibling hidden attempt "
        b"directory is retained to prevent replay after an ambiguous failure.\n"
    )
    directory = _publish_exact(
        destination,
        {
            "INSTRUCTIONS.txt": instructions,
            "vertex-evidence.json": _canonical_json(evidence),
        },
        _RESULT_FILES,
    )
    return VerifiedVertexAcceptance(
        directory=directory,
        evidence_path=directory / "vertex-evidence.json",
        attempt_path=attempt_path,
    )
