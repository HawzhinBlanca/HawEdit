"""Worker result-file contracts with real files, generated PCM and explicit model doubles."""

from __future__ import annotations

import json
import subprocess
import sys
import time
import wave
from pathlib import Path

import pytest

from hawedit.asr import SegmentTranscript
from hawedit.asr_worker import run_request
from hawedit.transcripts import RawTranscript, Word


class Backend:
    def __init__(self, text: str = "speech.") -> None:
        self.text = text
        self.calls = 0

    def transcribe_segment(self, audio_path: Path, duration_s: float) -> SegmentTranscript:
        self.calls += 1
        assert audio_path.is_file() and duration_s == 1.0
        return SegmentTranscript(self.text, self.text, (Word(self.text, 50, 500, 0.9),), -0.1)

    def align_segment(self, audio_path: Path, duration_s: float, text: str) -> SegmentTranscript:
        raise AssertionError("Agreeing synthetic transcript must not realign")


def inputs(root: Path) -> tuple[Path, Path]:
    audio = root / "speech.wav"
    with wave.open(str(audio), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16_000)
        stream.writeframes(b"\0\0" * 16_000)
    request = root / "request.json"
    request.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "media_id": "publication-contract",
                "validator_model_dir": "unused-in-agreeing-control",
                "segments": [{"path": audio.name, "start_ms": 0, "end_ms": 1_000}],
            }
        ),
        encoding="utf-8",
    )
    return request, root / "output.json"


def test_worker_encoding_failure_does_not_publish_empty_output(tmp_path: Path) -> None:
    request, output = inputs(tmp_path)
    with pytest.raises(UnicodeEncodeError):
        run_request(request, output, Backend("\ud800."))
    assert not output.exists(), "An encoding refusal must not reserve a corrupt final filename"


def test_worker_existing_output_refuses_before_backend(tmp_path: Path) -> None:
    request, output = inputs(tmp_path)
    original = b"retained-evidence-never-overwrite\n"
    output.write_bytes(original)
    backend = Backend()
    with pytest.raises(FileExistsError):
        run_request(request, output, backend)
    assert output.read_bytes() == original
    assert backend.calls == 0, "An occupied result name must refuse before model work"


def test_worker_existing_output_directory_refuses_before_backend(tmp_path: Path) -> None:
    request, output = inputs(tmp_path)
    output.mkdir()
    retained = output / "retained.txt"
    retained.write_bytes(b"retained\n")
    backend = Backend()
    with pytest.raises(OSError):
        run_request(request, output, backend)
    assert retained.read_bytes() == b"retained\n" and output.is_dir()
    assert backend.calls == 0


def test_worker_result_preserves_exact_utf8_and_newline(tmp_path: Path) -> None:
    request, output = inputs(tmp_path)
    transcript = run_request(request, output, Backend())
    assert output.read_bytes() == (transcript.to_json() + "\n").encode("utf-8")
    assert RawTranscript.from_json(output.read_text(encoding="utf-8")) == transcript


def test_worker_public_name_is_complete_before_original_child_termination(tmp_path: Path) -> None:
    request, output = inputs(tmp_path)
    text = "s" * (2 * 1024 * 1024) + "."
    code = (
        "import runpy,sys\n"
        f"ns=runpy.run_path({str(Path(__file__).resolve())!r})\n"
        "from pathlib import Path\n"
        f"backend=ns['Backend']({text[:1]!r}*(2*1024*1024)+'.')\n"
        "ns['run_request'](Path(sys.argv[1]),Path(sys.argv[2]),backend)\n"
    )
    process = subprocess.Popen(
        [sys.executable, "-B", "-c", code, str(request), str(output)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    observed: bytes | None = None
    try:
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            if output.exists():
                observed = output.read_bytes()
                break
            if process.poll() is not None:
                break
            time.sleep(0.001)
    finally:
        # Original Popen owns the creation handle; never cancel the Codex console.
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
    assert process.stderr is not None
    diagnostic = process.stderr.read(65_536)
    process.stderr.close()
    assert observed is not None, diagnostic.decode(errors="replace")
    assert observed.endswith(b"\n"), "The public name appeared before its bytes were complete"
    parsed = RawTranscript.from_json(observed.decode("utf-8"))
    assert parsed.text_ckb == text and parsed.words[0].w == text
    assert output.read_bytes() == observed, "Original-child death must not expose partial output"
