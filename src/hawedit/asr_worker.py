"""Single-process WSL worker for the canonical OmniASR Stage 1 path.

The Windows runner writes a small request beside its already-cut WAV segments. This process
loads the official LLM and CTC models once, transcribes every segment, shifts CTC/Viterbi word
timings onto the media clock, and publishes one validated ``RawTranscript`` with exclusive
creation. It is deliberately a file protocol: Sorani text and errors never depend on console
encoding across the Windows/WSL boundary.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from hawedit.asr import (
    LONG_AUDIO_THRESHOLD_S,
    OmniAsrBackend,
    OmniSegmentBackend,
    _assemble_canonical_transcript,
    _PreparedSpeechSegment,
)
from hawedit.transcripts import RawTranscript


def _segment_path(root: Path, value: object, index: int) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ValueError(f"ASR worker segment {index} path must be a relative filename")
    resolved = (root / value).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"ASR worker segment {index} escapes its request directory") from exc
    if not resolved.is_file():
        raise FileNotFoundError(f"ASR worker segment {index} is missing: {resolved}")
    return resolved


def _integer(value: object, field: str, index: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"ASR worker segment {index} {field} must be an integer")
    return value


def run_request(
    request_path: Path,
    output_path: Path,
    backend: OmniSegmentBackend | None = None,
) -> RawTranscript:
    """Execute one strict bridge request; primarily separated for deterministic tests."""
    payload: Any = json.loads(request_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("unsupported OmniASR worker request schema")
    media_id = payload.get("media_id")
    if not isinstance(media_id, str) or not media_id.strip():
        raise ValueError("ASR worker request media_id must be a non-empty string")
    raw_segments = payload.get("segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        raise ValueError("ASR worker request must contain at least one speech segment")

    root = request_path.resolve().parent
    prepared: list[_PreparedSpeechSegment] = []
    for index, item in enumerate(raw_segments):
        if not isinstance(item, dict):
            raise ValueError(f"ASR worker segment {index} must be an object")
        start_ms = _integer(item.get("start_ms"), "start_ms", index)
        end_ms = _integer(item.get("end_ms"), "end_ms", index)
        segment = _PreparedSpeechSegment(
            _segment_path(root, item.get("path"), index), start_ms, end_ms
        )
        if not 0 < segment.duration_s <= LONG_AUDIO_THRESHOLD_S:
            raise ValueError(
                f"ASR worker segment {index} is {segment.duration_s:.3f}s; expected 0.."
                f"{LONG_AUDIO_THRESHOLD_S:.0f}s"
            )
        prepared.append(segment)

    model = backend or OmniAsrBackend()
    transcript = _assemble_canonical_transcript(
        media_id,
        tuple(
            (segment, model.transcribe_segment(segment.path, segment.duration_s))
            for segment in prepared
        ),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(transcript.to_json())
        stream.write("\n")
    return transcript


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one HawEdit OmniASR WSL bridge request")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    run_request(args.request, args.output)
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through the WSL process
    raise SystemExit(main())
