"""Genuine legacy reader/sink/timeline tests, not paid-call or producer evidence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hawedit.agent import run_timeline
from hawedit.events import JsonlEventSink, RunEvent, RunEventLog, RunState, read_events


def first_record() -> bytes:
    event = RunEvent("owned-test", 1, 1000, "editorial", RunState.STARTED)
    return (json.dumps(event.to_dict()) + "\n").encode("utf-8")


@pytest.mark.parametrize("damage", [b'{"sequence":\n', b"not-json\n", b"[]\n", b'{"sequence":2}\n'])
def test_event_replay_refuses_corrupt_complete_or_middle_record(
    tmp_path: Path, damage: bytes
) -> None:
    path = tmp_path / "events.jsonl"
    billed = RunEvent(
        "owned-test", 2, 1001, "editorial", RunState.BILLED, model="no-call", tokens=7
    )
    payload = first_record() + damage + (json.dumps(billed.to_dict()) + "\n").encode()
    path.write_bytes(payload)
    try:
        with pytest.raises(ValueError, match="line 2.*preserve"):
            read_events(path)
    finally:
        assert path.read_bytes() == payload


@pytest.mark.parametrize(
    "damage", [b'{"sequence":2}', b"[]", b"null", b"not-json", b'{"run_id": bad']
)
def test_event_replay_refuses_complete_invalid_final_record(tmp_path: Path, damage: bytes) -> None:
    path = tmp_path / "events.jsonl"
    payload = first_record() + damage
    path.write_bytes(payload)
    try:
        with pytest.raises(ValueError, match="line 2.*preserve"):
            read_events(path)
    finally:
        assert path.read_bytes() == payload


@pytest.mark.parametrize(
    "partial", [b"{", b'{"run_id":', b'{"run_id":"owned', b'{"run_id":"owned",']
)
def test_event_replay_tolerates_incomplete_unterminated_final_record(
    tmp_path: Path, partial: bytes
) -> None:
    path = tmp_path / "events.jsonl"
    payload = first_record() + partial
    path.write_bytes(payload)
    assert [event.sequence for event in read_events(path)] == [1]
    assert path.read_bytes() == payload


def test_event_replay_accepts_complete_final_record_without_newline(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    payload = first_record().rstrip(b"\n")
    path.write_bytes(payload)
    assert [event.sequence for event in read_events(path)] == [1]
    assert path.read_bytes() == payload


def test_event_replay_preserves_actual_live_sink_and_billed_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    sink = JsonlEventSink(path)
    log = RunEventLog("owned-test", sink)
    try:
        start = log.started("editorial")
        billed = log.billed(
            "editorial", "no-call", 7, 0.001, "\u0647\u06d5\u0648\u0644\u06ce\u0631"
        )
        original = path.read_bytes()
        assert read_events(path) == (start, billed)
        assert path.read_bytes() == original
    finally:
        sink.close()


def test_event_replay_accepts_valid_crlf_records(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    payload = first_record().replace(b"\n", b"\r\n")
    path.write_bytes(payload)
    assert [event.sequence for event in read_events(path)] == [1]
    assert path.read_bytes() == payload


def test_event_replay_timeline_refuses_middle_corruption(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    payload = first_record() + b'{"sequence":\n' + first_record()
    path.write_bytes(payload)
    try:
        with pytest.raises(ValueError, match="line 2.*preserve"):
            run_timeline(tmp_path)
    finally:
        assert path.read_bytes() == payload


def test_event_replay_missing_file_behavior_is_preserved(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_events(tmp_path / "events.jsonl")
    assert run_timeline(tmp_path).available is False


def test_event_replay_refuses_invalid_utf8_without_repairing_bytes(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    payload = first_record() + b"\xff\n"
    path.write_bytes(payload)
    try:
        with pytest.raises(ValueError, match="UTF-8.*preserve"):
            read_events(path)
    finally:
        assert path.read_bytes() == payload
