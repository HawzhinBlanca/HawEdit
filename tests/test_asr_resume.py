"""Real storage recovery tests; controlled responses are not ASR quality evidence."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import wave
from pathlib import Path

import pytest

from hawedit.asr import SegmentTranscript
from hawedit.asr_resume import OperationJournal, ResumableBackend, ResumableValidator
from hawedit.studio_private import PrivateDirectory, StudioStorageError
from hawedit.transcripts import Word


class Backend:
    adapter_name = None

    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[str] = []
        self.fail = fail

    def transcribe_segment(self, path: Path, duration_s: float) -> SegmentTranscript:
        self.calls.append("draft")
        if self.fail:
            raise RuntimeError("declared failure")
        return SegmentTranscript("original", "original", (Word("original", 0, 500, 0.8),), -0.5)

    def align_segment(self, path: Path, duration_s: float, text: str) -> SegmentTranscript:
        self.calls.append("alignment")
        return SegmentTranscript(text, text, (Word(text, 0, 500, 0.7),), -0.6)


class Validator:
    model_id = "controlled-validator"

    def __init__(self) -> None:
        self.calls = 0

    def transcribe_segment(self, path: Path, duration_s: float) -> str:
        self.calls += 1
        return "correction"


def audio(root: Path) -> Path:
    path = root / "speech.wav"
    with wave.open(str(path), "wb") as stream:
        stream.setparams((1, 2, 16_000, 0, "NONE", "not compressed"))
        stream.writeframes(b"\x01\x00" * 16_000)
    return path


def private(root: Path) -> Path:
    return PrivateDirectory(root / "journal").path


@pytest.mark.parametrize("previous", [None, "qwen-text-only-old-policy"])
def test_qwen_policy_refuses_legacy_operation_journal(tmp_path: Path, previous: str | None) -> None:
    from hawedit.asr_completion import COMPLETION_POLICY_ID
    from hawedit.qwen_completion import QWEN_COMPLETION_POLICY_ID

    path, root = audio(tmp_path), private(tmp_path)
    old: dict[str, object] = {"completion_policy": COMPLETION_POLICY_ID}
    if previous is not None:
        old["validator_completion_policy"] = previous
    validator = Validator()
    with OperationJournal(root, old) as journal:
        assert ResumableValidator(validator, journal).transcribe_segment(path, 1.0) == "correction"
    before = {file.name: file.read_bytes() for file in root.glob("*.json")}
    current = {**old, "validator_completion_policy": QWEN_COMPLETION_POLICY_ID}
    with pytest.raises(RuntimeError, match="binding"), OperationJournal(root, current):
        pytest.fail("old validator text must not reach a resumed operation")
    assert {file.name: file.read_bytes() for file in root.glob("*.json")} == before
    assert validator.calls == 1


def test_checkpoint_survives_restart(tmp_path: Path) -> None:
    path, root = audio(tmp_path), private(tmp_path)
    first = Backend()
    with OperationJournal(root, {"input": "frozen"}) as journal:
        expected = ResumableBackend(first, journal).transcribe_segment(path, 1.0)
    second = Backend(fail=True)
    with OperationJournal(root, {"input": "frozen"}) as journal:
        assert ResumableBackend(second, journal).transcribe_segment(path, 1.0) == expected
    assert first.calls == ["draft"]
    assert second.calls == []


def test_checkpoint_resolves_operation_path_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, root = audio(tmp_path), private(tmp_path)
    bound_path = str(path.resolve())
    binding = {
        "audio": [
            {
                "path": bound_path,
                "start_ms": 0,
                "end_ms": 1000,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        ]
    }
    binding["audio"].extend(
        {"path": f"unused-{index}", "start_ms": 0, "end_ms": 1000, "sha256": "0" * 64}
        for index in range(157)
    )
    original = Path.resolve
    calls = 0

    def counted(self: Path, strict: bool = False) -> Path:
        nonlocal calls
        if self == path:
            calls += 1
        return original(self, strict=strict)

    with OperationJournal(root, binding) as journal:
        monkeypatch.setattr(Path, "resolve", counted)
        operation = journal.operation("draft", path, 1.0)
    assert operation["path"] == bound_path
    assert calls == 1


def test_checkpoint_failure_is_not_cached(tmp_path: Path) -> None:
    path, root = audio(tmp_path), private(tmp_path)
    with (
        OperationJournal(root, {"input": "frozen"}) as journal,
        pytest.raises(RuntimeError, match="declared failure"),
    ):
        ResumableBackend(Backend(fail=True), journal).transcribe_segment(path, 1.0)
    second = Backend()
    with OperationJournal(root, {"input": "frozen"}) as journal:
        ResumableBackend(second, journal).transcribe_segment(path, 1.0)
    assert second.calls == ["draft"]
    assert not (root / "output.json").exists()
    assert not (root / "stage1.done").exists()


def test_checkpoint_storage_failure_halts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import hawedit.asr_resume as resume

    path, root = audio(tmp_path), private(tmp_path)
    with OperationJournal(root, {"input": "frozen"}) as journal:

        def fail(path: Path, text: str) -> None:
            raise OSError("declared disk failure")

        monkeypatch.setattr(resume, "write_text_atomic", fail)
        with pytest.raises(OSError, match="declared disk failure"):
            ResumableBackend(Backend(), journal).transcribe_segment(path, 1.0)
    assert list(root.glob("operation-*.json")) == []


def test_checkpoint_refuses_changed_binding(tmp_path: Path) -> None:
    root = private(tmp_path)
    with OperationJournal(root, {"input": "frozen"}):
        pass
    before = (root / "binding.json").read_bytes()
    with pytest.raises(RuntimeError, match="binding"), OperationJournal(root, {"input": "changed"}):
        pass
    assert (root / "binding.json").read_bytes() == before


@pytest.mark.parametrize("damage", ["malformed", "null", "hash", "schema", "schema-bool", "words"])
def test_checkpoint_refuses_damaged_record(tmp_path: Path, damage: str) -> None:
    path, root = audio(tmp_path), private(tmp_path)
    with OperationJournal(root, {"input": "frozen"}) as journal:
        ResumableBackend(Backend(), journal).transcribe_segment(path, 1.0)
    record_path = next(root.glob("operation-*.json"))
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if damage == "malformed":
        record_path.write_text("{", encoding="utf-8")
    elif damage == "null":
        record_path.write_text("null", encoding="utf-8")
    else:
        if damage == "hash":
            record["result_sha256"] = "0" * 64
        elif damage == "schema":
            record["schema"] = 999
        elif damage == "schema-bool":
            record["schema"] = True
        else:
            record["result"]["words"] = []
        record_path.write_text(json.dumps(record), encoding="utf-8")
    broken = record_path.read_bytes()
    second = Backend()
    with (
        OperationJournal(root, {"input": "frozen"}) as journal,
        pytest.raises(RuntimeError, match="checkpoint"),
    ):
        ResumableBackend(second, journal).transcribe_segment(path, 1.0)
    assert second.calls == []
    assert record_path.read_bytes() == broken


def test_checkpoint_keeps_draft_validator_and_alignment_separate(tmp_path: Path) -> None:
    path, root = audio(tmp_path), private(tmp_path)
    backend, validator = Backend(), Validator()
    with OperationJournal(root, {"input": "frozen"}) as journal:
        wrapped = ResumableBackend(backend, journal)
        assert wrapped.transcribe_segment(path, 1.0).text_raw == "original"
        correction = ResumableValidator(validator, journal).transcribe_segment(path, 1.0)
        assert wrapped.align_segment(path, 1.0, correction).text_raw == "correction"
        assert wrapped.align_segment(path, 1.0, "different").text_raw == "different"
        assert wrapped.transcribe_segment(path, 1.0).text_raw == "original"
    assert backend.calls == ["draft", "alignment", "alignment"]
    assert validator.calls == 1
    assert len(list(root.glob("operation-*.json"))) == 4


def test_checkpoint_refuses_linked_storage(tmp_path: Path) -> None:
    path, root = audio(tmp_path), private(tmp_path)
    with OperationJournal(root, {"input": "frozen"}) as journal:
        ResumableBackend(Backend(), journal).transcribe_segment(path, 1.0)
    record_path = next(root.glob("operation-*.json"))
    (tmp_path / "linked.json").hardlink_to(record_path)
    with (
        OperationJournal(root, {"input": "frozen"}) as journal,
        pytest.raises(StudioStorageError, match="linked"),
    ):
        ResumableBackend(Backend(), journal).transcribe_segment(path, 1.0)


def test_checkpoint_refuses_concurrent_writer(tmp_path: Path) -> None:
    root = private(tmp_path)
    with (
        OperationJournal(root, {"input": "frozen"}),
        pytest.raises(RuntimeError, match="already owned"),
        OperationJournal(root, {"input": "frozen"}),
    ):
        pass


def test_checkpoint_changed_audio_cannot_reuse_prior_result(tmp_path: Path) -> None:
    path, root = audio(tmp_path), private(tmp_path)
    backend = Backend()
    with OperationJournal(root, {"input": "frozen"}) as journal:
        wrapped = ResumableBackend(backend, journal)
        wrapped.transcribe_segment(path, 1.0)
        content = bytearray(path.read_bytes())
        content[-1] ^= 1
        path.write_bytes(content)
        wrapped.transcribe_segment(path, 1.0)
    assert backend.calls == ["draft", "draft"]


def test_checkpoint_survives_abrupt_process_exit(tmp_path: Path) -> None:
    path, root = audio(tmp_path), private(tmp_path)
    code = """
import os, sys
from pathlib import Path
from hawedit.asr_resume import OperationJournal
root, path = map(Path, sys.argv[1:])
with OperationJournal(root, {'input': 'frozen'}) as journal:
    operation = journal.operation('draft', path, 1.0)
    journal.save(operation, {'text_raw': 'original', 'ctc_text': 'original',
        'mean_logprob': -0.5, 'words': [{'w': 'original', 'start_ms': 0,
        'end_ms': 500, 'conf': 0.8}]})
    os._exit(17)
"""
    process = subprocess.run(
        [sys.executable, "-B", "-c", code, str(root), str(path)], timeout=30, check=False
    )
    assert process.returncode == 17
    backend = Backend(fail=True)
    with OperationJournal(root, {"input": "frozen"}) as journal:
        assert (
            ResumableBackend(backend, journal).transcribe_segment(path, 1.0).text_raw == "original"
        )
    assert backend.calls == []


def test_checkpoint_input_mutation_during_inference_halts(tmp_path: Path) -> None:
    path, root = audio(tmp_path), private(tmp_path)

    class MutatingBackend(Backend):
        def transcribe_segment(self, path: Path, duration_s: float) -> SegmentTranscript:
            result = super().transcribe_segment(path, duration_s)
            data = bytearray(path.read_bytes())
            data[-1] ^= 1
            path.write_bytes(data)
            return result

    with (
        OperationJournal(root, {"input": "frozen"}) as journal,
        pytest.raises(RuntimeError, match="audio changed"),
    ):
        ResumableBackend(MutatingBackend(), journal).transcribe_segment(path, 1.0)
    assert list(root.glob("operation-*.json")) == []


def test_checkpoint_refuses_changed_bound_pcm(tmp_path: Path) -> None:
    path, root = audio(tmp_path), private(tmp_path)
    binding = {
        "audio": [
            {
                "path": str(path.resolve()),
                "start_ms": 0,
                "end_ms": 1000,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        ]
    }
    backend = Backend()
    with OperationJournal(root, binding) as journal:
        wrapped = ResumableBackend(backend, journal)
        wrapped.transcribe_segment(path, 1.0)
        content = bytearray(path.read_bytes())
        content[-1] ^= 1
        path.write_bytes(content)
        with pytest.raises(RuntimeError, match="bound audio changed"):
            wrapped.transcribe_segment(path, 1.0)
    assert backend.calls == ["draft"]


def test_checkpoint_binding_mutation_during_inference_halts(tmp_path: Path) -> None:
    path, root = audio(tmp_path), private(tmp_path)

    class MutatingBackend(Backend):
        def transcribe_segment(self, path: Path, duration_s: float) -> SegmentTranscript:
            result = super().transcribe_segment(path, duration_s)
            (root / "binding.json").write_text('{"schema":1,"inputs":{}}', encoding="utf-8")
            return result

    with (
        OperationJournal(root, {"input": "frozen"}) as journal,
        pytest.raises(RuntimeError, match="binding changed"),
    ):
        ResumableBackend(MutatingBackend(), journal).transcribe_segment(path, 1.0)
    assert list(root.glob("operation-*.json")) == []


@pytest.mark.parametrize("failed_index", [0, 1, 2])
def test_worker_checkpoint_resumes_validation_without_redrafting(
    tmp_path: Path, failed_index: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hawedit.asr_worker as worker
    import test_asr_stop as fixtures

    # Controlled binding isolates composition; actual production model verification
    # remains mandatory and requires the source-bound real-media run.
    root = private(tmp_path)

    def controlled_binding(*args: object) -> OperationJournal:
        return OperationJournal(root, {"scope": "controlled-component-only"})

    monkeypatch.setattr(worker, "worker_journal", controlled_binding)
    request = fixtures.worker_request(tmp_path)
    output = tmp_path / "output.json"
    first_backend = fixtures.RegionBackend()
    first_validator = fixtures.RegionValidator(fail_at=failed_index)
    with pytest.raises(RuntimeError, match="declared correction transcription failure"):
        worker.run_request(request, output, first_backend, first_validator, checkpoint_root=root)
    assert len(first_backend.calls) == 3
    assert len(first_validator.calls) == failed_index + 1
    assert not output.exists()
    second_backend = fixtures.RegionBackend(fail_draft=0)
    second_validator = fixtures.RegionValidator()
    result = worker.run_request(
        request, output, second_backend, second_validator, checkpoint_root=root
    )
    assert second_backend.calls == []
    assert len(second_validator.calls) == 3 - failed_index
    assert len(second_backend.align_calls) == 3 - failed_index
    assert result.unaligned == ()
    assert result.rejected_validator_corrections == ()
    assert output.is_file()
