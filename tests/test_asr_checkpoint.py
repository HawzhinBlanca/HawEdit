"""Real storage/frame contracts; controlled speech is not model accuracy evidence."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import threading
from pathlib import Path
from typing import BinaryIO

import pytest

from hawedit.asr_checkpoint import (
    RESULT_CHUNK,
    CheckpointHost,
    CheckpointJournal,
    decode_frame,
    encode_frame,
    read_frame,
    write_frame,
)
from hawedit.asr_resume import OperationJournal
from hawedit.asr_worker import infer_protected_request, run_request
from test_worker_publication import Backend, inputs


def binding(path: Path) -> dict[str, object]:
    return {
        "source_sha256": "1" * 64,
        "configuration_sha256": "2" * 64,
        "runtime_sha256": "3" * 64,
        "media_id": "publication-contract",
        "audio": [
            {
                "path": str(path.resolve()),
                "sha256": digest(path.read_bytes()),
                "start_ms": 0,
                "end_ms": 1000,
            }
        ],
    }


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def message(
    journal: OperationJournal, *, sequence: int = 1, action: str = "load", result: object = None
) -> dict[str, object]:
    request: dict[str, object] = {
        "schema": 1,
        "sequence": sequence,
        "binding_sha256": journal.binding_sha256,
        "action": action,
        "operation": {
            "audio_id": "speech-0",
            "audio_sha256": journal.binding["inputs"]["audio"][0]["sha256"],
            "duration_s": 1.0,
            "stage": "draft",
            "text": None,
        },
    }
    if action == "save":
        request["result"] = result
    return request


def test_checkpoint_exchange_persists_before_ack_and_survives_restart(tmp_path: Path) -> None:
    request, _ = inputs(tmp_path)
    path = request.parent / "speech.wav"
    root = tmp_path / "host-checkpoints"
    record = {"retained": "\u06a9\u0648\u0631\u062f\u06cc"}
    with OperationJournal(root, binding(path)) as journal:
        host = CheckpointHost(journal, {"speech-0": path})
        frame = encode_frame(message(journal, action="save", result=record))
        reply = decode_frame(host.handle(frame))
        records = list(root.glob("operation-*.json"))
        assert len(records) == 1
        assert json.loads(records[0].read_bytes())["result"] == record
        assert reply["payload"] is None and reply["request_sha256"] == digest(frame)
        retained = records[0].read_bytes()
    with OperationJournal(root, binding(path)) as journal:
        host = CheckpointHost(journal, {"speech-0": path})
        reply = decode_frame(host.handle(encode_frame(message(journal))))
        assert reply["payload"] == record
    assert records[0].read_bytes() == retained


@pytest.mark.parametrize(
    "damage",
    ["sequence", "sequence-bool", "binding", "hash", "clock", "path", "extra", "stage", "text"],
)
def test_checkpoint_exchange_refuses_changed_evidence(tmp_path: Path, damage: str) -> None:
    request, _ = inputs(tmp_path)
    path = request.parent / "speech.wav"
    with OperationJournal(tmp_path / "checkpoints", binding(path)) as journal:
        host = CheckpointHost(journal, {"speech-0": path})
        value = message(journal)
        operation = value["operation"]
        assert isinstance(operation, dict)
        if damage == "sequence":
            value["sequence"] = 2
        elif damage == "sequence-bool":
            value["sequence"] = True
        elif damage == "binding":
            value["binding_sha256"] = "0" * 64
        elif damage == "hash":
            operation["audio_sha256"] = "0" * 64
        elif damage == "clock":
            operation["duration_s"] = 2.0
        elif damage == "path":
            operation["audio_id"] = str(path)
        elif damage == "extra":
            value["host_path"] = str(path)
        elif damage == "stage":
            operation["stage"] = "pretend-complete"
        else:
            operation["text"] = "unbound draft correction"
        with pytest.raises(RuntimeError, match="checkpoint"):
            host.handle(encode_frame(value))
        with pytest.raises(RuntimeError, match="failed"):
            host.handle(encode_frame(message(journal)))
        assert list((tmp_path / "checkpoints").glob("operation-*.json")) == []


def test_checkpoint_exchange_storage_failure_has_no_ack(tmp_path: Path) -> None:
    request, _ = inputs(tmp_path)
    path = request.parent / "speech.wav"
    root = tmp_path / "checkpoints"
    with OperationJournal(root, binding(path)) as journal:
        host = CheckpointHost(journal, {"speech-0": path})
        # Release the actual owner lease, not a mocked fsync or storage function.
        journal.__exit__(None, None, None)
        with pytest.raises(RuntimeError, match="lease"):
            host.handle(encode_frame(message(journal, action="save", result="retained")))
        with pytest.raises(RuntimeError, match="failed"):
            host.handle(encode_frame(message(journal)))
    assert list(root.glob("operation-*.json")) == []


@pytest.mark.parametrize(
    "frame",
    [b"{}", b'{"schema":1,"schema":1}', b'{"value":NaN}', b"\xff", b"x" * 65537],
    ids=["empty", "duplicate-key", "nonfinite", "non-utf8", "oversize"],
)
def test_checkpoint_exchange_refuses_malformed_frames(frame: bytes) -> None:
    with pytest.raises(RuntimeError, match="checkpoint"):
        decode_frame(frame)


def test_protected_inference_requires_remote_journal(tmp_path: Path) -> None:
    request, output = inputs(tmp_path)
    with (
        OperationJournal(tmp_path / "checkpoints", {}) as journal,
        pytest.raises(TypeError, match="remote"),
    ):
        infer_protected_request(request, journal, Backend())
    assert not output.exists()


def test_checkpoint_exchange_client_refuses_false_ack(tmp_path: Path) -> None:
    request, _ = inputs(tmp_path)
    path = request.parent / "speech.wav"
    output = io.BytesIO()
    journal = CheckpointJournal(
        io.BytesIO(b"\x00\x00\x00\x02{}"), output, "1" * 64, {path: "speech-0"}
    )
    operation = journal.operation("draft", path, 1.0)
    with pytest.raises(RuntimeError, match="checkpoint"):
        journal.save(operation, "not-yet-durable")
    before = output.getvalue()
    with pytest.raises(RuntimeError, match="failed"):
        journal.load(operation)
    assert output.getvalue() == before


def _serve(
    host: CheckpointHost,
    incoming: BinaryIO,
    outgoing: BinaryIO,
    count: int,
    errors: list[BaseException],
) -> None:
    try:
        for _ in range(count):
            write_frame(outgoing, host.handle(read_frame(incoming)))
    except BaseException as exc:
        errors.append(exc)
        outgoing.close()


def test_protected_inference_uses_host_checkpoint_without_worker_writes(tmp_path: Path) -> None:
    worker = tmp_path / "worker"
    worker.mkdir()
    request, output = inputs(worker)
    audio = worker / "speech.wav"
    before = {path.name: path.read_bytes() for path in worker.iterdir()}
    first = Backend("\u06a9\u0648\u0631\u062f\u06cc.")
    second = Backend("must not become a new canonical transcript")
    results = []
    for index, backend in enumerate((first, second)):
        host_read, worker_write = os.pipe()
        worker_read, host_write = os.pipe()
        errors: list[BaseException] = []
        with (
            OperationJournal(tmp_path / "host", binding(audio)) as journal,
            os.fdopen(host_read, "rb", buffering=0) as incoming,
            os.fdopen(host_write, "wb", buffering=0) as outgoing,
            os.fdopen(worker_read, "rb", buffering=0) as reader,
            os.fdopen(worker_write, "wb", buffering=0) as writer,
        ):
            host = CheckpointHost(journal, {"speech-0": audio})

            # First run loads then saves. Restart loads the retained operation only.
            thread = threading.Thread(
                target=_serve, args=(host, incoming, outgoing, 5 if index == 0 else 4, errors)
            )
            thread.start()
            try:
                remote = CheckpointJournal(
                    reader, writer, journal.binding_sha256, {audio: "speech-0"}
                )
                results.append(infer_protected_request(request, remote, backend))
            finally:
                writer.close()
                thread.join(timeout=10)
            assert not thread.is_alive() and errors == []
            assert host.transcript == results[-1]
    assert results[0] == results[1]
    assert first.calls == 1 and second.calls == 0
    assert results[0].text_ckb == "\u06a9\u0648\u0631\u062f\u06cc."
    assert not output.exists()
    assert {path.name: path.read_bytes() for path in worker.iterdir()} == before
    # One segment, one result chunk and its durable completion record.
    assert len(list((tmp_path / "host").glob("operation-*.json"))) == 3


def test_checkpoint_exchange_refuses_changed_host_audio(tmp_path: Path) -> None:
    request, _ = inputs(tmp_path)
    audio = request.parent / "speech.wav"
    with OperationJournal(tmp_path / "host", binding(audio)) as journal:
        host = CheckpointHost(journal, {"speech-0": audio})
        frame = encode_frame(message(journal))
        audio.write_bytes(audio.read_bytes() + b"changed")
        with pytest.raises(RuntimeError, match="audio changed"):
            host.handle(frame)
        with pytest.raises(RuntimeError, match="failed"):
            host.handle(frame)


def test_checkpoint_exchange_failed_session_cannot_continue(tmp_path: Path) -> None:
    request, _ = inputs(tmp_path)
    audio = request.parent / "speech.wav"
    with OperationJournal(tmp_path / "host", binding(audio)) as journal:
        host = CheckpointHost(journal, {"speech-0": audio})
        frame = encode_frame(message(journal))
        assert decode_frame(host.handle(frame))["payload"] is None
        with pytest.raises(RuntimeError, match="sequence"):
            host.handle(frame)
        with pytest.raises(RuntimeError, match="failed"):
            host.handle(encode_frame(message(journal, sequence=2)))


@pytest.mark.parametrize("header", [0, 65537, 2**32 - 1])
def test_checkpoint_exchange_refuses_oversize_before_payload_read(header: int) -> None:
    stream = io.BytesIO(header.to_bytes(4, "big") + b"retained-unread")
    with pytest.raises(RuntimeError, match="bound"):
        read_frame(stream)
    assert stream.tell() == 4


@pytest.mark.parametrize("frame", [b"", b"\0", b"\0\0\0\x04{}"])
def test_checkpoint_exchange_refuses_closed_or_truncated_pipe(frame: bytes) -> None:
    with pytest.raises(RuntimeError, match="ended"):
        read_frame(io.BytesIO(frame))


def test_checkpoint_exchange_result_cannot_exceed_frame_bound(tmp_path: Path) -> None:
    request, _ = inputs(tmp_path)
    audio = request.parent / "speech.wav"
    with OperationJournal(tmp_path / "host", binding(audio)) as journal:
        frame = message(journal, action="save", result="x" * 65536)
        with pytest.raises(RuntimeError, match="bound"):
            encode_frame(frame)
    assert list((tmp_path / "host").glob("operation-*.json")) == []


def result_message(
    journal: OperationJournal, sequence: int, action: str, **fields: object
) -> bytes:
    return encode_frame(
        {
            "schema": 1,
            "sequence": sequence,
            "binding_sha256": journal.binding_sha256,
            "action": action,
            **fields,
        }
    )


def test_checkpoint_result_large_utf8_uses_durable_bounded_chunks(tmp_path: Path) -> None:
    request, output = inputs(tmp_path)
    transcript = run_request(
        request, output, Backend("\u06a9\u0648\u0631\u062f\u06cc " * 10_000 + ".")
    )
    content = output.read_bytes()
    assert len(content) > 65536
    audio = tmp_path / "speech.wav"
    with OperationJournal(tmp_path / "host", binding(audio)) as journal:
        host = CheckpointHost(journal, {"speech-0": audio})
        host.handle(
            result_message(journal, 1, "result-start", size=len(content), sha256=digest(content))
        )
        chunks = 0
        for index, offset in enumerate(range(0, len(content), RESULT_CHUNK)):
            chunk = content[offset : offset + RESULT_CHUNK]
            frame = result_message(
                journal,
                index + 2,
                "result-chunk",
                index=index,
                data=base64.b64encode(chunk).decode("ascii"),
                sha256=digest(chunk),
            )
            assert len(frame) <= 65536
            reply = decode_frame(host.handle(frame))
            assert reply["request_sha256"] == digest(frame)
            chunks += 1
            assert len(list((tmp_path / "host").glob("operation-*.json"))) == chunks
            assert host.transcript is None
        host.handle(result_message(journal, chunks + 2, "result-end"))
        assert host.transcript == transcript
        assert len(list((tmp_path / "host").glob("operation-*.json"))) == chunks + 1
        with pytest.raises(RuntimeError, match="failed"):
            host.handle(result_message(journal, chunks + 3, "result-end"))


@pytest.mark.parametrize(
    "damage", ["length", "hash", "order", "chunk-hash", "incomplete", "media", "changed-audio"]
)
def test_checkpoint_result_refuses_damage_without_completion(tmp_path: Path, damage: str) -> None:
    request, output = inputs(tmp_path)
    run_request(request, output, Backend())
    content = output.read_bytes()
    audio = tmp_path / "speech.wav"
    bound = binding(audio)
    if damage == "media":
        bound["media_id"] = "a-different-source"
    with OperationJournal(tmp_path / "host", bound) as journal:
        host = CheckpointHost(journal, {"speech-0": audio})
        start = result_message(
            journal,
            1,
            "result-start",
            size=16 * 1024 * 1024 + 1 if damage == "length" else len(content),
            sha256="0" * 64 if damage == "hash" else digest(content),
        )
        with pytest.raises(RuntimeError, match="checkpoint"):
            host.handle(start)
            if damage == "incomplete":
                host.handle(result_message(journal, 2, "result-end"))
            else:
                host.handle(
                    result_message(
                        journal,
                        2,
                        "result-chunk",
                        index=1 if damage == "order" else 0,
                        data=base64.b64encode(content).decode("ascii"),
                        sha256="0" * 64 if damage == "chunk-hash" else digest(content),
                    )
                )
                if damage == "changed-audio":
                    audio.write_bytes(audio.read_bytes() + b"changed-after-checkpoint")
                host.handle(result_message(journal, 3, "result-end"))
        assert host.transcript is None
        with pytest.raises(RuntimeError, match="failed"):
            host.handle(start)
    assert all(
        json.loads(path.read_bytes())["operation"]["stage"] != "transcript-result"
        for path in (tmp_path / "host").glob("operation-*.json")
    )
