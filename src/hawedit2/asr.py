"""The ASR adapter boundary, and the throughput half of §8.1.

    real-time factor measured on hawapc01 · VRAM · long-audio failure rate

§3 Stage 1 states the trap plainly: Meta's published RTF figures — 0.003 for CTC-3B, 0.092
for LLM-7B — are "measured at batch=1, 30 s audio, BF16, on an A100. Do not derive wall-clock
promises for hawapc01 from them." A throughput number carries its hardware or it is not a
number, so `Hardware` is a required field and mixing measurements from different hosts is
refused rather than averaged.

Two more things follow from "fail visible, not silent" (§1):

* **A failing transcription is data.** §8.1 asks for a long-audio *failure rate*, which only
  exists if failures are recorded instead of aborting the run.
* **Unmeasured is `None`.** No VRAM probe means `None`, not 0 — a zero would read as a
  measured result on a box that had no GPU at all.

Every measurement records the adapter class that produced it, so a run driven by a test
double is self-evident in the report and can never be read as a run on real weights. The
real adapters (LLM-7B, CTC-3B, the validator, Gemini native audio) are M0.11 and need
hardware and credentials this environment does not have — see BLOCKED.md.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol, runtime_checkable

from hawedit2.corpus import CorpusItem
from hawedit2.registry import ASR_ROLES, ModelEntry, resolve_role
from hawedit2.transcripts import Word

__all__ = [
    "LONG_AUDIO_THRESHOLD_S",
    "ASRAdapter",
    "ASRResult",
    "Hardware",
    "IncomparableHardware",
    "Measurement",
    "MeasurementSession",
    "long_audio_failure_rate",
    "validate_adapter",
]

# §3 Stage 1: OmniASR's interface ceiling. Stage 0's VAD uses max_speech_duration_s=38 to
# stay under it, so anything past this is by definition outside the designed operating range
# and its failure rate is a property worth measuring rather than an accident.
LONG_AUDIO_THRESHOLD_S: Final = 40.0


class IncomparableHardware(ValueError):
    """Raised when measurements from different hardware are combined into one figure."""


@dataclass(frozen=True, slots=True)
class Hardware:
    """The machine a throughput figure was measured on. Required, never inferred."""

    host: str
    accelerator: str
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.host.strip():
            raise ValueError(
                "host must be named: §8.1 asks for real-time factor measured on hawapc01, "
                "and an unattributed RTF cannot be compared with anything."
            )


@dataclass(frozen=True, slots=True)
class ASRResult:
    """What an ASR model returned for one item.

    `text_raw` is exactly as the model emitted it — invariant #1 governs it from here on,
    and normalization happens at scoring time. `emissions_path` is where CTC frame posteriors
    were written: §3 Stage 1 runs CTC-3B in parallel precisely because the LLM decoder gives
    none, and §4.2's Viterbi forced alignment consumes them.
    """

    text_raw: str
    mean_logprob: float | None = None
    emissions_path: str | None = None
    words: tuple[Word, ...] = ()


@runtime_checkable
class ASRAdapter(Protocol):
    """One §7 ASR model, behind a uniform interface.

    Implementations belong to M0.11. Keeping the boundary this thin is what makes the
    §8.1 decision rule a config change rather than a refactor.
    """

    model_id: str

    def transcribe(self, audio_path: Path, duration_s: float) -> ASRResult: ...


def validate_adapter(adapter: ASRAdapter) -> ModelEntry:
    """Resolve the adapter's model against §7, refusing anything the blueprint excludes.

    Raises:
        ModelNotInRegistry: the model is not in §7.
        ModelExcluded: §7 names it in the exclusion table.
        WrongRole: the model is in §7 but is not an ASR model (audit finding #8).
    """
    return resolve_role(adapter.model_id, ASR_ROLES, "an ASR adapter")


@dataclass(frozen=True, slots=True)
class Measurement:
    """One (model, item) run: what it produced, how long it took, and on what."""

    item_id: str
    model_id: str
    adapter_impl: str
    hardware: Hardware
    duration_s: float
    wall_clock_s: float
    result: ASRResult | None
    error: str | None = None
    peak_vram_bytes: int | None = None

    @property
    def failed(self) -> bool:
        return self.result is None

    @property
    def rtf(self) -> float:
        """Real-time factor: wall clock over audio duration. Lower is faster."""
        return self.wall_clock_s / self.duration_s

    @property
    def is_long_audio(self) -> bool:
        return self.duration_s > LONG_AUDIO_THRESHOLD_S


class MeasurementSession:
    """Runs adapters against corpus items on one named machine."""

    def __init__(
        self,
        hardware: Hardware,
        clock: Callable[[], float] = time.perf_counter,
        vram_probe: Callable[[], int | None] | None = None,
    ) -> None:
        self.hardware = hardware
        self._clock = clock
        self._vram_probe = vram_probe

    def measure(self, adapter: ASRAdapter, item: CorpusItem) -> Measurement:
        """Transcribe one item, recording timing, VRAM and any failure.

        A raised exception becomes a recorded failure rather than an aborted run: §8.1 wants
        a long-audio failure *rate*, and a run that dies on the first 62-second file
        produces no rate at all.
        """
        validate_adapter(adapter)
        started = self._clock()
        result: ASRResult | None = None
        error: str | None = None
        try:
            result = adapter.transcribe(Path(item.audio_path), item.duration_s)
        except Exception as exc:  # broad on purpose: a failure IS the measurement
            error = f"{type(exc).__name__}: {exc}"
        elapsed = self._clock() - started

        return Measurement(
            item_id=item.item_id,
            model_id=adapter.model_id,
            adapter_impl=type(adapter).__name__,
            hardware=self.hardware,
            duration_s=item.duration_s,
            wall_clock_s=elapsed,
            result=result,
            error=error,
            peak_vram_bytes=self._vram_probe() if self._vram_probe else None,
        )


def assert_one_hardware(measurements: Sequence[Measurement]) -> Hardware | None:
    """Refuse a mixed-hardware set before it becomes a single figure.

    Raises:
        IncomparableHardware: the measurements come from more than one machine.
    """
    hosts = {m.hardware for m in measurements}
    if not hosts:
        return None
    if len(hosts) > 1:
        named = ", ".join(sorted(h.host for h in hosts))
        raise IncomparableHardware(
            f"measurements span multiple machines ({named}). §3 Stage 1: a published A100 "
            f"figure is not a 3090 Ti figure, and combining them invents a number that was "
            f"never measured anywhere."
        )
    return next(iter(hosts))


def long_audio_failure_rate(
    measurements: Sequence[Measurement],
    threshold_s: float = LONG_AUDIO_THRESHOLD_S,
) -> float | None:
    """Fraction of over-threshold items the model failed to transcribe.

    Returns:
        The rate, or `None` when no item exceeded the threshold — a corpus of 30-second
        clips says nothing about long-audio behaviour, and 0.0 would claim it does.

    Raises:
        IncomparableHardware: the measurements come from more than one machine.
    """
    assert_one_hardware(measurements)
    long_items = [m for m in measurements if m.duration_s > threshold_s]
    if not long_items:
        return None
    return sum(1 for m in long_items if m.failed) / len(long_items)
