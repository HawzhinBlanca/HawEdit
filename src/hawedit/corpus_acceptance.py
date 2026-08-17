"""Content-bound, human-signed acceptance packets for the real §8.1 Sorani corpus.

The ordinary :mod:`hawedit.corpus` manifest is the linguistic label schema. This module is
its trust envelope: it binds those labels to exact corpus/audio bytes, records the human rights
assertions HawEdit cannot infer, excludes known training material, and verifies an OpenSSH
detached signature before a result may call itself production evidence.
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
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any, Final

from hawedit.atomic_fs import rename_directory_noreplace
from hawedit.cli import machine_readable_stdout, program_name, use_utf8_streams
from hawedit.corpus import Corpus, CorpusItem, Provenance

__all__ = [
    "SIGNATURE_NAMESPACE",
    "CorpusAcceptanceError",
    "CorpusRights",
    "PreparedCorpusAcceptance",
    "VerifiedCorpusAcceptance",
    "main",
    "prepare_corpus_acceptance",
    "verify_corpus_acceptance",
]

SIGNATURE_NAMESPACE: Final = "hawedit-corpus-acceptance-v1"
_SCHEMA: Final = 1
_MAX_JSON_BYTES: Final = 64 * 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_RFC3339_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_KIT_FILENAMES: Final = (
    "INSTRUCTIONS.txt",
    "approval.template.json",
    "corpus-acceptance.json",
    "coverage.json",
)
_PLACEHOLDERS: Final = frozenset(
    {"", "unknown", "tbd", "todo", "none", "n/a", "unrecorded", "placeholder"}
)


class CorpusAcceptanceError(ValueError):
    """The purported production corpus evidence is incomplete or no longer authentic."""


def _one_line(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise CorpusAcceptanceError(f"{field} must be a string")
    if (
        not value
        or value.strip() != value
        or not value.isprintable()
        or value.splitlines() != [value]
    ):
        raise CorpusAcceptanceError(f"{field} must be non-empty, trimmed, printable, and one line")
    if value.casefold() in _PLACEHOLDERS:
        raise CorpusAcceptanceError(f"{field} is placeholder text, not acceptance evidence")
    return value


def _exact_bool(value: object, field: str) -> bool:
    if type(value) is not bool:
        raise CorpusAcceptanceError(f"{field} must be a JSON boolean")
    return value


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise CorpusAcceptanceError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _strict_object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise CorpusAcceptanceError(f"{field} must be a JSON object")
    return value


def _exact_fields(value: Mapping[str, Any], expected: set[str], field: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise CorpusAcceptanceError(
            f"{field} fields do not match schema; missing={missing}, extra={extra}"
        )


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CorpusAcceptanceError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _is_reparse(info: os.stat_result) -> bool:
    attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(getattr(info, "st_file_attributes", 0) & attribute)


def _identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_nlink)


def _read_bound_file(path: Path, label: str, *, max_bytes: int | None) -> bytes:
    try:
        before_path = os.lstat(path)
    except OSError as exc:
        raise CorpusAcceptanceError(f"cannot inspect {label} {path}: {exc}") from exc
    if stat.S_ISLNK(before_path.st_mode) or _is_reparse(before_path):
        raise CorpusAcceptanceError(f"{label} must not be a symlink or reparse point: {path}")
    if not stat.S_ISREG(before_path.st_mode):
        raise CorpusAcceptanceError(f"{label} must be a regular file: {path}")
    if before_path.st_nlink != 1:
        raise CorpusAcceptanceError(f"{label} must not be a hardlink: {path}")
    if max_bytes is not None and before_path.st_size > max_bytes:
        raise CorpusAcceptanceError(
            f"{label} exceeds the {max_bytes}-byte acceptance limit: {path}"
        )

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise CorpusAcceptanceError(f"cannot open {label} {path}: {exc}") from exc
    try:
        before_fd = os.fstat(descriptor)
        if _identity(before_fd) != _identity(before_path):
            raise CorpusAcceptanceError(f"{label} changed while it was being opened: {path}")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if max_bytes is not None and total > max_bytes:
                raise CorpusAcceptanceError(
                    f"{label} exceeds the {max_bytes}-byte acceptance limit: {path}"
                )
            chunks.append(chunk)
        after_fd = os.fstat(descriptor)
        if (
            _identity(after_fd) != _identity(before_fd)
            or after_fd.st_ctime_ns != before_fd.st_ctime_ns
        ):
            raise CorpusAcceptanceError(f"{label} changed while it was being read: {path}")
    finally:
        os.close(descriptor)
    try:
        after_path = os.lstat(path)
    except OSError as exc:
        raise CorpusAcceptanceError(f"cannot re-inspect {label} {path}: {exc}") from exc
    if (
        _identity(after_path) != _identity(before_path)
        or after_path.st_ctime_ns != before_path.st_ctime_ns
    ):
        raise CorpusAcceptanceError(f"{label} path changed while it was being read: {path}")
    return b"".join(chunks)


def _stable_digest(path: Path, label: str) -> str:
    digest = hashlib.sha256()
    try:
        before_path = os.lstat(path)
    except OSError as exc:
        raise CorpusAcceptanceError(f"cannot inspect {label} {path}: {exc}") from exc
    if stat.S_ISLNK(before_path.st_mode) or _is_reparse(before_path):
        raise CorpusAcceptanceError(f"{label} must not be a symlink or reparse point: {path}")
    if not stat.S_ISREG(before_path.st_mode):
        raise CorpusAcceptanceError(f"{label} must be a regular file: {path}")
    if before_path.st_nlink != 1:
        raise CorpusAcceptanceError(f"{label} must not be a hardlink: {path}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise CorpusAcceptanceError(f"cannot open {label} {path}: {exc}") from exc
    try:
        before_fd = os.fstat(descriptor)
        if _identity(before_fd) != _identity(before_path):
            raise CorpusAcceptanceError(f"{label} changed while it was being opened: {path}")
        while chunk := os.read(descriptor, 1024 * 1024):
            digest.update(chunk)
        after_fd = os.fstat(descriptor)
        if (
            _identity(after_fd) != _identity(before_fd)
            or after_fd.st_ctime_ns != before_fd.st_ctime_ns
        ):
            raise CorpusAcceptanceError(f"{label} changed while it was being hashed: {path}")
    finally:
        os.close(descriptor)
    try:
        after_path = os.lstat(path)
    except OSError as exc:
        raise CorpusAcceptanceError(f"cannot re-inspect {label} {path}: {exc}") from exc
    if (
        _identity(after_path) != _identity(before_path)
        or after_path.st_ctime_ns != before_path.st_ctime_ns
    ):
        raise CorpusAcceptanceError(f"{label} path changed while it was being hashed: {path}")
    return digest.hexdigest()


def _load_json_bytes(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    payload = _read_bound_file(path, label, max_bytes=_MAX_JSON_BYTES)
    try:
        decoded = json.loads(payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CorpusAcceptanceError(f"{label} is not strict UTF-8 JSON: {exc}") from exc
    return _strict_object(decoded, label), payload


def _load_corpus_bytes(path: Path) -> tuple[Corpus, bytes]:
    document, payload = _load_json_bytes(path, "corpus manifest")
    _exact_fields(document, {"items", "provenance"}, "corpus manifest")
    raw_items = document["items"]
    if not isinstance(raw_items, list):
        raise CorpusAcceptanceError("corpus manifest items must be a JSON array")
    raw_provenance = _strict_object(document["provenance"], "corpus provenance")
    _exact_fields(raw_provenance, {"name", "licence", "interim", "note"}, "corpus provenance")
    interim = _exact_bool(raw_provenance["interim"], "corpus provenance interim")
    for raw_item in raw_items:
        _validate_corpus_item_json(_strict_object(raw_item, "corpus item"))
    if not isinstance(raw_provenance["note"], str):
        raise CorpusAcceptanceError("corpus provenance note must be a string")
    try:
        corpus = Corpus(
            tuple(CorpusItem.from_dict(_strict_object(item, "corpus item")) for item in raw_items),
            provenance=Provenance(
                name=_one_line(raw_provenance["name"], "corpus provenance name"),
                licence=_one_line(raw_provenance["licence"], "corpus provenance licence"),
                interim=interim,
                note=str(raw_provenance["note"]),
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CorpusAcceptanceError(f"invalid corpus manifest: {exc}") from exc
    return corpus, payload


def _validate_string_array(value: object, field: str, *, unique: bool = False) -> None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise CorpusAcceptanceError(f"{field} must be an array of strings")
    if unique and len(value) != len(set(value)):
        raise CorpusAcceptanceError(f"{field} contains duplicate values")


def _validate_corpus_item_json(document: Mapping[str, Any]) -> None:
    expected = {
        "audio_path",
        "code_switch_spans",
        "conditions",
        "dialect",
        "duration_s",
        "item_id",
        "named_entities",
        "reference_ckb",
        "reference_words",
        "speaker_count",
    }
    _exact_fields(document, expected, "corpus item")
    _one_line(document["item_id"], "corpus item id")
    audio_path = _one_line(document["audio_path"], "corpus audio path")
    _relative_audio_path(audio_path)
    if not isinstance(document["reference_ckb"], str):
        raise CorpusAcceptanceError("corpus reference_ckb must be a string")
    dialect = document["dialect"]
    if dialect is not None and not isinstance(dialect, str):
        raise CorpusAcceptanceError("corpus dialect must be a string or null")
    _validate_string_array(document["conditions"], "corpus conditions", unique=True)
    duration = document["duration_s"]
    if (
        not isinstance(duration, int | float)
        or isinstance(duration, bool)
        or not math.isfinite(float(duration))
    ):
        raise CorpusAcceptanceError("corpus duration_s must be a finite JSON number")
    _validate_string_array(document["named_entities"], "corpus named_entities")
    _validate_string_array(document["code_switch_spans"], "corpus code_switch_spans")
    if type(document["speaker_count"]) is not int:
        raise CorpusAcceptanceError("corpus speaker_count must be an exact JSON integer")
    words = document["reference_words"]
    if not isinstance(words, list):
        raise CorpusAcceptanceError("corpus reference_words must be a JSON array")
    for raw_word in words:
        word = _strict_object(raw_word, "corpus reference word")
        _exact_fields(word, {"conf", "end_ms", "start_ms", "w"}, "corpus reference word")
        if not isinstance(word["w"], str):
            raise CorpusAcceptanceError("corpus reference word surface must be a string")
        if type(word["start_ms"]) is not int or type(word["end_ms"]) is not int:
            raise CorpusAcceptanceError("corpus reference word bounds must be exact integers")
        confidence = word["conf"]
        if (
            not isinstance(confidence, int | float)
            or isinstance(confidence, bool)
            or not math.isfinite(float(confidence))
        ):
            raise CorpusAcceptanceError("corpus reference word confidence must be finite numeric")


def _canonical_json(document: Mapping[str, Any]) -> bytes:
    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _item_digest(item: CorpusItem) -> str:
    return hashlib.sha256(_canonical_json(item.to_dict())).hexdigest()


def _relative_audio_path(value: str) -> PurePosixPath:
    if "\\" in value:
        raise CorpusAcceptanceError(f"audio path must use forward slashes: {value!r}")
    relative = PurePosixPath(value)
    if (
        not value
        or relative.is_absolute()
        or any(part in {"", ".", ".."} or ":" in part for part in relative.parts)
    ):
        raise CorpusAcceptanceError(f"audio path must be a contained relative path: {value!r}")
    return relative


def _validated_root(root: Path) -> Path:
    absolute = root.absolute()
    try:
        info = os.lstat(absolute)
    except OSError as exc:
        raise CorpusAcceptanceError(f"cannot inspect audio root {absolute}: {exc}") from exc
    if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
        raise CorpusAcceptanceError(
            f"audio root must not be a symlink or reparse point: {absolute}"
        )
    if not stat.S_ISDIR(info.st_mode):
        raise CorpusAcceptanceError(f"audio root is not a directory: {absolute}")
    return absolute


def _root_identity(root: Path) -> tuple[int, int]:
    try:
        info = os.lstat(root)
    except OSError as exc:
        raise CorpusAcceptanceError(f"cannot inspect audio root {root}: {exc}") from exc
    if stat.S_ISLNK(info.st_mode) or _is_reparse(info) or not stat.S_ISDIR(info.st_mode):
        raise CorpusAcceptanceError(f"audio root identity is unsafe: {root}")
    return (info.st_dev, info.st_ino)


def _write_private_file(path: Path, payload: bytes) -> None:
    try:
        with path.open("xb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
            descriptor_identity = _identity(os.fstat(output.fileno()))
        path_info = os.lstat(path)
    except OSError as exc:
        raise CorpusAcceptanceError(f"cannot stage acceptance-kit file {path}: {exc}") from exc
    if (
        not stat.S_ISREG(path_info.st_mode)
        or stat.S_ISLNK(path_info.st_mode)
        or _is_reparse(path_info)
        or path_info.st_nlink != 1
        or _identity(path_info) != descriptor_identity
    ):
        raise CorpusAcceptanceError(f"acceptance-kit file identity is unsafe: {path}")


def _discard_private_kit(staging: Path, identity: tuple[int, int]) -> None:
    if not os.path.lexists(staging):
        return
    if _root_identity(staging) != identity:
        raise CorpusAcceptanceError(
            f"refusing to clean a replaced acceptance-kit staging directory: {staging}"
        )
    try:
        children = tuple(staging.iterdir())
    except OSError as exc:
        raise CorpusAcceptanceError(
            f"cannot inspect acceptance-kit staging directory {staging}: {exc}"
        ) from exc
    unexpected = sorted(path.name for path in children if path.name not in _KIT_FILENAMES)
    if unexpected:
        raise CorpusAcceptanceError(
            "refusing to clean unexpected acceptance-kit staging entries: " + ", ".join(unexpected)
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
                raise CorpusAcceptanceError(
                    f"refusing to clean unsafe acceptance-kit staging entry: {path}"
                )
            path.unlink()
        staging.rmdir()
    except CorpusAcceptanceError:
        raise
    except OSError as exc:
        raise CorpusAcceptanceError(
            f"cannot clean acceptance-kit staging directory {staging}: {exc}"
        ) from exc


def _publish_kit(output_dir: Path, payloads: Mapping[str, bytes]) -> Path:
    if set(payloads) != set(_KIT_FILENAMES):
        raise CorpusAcceptanceError("acceptance kit is not the exact required four-file set")
    destination = Path(os.path.abspath(output_dir))
    parent = _validated_root(destination.parent)
    parent_identity = _root_identity(parent)
    if os.path.lexists(destination):
        raise CorpusAcceptanceError(f"refusing to overwrite acceptance kit {destination}")
    try:
        staging = Path(
            tempfile.mkdtemp(
                prefix=f".{destination.name}.",
                suffix=".staging",
                dir=parent,
            )
        )
    except OSError as exc:
        raise CorpusAcceptanceError(
            f"cannot create private acceptance-kit staging under {parent}: {exc}"
        ) from exc
    staging_identity = _root_identity(staging)
    try:
        for filename in _KIT_FILENAMES:
            _write_private_file(staging / filename, payloads[filename])
        if _root_identity(parent) != parent_identity:
            raise CorpusAcceptanceError("acceptance-kit output parent changed during publication")
        if _root_identity(staging) != staging_identity:
            raise CorpusAcceptanceError(
                "acceptance-kit staging identity changed during publication"
            )
        actual = tuple(sorted(path.name for path in staging.iterdir()))
        if actual != _KIT_FILENAMES:
            raise CorpusAcceptanceError(
                f"acceptance-kit staging set changed; expected={_KIT_FILENAMES}, actual={actual}"
            )
        rename_directory_noreplace(staging, destination)
        if _root_identity(parent) != parent_identity:
            raise CorpusAcceptanceError("acceptance-kit output parent changed after publication")
        if _root_identity(destination) != staging_identity:
            raise CorpusAcceptanceError("published acceptance-kit identity changed")
    except BaseException as primary:
        try:
            _discard_private_kit(staging, staging_identity)
        except CorpusAcceptanceError as cleanup:
            primary.add_note(f"HawEdit acceptance-kit cleanup also failed: {cleanup}")
        if isinstance(primary, FileExistsError):
            raise CorpusAcceptanceError(
                f"refusing to overwrite acceptance kit {destination}; another publisher won"
            ) from primary
        if isinstance(primary, OSError):
            raise CorpusAcceptanceError(
                f"cannot atomically publish acceptance kit {destination}: {primary}"
            ) from primary
        raise
    return destination


def _audio_path(root: Path, relative: str) -> Path:
    parts = _relative_audio_path(relative).parts
    current = root
    for index, part in enumerate(parts):
        current /= part
        try:
            info = os.lstat(current)
        except OSError as exc:
            raise CorpusAcceptanceError(f"cannot inspect corpus audio {current}: {exc}") from exc
        if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
            raise CorpusAcceptanceError(
                f"corpus audio path contains a symlink or reparse point: {current}"
            )
        if index < len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise CorpusAcceptanceError(f"corpus audio parent is not a directory: {current}")
    return current


@dataclass(frozen=True, slots=True)
class CorpusRights:
    dataset_owner: str
    authorized_by: str
    licence: str
    consent_basis: str
    permitted_use: str
    redistribution_allowed: bool

    def __post_init__(self) -> None:
        _one_line(self.dataset_owner, "dataset owner")
        _one_line(self.authorized_by, "rights authorizer")
        _one_line(self.licence, "corpus licence")
        _one_line(self.consent_basis, "consent basis")
        _one_line(self.permitted_use, "permitted use")
        _exact_bool(self.redistribution_allowed, "redistribution_allowed")

    def to_dict(self) -> dict[str, object]:
        return {
            "authorized_by": self.authorized_by,
            "consent_basis": self.consent_basis,
            "dataset_owner": self.dataset_owner,
            "licence": self.licence,
            "permitted_use": self.permitted_use,
            "redistribution_allowed": self.redistribution_allowed,
        }

    @staticmethod
    def from_dict(value: object) -> CorpusRights:
        document = _strict_object(value, "rights")
        _exact_fields(
            document,
            {
                "authorized_by",
                "consent_basis",
                "dataset_owner",
                "licence",
                "permitted_use",
                "redistribution_allowed",
            },
            "rights",
        )
        return CorpusRights(
            dataset_owner=_one_line(document["dataset_owner"], "dataset owner"),
            authorized_by=_one_line(document["authorized_by"], "rights authorizer"),
            licence=_one_line(document["licence"], "corpus licence"),
            consent_basis=_one_line(document["consent_basis"], "consent basis"),
            permitted_use=_one_line(document["permitted_use"], "permitted use"),
            redistribution_allowed=_exact_bool(
                document["redistribution_allowed"], "redistribution_allowed"
            ),
        )


@dataclass(frozen=True, slots=True)
class _ItemBinding:
    item_id: str
    audio_path: str
    audio_sha256: str
    reference_sha256: str
    corpus_item_sha256: str

    def to_dict(self) -> dict[str, str]:
        return {
            "audio_path": self.audio_path,
            "audio_sha256": self.audio_sha256,
            "corpus_item_sha256": self.corpus_item_sha256,
            "item_id": self.item_id,
            "reference_sha256": self.reference_sha256,
        }

    @staticmethod
    def from_dict(value: object) -> _ItemBinding:
        document = _strict_object(value, "acceptance item")
        _exact_fields(
            document,
            {
                "audio_path",
                "audio_sha256",
                "corpus_item_sha256",
                "item_id",
                "reference_sha256",
            },
            "acceptance item",
        )
        item_id = _one_line(document["item_id"], "acceptance item id")
        audio_path = _one_line(document["audio_path"], f"{item_id} audio path")
        _relative_audio_path(audio_path)
        return _ItemBinding(
            item_id=item_id,
            audio_path=audio_path,
            audio_sha256=_sha256(document["audio_sha256"], f"{item_id} audio SHA-256"),
            reference_sha256=_sha256(document["reference_sha256"], f"{item_id} reference SHA-256"),
            corpus_item_sha256=_sha256(
                document["corpus_item_sha256"], f"{item_id} corpus-item SHA-256"
            ),
        )


@dataclass(frozen=True, slots=True)
class PreparedCorpusAcceptance:
    manifest_path: Path
    approval_template_path: Path
    coverage_report_path: Path
    instructions_path: Path
    manifest_sha256: str


@dataclass(frozen=True, slots=True)
class VerifiedCorpusAcceptance:
    corpus: Corpus
    audio_root: Path
    manifest_sha256: str
    rights: CorpusRights
    approval_sha256: str
    signature_sha256: str
    allowed_signers_sha256: str
    approved_at_utc: str
    _bindings: Mapping[str, _ItemBinding]
    _audio_root_identity: tuple[int, int]

    @property
    def evidence(self) -> Mapping[str, str]:
        return {
            "allowed_signers_sha256": self.allowed_signers_sha256,
            "approval_sha256": self.approval_sha256,
            "approved_at_utc": self.approved_at_utc,
            "approved_by": self.rights.authorized_by,
            "manifest_sha256": self.manifest_sha256,
            "signature_sha256": self.signature_sha256,
        }

    @contextmanager
    def guard(self, item: CorpusItem) -> Iterator[None]:
        if _root_identity(self.audio_root) != self._audio_root_identity:
            raise CorpusAcceptanceError("audio root changed after human approval")
        try:
            binding = self._bindings[item.item_id]
        except KeyError as exc:
            raise CorpusAcceptanceError(
                f"benchmark item {item.item_id!r} is absent from the signed acceptance manifest"
            ) from exc
        audio = _audio_path(self.audio_root, binding.audio_path)
        if Path(item.audio_path).absolute() != audio.absolute():
            raise CorpusAcceptanceError(
                f"benchmark item {item.item_id!r} reads {item.audio_path}, not signed audio {audio}"
            )
        before = _stable_digest(audio, f"{item.item_id} corpus audio")
        if before != binding.audio_sha256:
            raise CorpusAcceptanceError(
                f"{item.item_id}: audio SHA-256 changed after human approval"
            )
        try:
            yield
        except BaseException as primary:
            try:
                after = _stable_digest(audio, f"{item.item_id} corpus audio")
                if after != before:
                    raise CorpusAcceptanceError(
                        f"{item.item_id}: audio changed while the benchmark was reading it"
                    )
                if _root_identity(self.audio_root) != self._audio_root_identity:
                    raise CorpusAcceptanceError("audio root changed during the benchmark")
            except CorpusAcceptanceError as integrity:
                primary.add_note(f"HawEdit corpus-integrity check also failed: {integrity}")
            raise
        else:
            after = _stable_digest(audio, f"{item.item_id} corpus audio")
            if after != before:
                raise CorpusAcceptanceError(
                    f"{item.item_id}: audio changed while the benchmark was reading it"
                )
            if _root_identity(self.audio_root) != self._audio_root_identity:
                raise CorpusAcceptanceError("audio root changed during the benchmark")


def _validated_exclusions(values: Sequence[str]) -> tuple[str, ...]:
    digests = tuple(_sha256(value, "excluded audio SHA-256") for value in values)
    if len(digests) != len(set(digests)):
        raise CorpusAcceptanceError("training/exclusion set contains duplicate SHA-256 entries")
    return tuple(sorted(digests))


def prepare_corpus_acceptance(
    *,
    corpus_path: Path,
    audio_root: Path,
    output_dir: Path,
    rights: CorpusRights,
    excluded_audio_sha256: Sequence[str] = (),
) -> PreparedCorpusAcceptance:
    """Prepare canonical bytes for human review and detached OpenSSH signing."""
    if output_dir.exists():
        raise CorpusAcceptanceError(f"refusing to overwrite acceptance kit {output_dir}")
    corpus, corpus_bytes = _load_corpus_bytes(corpus_path)
    if corpus.provenance.interim:
        raise CorpusAcceptanceError(
            "an interim corpus cannot become production acceptance evidence"
        )
    try:
        corpus.assert_section_8_1_coverage()
    except RuntimeError as exc:
        raise CorpusAcceptanceError(str(exc)) from exc
    if rights.licence != corpus.provenance.licence:
        raise CorpusAcceptanceError(
            f"rights licence {rights.licence!r} does not match corpus licence "
            f"{corpus.provenance.licence!r}"
        )
    root = _validated_root(audio_root)
    exclusions = _validated_exclusions(excluded_audio_sha256)
    excluded = set(exclusions)
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    seen_audio: dict[str, str] = {}
    bindings: list[_ItemBinding] = []
    for item in corpus.items:
        if item.item_id in seen_ids:
            raise CorpusAcceptanceError(f"duplicate corpus item id {item.item_id!r}")
        if item.audio_path in seen_paths:
            raise CorpusAcceptanceError(f"duplicate corpus audio path {item.audio_path!r}")
        seen_ids.add(item.item_id)
        seen_paths.add(item.audio_path)
        audio = _audio_path(root, item.audio_path)
        audio_sha256 = _stable_digest(audio, f"{item.item_id} corpus audio")
        if audio_sha256 in excluded:
            raise CorpusAcceptanceError(
                f"{item.item_id}: audio is present in the declared training/exclusion set"
            )
        duplicate = seen_audio.get(audio_sha256)
        if duplicate is not None:
            raise CorpusAcceptanceError(
                f"duplicate audio bytes for {duplicate!r} and {item.item_id!r}"
            )
        seen_audio[audio_sha256] = item.item_id
        bindings.append(
            _ItemBinding(
                item_id=item.item_id,
                audio_path=item.audio_path,
                audio_sha256=audio_sha256,
                reference_sha256=hashlib.sha256(item.reference_ckb.encode("utf-8")).hexdigest(),
                corpus_item_sha256=_item_digest(item),
            )
        )

    document = {
        "corpus_sha256": hashlib.sha256(corpus_bytes).hexdigest(),
        "excluded_audio_sha256": list(exclusions),
        "items": [binding.to_dict() for binding in bindings],
        "rights": rights.to_dict(),
        "schema": _SCHEMA,
    }
    manifest_bytes = _canonical_json(document)
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    approval = {
        "approved_at_utc": "",
        "approved_by": "",
        "manifest_sha256": manifest_sha256,
        "rights_attested": False,
        "schema": _SCHEMA,
    }
    instructions = (
        "HawEdit Sorani ASR acceptance approval\n\n"
        "1. Review corpus-acceptance.json, the licence, consent basis, and excluded hashes.\n"
        "2. Fill approval.template.json without changing manifest_sha256.\n"
        f"3. Sign it: ssh-keygen -Y sign -f <PRIVATE_KEY> -n {SIGNATURE_NAMESPACE} "
        "approval.template.json\n"
        "4. Verify with: python -m hawedit.corpus_acceptance verify "
        "corpus-acceptance.json <CORPUS_JSON> --audio-root <AUDIO_ROOT> "
        "--approval <APPROVAL_JSON> --signature <APPROVAL_SIG> "
        "--allowed-signers <ALLOWED_SIGNERS>.\n"
        "5. Benchmark with: hawedit-asr-bench <CORPUS_JSON> --audio-root <AUDIO_ROOT> "
        "--acceptance-manifest corpus-acceptance.json --approval <APPROVAL_JSON> "
        "--signature <APPROVAL_SIG> --allowed-signers <ALLOWED_SIGNERS> "
        "--host <HOST> --accelerator <ACCELERATOR> --output <REPORT_JSON>.\n"
        "The private key, allowed-signers trust file, client audio, and approval signature stay "
        "outside Git.\n"
    )
    coverage = corpus.coverage()
    coverage_report = {
        "corpus_sha256": document["corpus_sha256"],
        "hours_by_dialect": {
            dialect.value: coverage.hours_by_dialect[dialect]
            for dialect in coverage.hours_by_dialect
        },
        "item_count": len(corpus.items),
        "labelled_hours": coverage.labelled_hours,
        "manifest_sha256": manifest_sha256,
        "meets_section_8_1": coverage.is_complete(),
        "missing_cells": [
            f"{dialect.value}/{condition.value}" for dialect, condition in coverage.missing_cells
        ],
        "schema": _SCHEMA,
        "unlabelled_hours": coverage.unlabelled_hours,
    }
    published = _publish_kit(
        output_dir,
        {
            "INSTRUCTIONS.txt": instructions.encode("utf-8"),
            "approval.template.json": _canonical_json(approval),
            "corpus-acceptance.json": manifest_bytes,
            "coverage.json": _canonical_json(coverage_report),
        },
    )
    manifest_path = published / "corpus-acceptance.json"
    approval_path = published / "approval.template.json"
    coverage_path = published / "coverage.json"
    instructions_path = published / "INSTRUCTIONS.txt"
    return PreparedCorpusAcceptance(
        manifest_path=manifest_path,
        approval_template_path=approval_path,
        coverage_report_path=coverage_path,
        instructions_path=instructions_path,
        manifest_sha256=manifest_sha256,
    )


def _parse_manifest(
    document: Mapping[str, Any],
) -> tuple[str, CorpusRights, tuple[_ItemBinding, ...]]:
    _exact_fields(
        document,
        {"corpus_sha256", "excluded_audio_sha256", "items", "rights", "schema"},
        "acceptance manifest",
    )
    if type(document["schema"]) is not int or document["schema"] != _SCHEMA:
        raise CorpusAcceptanceError(
            f"acceptance manifest has unsupported schema {document['schema']!r}"
        )
    exclusions = document["excluded_audio_sha256"]
    items = document["items"]
    if not isinstance(exclusions, list):
        raise CorpusAcceptanceError("excluded_audio_sha256 must be a JSON array")
    if not isinstance(items, list):
        raise CorpusAcceptanceError("acceptance items must be a JSON array")
    validated_exclusions = set(_validated_exclusions(tuple(exclusions)))
    bindings = tuple(_ItemBinding.from_dict(item) for item in items)
    ids = [binding.item_id for binding in bindings]
    paths = [binding.audio_path for binding in bindings]
    hashes = [binding.audio_sha256 for binding in bindings]
    if len(ids) != len(set(ids)):
        raise CorpusAcceptanceError("acceptance manifest contains duplicate item ids")
    if len(paths) != len(set(paths)):
        raise CorpusAcceptanceError("acceptance manifest contains duplicate audio paths")
    if len(hashes) != len(set(hashes)):
        raise CorpusAcceptanceError("acceptance manifest contains duplicate audio bytes")
    if validated_exclusions.intersection(hashes):
        raise CorpusAcceptanceError(
            "acceptance manifest includes audio from its own training/exclusion set"
        )
    return (
        _sha256(document["corpus_sha256"], "corpus SHA-256"),
        CorpusRights.from_dict(document["rights"]),
        bindings,
    )


def _verify_approval(
    *,
    approval_path: Path,
    signature_path: Path,
    allowed_signers_path: Path,
    manifest_sha256: str,
    rights: CorpusRights,
    ssh_keygen: str,
) -> tuple[str, str, str, str]:
    approval, approval_bytes = _load_json_bytes(approval_path, "corpus approval")
    _exact_fields(
        approval,
        {"approved_at_utc", "approved_by", "manifest_sha256", "rights_attested", "schema"},
        "corpus approval",
    )
    if type(approval["schema"]) is not int or approval["schema"] != _SCHEMA:
        raise CorpusAcceptanceError(
            f"corpus approval has unsupported schema {approval['schema']!r}"
        )
    approved_by = _one_line(approval["approved_by"], "approval identity")
    if approved_by != rights.authorized_by:
        raise CorpusAcceptanceError(
            f"approval identity {approved_by!r} does not match rights authorizer "
            f"{rights.authorized_by!r}"
        )
    approved_at = _one_line(approval["approved_at_utc"], "approval timestamp")
    if _RFC3339_UTC.fullmatch(approved_at) is None:
        raise CorpusAcceptanceError("approval timestamp must be exact UTC YYYY-MM-DDTHH:MM:SSZ")
    if _sha256(approval["manifest_sha256"], "approved manifest SHA-256") != manifest_sha256:
        raise CorpusAcceptanceError("human approval names a different acceptance manifest")
    if _exact_bool(approval["rights_attested"], "rights_attested") is not True:
        raise CorpusAcceptanceError("human approval did not attest the recorded rights")

    signature = _read_bound_file(signature_path, "approval signature", max_bytes=1024 * 1024)
    allowed_signers = _read_bound_file(
        allowed_signers_path, "allowed signers", max_bytes=1024 * 1024
    )
    executable = shutil.which(ssh_keygen)
    if executable is None:
        raise CorpusAcceptanceError(f"OpenSSH signature verifier {ssh_keygen!r} is unavailable")
    with tempfile.TemporaryDirectory(prefix="hawedit-corpus-signature-") as temporary:
        snapshot = Path(temporary)
        signature_snapshot = snapshot / "approval.sig"
        signers_snapshot = snapshot / "allowed_signers"
        signature_snapshot.write_bytes(signature)
        signers_snapshot.write_bytes(allowed_signers)
        try:
            result = subprocess.run(
                [
                    executable,
                    "-Y",
                    "verify",
                    "-f",
                    str(signers_snapshot),
                    "-I",
                    approved_by,
                    "-n",
                    SIGNATURE_NAMESPACE,
                    "-s",
                    str(signature_snapshot),
                ],
                input=approval_bytes,
                capture_output=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CorpusAcceptanceError(f"approval signature verification failed: {exc}") from exc
    if result.returncode != 0:
        raise CorpusAcceptanceError("approval signature verification failed")
    return (
        hashlib.sha256(approval_bytes).hexdigest(),
        hashlib.sha256(signature).hexdigest(),
        hashlib.sha256(allowed_signers).hexdigest(),
        approved_at,
    )


def verify_corpus_acceptance(
    *,
    manifest_path: Path,
    corpus_path: Path,
    audio_root: Path,
    approval_path: Path,
    signature_path: Path,
    allowed_signers_path: Path,
    ssh_keygen: str = "ssh-keygen",
) -> VerifiedCorpusAcceptance:
    """Verify human approval and every corpus byte, returning a per-measurement guard."""
    manifest, manifest_bytes = _load_json_bytes(manifest_path, "acceptance manifest")
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    corpus_sha256, rights, bindings = _parse_manifest(manifest)
    approval_sha256, signature_sha256, allowed_signers_sha256, approved_at = _verify_approval(
        approval_path=approval_path,
        signature_path=signature_path,
        allowed_signers_path=allowed_signers_path,
        manifest_sha256=manifest_sha256,
        rights=rights,
        ssh_keygen=ssh_keygen,
    )
    corpus, corpus_bytes = _load_corpus_bytes(corpus_path)
    if hashlib.sha256(corpus_bytes).hexdigest() != corpus_sha256:
        raise CorpusAcceptanceError("corpus manifest SHA-256 changed after human approval")
    if corpus.provenance.interim:
        raise CorpusAcceptanceError(
            "an interim corpus cannot become production acceptance evidence"
        )
    try:
        corpus.assert_section_8_1_coverage()
    except RuntimeError as exc:
        raise CorpusAcceptanceError(str(exc)) from exc
    if corpus.provenance.licence != rights.licence:
        raise CorpusAcceptanceError("signed rights licence does not match the corpus provenance")
    by_id = {item.item_id: item for item in corpus.items}
    binding_by_id = {binding.item_id: binding for binding in bindings}
    if len(by_id) != len(corpus.items):
        raise CorpusAcceptanceError("corpus contains duplicate item ids")
    if set(by_id) != set(binding_by_id):
        raise CorpusAcceptanceError("signed acceptance items do not exactly match corpus item ids")
    root = _validated_root(audio_root)
    rooted: list[CorpusItem] = []
    for item_id, item in by_id.items():
        binding = binding_by_id[item_id]
        if item.audio_path != binding.audio_path:
            raise CorpusAcceptanceError(f"{item_id}: signed audio path does not match corpus")
        if _item_digest(item) != binding.corpus_item_sha256:
            raise CorpusAcceptanceError(f"{item_id}: corpus labels changed after human approval")
        reference_sha256 = hashlib.sha256(item.reference_ckb.encode("utf-8")).hexdigest()
        if reference_sha256 != binding.reference_sha256:
            raise CorpusAcceptanceError(f"{item_id}: reference text changed after human approval")
        audio = _audio_path(root, binding.audio_path)
        if _stable_digest(audio, f"{item_id} corpus audio") != binding.audio_sha256:
            raise CorpusAcceptanceError(f"{item_id}: audio SHA-256 changed after human approval")
        rooted.append(replace(item, audio_path=str(audio)))
    return VerifiedCorpusAcceptance(
        corpus=Corpus(tuple(rooted), provenance=corpus.provenance),
        audio_root=root,
        manifest_sha256=manifest_sha256,
        rights=rights,
        approval_sha256=approval_sha256,
        signature_sha256=signature_sha256,
        allowed_signers_sha256=allowed_signers_sha256,
        approved_at_utc=approved_at,
        _bindings=binding_by_id,
        _audio_root_identity=_root_identity(root),
    )


def _exclusion_file(path: Path | None) -> tuple[str, ...]:
    if path is None:
        return ()
    payload = _read_bound_file(path, "training/exclusion hashes", max_bytes=_MAX_JSON_BYTES)
    try:
        text = payload.decode("ascii")
    except UnicodeDecodeError as exc:
        raise CorpusAcceptanceError("training/exclusion hashes must be ASCII") from exc
    lines = text.splitlines()
    if any(not line or line.strip() != line for line in lines):
        raise CorpusAcceptanceError(
            "training/exclusion hashes must contain one lowercase SHA-256 per non-empty line"
        )
    return _validated_exclusions(tuple(lines))


def _verification_report(verified: VerifiedCorpusAcceptance) -> dict[str, object]:
    coverage = verified.corpus.coverage()
    return {
        "acceptance": dict(verified.evidence),
        "hours_by_dialect": {
            dialect.value: coverage.hours_by_dialect[dialect]
            for dialect in coverage.hours_by_dialect
        },
        "item_count": len(verified.corpus.items),
        "labelled_hours": coverage.labelled_hours,
        "manifest_sha256": verified.manifest_sha256,
        "meets_section_8_1": coverage.is_complete(),
        "schema": _SCHEMA,
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Prepare or verify a signed AC-7 corpus packet without reading model weights."""
    use_utf8_streams()
    parser = argparse.ArgumentParser(
        prog=program_name("hawedit.corpus_acceptance"),
        description="Prepare and verify content-bound Sorani ASR acceptance packets",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare", help="hash and package an unsigned review packet")
    prepare.add_argument("corpus", type=Path)
    prepare.add_argument("--audio-root", type=Path, required=True)
    prepare.add_argument("--output-dir", type=Path, required=True)
    prepare.add_argument("--dataset-owner", required=True)
    prepare.add_argument("--authorized-by", required=True)
    prepare.add_argument("--licence", required=True)
    prepare.add_argument("--consent-basis", required=True)
    prepare.add_argument("--permitted-use", required=True)
    prepare.add_argument("--exclude-hashes", type=Path)
    redistribution = prepare.add_mutually_exclusive_group(required=True)
    redistribution.add_argument(
        "--redistribution-allowed", action="store_true", dest="redistribution_allowed"
    )
    redistribution.add_argument(
        "--redistribution-forbidden", action="store_false", dest="redistribution_allowed"
    )

    verify = subparsers.add_parser("verify", help="verify signed approval and current corpus bytes")
    verify.add_argument("manifest", type=Path)
    verify.add_argument("corpus", type=Path)
    verify.add_argument("--audio-root", type=Path, required=True)
    verify.add_argument("--approval", type=Path, required=True)
    verify.add_argument("--signature", type=Path, required=True)
    verify.add_argument("--allowed-signers", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        with machine_readable_stdout() as report_stream:
            if args.command == "prepare":
                prepared = prepare_corpus_acceptance(
                    corpus_path=args.corpus,
                    audio_root=args.audio_root,
                    output_dir=args.output_dir,
                    rights=CorpusRights(
                        dataset_owner=args.dataset_owner,
                        authorized_by=args.authorized_by,
                        licence=args.licence,
                        consent_basis=args.consent_basis,
                        permitted_use=args.permitted_use,
                        redistribution_allowed=args.redistribution_allowed,
                    ),
                    excluded_audio_sha256=_exclusion_file(args.exclude_hashes),
                )
                document: dict[str, object] = {
                    "approval_template": str(prepared.approval_template_path),
                    "coverage_report": str(prepared.coverage_report_path),
                    "instructions": str(prepared.instructions_path),
                    "manifest": str(prepared.manifest_path),
                    "manifest_sha256": prepared.manifest_sha256,
                    "status": "prepared-not-approved",
                }
            else:
                verified = verify_corpus_acceptance(
                    manifest_path=args.manifest,
                    corpus_path=args.corpus,
                    audio_root=args.audio_root,
                    approval_path=args.approval,
                    signature_path=args.signature,
                    allowed_signers_path=args.allowed_signers,
                )
                document = {"status": "signed-and-verified", **_verification_report(verified)}
            print(json.dumps(document, ensure_ascii=False, sort_keys=True), file=report_stream)
    except (CorpusAcceptanceError, OSError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
