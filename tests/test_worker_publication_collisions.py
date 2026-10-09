"""Real result collisions/staging isolation and exact Sorani bytes, not inference."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from hawedit.asr import SegmentTranscript
from hawedit.asr_worker import run_request
from hawedit.transcripts import RawTranscript
from test_worker_publication import Backend, inputs


def test_worker_concurrent_result_publication_has_one_unchanged_winner(tmp_path: Path) -> None:
    request, output = inputs(tmp_path)
    admitted = threading.Barrier(2, timeout=5)

    class BarrierBackend(Backend):
        def transcribe_segment(self, audio_path: Path, duration_s: float) -> SegmentTranscript:
            admitted.wait()
            return super().transcribe_segment(audio_path, duration_s)

    backends = (BarrierBackend(), BarrierBackend())
    results: list[RawTranscript] = []
    refused = 0
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run_request, request, output, backend) for backend in backends]
        for future in futures:
            try:
                results.append(future.result(timeout=10))
            except FileExistsError:
                refused += 1
    assert len(results) == 1 and refused == 1
    assert tuple(backend.calls for backend in backends) == (1, 1)
    assert output.read_bytes() == (results[0].to_json() + "\n").encode("utf-8")
    assert RawTranscript.from_json(output.read_text(encoding="utf-8")) == results[0]
    assert not list(tmp_path.glob(".output.json.*.tmp"))


def test_worker_does_not_remove_unrelated_staging_evidence(tmp_path: Path) -> None:
    request, output = inputs(tmp_path)
    retained = tmp_path / ".output.json.retained.tmp"
    retained.write_bytes(b"retained-unknown-old-writer\n")
    result = run_request(request, output, Backend())
    assert retained.read_bytes() == b"retained-unknown-old-writer\n"
    assert output.read_bytes() == (result.to_json() + "\n").encode("utf-8")
    assert sorted(tmp_path.glob(".output.json.*.tmp")) == [retained]


def test_worker_publication_preserves_sorani_utf8_bytes(tmp_path: Path) -> None:
    request, output = inputs(tmp_path)
    text = "\u06a9\u0648\u0631\u062f\u06cc."
    transcript = run_request(request, output, Backend(text))
    payload = output.read_bytes()
    assert text.encode("utf-8") in payload
    assert payload == (transcript.to_json() + "\n").encode("utf-8")
    assert RawTranscript.from_json(payload.decode("utf-8")).text_ckb == text
