"""Decoded Stage0 evidence and recovery; not canonical ASR/editorial acceptance."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import wave
from pathlib import Path
from typing import Any

import pytest

from hawedit.captions import ffprobe_for, find_ffmpeg
from hawedit.diarization import Segment
from hawedit.events import RunEvent, RunState
from hawedit.ingest import IngestResult, extract_audio
from hawedit.ingest_cache import IngestCacheError, _open
from hawedit.pipeline import StageSkipped, run_pipeline

MEDIA = Path(__file__).resolve().parent / "fixtures/kurdish-speech-3cuts.mp4"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def records(work: Path) -> list[Path]:
    root = work / "stage0-recovery"
    return sorted(root.glob("recovery-*")) if root.is_dir() else []


def known_files(work: Path) -> dict[str, Path]:
    return {
        "audio.wav": work / "stage0/audio.wav",
        "proxy.mp4": work / "stage0/proxy.mp4",
        "ingest.json": work / "stage0/ingest.json",
        "stage0_ingest.done": work / "stage0_ingest.done",
        "audio.wav.provenance.json": work / "stage0/audio.wav.provenance.json",
        "proxy.mp4.provenance.json": work / "stage0/proxy.mp4.provenance.json",
    }


def initial(work: Path, ffmpeg: Path | None = None) -> IngestResult:
    result = run_pipeline(MEDIA, work, ffmpeg=ffmpeg)
    assert isinstance(result.ingest, IngestResult)
    assert not result.complete
    return result.ingest


def test_ingest_checkpoint_binds_actual_output_bytes(tmp_path: Path) -> None:
    work = tmp_path / "work"
    measured = initial(work)
    checkpoint = json.loads((work / "stage0_ingest.done").read_text(encoding="utf-8"))
    metadata = checkpoint["metadata"]
    assert metadata["cache_schema"] == 2
    assert metadata["outputs"] == {
        name: digest(path)
        for name, path in known_files(work).items()
        if name != "stage0_ingest.done"
    }
    binding = metadata["binding"]
    assert binding["source_sha256"] == measured.source_sha256 == digest(MEDIA)
    assert binding["media_id"] == measured.media_id
    assert len(binding["producer_source_sha256"]) == 64
    assert len(binding["vad_model_sha256"]) == 64
    assert set(binding["tools"]) == {"ffmpeg", "ffprobe"}
    for tool in binding["tools"].values():
        assert tool["sha256"] == digest(Path(tool["path"]))


def test_unchanged_ingest_cache_reuses_exact_files(tmp_path: Path) -> None:
    work = tmp_path / "work"
    first = initial(work)
    stamps = {
        name: (digest(path), path.stat().st_mtime_ns) for name, path in known_files(work).items()
    }
    events: list[RunEvent] = []
    second = run_pipeline(MEDIA, work, on_event=events.append)
    assert second.ingest == first
    assert stamps == {
        name: (digest(path), path.stat().st_mtime_ns) for name, path in known_files(work).items()
    }
    assert any(
        event.stage == "ingest"
        and event.state is RunState.SKIPPED
        and event.reason == "resumed from checkpoint"
        for event in events
    )
    assert records(work) == []


@pytest.mark.parametrize("name", ["audio.wav", "proxy.mp4"])
def test_decodable_changed_ingest_media_is_preserved_and_regenerated(
    tmp_path: Path, name: str
) -> None:
    work = tmp_path / "work"
    original_source = digest(MEDIA)
    first = initial(work)
    paths = known_files(work)
    expected = digest(paths[name])
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    output = tmp_path / name
    transform = (
        ["-af", "volume=0", "-c:a", "pcm_s16le"]
        if name == "audio.wav"
        else ["-vf", "negate", "-an", "-c:v", "libx264"]
    )
    subprocess.run(
        [
            str(ffmpeg),
            "-hide_banner",
            "-nostdin",
            "-threads",
            "1",
            "-i",
            str(paths[name]),
            *transform,
            "-threads",
            "1",
            str(output),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    changed = digest(output)
    assert changed != expected
    if name == "audio.wav":
        with wave.open(str(output), "rb") as reader:
            assert not any(reader.readframes(reader.getnframes()))
    output.replace(paths[name])
    prior = {key: digest(path) for key, path in paths.items()}
    events: list[RunEvent] = []
    second = run_pipeline(MEDIA, work, on_event=events.append)
    assert isinstance(second.ingest, IngestResult)
    assert second.ingest == first
    assert digest(paths[name]) == expected
    retained = records(work)
    assert len(retained) == 1
    assert {key: digest(retained[0] / key) for key in prior} == prior
    manifest = json.loads((retained[0] / "recovery.json").read_text(encoding="utf-8"))
    assert manifest["files"] == prior
    assert manifest["reason"]
    assert any(
        event.stage == "ingest_cache_reuse" and event.state is RunState.SKIPPED for event in events
    )
    assert digest(MEDIA) == original_source


def test_changed_ingest_measurement_is_not_reused(tmp_path: Path) -> None:
    work = tmp_path / "work"
    measured = initial(work)
    path = work / "stage0/ingest.json"
    record: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    record["duration_ms"] += 5000
    damaged = json.dumps(record).encode()
    path.write_bytes(damaged)
    second = run_pipeline(MEDIA, work)
    assert isinstance(second.ingest, IngestResult)
    assert second.ingest.duration_ms == measured.duration_ms
    assert (records(work)[0] / "ingest.json").read_bytes() == damaged


def test_unverified_legacy_ingest_checkpoint_is_preserved(tmp_path: Path) -> None:
    work = tmp_path / "work"
    measured = initial(work)
    marker = work / "stage0_ingest.done"
    legacy = json.loads(marker.read_text(encoding="utf-8"))
    legacy["metadata"] = {"audio_path": measured.audio_path}
    raw = json.dumps(legacy).encode()
    marker.write_bytes(raw)
    events: list[RunEvent] = []
    second = run_pipeline(MEDIA, work, on_event=events.append)
    assert isinstance(second.ingest, IngestResult)
    assert (records(work)[0] / "stage0_ingest.done").read_bytes() == raw
    assert any("legacy" in event.reason.lower() for event in events)
    assert json.loads(marker.read_text(encoding="utf-8"))["metadata"]["cache_schema"] == 2


def test_actual_ffmpeg_byte_drift_invalidates_ingest_cache(tmp_path: Path) -> None:
    selected = find_ffmpeg()
    assert selected is not None
    binary = tmp_path / selected.name
    probe = ffprobe_for(binary)
    installed_hash = digest(selected)
    shutil.copy2(selected, binary)
    shutil.copy2(ffprobe_for(selected), probe)
    replacement = tmp_path / "changed-ffmpeg.exe"
    shutil.copy2(selected, replacement)
    with replacement.open("ab") as handle:
        handle.write(b"HawEdit diagnostic overlay; no installed executable modified")
    work = tmp_path / "work"
    first = initial(work, binary)
    before_stamps = {
        name: known_files(work)[name].stat().st_mtime_ns for name in ("audio.wav", "proxy.mp4")
    }
    replacement.replace(binary)
    events: list[RunEvent] = []
    second = run_pipeline(MEDIA, work, ffmpeg=binary, on_event=events.append)
    assert isinstance(second.ingest, IngestResult)
    assert second.ingest == first
    assert len(records(work)) == 1
    assert all(
        known_files(work)[name].stat().st_mtime_ns != stamp for name, stamp in before_stamps.items()
    )
    assert any("configuration" in event.reason for event in events)
    checkpoint = json.loads((work / "stage0_ingest.done").read_text(encoding="utf-8"))
    assert checkpoint["metadata"]["binding"]["tools"]["ffmpeg"]["sha256"] == digest(binary)
    assert digest(selected) == installed_hash


def test_ingest_recovery_storage_failure_preserves_originals(tmp_path: Path) -> None:
    work = tmp_path / "work"
    initial(work)
    audio = work / "stage0/audio.wav"
    with audio.open("ab") as handle:
        handle.write(b"changed cache")
    before = {name: path.read_bytes() for name, path in known_files(work).items()}
    (work / "stage0-recovery").write_bytes(b"owner collision")
    second = run_pipeline(MEDIA, work)
    assert isinstance(second.ingest, StageSkipped)
    assert "preserv" in second.ingest.reason.lower()
    assert not second.complete
    assert before == {name: path.read_bytes() for name, path in known_files(work).items()}
    assert (work / "stage0-recovery").read_bytes() == b"owner collision"


def test_hardlinked_ingest_cache_is_refused_without_rewriting(tmp_path: Path) -> None:
    work = tmp_path / "work"
    initial(work)
    audio = work / "stage0/audio.wav"
    alias = tmp_path / "owner-audio.wav"
    os.link(audio, alias)
    before = {name: path.read_bytes() for name, path in known_files(work).items()}
    second = run_pipeline(MEDIA, work)
    assert isinstance(second.ingest, StageSkipped)
    assert not second.complete
    assert before == {name: path.read_bytes() for name, path in known_files(work).items()}
    assert alias.read_bytes() == before["audio.wav"]


def test_malformed_ingest_metadata_is_preserved_before_regeneration(tmp_path: Path) -> None:
    work = tmp_path / "work"
    first = initial(work)
    damaged = b"{invalid JSON truncated"
    (work / "stage0/ingest.json").write_bytes(damaged)
    second = run_pipeline(MEDIA, work)
    assert isinstance(second.ingest, IngestResult)
    assert second.ingest == first
    assert (records(work)[0] / "ingest.json").read_bytes() == damaged


def test_held_ingest_reader_verifies_real_bytes(tmp_path: Path) -> None:
    path = tmp_path / "owned"
    path.write_bytes(b"bound observed bytes")
    with _open(path) as opened:
        assert opened.digest() == digest(path)
        assert opened.read(128) == b"bound observed bytes"
        opened.check()


def test_held_ingest_reader_refuses_changed_bytes(tmp_path: Path) -> None:
    path = tmp_path / "owned"
    path.write_bytes(b"bound observed bytes")
    with pytest.raises(IngestCacheError), _open(path) as opened:
        path.write_bytes(b"different bytes and size")
        opened.check()


def test_held_ingest_reader_refuses_new_hardlink(tmp_path: Path) -> None:
    path = tmp_path / "owned"
    path.write_bytes(b"bound observed bytes")
    with pytest.raises(IngestCacheError), _open(path) as opened:
        os.link(path, tmp_path / "owner-alias")
        opened.check()


def test_diarization_does_not_mutate_or_leak_through_base_ingest_cache(tmp_path: Path) -> None:
    class DispatchProbe:
        def __init__(self, speaker: str) -> None:
            self.speaker = speaker
            self.calls = 0

        def diarize(self, audio: Path) -> tuple[Segment, ...]:
            assert audio.name == "audio.wav"
            self.calls += 1
            return (Segment(0, 1000, self.speaker),)

    work = tmp_path / "work"
    first_producer = DispatchProbe("producer-one")
    first = run_pipeline(MEDIA, work, diarizer=first_producer)
    assert isinstance(first.ingest, IngestResult)
    assert first.ingest.diarization == (Segment(0, 1000, "producer-one"),)
    assert first_producer.calls == 1
    before = {name: digest(path) for name, path in known_files(work).items()}
    base = json.loads((work / "stage0/ingest.json").read_text(encoding="utf-8"))
    assert base["diarization"] is None
    repeated = run_pipeline(MEDIA, work, diarizer=first_producer)
    assert isinstance(repeated.ingest, IngestResult)
    assert repeated.ingest.diarization == first.ingest.diarization
    assert first_producer.calls == 2
    second_producer = DispatchProbe("producer-two")
    second = run_pipeline(MEDIA, work, diarizer=second_producer)
    assert isinstance(second.ingest, IngestResult)
    assert second.ingest.diarization == (Segment(0, 1000, "producer-two"),)
    assert second_producer.calls == 1
    without = run_pipeline(MEDIA, work)
    assert isinstance(without.ingest, IngestResult)
    assert without.ingest.diarization is None
    assert before == {name: digest(path) for name, path in known_files(work).items()}
    assert records(work) == []


def test_same_length_changed_extracted_audio_is_regenerated(tmp_path: Path) -> None:
    dest = tmp_path / "audio.wav"
    expected = extract_audio(MEDIA, dest).read_bytes()
    with wave.open(str(dest), "rb") as handle:
        frame_bytes = handle.getnframes() * handle.getnchannels() * handle.getsampwidth()
    changed = expected[:-frame_bytes] + bytes(frame_bytes)
    assert len(changed) == len(expected)
    assert changed != expected
    dest.write_bytes(changed)
    with wave.open(str(dest), "rb") as handle:
        assert not any(handle.readframes(handle.getnframes()))
    assert extract_audio(MEDIA, dest).read_bytes() == expected
    provenance = json.loads(dest.with_suffix(".wav.provenance.json").read_text(encoding="utf-8"))
    assert provenance["output_sha256"] == digest(dest)


def test_size_only_extraction_provenance_is_not_reused(tmp_path: Path) -> None:
    dest = tmp_path / "audio.wav"
    expected = extract_audio(MEDIA, dest).read_bytes()
    sidecar = dest.with_suffix(".wav.provenance.json")
    legacy = json.loads(sidecar.read_text(encoding="utf-8"))
    legacy.pop("output_sha256", None)
    legacy["schema"] = 1
    sidecar.write_text(json.dumps(legacy), encoding="utf-8")
    before = dest.stat().st_mtime_ns
    assert extract_audio(MEDIA, dest).read_bytes() == expected
    assert dest.stat().st_mtime_ns != before
    assert json.loads(sidecar.read_text(encoding="utf-8"))["output_sha256"] == digest(dest)
