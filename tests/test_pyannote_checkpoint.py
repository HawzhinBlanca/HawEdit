"""Actual checkpoint byte/OS-lock boundaries; upstream doubles are not inference."""

from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
import sys
from collections.abc import Callable
from functools import partial
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

import hawedit.models as models
from hawedit.diarization import Segment
from hawedit.diarization_acceptance import COMMUNITY_MODEL_ID, COMMUNITY_REVISION
from hawedit.ingest import DiarizationInvalidOutput, DiarizationUnavailable
from hawedit.models import ModelStore
from hawedit.pyannote_adapter import PyannoteDiarizer


def provision_checkpoint(root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Configure a real store over opaque test bytes, never the protected manifest."""
    metadata = root / "test-manifests"
    metadata.mkdir()
    checkpoint = root / "wire-only-checkpoint"
    checkpoint.mkdir()
    contents = {"config.yaml": b"test-only config", "weights.bin": b"opaque test weights"}
    for name, value in contents.items():
        (checkpoint / name).write_bytes(value)
    documents = {
        "sources.json": {COMMUNITY_MODEL_ID: COMMUNITY_MODEL_ID},
        "revisions.json": {COMMUNITY_MODEL_ID: COMMUNITY_REVISION},
        "integrity.json": {
            "schema": 1,
            "models": {
                COMMUNITY_MODEL_ID: {
                    "repository": COMMUNITY_MODEL_ID,
                    "revision": COMMUNITY_REVISION,
                    "status": "verified",
                    "files": {
                        name: {
                            "algorithm": "sha256",
                            "digest": hashlib.sha256(value).hexdigest(),
                            "size_bytes": len(value),
                        }
                        for name, value in contents.items()
                    },
                }
            },
        },
    }
    for name, document in documents.items():
        (metadata / name).write_text(json.dumps(document), encoding="utf-8")
    # Configure actual store construction; verification, hashing and locking stay real.
    monkeypatch.setattr(models, "ModelStore", partial(ModelStore, metadata_root=metadata))
    return checkpoint


def _dependency(monkeypatch: pytest.MonkeyPatch, stage: Callable[[str], None]) -> None:
    class Pipeline:
        @classmethod
        def from_pretrained(cls, selected: Path) -> Pipeline:
            stage("load")
            assert (selected / "weights.bin").read_bytes() == b"opaque test weights"
            return cls()

        def to(self, device: object) -> None:
            stage("device")
            assert str(device) == "cuda:1"

        def __call__(self, audio: str) -> object:
            stage("inference")
            assert Path(audio).read_bytes() == b"test-only audio"
            return SimpleNamespace(exclusive_speaker_diarization=Annotation())

    class Annotation:
        def itertracks(self, *, yield_label: bool) -> list[tuple[object, str, str]]:
            stage("conversion")
            assert yield_label
            return [(SimpleNamespace(start=0.0, end=1.0), "track", "SPEAKER_00")]

    dependency = ModuleType("pyannote.audio")
    dependency.Pipeline = Pipeline  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pyannote.audio", dependency)


_LOCK_PROBE = """
import os, sys
from pathlib import Path
checkpoint = Path(sys.argv[1])
with (checkpoint.parent / ('.' + checkpoint.name + '.hawedit.lock')).open('r+b') as f:
    if os.name == 'nt':
        import msvcrt
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            print('held')
        else:
            print('free')
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('held')
        else:
            print('free')
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
"""


def _lock_state(checkpoint: Path) -> str:
    return subprocess.run(
        [sys.executable, "-B", "-c", _LOCK_PROBE, str(checkpoint)],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()


def _audio(root: Path) -> Path:
    audio = root / "test-only.wav"
    audio.write_bytes(b"test-only audio")
    return audio


@pytest.mark.parametrize("model_id", ["Qwen3-ASR-1.7B", "", "other/model"])
def test_diarizer_refuses_noncanonical_model_identity(model_id: str) -> None:
    with pytest.raises(ValueError, match="Community-1 model"):
        PyannoteDiarizer(model_id=model_id)


@pytest.mark.parametrize("damage", ["missing", "same-size", "extra", "blocked", "revision"])
def test_diarizer_rejects_unverified_explicit_checkpoint_before_loading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, damage: str
) -> None:
    checkpoint = provision_checkpoint(tmp_path, monkeypatch)
    if damage == "missing":
        (checkpoint / "weights.bin").unlink()
    elif damage == "same-size":
        (checkpoint / "weights.bin").write_bytes(b"X" * len(b"opaque test weights"))
    elif damage == "extra":
        (checkpoint / "injected.py").write_text("raise RuntimeError", encoding="utf-8")
    else:
        path = tmp_path / "test-manifests" / "integrity.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        entry = document["models"][COMMUNITY_MODEL_ID]
        if damage == "blocked":
            entry.update(status="blocked", reason="test-only missing evidence")
        else:
            entry["revision"] = "a" * 40
        path.write_text(json.dumps(document), encoding="utf-8")
    calls: list[str] = []
    _dependency(monkeypatch, calls.append)
    original = importlib.import_module

    def observed_import(name: str, package: str | None = None) -> ModuleType:
        if name == "pyannote.audio":
            calls.append("import")
        return original(name, package)

    monkeypatch.setattr(importlib, "import_module", observed_import)
    with pytest.raises(DiarizationUnavailable, match=r"BLOCKED\.md #4"):
        PyannoteDiarizer(model_dir=checkpoint).diarize(_audio(tmp_path))
    assert calls == []


def test_diarizer_refusal_survives_model_module_reload(tmp_path: Path) -> None:
    audio = _audio(tmp_path)
    probe = """
import importlib, sys
from pathlib import Path
import hawedit.models as models
from hawedit.ingest import DiarizationUnavailable
from hawedit.pyannote_adapter import PyannoteDiarizer
original = models.CheckpointIntegrityError
importlib.reload(models)
assert models.CheckpointIntegrityError is not original
try:
    PyannoteDiarizer(model_dir=Path(sys.argv[2])).diarize(Path(sys.argv[1]))
except DiarizationUnavailable as exc:
    assert 'BLOCKED.md #4' in str(exc)
else:
    raise AssertionError('Missing checkpoint was not refused')
assert 'pyannote.audio' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", probe, str(audio), str(tmp_path / "missing-checkpoint")],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("explicit", [True, False])
def test_diarizer_holds_real_checkpoint_lock_through_all_consumer_stages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, explicit: bool
) -> None:
    checkpoint = provision_checkpoint(tmp_path, monkeypatch)
    if not explicit:
        canonical = tmp_path / COMMUNITY_MODEL_ID.replace("/", "__")
        checkpoint.rename(canonical)
        checkpoint = canonical
        monkeypatch.setattr(models, "DEFAULT_MODELS_ROOT", tmp_path)
    stages: list[str] = []

    def held(stage: str) -> None:
        stages.append(stage)
        assert _lock_state(checkpoint) == "held", stage

    _dependency(monkeypatch, held)
    original = importlib.import_module

    def observed_import(name: str, package: str | None = None) -> ModuleType:
        if name == "pyannote.audio":
            held("import")
        return original(name, package)

    monkeypatch.setattr(importlib, "import_module", observed_import)
    selected = checkpoint if explicit else None
    assert PyannoteDiarizer(model_dir=selected, device="cuda:1").diarize(_audio(tmp_path)) == (
        Segment(0, 1000, "SPEAKER_00"),
    )
    assert stages == ["import", "load", "device", "inference", "conversion"]
    assert _lock_state(checkpoint) == "free"


@pytest.mark.parametrize("failure_stage", ["load", "device", "inference", "conversion"])
def test_diarizer_releases_checkpoint_lock_after_consumer_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_stage: str
) -> None:
    checkpoint = provision_checkpoint(tmp_path, monkeypatch)

    def fail(stage: str) -> None:
        assert _lock_state(checkpoint) == "held"
        if stage == failure_stage:
            raise DiarizationInvalidOutput("test-only consumer failure")

    _dependency(monkeypatch, fail)
    with pytest.raises(DiarizationUnavailable, match="test-only consumer failure"):
        PyannoteDiarizer(model_dir=checkpoint, device="cuda:1").diarize(_audio(tmp_path))
    assert _lock_state(checkpoint) == "free"


def test_diarizer_reverifies_checkpoint_on_every_invocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkpoint = provision_checkpoint(tmp_path, monkeypatch)
    calls: list[str] = []
    _dependency(monkeypatch, calls.append)
    adapter = PyannoteDiarizer(model_dir=checkpoint)
    audio = _audio(tmp_path)
    assert adapter.diarize(audio) == (Segment(0, 1000, "SPEAKER_00"),)
    calls.clear()
    (checkpoint / "weights.bin").write_bytes(b"X" * len(b"opaque test weights"))
    with pytest.raises(DiarizationUnavailable, match=r"BLOCKED\.md #4"):
        adapter.diarize(audio)
    assert calls == []
