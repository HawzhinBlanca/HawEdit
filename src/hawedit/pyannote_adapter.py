"""Production pyannote diarizer adapter (§3 Stage 0).

Implements the `Diarizer` protocol bound to `pyannote/speaker-diarization-community-1`.
Converts float-second pyannote tracks into exact-integer millisecond `Segment` instances
via monotonic rounding, enforcing refusal rules (zero/negative durations, missing weights,
mismatched revisions) without mutating or repairing overlaps.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hawedit.diarization import Segment
from hawedit.diarization_acceptance import COMMUNITY_MODEL_ID, COMMUNITY_REVISION
from hawedit.ingest import DiarizationInvalidOutput, DiarizationUnavailable, Diarizer
from hawedit.models import ModelNotProvisioned, ModelStore

__all__ = [
    "COMMUNITY_MODEL_ID",
    "COMMUNITY_REVISION",
    "PyannoteDiarizer",
    "convert_annotation_to_segments",
    "create_diarizer",
]


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
            resolved_dir = self.model_dir or ModelStore().assert_available(self.model_id)
        except (ModelNotProvisioned, RuntimeError) as exc:
            raise DiarizationUnavailable(
                f"pyannote model {self.model_id!r} is not available (BLOCKED.md #4): {exc}"
            ) from exc

        try:
            import importlib

            pyannote_audio = importlib.import_module("pyannote.audio")
            pipeline_cls = pyannote_audio.Pipeline
        except (ImportError, AttributeError) as exc:
            raise DiarizationUnavailable(
                f"pyannote.audio is not installed ({exc}). "
                "Install hawedit[diarization] to enable speaker diarization."
            ) from exc

        try:
            import torch

            pipeline = pipeline_cls.from_pretrained(resolved_dir or self.model_id)
            if self.device != "cpu":
                pipeline.to(torch.device(self.device))
            annotation = pipeline(str(audio_path))
        except Exception as exc:
            raise DiarizationUnavailable(f"pyannote diarization failed: {exc}") from exc

        return convert_annotation_to_segments(annotation)


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
