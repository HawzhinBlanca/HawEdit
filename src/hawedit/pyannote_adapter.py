"""Production pyannote diarizer adapter (§3 Stage 0).

Implements the `Diarizer` protocol bound to `pyannote/speaker-diarization-community-1`.
Converts float-second pyannote tracks into exact-integer millisecond `Segment` instances
via monotonic rounding, enforcing refusal rules (zero/negative durations, missing weights,
mismatched revisions) without mutating or repairing overlaps.
"""

from __future__ import annotations

import importlib
import os
import sys
import wave
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from importlib.abc import MetaPathFinder
from importlib.machinery import ModuleSpec
from pathlib import Path
from threading import RLock
from types import ModuleType
from typing import Any

import hawedit.models as model_contract
from hawedit.diarization import Segment
from hawedit.diarization_acceptance import COMMUNITY_MODEL_ID, COMMUNITY_REVISION
from hawedit.ingest import DiarizationInvalidOutput, DiarizationUnavailable, Diarizer

__all__ = [
    "COMMUNITY_MODEL_ID",
    "COMMUNITY_REVISION",
    "PyannoteDiarizer",
    "convert_annotation_to_segments",
    "create_diarizer",
]

_LOCAL_CONSUMER_LOCK = RLock()


def _is_sdk(name: str) -> bool:
    return name == "pyannoteai" or name.startswith("pyannoteai.")


class _LocalImports(MetaPathFinder):
    def __init__(self) -> None:
        self.attempted: str | None = None

    def find_spec(
        self, fullname: str, path: Sequence[str] | None, target: ModuleType | None = None
    ) -> ModuleSpec | None:
        if _is_sdk(fullname):
            self.attempted = fullname
            raise ImportError(f"Local diarization refuses SDK import: {fullname}")
        return None

    def check(self) -> None:
        loaded = next(
            (name for name in tuple(sys.modules) if _is_sdk(name) and sys.modules.get(name)),
            None,
        )
        if self.attempted is not None or loaded is not None:
            raise DiarizationUnavailable(
                f"Local diarization refuses SDK use: {self.attempted or loaded}. "
                "Start an SDK-free local worker."
            )
        os.environ["PYANNOTE_METRICS_ENABLED"] = "false"


@contextmanager
def _local_imports() -> Iterator[_LocalImports]:
    # Serialize this process-wide import policy; it is not native network isolation.
    with _LOCAL_CONSUMER_LOCK:
        guard = _LocalImports()
        guard.check()
        sys.meta_path.insert(0, guard)
        try:
            yield guard
        finally:
            try:
                guard.check()
            finally:
                if guard in sys.meta_path:
                    sys.meta_path.remove(guard)


def _read_canonical_pcm(audio: Path) -> bytearray:
    try:
        with audio.open("rb") as source:
            before = os.fstat(source.fileno())
            with wave.open(source, "rb") as stream:
                if (
                    stream.getnchannels() != 1
                    or stream.getsampwidth() != 2
                    or stream.getframerate() != 16000
                    or stream.getcomptype() != "NONE"
                ):
                    raise DiarizationUnavailable(
                        "Diarization requires Stage 0 mono 16kHz 16-bit PCM WAV audio."
                    )
                size = stream.getnframes() * 2
                if size == 0 or size > before.st_size:
                    raise DiarizationUnavailable("PCM WAV audio is empty or truncated.")
                # Read the data-chunk remainder too: WAV frame counts round odd bytes down.
                pcm = bytearray(stream.readframes(stream.getnframes() + 1))
            after = os.fstat(source.fileno())
            identity_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
            if len(pcm) != size or any(
                getattr(before, field) != getattr(after, field) for field in identity_fields
            ):
                raise DiarizationUnavailable(
                    "PCM WAV audio is truncated or changed during reading."
                )
            if sys.byteorder != "little":
                raise DiarizationUnavailable("PCM audio requires a supported little-endian host.")
            return pcm
    except (OSError, EOFError, wave.Error, OverflowError) as exc:
        raise DiarizationUnavailable(f"Cannot read canonical PCM WAV audio: {exc}") from exc


def convert_annotation_to_segments(annotation: Any) -> tuple[Segment, ...]:
    """Convert pyannote Annotation tracks to HawEdit Segment tuple under monotonic rounding.

    AC-5: Converts float seconds to exact integer milliseconds by monotonic rounding.
          SHALL NOT merge, clamp, pad or reorder turns.
    AC-6: Refuses zero- or negative-length turns rather than dropping them.
    AC-7: Does not repair overlaps; let attach_diarization refuse overlapping turns.
    """
    if not hasattr(annotation, "itertracks"):
        raise DiarizationInvalidOutput(
            "diarization output must be a pyannote Annotation supporting itertracks()"
        )

    segments: list[Segment] = []
    for item in annotation.itertracks(yield_label=True):
        if len(item) == 3:
            segment, _track, label = item
        elif len(item) == 2:
            segment, label = item
        else:
            raise DiarizationInvalidOutput(f"unexpected track tuple structure: {item!r}")

        start_ms = round(float(segment.start) * 1000)
        end_ms = round(float(segment.end) * 1000)
        speaker = str(label)

        if end_ms <= start_ms:
            raise DiarizationInvalidOutput(
                f"diarization turn {speaker!r} {start_ms}..{end_ms} ms has non-positive duration "
                f"after conversion ({segment.start}..{segment.end} s)"
            )

        segments.append(Segment(start_ms=start_ms, end_ms=end_ms, speaker=speaker))

    return tuple(segments)


@dataclass(frozen=True, slots=True)
class PyannoteDiarizer(Diarizer):
    """Production pyannote diarizer adapter implementing §3 Stage 0 exclusive diarization."""

    model_id: str = COMMUNITY_MODEL_ID
    revision: str = COMMUNITY_REVISION
    device: str = "cpu"
    model_dir: Path | None = None

    def __post_init__(self) -> None:
        if self.model_id != COMMUNITY_MODEL_ID:
            raise ValueError(f"Community-1 model must be {COMMUNITY_MODEL_ID!r}")
        if self.revision != COMMUNITY_REVISION:
            raise ValueError(
                f"Community-1 run must use pinned revision {COMMUNITY_REVISION}, "
                f"got {self.revision!r}"
            )

    def diarize(self, audio: Path) -> Sequence[Segment]:
        """Run diarization over audio file, resolving model weights and checking refusals."""
        audio_path = Path(audio)
        if not audio_path.exists():
            raise FileNotFoundError(f"audio file not found: {audio_path}")

        if self.revision != COMMUNITY_REVISION:
            raise ValueError(
                f"Community-1 run must use pinned revision {COMMUNITY_REVISION}, "
                f"got {self.revision!r}"
            )

        try:
            with model_contract.verified_checkpoint_access(
                self.model_id, self.model_dir
            ) as resolved_dir:
                pcm = _read_canonical_pcm(audio_path)
                with _local_imports() as imports:
                    try:
                        pyannote_audio = importlib.import_module("pyannote.audio")
                        pipeline_cls = pyannote_audio.Pipeline
                    except (ImportError, AttributeError) as exc:
                        raise DiarizationUnavailable(
                            f"pyannote.audio is not installed ({exc}). "
                            "Install hawedit[diarization] to enable speaker diarization."
                        ) from exc

                    try:
                        import torch

                        imports.check()
                        waveform = torch.frombuffer(pcm, dtype=torch.int16).to(torch.float32)
                        waveform.div_(32768).unsqueeze_(0)
                        pipeline = pipeline_cls.from_pretrained(resolved_dir)
                        imports.check()
                        if self.device != "cpu":
                            pipeline.to(torch.device(self.device))
                        imports.check()
                        output = pipeline({"waveform": waveform, "sample_rate": 16000})
                        imports.check()
                        exclusive = getattr(output, "exclusive_speaker_diarization", None)
                        if exclusive is None or not callable(
                            getattr(exclusive, "itertracks", None)
                        ):
                            raise DiarizationInvalidOutput(
                                "Community-1 requires an exclusive_speaker_diarization Annotation "
                                "from the pinned pyannote.audio 4.0.7 output; ordinary or legacy "
                                "output is not a fallback"
                            )
                        return convert_annotation_to_segments(exclusive)
                    except DiarizationUnavailable:
                        raise
                    except Exception as exc:
                        raise DiarizationUnavailable(f"pyannote diarization failed: {exc}") from exc
        except (
            model_contract.CheckpointIntegrityError,
            model_contract.RevisionNotPinned,
            model_contract.SourceNotConfigured,
            OSError,
        ) as exc:
            raise DiarizationUnavailable(
                f"pyannote model {self.model_id!r} is not available (BLOCKED.md #4): {exc}"
            ) from exc


def create_diarizer(
    model_id: str = COMMUNITY_MODEL_ID,
    *,
    revision: str = COMMUNITY_REVISION,
    device: str = "cpu",
    model_dir: Path | None = None,
) -> PyannoteDiarizer:
    """Create a configured PyannoteDiarizer instance."""
    return PyannoteDiarizer(
        model_id=model_id,
        revision=revision,
        device=device,
        model_dir=model_dir,
    )
