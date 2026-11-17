"""Single-process WSL worker for the canonical OmniASR Stage 1 path.

The Windows runner writes a small request beside its already-cut WAV segments. This process
loads the official LLM and CTC models once, transcribes every segment, shifts CTC/Viterbi word
timings onto the media clock, and publishes one validated ``RawTranscript`` with exclusive
creation. It is deliberately a file protocol: Sorani text and errors never depend on console
encoding across the Windows/WSL boundary.
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import re
import tempfile
from collections.abc import Callable, Iterable, Mapping
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from hawedit.asr import (
    LONG_AUDIO_THRESHOLD_S,
    OmniAsrBackend,
    OmniSegmentBackend,
    QwenSoraniValidator,
    SoraniValidator,
    _assemble_canonical_transcript,
    _PreparedSpeechSegment,
    _validate_hard_segments,
    transcribe_prepared_segments,
)
from hawedit.asr_resume import OperationCache, ResumableBackend, ResumableValidator, worker_journal
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


MIN_FREE_GPU_GIB_ENV = "HAWEDIT_ASR_MIN_FREE_GPU_GIB"
# Judgment, not a measurement (D-331): an idle 24 GiB card passes, a card the omniasr :8000
# server holds (~14.6 GB) does not. The T0 hardware run must replace it with the measured peak.
DEFAULT_MIN_FREE_GPU_GIB = 20.0


def assert_gpu_headroom(
    devices: Iterable[str],
    mem_get_info: Callable[[int], tuple[int, int]],
    environ: Mapping[str, str] = os.environ,
) -> None:
    """Halt before loading anything when another process holds a Stage 1 GPU (D-260)."""
    try:
        need_gib = float(environ.get(MIN_FREE_GPU_GIB_ENV, DEFAULT_MIN_FREE_GPU_GIB))
    except ValueError as exc:
        raise ValueError(f"{MIN_FREE_GPU_GIB_ENV} must be a number of GiB") from exc
    for device in sorted(set(devices)):
        if not device.startswith("cuda:"):
            continue
        index = int(device.removeprefix("cuda:"))
        free, total = mem_get_info(index)
        if free < need_gib * 1024**3:
            raise RuntimeError(
                f"GPU {index} has {free / 1024**3:.1f} of {total / 1024**3:.1f} GiB free; Stage 1 "
                f"needs {need_gib:.1f} GiB ({MIN_FREE_GPU_GIB_ENV}). Another process is using it "
                "(e.g. the omniasr :8000 server: run through scripts/run-with-omniasr-paused.sh). "
                "Refusing rather than drafting on another device or model."
            )


def run_request(
    request_path: Path,
    output_path: Path,
    backend: OmniSegmentBackend | None = None,
    validator: SoraniValidator | None = None,
    *,
    checkpoint_root: Path | None = None,
) -> RawTranscript:
    """Execute one strict bridge request; primarily separated for deterministic tests."""
    try:
        output_path.lstat()
    except FileNotFoundError:
        pass
    else:
        raise FileExistsError(
            errno.EEXIST,
            "ASR worker result already exists; preserve and reconcile it or use a new output path",
            str(output_path),
        )
    transcript = _infer_request(request_path, backend, validator, checkpoint_root=checkpoint_root)
    result_bytes = (transcript.to_json() + "\n").encode("utf-8")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            dir=output_path.parent,
            delete=False,
        ) as stream:
            staging = Path(stream.name)
            stream.write(result_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        # The final name must expose complete bytes without replacing retained evidence.
        os.link(staging, output_path)
    finally:
        if staging is not None:
            staging.unlink(missing_ok=True)
    return transcript


def infer_protected_request(
    request_path: Path,
    journal: OperationCache,
    backend: OmniSegmentBackend | None = None,
    validator: SoraniValidator | None = None,
) -> RawTranscript:
    """Canonical inference without worker writes; launch admission is a separate prerequisite."""
    from hawedit.asr_checkpoint import CheckpointJournal

    if type(journal) is not CheckpointJournal:
        raise TypeError("protected ASR requires the remote host checkpoint journal")
    transcript = _infer_request(request_path, backend, validator, journal=journal)
    if len((transcript.to_json() + "\n").encode("utf-8")) > 16 * 1024 * 1024:
        raise RuntimeError("protected ASR transcript exceeds its 16MiB result bound")
    journal.finish(transcript)
    return transcript


def _infer_request(
    request_path: Path,
    backend: OmniSegmentBackend | None,
    validator: SoraniValidator | None,
    *,
    checkpoint_root: Path | None = None,
    journal: OperationCache | None = None,
) -> RawTranscript:
    if checkpoint_root is not None and journal is not None:
        raise ValueError("ASR inference cannot use both local and remote checkpoints")
    payload: Any = json.loads(request_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 2:
        raise ValueError("unsupported OmniASR worker request schema")
    media_id = payload.get("media_id")
    if not isinstance(media_id, str) or not media_id.strip():
        raise ValueError("ASR worker request media_id must be a non-empty string")
    raw_segments = payload.get("segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        raise ValueError("ASR worker request must contain at least one speech segment")
    validator_path = payload.get("validator_model_dir")
    if not isinstance(validator_path, str) or not validator_path.strip():
        raise ValueError("ASR worker validator_model_dir must be a non-empty path")

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

    # An adapter named in the request must reach the weights or stop the run. Ignoring it would
    # transcribe on base weights and publish the result under the adapter's name — the request is
    # the only channel across the WSL boundary, so a field read by nobody is silently wrong
    # output, not a no-op. Carried across the readiness merge, which added the Sorani validator
    # to this same request and had no adapter field at all.
    adapter = payload.get("lora_adapter")
    if adapter is not None and not isinstance(adapter, str):
        raise ValueError("ASR worker request lora_adapter must be a path string")
    if adapter is not None and backend is not None:
        raise ValueError(
            "ASR worker request names a LoRA adapter but a backend was supplied; the adapter "
            "would be ignored and its transcript filed under the adapter's name anyway"
        )
    # The fused champion (D-331) follows the same rules under its own identity prefix, and
    # neither kind may stand in for the other.
    fused = payload.get("fused_checkpoint")
    if fused is not None and not isinstance(fused, str):
        raise ValueError("ASR worker request fused_checkpoint must be a path string")
    if fused is not None and adapter is not None:
        raise ValueError("ASR worker request names both a LoRA adapter and a fused checkpoint")
    if fused is not None and backend is not None:
        raise ValueError(
            "ASR worker request names a fused checkpoint but a backend was supplied; the "
            "checkpoint would be ignored and its transcript filed under its name anyway"
        )
    claimed_identity = payload.get("model_identity")
    if adapter is not None or fused is not None:
        kind, weights = ("lora", adapter) if adapter is not None else ("fused", fused)
        if (
            not weights
            or not weights.strip()
            or not isinstance(claimed_identity, str)
            or re.fullmatch(rf"{kind}:[a-f0-9]{{64}}", claimed_identity) is None
        ):
            raise ValueError("ASR worker requires a current complete adapter identity")
    elif claimed_identity is not None:
        raise ValueError("ASR worker stock request cannot claim an adapter identity")
    model = backend or OmniAsrBackend(
        lora_adapter=Path(adapter) if adapter is not None else None,
        fused_checkpoint=Path(fused) if fused is not None else None,
    )
    expected_identity = getattr(model, "adapter_name", None)
    if claimed_identity != expected_identity:
        raise ValueError("ASR worker adapter identity differs from the host request")
    if backend is None and isinstance(model, OmniAsrBackend):
        import torch

        assert_gpu_headroom((model.llm_device, model.ctc_device), torch.cuda.mem_get_info)
    with ExitStack() as leases:
        journal = (
            leases.enter_context(
                worker_journal(
                    checkpoint_root, request_path, prepared, Path(validator_path), expected_identity
                )
            )
            if checkpoint_root is not None
            else journal
        )
        active_model: OmniSegmentBackend = ResumableBackend(model, journal) if journal else model
        # D-278: checkpoints preserve successes, never authorise failure continuation.
        initial, unaligned = transcribe_prepared_segments(
            active_model, prepared, stop_on_failure=True
        )
        if type(model) is OmniAsrBackend:
            model.release_draft_model()
        selected_validator = validator

        def validator_factory() -> SoraniValidator:
            nonlocal selected_validator
            if selected_validator is None:
                model_dir = Path(validator_path)
                if not model_dir.is_dir():
                    raise FileNotFoundError(
                        f"ASR worker validator weights are missing: {model_dir}"
                    )
                selected_validator = QwenSoraniValidator(model_dir)
            return (
                ResumableValidator(selected_validator, journal) if journal else selected_validator
            )

        results, validated_by, rejected_corrections, origins = _validate_hard_segments(
            initial, active_model, validator_factory, stop_on_failure=True
        )
        if getattr(model, "adapter_name", None) != expected_identity:
            raise ValueError("ASR worker adapter identity changed during inference")
        transcript = _assemble_canonical_transcript(
            media_id,
            results,
            unaligned,
            adapter=expected_identity,
            validated_by=validated_by,
            rejected_validator_corrections=rejected_corrections,
            segment_origins=origins,
        )
        return transcript


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one HawEdit OmniASR WSL bridge request")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    # Native Linux storage enforces owner-private permissions; DrvFS does not.
    run_request(args.request, args.output, checkpoint_root=Path.home() / ".hawedit-asr-checkpoints")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through the WSL process
    raise SystemExit(main())
