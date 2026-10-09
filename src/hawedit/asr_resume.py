"""Owner-private operation recovery, never a transcript or publication certificate."""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import json
import os
import platform
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any, BinaryIO, cast

from hawedit.asr import (
    VALIDATOR_MODEL_ID,
    OmniSegmentBackend,
    SegmentTranscript,
    SoraniValidator,
    _PreparedSpeechSegment,
)
from hawedit.asr_completion import COMPLETION_POLICY_ID
from hawedit.models import ModelStore
from hawedit.omni_assets import (
    assert_omni_asset_integrity,
    assert_omni_card_integrity,
    freeze_fairseq2_asset_overrides,
)
from hawedit.qwen_completion import QWEN_COMPLETION_POLICY_ID
from hawedit.studio_private import PrivateDirectory, write_text_atomic
from hawedit.transcripts import Word


def _json(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _digest(value: object) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class OperationJournal:
    """Strict private/fsynced records with a nonblocking process-owned writer lease."""

    def __init__(self, root: Path, binding: Mapping[str, object]) -> None:
        self.directory = PrivateDirectory(root)
        self.binding: dict[str, Any] = json.loads(_json({"schema": 1, "inputs": dict(binding)}))
        self.binding_sha256 = _digest(self.binding)
        self._lease: BinaryIO | None = None

    def __enter__(self) -> OperationJournal:
        try:
            self.directory.check_file("writer.lock")
        except FileNotFoundError:
            with self.directory.open_new_file("writer.lock") as stream:
                stream.write(b"0")
                stream.flush()
                os.fsync(stream.fileno())
            self.directory.sync()
        before = self.directory.member_identity("writer.lock")
        expected_file = self.directory.check_file("writer.lock")
        self._lease = (self.directory.path / "writer.lock").open("r+b")
        try:
            opened = os.fstat(self._lease.fileno())
            if self.directory.member_identity("writer.lock") != before or (
                opened.st_dev,
                opened.st_ino,
            ) != (expected_file.st_dev, expected_file.st_ino):
                raise RuntimeError("ASR checkpoint writer identity changed")
            if os.name == "nt":
                msvcrt = importlib.import_module("msvcrt")
                msvcrt.locking(self._lease.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl = importlib.import_module("fcntl")
                fcntl.flock(self._lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException as exc:
            self._lease.close()
            self._lease = None
            raise RuntimeError(
                "ASR checkpoint request is already owned or lease is unsafe"
            ) from exc
        try:
            existing = self._read("binding.json")
            if existing is None:
                write_text_atomic(self.directory.path / "binding.json", _json(self.binding) + "\n")
            elif _json(existing) != _json(self.binding):
                raise RuntimeError("ASR checkpoint binding changed; preserve records and reconcile")
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *_args: object) -> None:
        if self._lease is not None:
            self._lease.close()
            self._lease = None

    def _read(self, name: str) -> Any:
        try:
            info = self.directory.check_file(name)
        except FileNotFoundError:
            return None
        if info.st_size > 1024 * 1024:
            raise RuntimeError("ASR checkpoint exceeds its record size bound")
        identity = self.directory.member_identity(name)
        try:
            descriptor = os.open(
                self.directory.path / name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            )
            with os.fdopen(descriptor, "rb") as stream:
                opened = os.fstat(stream.fileno())
                if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                    raise RuntimeError("ASR checkpoint opened a changed identity")
                content = stream.read(1024 * 1024 + 1)
                if len(content) > 1024 * 1024:
                    raise RuntimeError("ASR checkpoint exceeds its record size bound")
                value = json.loads(content)
        except (ValueError, UnicodeError) as exc:
            raise RuntimeError(
                "ASR checkpoint is malformed; preserve it for reconciliation"
            ) from exc
        if value is None:
            raise RuntimeError("ASR checkpoint cannot contain a null record")
        if self.directory.member_identity(name) != identity:
            raise RuntimeError("ASR checkpoint identity changed while reading")
        return value

    def operation(
        self, stage: str, path: Path, duration_s: float, text: str | None = None
    ) -> dict[str, object]:
        if self._lease is None:
            raise RuntimeError("ASR checkpoint operation requires an active writer lease")
        if _json(self._read("binding.json")) != _json(self.binding):
            raise RuntimeError("ASR checkpoint binding changed during the run")
        audio_sha256 = _file_digest(path)
        resolved_path = str(path.resolve())
        audio_inputs = self.binding["inputs"].get("audio")
        if audio_inputs is not None:
            matches = [item for item in audio_inputs if item["path"] == resolved_path]
            if (
                len(matches) != 1
                or matches[0]["sha256"] != audio_sha256
                or matches[0]["end_ms"] - matches[0]["start_ms"] != round(duration_s * 1000)
            ):
                raise RuntimeError(
                    "ASR checkpoint bound audio changed; recovery reconciliation required"
                )
        return {
            "stage": stage,
            "path": resolved_path,
            "audio_sha256": audio_sha256,
            "duration_s": duration_s,
            "text": text,
            "binding_sha256": self.binding_sha256,
        }

    def load(self, operation: Mapping[str, object]) -> Any:
        if self._lease is None:
            raise RuntimeError("ASR checkpoint load requires an active writer lease")
        record = self._read("operation-" + _digest(operation) + ".json")
        if record is None:
            return None
        try:
            if (
                not isinstance(record, dict)
                or set(record) != {"schema", "operation", "result", "result_sha256"}
                or type(record["schema"]) is not int
                or record["schema"] != 1
                or _json(record["operation"]) != _json(dict(operation))
                or record["result_sha256"] != _digest(record["result"])
            ):
                raise ValueError("invalid record")
        except (TypeError, ValueError) as exc:
            raise RuntimeError("ASR checkpoint record evidence is invalid") from exc
        return record["result"]

    def save(self, operation: Mapping[str, object], result: object) -> None:
        if self._lease is None:
            raise RuntimeError("ASR checkpoint save requires an active writer lease")
        if _json(self._read("binding.json")) != _json(self.binding):
            raise RuntimeError("ASR checkpoint binding changed during inference")
        path = Path(str(operation["path"]))
        if _file_digest(path) != operation["audio_sha256"]:
            raise RuntimeError("ASR checkpoint audio changed during inference")
        record = {
            "schema": 1,
            "operation": dict(operation),
            "result": result,
            "result_sha256": _digest(result),
        }
        destination = self.directory.path / ("operation-" + _digest(operation) + ".json")
        if destination.exists():
            raise RuntimeError("ASR checkpoint refuses to overwrite a completed operation")
        encoded = _json(record) + "\n"
        if len(encoded.encode("utf-8")) > 1024 * 1024:
            raise RuntimeError("ASR checkpoint exceeds its record size bound")
        write_text_atomic(destination, encoded)


def _segment(value: Any) -> SegmentTranscript:
    try:
        if not isinstance(value, dict) or set(value) != {
            "text_raw",
            "ctc_text",
            "words",
            "mean_logprob",
        }:
            raise ValueError("invalid segment fields")
        return SegmentTranscript(
            value["text_raw"],
            value["ctc_text"],
            tuple(Word(**word) for word in value["words"]),
            value["mean_logprob"],
        )
    except (AttributeError, TypeError, ValueError, KeyError) as exc:
        raise RuntimeError("ASR checkpoint segment is invalid") from exc


class ResumableBackend:
    def __init__(self, backend: OmniSegmentBackend, journal: OperationJournal) -> None:
        self.backend, self.journal = backend, journal

    @property
    def adapter_name(self) -> str | None:
        return cast(str | None, getattr(self.backend, "adapter_name", None))

    def transcribe_segment(self, audio_path: Path, duration_s: float) -> SegmentTranscript:
        operation = self.journal.operation("draft", audio_path, duration_s)
        saved = self.journal.load(operation)
        if saved is not None:
            return _segment(saved)
        result = self.backend.transcribe_segment(audio_path, duration_s)
        self.journal.save(operation, asdict(result))
        return result

    def align_segment(self, audio_path: Path, duration_s: float, text: str) -> SegmentTranscript:
        operation = self.journal.operation("correction-alignment", audio_path, duration_s, text)
        saved = self.journal.load(operation)
        if saved is not None:
            return _segment(saved)
        result = self.backend.align_segment(audio_path, duration_s, text)
        self.journal.save(operation, asdict(result))
        return result


class ResumableValidator:
    def __init__(self, validator: SoraniValidator, journal: OperationJournal) -> None:
        self.validator, self.journal = validator, journal
        self.model_id = validator.model_id

    def transcribe_segment(self, audio_path: Path, duration_s: float) -> str:
        operation = self.journal.operation("validator:" + self.model_id, audio_path, duration_s)
        saved = self.journal.load(operation)
        if saved is not None:
            if not isinstance(saved, str) or not saved.strip():
                raise RuntimeError("ASR checkpoint validator response is invalid")
            return saved
        result = self.validator.transcribe_segment(audio_path, duration_s)
        if not isinstance(result, str) or not result.strip():
            raise RuntimeError("ASR checkpoint cannot save an empty validator response")
        self.journal.save(operation, result)
        return result


def worker_journal(
    root: Path,
    request_path: Path,
    prepared: Sequence[_PreparedSpeechSegment],
    validator_path: Path,
    model_identity: str | None,
) -> OperationJournal:
    """Production cache binding verifies current bytes before any cached operation is used."""
    from hawedit.wsl_setup import package_digest

    parent = PrivateDirectory(root)
    freeze_fairseq2_asset_overrides()
    canonical_card = assert_omni_card_integrity()
    request_identity = hashlib.sha256(str(request_path.resolve()).encode("utf-8")).hexdigest()
    directory = parent.child(request_identity, create=True)
    binding: dict[str, object] = {
        "request_path": str(request_path.resolve()),
        "request_sha256": _file_digest(request_path),
        "source_package_sha256": package_digest(),
        "adapter": model_identity,
        "completion_policy": COMPLETION_POLICY_ID,
        "validator_completion_policy": QWEN_COMPLETION_POLICY_ID,
        "canonical_card_sha256": _file_digest(canonical_card),
        "python": platform.python_version(),
        "runtime_prefix": sys.prefix,
        "host": platform.node(),
        "platform": platform.platform(),
        "decoder_sources": {
            name: _file_digest(
                Path(
                    str(
                        importlib.metadata.distribution("omnilingual-asr").locate_file(
                            "omnilingual_asr/models/wav2vec2_llama/" + name
                        )
                    )
                )
            )
            for name in ("beamsearch.py", "model.py")
        },
        "runtime": {
            name: importlib.metadata.version(name)
            for name in ("torch", "qwen-asr", "omnilingual-asr", "fairseq2", "peft", "transformers")
        },
        "devices": {
            name: os.environ.get(name, default)
            for name, default in (
                ("HAWEDIT_ASR_LLM_DEVICE", "cuda:0"),
                ("HAWEDIT_ASR_CTC_DEVICE", "cuda:1"),
                ("HAWEDIT_ASR_VALIDATOR_DEVICE", "cuda:1"),
            )
        },
        "audio": [
            {
                "path": str(item.path),
                "start_ms": item.start_ms,
                "end_ms": item.end_ms,
                "sha256": _file_digest(item.path),
            }
            for item in prepared
        ],
        "canonical_assets": [asdict(report) for report in assert_omni_asset_integrity()],
        "validator": asdict(ModelStore().verify_checkpoint(VALIDATOR_MODEL_ID, validator_path)),
    }
    # Asset reports contain Path instances; retain their actual paths in canonical JSON.
    binding = json.loads(json.dumps(binding, default=str))
    return OperationJournal(directory.path, binding)
