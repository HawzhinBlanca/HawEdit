"""M0.7 — the ASR adapter boundary and the throughput half of §8.1.

    real-time factor measured on hawapc01 · VRAM · long-audio failure rate

§3 Stage 1 is emphatic about the trap here: Meta's published RTF (0.003 for CTC-3B, 0.092
for LLM-7B) is "batch=1, 30 s audio, BF16, on an A100. Do not derive wall-clock promises for
hawapc01 from them." A throughput number without the hardware it was measured on is not a
weaker number, it is a wrong one — so `Hardware` is required, not optional, and comparing
measurements across hardware is refused.

The real adapters need GPUs this container does not have (M0.11, BLOCKED.md #2). What is
built and tested here is the boundary they plug into, and every measurement records the
adapter class that produced it so a run driven by a test double can never be mistaken for a
run on real weights.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hawedit2.asr import (
    LONG_AUDIO_THRESHOLD_S,
    ASRResult,
    Hardware,
    IncomparableHardware,
    MeasurementSession,
    long_audio_failure_rate,
    validate_adapter,
)
from hawedit2.corpus import Condition, CorpusItem, Dialect
from hawedit2.registry import ModelExcluded, ModelNotInRegistry

HAWAPC01 = Hardware(host="hawapc01", accelerator="2x RTX 3090 Ti", notes="Threadripper 3990X")
AN_A100 = Hardware(host="a100-box", accelerator="A100")


class StubAdapter:
    """A test double. Named so it is obvious in any report it appears in."""

    def __init__(self, model_id: str = "omniASR_LLM_7B_v2", text: str = "ئەمە") -> None:
        self.model_id = model_id
        self._text = text

    def transcribe(self, audio_path: Path, duration_s: float) -> ASRResult:
        return ASRResult(text_raw=self._text)


class FailingAdapter(StubAdapter):
    def transcribe(self, audio_path: Path, duration_s: float) -> ASRResult:
        raise RuntimeError("model refused a 62 s input")


def an_item(item_id: str = "itm-001", duration_s: float = 30.0) -> CorpusItem:
    return CorpusItem(
        item_id=item_id,
        audio_path=f"audio/{item_id}.wav",
        reference_ckb="ئەمە زۆر باشە",
        dialect=Dialect.HEWLER,
        conditions=frozenset({Condition.FORMAL_NEWS}),
        duration_s=duration_s,
    )


class FakeClock:
    def __init__(self, step: float) -> None:
        self._now = 0.0
        self._step = step

    def __call__(self) -> float:
        now = self._now
        self._now += self._step
        return now


# --- the adapter boundary is the §7 boundary ------------------------------------------


def test_an_adapter_for_an_unregistered_model_is_refused() -> None:
    with pytest.raises(ModelNotInRegistry):
        validate_adapter(StubAdapter(model_id="openai/whisper-large-v3"))


def test_an_adapter_for_an_excluded_model_is_refused() -> None:
    with pytest.raises(ModelExcluded):
        validate_adapter(StubAdapter(model_id="RevgeAI/vekol-stt-ckb-small"))


def test_an_adapter_for_a_registered_model_is_accepted() -> None:
    assert validate_adapter(StubAdapter()).role == "canonical_asr"


# --- measurement ----------------------------------------------------------------------


def test_a_measurement_records_wall_clock_and_real_time_factor() -> None:
    session = MeasurementSession(hardware=HAWAPC01, clock=FakeClock(step=3.0))
    measurement = session.measure(StubAdapter(), an_item(duration_s=30.0))
    assert measurement.wall_clock_s == pytest.approx(3.0)
    assert measurement.rtf == pytest.approx(0.1)


def test_a_measurement_names_the_adapter_that_produced_it() -> None:
    """A run driven by a test double must be self-evident in the report."""
    session = MeasurementSession(hardware=HAWAPC01, clock=FakeClock(step=1.0))
    assert session.measure(StubAdapter(), an_item()).adapter_impl == "StubAdapter"


def test_a_failing_adapter_is_recorded_not_raised() -> None:
    """§8.1 measures a long-audio *failure rate*, so failure is data, not an abort."""
    session = MeasurementSession(hardware=HAWAPC01, clock=FakeClock(step=1.0))
    measurement = session.measure(FailingAdapter(), an_item(duration_s=62.0))
    assert measurement.failed
    assert measurement.result is None
    assert "62 s" in (measurement.error or "")


def test_vram_is_none_without_a_probe_never_zero() -> None:
    """Zero VRAM would read as a measured result. This ran on a box with no GPU."""
    session = MeasurementSession(hardware=HAWAPC01, clock=FakeClock(step=1.0))
    assert session.measure(StubAdapter(), an_item()).peak_vram_bytes is None


def test_vram_comes_from_the_probe_when_one_is_supplied() -> None:
    session = MeasurementSession(
        hardware=HAWAPC01, clock=FakeClock(step=1.0), vram_probe=lambda: 17 * 1024**3
    )
    assert session.measure(StubAdapter(), an_item()).peak_vram_bytes == 17 * 1024**3


# --- hardware provenance --------------------------------------------------------------


def test_hardware_must_be_named() -> None:
    with pytest.raises(ValueError, match="host"):
        Hardware(host="  ", accelerator="2x RTX 3090 Ti")


def test_measurements_from_different_hardware_refuse_to_be_compared() -> None:
    """§3 Stage 1: an A100 RTF is not a 3090 Ti RTF, and averaging them invents a number."""
    on_hawapc01 = MeasurementSession(hardware=HAWAPC01, clock=FakeClock(step=3.0)).measure(
        StubAdapter(), an_item()
    )
    on_a100 = MeasurementSession(hardware=AN_A100, clock=FakeClock(step=1.0)).measure(
        StubAdapter(), an_item()
    )
    with pytest.raises(IncomparableHardware, match="hawapc01"):
        long_audio_failure_rate([on_hawapc01, on_a100])


# --- long-audio failure rate ----------------------------------------------------------


def test_long_audio_threshold_is_the_omniasr_interface_limit() -> None:
    """§3 Stage 1: the 40 s ceiling is what VAD's 38 s max_speech_duration_s stays under."""
    assert LONG_AUDIO_THRESHOLD_S == 40.0


def test_long_audio_failure_rate_counts_only_long_items() -> None:
    session = MeasurementSession(hardware=HAWAPC01, clock=FakeClock(step=1.0))
    measurements = [
        session.measure(FailingAdapter(), an_item("short-fail", duration_s=10.0)),
        session.measure(FailingAdapter(), an_item("long-fail", duration_s=62.0)),
        session.measure(StubAdapter(), an_item("long-ok", duration_s=55.0)),
    ]
    assert long_audio_failure_rate(measurements) == pytest.approx(0.5)


def test_long_audio_failure_rate_is_none_when_nothing_was_long() -> None:
    """Unmeasured is not 0.0 — a corpus of 30 s clips says nothing about long-audio."""
    session = MeasurementSession(hardware=HAWAPC01, clock=FakeClock(step=1.0))
    measurements = [session.measure(StubAdapter(), an_item(duration_s=30.0))]
    assert long_audio_failure_rate(measurements) is None


def test_long_audio_failure_rate_of_an_empty_run_is_none() -> None:
    assert long_audio_failure_rate([]) is None
