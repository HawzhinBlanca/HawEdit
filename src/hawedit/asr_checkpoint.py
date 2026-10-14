"""Bounded host-owned ASR checkpoints, not endpoint authentication or model admission.

The launch owner must supply authenticated private streams and enforce deadlines
and drain. This module never launches a process or grants a resource/security lease.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, BinaryIO

from hawedit.asr import LONG_AUDIO_THRESHOLD_S, VALIDATOR_MODEL_ID
from hawedit.asr_resume import OperationJournal
from hawedit.transcripts import RawTranscript

FRAME_LIMIT = 64 * 1024
EXCHANGE_LIMIT = 100_000
RESULT_LIMIT = 16 * 1024 * 1024
RESULT_CHUNK = 32 * 1024
_HASH = re.compile(r"[a-f0-9]{64}")
_AUDIO_ID = re.compile(r"[a-zA-Z0-9_-]{1,128}")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hash(value: object) -> bool:
    return isinstance(value, str) and _HASH.fullmatch(value) is not None


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("duplicate JSON key")
        result[name] = value
    return result


def _nonfinite(value: str) -> Any:
    raise ValueError("nonfinite JSON number: " + value)


def encode_frame(value: Mapping[str, object]) -> bytes:
    try:
        frame = json.dumps(
            dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise RuntimeError("ASR checkpoint frame cannot be encoded") from exc
    if not 0 < len(frame) <= FRAME_LIMIT:
        raise RuntimeError("ASR checkpoint frame exceeds its bound")
    return frame


def decode_frame(frame: bytes) -> dict[str, Any]:
    if not 0 < len(frame) <= FRAME_LIMIT:
        raise RuntimeError("ASR checkpoint frame exceeds its bound")
    try:
        value = json.loads(frame, object_pairs_hook=_pairs, parse_constant=_nonfinite)
        if not isinstance(value, dict) or not value:
            raise ValueError("frame must be a nonempty object")
        # Reject alternate encodings before they can have two different evidence hashes.
        if encode_frame(value) != frame:
            raise ValueError("noncanonical frame")
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise RuntimeError("ASR checkpoint frame is malformed") from exc
    return value


def _read_exact(stream: BinaryIO, size: int) -> bytes:
    result = bytearray()
    while len(result) < size:
        chunk = stream.read(size - len(result))
        if not isinstance(chunk, bytes) or not chunk or len(chunk) > size - len(result):
            raise RuntimeError("ASR checkpoint channel ended or violated its read bound")
        result.extend(chunk)
    return bytes(result)


def read_frame(stream: BinaryIO) -> bytes:
    size = int.from_bytes(_read_exact(stream, 4), "big")
    if not 0 < size <= FRAME_LIMIT:
        raise RuntimeError("ASR checkpoint declared frame exceeds its bound")
    return _read_exact(stream, size)


def write_frame(stream: BinaryIO, frame: bytes) -> None:
    decode_frame(frame)
    data = len(frame).to_bytes(4, "big") + frame
    offset = 0
    while offset < len(data):
        count = stream.write(data[offset:])
        if type(count) is not int or not 0 < count <= len(data) - offset:
            raise RuntimeError("ASR checkpoint channel failed its bounded write")
        offset += count
    stream.flush()


def _operation(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "audio_id",
        "audio_sha256",
        "duration_s",
        "stage",
        "text",
    }:
        raise RuntimeError("ASR checkpoint operation has invalid fields")
    duration = value["duration_s"]
    stage, text = value["stage"], value["text"]
    if (
        not isinstance(value["audio_id"], str)
        or _AUDIO_ID.fullmatch(value["audio_id"]) is None
        or not _hash(value["audio_sha256"])
        or type(duration) not in (int, float)
        or not math.isfinite(duration)
        or not 0 < duration <= LONG_AUDIO_THRESHOLD_S
        or stage not in ("draft", "correction-alignment", "validator:" + VALIDATOR_MODEL_ID)
        or (stage == "correction-alignment" and (not isinstance(text, str) or not text.strip()))
        or (stage != "correction-alignment" and text is not None)
    ):
        raise RuntimeError("ASR checkpoint operation evidence is invalid")
    return value


class CheckpointHost:
    """One ordered session, with host paths selected exclusively from its frozen binding."""

    def __init__(self, journal: OperationJournal, audio: Mapping[str, Path]) -> None:
        inputs = journal.binding["inputs"]
        if any(
            not _hash(inputs.get(name))
            for name in ("source_sha256", "configuration_sha256", "runtime_sha256")
        ):
            raise RuntimeError("ASR checkpoint requires source/configuration/runtime binding")
        bound = inputs.get("audio")
        if not isinstance(bound, list) or not bound or not audio:
            raise RuntimeError("ASR checkpoint requires bound audio")
        self._audio: dict[str, Path] = {}
        for name, path in audio.items():
            if not isinstance(name, str) or _AUDIO_ID.fullmatch(name) is None:
                raise RuntimeError("ASR checkpoint audio ID is invalid")
            resolved = path.resolve()
            matches = [entry for entry in bound if entry.get("path") == str(resolved)]
            if len(matches) != 1 or resolved in self._audio.values():
                raise RuntimeError("ASR checkpoint audio is not uniquely bound")
            self._audio[name] = resolved
        if len(self._audio) != len(bound):
            raise RuntimeError("ASR checkpoint audio binding is incomplete")
        self._journal = journal
        self._sequence = 1
        self._failed = False
        self._result_size: int | None = None
        self._result_hash: str | None = None
        self._chunks: list[bytes] = []
        self._received = 0
        self._transcript: RawTranscript | None = None

    @property
    def transcript(self) -> RawTranscript | None:
        """Pending private result, never a completed pipeline/delivery artifact."""
        return None if self._failed else self._transcript

    def _retain_result_record(self, stage: str, text: str, result: object) -> None:
        path = next(iter(self._audio.values()))
        entry = next(
            item for item in self._journal.binding["inputs"]["audio"] if item["path"] == str(path)
        )
        operation = self._journal.operation(
            stage, path, (entry["end_ms"] - entry["start_ms"]) / 1000, text
        )
        previous = self._journal.load(operation)
        if previous is None:
            self._journal.save(operation, result)
        elif previous != result:
            raise RuntimeError("ASR checkpoint retained result changed; reconcile")

    def _result(self, value: dict[str, Any]) -> None:
        action = value["action"]
        if action == "result-start":
            size, digest = value["size"], value["sha256"]
            if (
                self._result_size is not None
                or type(size) is not int
                or not 0 < size <= RESULT_LIMIT
                or not _hash(digest)
            ):
                raise RuntimeError("ASR checkpoint result declaration is invalid")
            self._result_size, self._result_hash = size, digest
        elif action == "result-chunk":
            if (
                self._result_size is None
                or type(value["index"]) is not int
                or value["index"] != len(self._chunks)
                or not isinstance(value["data"], str)
            ):
                raise RuntimeError("ASR checkpoint result chunk sequence is invalid")
            try:
                chunk = base64.b64decode(value["data"], validate=True)
            except (ValueError, binascii.Error) as exc:
                raise RuntimeError("ASR checkpoint result chunk encoding is invalid") from exc
            if (
                not 0 < len(chunk) <= RESULT_CHUNK
                or self._received + len(chunk) > self._result_size
                or value["sha256"] != _digest(chunk)
                or len(chunk) != min(RESULT_CHUNK, self._result_size - self._received)
            ):
                raise RuntimeError("ASR checkpoint result chunk evidence is invalid")
            self._retain_result_record(
                "transcript-chunk",
                f"{self._result_hash}:{len(self._chunks)}",
                {"data": value["data"], "sha256": value["sha256"]},
            )
            self._chunks.append(chunk)
            self._received += len(chunk)
        else:
            if self._result_size is None or self._received != self._result_size:
                raise RuntimeError("ASR checkpoint result is incomplete")
            content = b"".join(self._chunks)
            if _digest(content) != self._result_hash:
                raise RuntimeError("ASR checkpoint result hash differs")
            try:
                transcript = RawTranscript.from_json(content.decode("utf-8"))
                if (transcript.to_json() + "\n").encode(
                    "utf-8"
                ) != content or transcript.media_id != self._journal.binding["inputs"].get(
                    "media_id"
                ):
                    raise ValueError("canonical result or media identity differs")
            except (ValueError, TypeError, UnicodeError) as exc:
                raise RuntimeError("ASR checkpoint transcript evidence is invalid") from exc
            # A source segment changed after its earlier ACK must not reach final acceptance.
            for path in self._audio.values():
                entry = next(
                    item
                    for item in self._journal.binding["inputs"]["audio"]
                    if item["path"] == str(path)
                )
                self._journal.operation(
                    "transcript-final", path, (entry["end_ms"] - entry["start_ms"]) / 1000
                )
            self._retain_result_record(
                "transcript-result",
                str(self._result_hash),
                {
                    "size": self._result_size,
                    "sha256": self._result_hash,
                    "chunks": len(self._chunks),
                },
            )
            self._transcript = transcript
            self._chunks.clear()

    def handle(self, frame: bytes) -> bytes:
        if self._failed or self.transcript is not None:
            raise RuntimeError("ASR checkpoint session has failed; reconcile and restart")
        try:
            value = decode_frame(frame)
            action = value.get("action")
            fields = {"schema", "sequence", "binding_sha256", "action"}
            extra = {
                "load": {"operation"},
                "save": {"operation", "result"},
                "result-start": {"size", "sha256"},
                "result-chunk": {"index", "data", "sha256"},
                "result-end": set(),
            }
            if not isinstance(action, str) or action not in extra:
                raise RuntimeError("ASR checkpoint action is invalid")
            fields.update(extra[action])
            if (
                set(value) != fields
                or type(value["schema"]) is not int
                or value["schema"] != 1
                or type(value["sequence"]) is not int
                or value["sequence"] != self._sequence
                or self._sequence > EXCHANGE_LIMIT
                or value["binding_sha256"] != self._journal.binding_sha256
            ):
                raise RuntimeError("ASR checkpoint sequence/binding/action evidence is invalid")
            payload: Any = None
            if action.startswith("result-"):
                self._result(value)
            else:
                if self._result_size is not None:
                    raise RuntimeError("ASR checkpoint operations cannot follow result start")
                operation = _operation(value["operation"])
                path = self._audio.get(operation["audio_id"])
                if path is None:
                    raise RuntimeError("ASR checkpoint audio ID is not bound")
                host_operation = self._journal.operation(
                    operation["stage"], path, operation["duration_s"], operation["text"]
                )
                if host_operation["audio_sha256"] != operation["audio_sha256"]:
                    raise RuntimeError("ASR checkpoint worker/host audio hash differs")
                if action == "load":
                    payload = self._journal.load(host_operation)
                else:
                    self._journal.save(host_operation, value["result"])
            # No success frame exists until the actual journal write/fsync has returned.
            reply = encode_frame(
                {
                    "schema": 1,
                    "sequence": self._sequence,
                    "binding_sha256": self._journal.binding_sha256,
                    "request_sha256": _digest(frame),
                    "payload": payload,
                    "payload_sha256": _digest(encode_frame({"value": payload})),
                }
            )
            self._sequence += 1
            return reply
        except BaseException:
            self._failed = True
            raise


class CheckpointJournal:
    """Read-only worker cache client; an ACK, not a writable directory, advances inference."""

    def __init__(
        self, reader: BinaryIO, writer: BinaryIO, binding_sha256: str, audio: Mapping[Path, str]
    ) -> None:
        if not _hash(binding_sha256) or not audio:
            raise RuntimeError("ASR checkpoint client binding is invalid")
        self._audio = {path.resolve(): name for path, name in audio.items()}
        if len(self._audio) != len(audio) or len(set(self._audio.values())) != len(audio):
            raise RuntimeError("ASR checkpoint client audio must be unique")
        if any(
            not isinstance(name, str) or _AUDIO_ID.fullmatch(name) is None
            for name in self._audio.values()
        ):
            raise RuntimeError("ASR checkpoint client audio ID is invalid")
        self._reader, self._writer = reader, writer
        self._binding = binding_sha256
        self._sequence = 1
        self._failed = False
        self._issued: dict[str, Path] = {}

    def operation(
        self, stage: str, path: Path, duration_s: float, text: str | None = None
    ) -> dict[str, object]:
        if self._failed:
            raise RuntimeError("ASR checkpoint client has failed")
        try:
            resolved = path.resolve()
            name = self._audio.get(resolved)
            with resolved.open("rb") as stream:
                audio_hash = hashlib.file_digest(stream, "sha256").hexdigest()
            operation = _operation(
                {
                    "audio_id": name,
                    "audio_sha256": audio_hash,
                    "duration_s": duration_s,
                    "stage": stage,
                    "text": text,
                }
            )
            self._issued[_digest(encode_frame(operation))] = resolved
            return operation
        except BaseException:
            self._failed = True
            raise

    def _exchange(self, action: str, operation: Mapping[str, object], result: object = None) -> Any:
        if self._failed:
            raise RuntimeError("ASR checkpoint client has failed; reconcile and restart")
        try:
            checked = _operation(dict(operation))
            path = self._issued.get(_digest(encode_frame(checked)))
            if path is None:
                raise RuntimeError("ASR checkpoint client operation was not issued")
            with path.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != checked["audio_sha256"]:
                    raise RuntimeError("ASR checkpoint worker audio changed during inference")
            fields: dict[str, object] = {"operation": checked}
            if action == "save":
                fields["result"] = result
            return self._request(action, fields)
        except BaseException:
            self._failed = True
            raise

    def _request(self, action: str, fields: Mapping[str, object]) -> Any:
        if self._failed:
            raise RuntimeError("ASR checkpoint client has failed; reconcile and restart")
        try:
            if self._sequence > EXCHANGE_LIMIT:
                raise RuntimeError("ASR checkpoint exchange count exceeds its bound")
            request: dict[str, object] = {
                "schema": 1,
                "sequence": self._sequence,
                "binding_sha256": self._binding,
                "action": action,
                **fields,
            }
            frame = encode_frame(request)
            write_frame(self._writer, frame)
            reply = decode_frame(read_frame(self._reader))
            if (
                set(reply)
                != {
                    "schema",
                    "sequence",
                    "binding_sha256",
                    "request_sha256",
                    "payload",
                    "payload_sha256",
                }
                or type(reply["schema"]) is not int
                or reply["schema"] != 1
                or type(reply["sequence"]) is not int
                or reply["sequence"] != self._sequence
                or reply["binding_sha256"] != self._binding
                or reply["request_sha256"] != _digest(frame)
                or reply["payload_sha256"] != _digest(encode_frame({"value": reply["payload"]}))
                or (action != "load" and reply["payload"] is not None)
            ):
                raise RuntimeError("ASR checkpoint acknowledgment evidence is invalid")
            self._sequence += 1
            return reply["payload"]
        except BaseException:
            self._failed = True
            raise

    def load(self, operation: Mapping[str, object]) -> Any:
        return self._exchange("load", operation)

    def save(self, operation: Mapping[str, object], result: object) -> None:
        self._exchange("save", operation, result)

    def finish(self, transcript: RawTranscript) -> None:
        """Retain a private result only; original-owner drain still precedes acceptance."""
        if self._failed:
            raise RuntimeError("ASR checkpoint client has failed")
        try:
            content = (transcript.to_json() + "\n").encode("utf-8")
            if not 0 < len(content) <= RESULT_LIMIT:
                raise RuntimeError("ASR checkpoint transcript exceeds its 16MiB bound")
            self._request("result-start", {"size": len(content), "sha256": _digest(content)})
            for index, offset in enumerate(range(0, len(content), RESULT_CHUNK)):
                chunk = content[offset : offset + RESULT_CHUNK]
                self._request(
                    "result-chunk",
                    {
                        "index": index,
                        "data": base64.b64encode(chunk).decode("ascii"),
                        "sha256": _digest(chunk),
                    },
                )
            self._request("result-end", {})
            # A client cannot silently perform another inference in this completed session.
            self._failed = True
        except BaseException:
            self._failed = True
            raise
