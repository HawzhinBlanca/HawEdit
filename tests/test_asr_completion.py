"""Test-first mechanical completion contract, not speech accuracy evidence."""

from __future__ import annotations

import importlib.metadata
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

import test_asr_stop as stop_fixtures
import test_transcripts as transcript_fixtures
from hawedit.asr import OmniAsrBackend, OmniAsrProducer, WslOmniAsrProducer
from hawedit.asr_completion import (
    COMPLETION_POLICY_ID,
    DecodeIncomplete,
    NoNaturalEos,
    loop_suspect,
    looped,
    require_natural_completion,
    transcribe_completed,
)
from hawedit.asr_worker import run_request
from hawedit.pipeline import PipelineRun
from hawedit.transcripts import RawTranscript, RawTranscriptImmutable, TranscriptStore, Word


class Tokens:
    def __init__(self, value: Any) -> None:
        self.value = value

    def detach(self) -> Tokens:
        return self

    def cpu(self) -> Tokens:
        return self

    def tolist(self) -> Any:
        return self.value


class Model:
    def __init__(self) -> None:
        self.calls: list[tuple[Tokens, object]] = []

    def embed_text(self, seqs: Tokens, dtype: object) -> Tokens:
        self.calls.append((seqs, dtype))
        return seqs


class Generator:
    def __init__(self) -> None:
        self.model: Any = Model()
        self.config = SimpleNamespace(nbest=1)
        self.eos_idx = 2

    def generate_hypotheses_one_segment(self, tokens: list[Any], output: object) -> object:
        for value in tokens:
            seqs = Tokens(value)
            assert self.model.embed_text(seqs, dtype="unchanged") is seqs
        return output


def pipeline() -> Any:
    return SimpleNamespace(beam_search_generator=Generator())


def test_completion_observer_preserves_natural_eos_output() -> None:
    item = pipeline()
    generator = item.beam_search_generator
    model = generator.model
    output = object()
    with require_natural_completion(item):
        assert generator.generate_hypotheses_one_segment([[[9095]], [[2]]], output) is output
    assert generator.model is model
    assert "generate_hypotheses_one_segment" not in vars(generator)
    assert [seqs.value for seqs, _ in model.calls] == [[[9095]], [[2]]]
    assert all(dtype == "unchanged" for _, dtype in model.calls)


@pytest.mark.parametrize("value", [[[9095]], [[1]], [], [[2, 2]], [[2], [2]], [[True]]])
def test_completion_observer_refuses_non_eos_or_malformed_observation(value: Any) -> None:
    item = pipeline()
    generator = item.beam_search_generator
    model = generator.model
    with (
        pytest.raises(DecodeIncomplete, match="without natural EOS"),
        require_natural_completion(item),
    ):
        generator.generate_hypotheses_one_segment([value], "alignable is not complete")
    assert generator.model is model
    assert "generate_hypotheses_one_segment" not in vars(generator)


def test_completion_observer_refuses_unobserved_decoding() -> None:
    with (
        pytest.raises(DecodeIncomplete, match="without observed decoding"),
        require_natural_completion(pipeline()),
    ):
        pass


def test_completion_observer_refuses_empty_generation() -> None:
    item = pipeline()
    with (
        pytest.raises(DecodeIncomplete, match="without a sampled"),
        require_natural_completion(item),
    ):
        item.beam_search_generator.generate_hypotheses_one_segment([], "empty")


def test_completion_observer_cannot_hide_earlier_incomplete_segment() -> None:
    item = pipeline()
    with (
        pytest.raises(DecodeIncomplete, match="without natural EOS"),
        require_natural_completion(item),
    ):
        item.beam_search_generator.generate_hypotheses_one_segment([[[9095]]], "first")
        pytest.fail("An incomplete segment must halt before a later natural EOS")


def test_completion_observer_restores_after_exception() -> None:
    item = pipeline()
    generator = item.beam_search_generator
    model = generator.model
    with pytest.raises(ValueError, match="model error"), require_natural_completion(item):
        generator.generate_hypotheses_one_segment([[[2]]], "complete")
        raise ValueError("model error")
    assert generator.model is model
    assert "generate_hypotheses_one_segment" not in vars(generator)
    with (
        pytest.raises(DecodeIncomplete, match="without observed decoding"),
        require_natural_completion(item),
    ):
        pass


def test_completion_observer_refuses_configuration_replacement() -> None:
    item = pipeline()
    generator = item.beam_search_generator
    with (
        pytest.raises(DecodeIncomplete, match="configuration"),
        require_natural_completion(item),
    ):
        generator.generate_hypotheses_one_segment([[[2]]], "complete")
        generator.config = SimpleNamespace(nbest=1)


def test_completion_observer_cleanup_does_not_mask_removed_method_refusal() -> None:
    item = pipeline()
    generator = item.beam_search_generator
    model = generator.model
    with (
        pytest.raises(DecodeIncomplete, match="method changed"),
        require_natural_completion(item),
    ):
        generator.generate_hypotheses_one_segment([[[2]]], "complete")
        del generator.generate_hypotheses_one_segment
    assert generator.model is model
    assert "generate_hypotheses_one_segment" not in vars(generator)


@pytest.mark.parametrize("nbest", [0, 3, True, "1", None])
def test_completion_observer_refuses_unsupported_beams(nbest: object) -> None:
    item = pipeline()
    item.beam_search_generator.config.nbest = nbest
    with pytest.raises(DecodeIncomplete, match="one-beam"), require_natural_completion(item):
        pytest.fail("Unsupported beams must refuse before generation")


def test_completion_observer_serializes_and_restores_concurrent_contexts() -> None:
    item = pipeline()
    model = item.beam_search_generator.model

    def observe(index: int) -> int:
        with require_natural_completion(item):
            assert (
                item.beam_search_generator.generate_hypotheses_one_segment([[[2]]], index) == index
            )
        return index

    with ThreadPoolExecutor(max_workers=4) as executor:
        assert list(executor.map(observe, range(40))) == list(range(40))
    assert item.beam_search_generator.model is model
    assert "generate_hypotheses_one_segment" not in vars(item.beam_search_generator)
    assert len(model.calls) == 40


class IncompletePipeline:
    def __init__(self) -> None:
        self.beam_search_generator = Generator()

    def transcribe(self, *args: object, **kwargs: object) -> list[str]:
        self.beam_search_generator.generate_hypotheses_one_segment([[[9095]]], "speech")
        return ["speech"]


class CompletionBackend(OmniAsrBackend):
    def __init__(self) -> None:
        super().__init__()
        self.align_calls = 0
        self.draft_calls = 0
        self.beam_calls = 0

    def _load(self) -> tuple[object, object]:
        return IncompletePipeline(), object()

    def _transcribe_llm(self, item: Any, audio_path: Path) -> list[str]:
        self.draft_calls += 1
        # Simulate only the optional upstream dependency. The observer and the
        # actual backend's sequencing/refusal path remain under test.
        with require_natural_completion(item):
            result: list[str] = item.transcribe([str(audio_path)])
            return result

    def _transcribe_llm_beam(self, item: Any, audio_path: Path) -> list[str]:
        # D-332: the one retry loops too here, so the segment must still halt.
        self.beam_calls += 1
        with require_natural_completion(item):
            result: list[str] = item.transcribe([str(audio_path)])
            return result

    def _ctc_emissions(self, item: object, audio_path: Path) -> tuple[object, int, str]:
        return object(), 100, "speech"

    def _park_ctc(self, ctc: object) -> None:
        pass  # D-332 option 1: no real CTC model to move in this fake.

    def _restore_ctc(self, ctc: object) -> None:
        pass

    def _align_emissions(
        self,
        item: object,
        log_probs: object,
        frames: int,
        text: str,
        duration_s: float,
    ) -> tuple[Word, ...]:
        self.align_calls += 1
        return (Word(text, 0, 500, 0.9),)


def test_alignable_repetition_stop_is_refused_before_alignment() -> None:
    backend = CompletionBackend()
    with pytest.raises(DecodeIncomplete, match="without natural EOS"):
        backend.transcribe_segment(Path("segment.wav"), 1.0)
    assert backend.draft_calls == 1
    assert backend.beam_calls == 1
    assert backend.align_calls == 0


def test_incomplete_decode_stops_worker_before_later_segments(tmp_path: Path) -> None:
    backend = CompletionBackend()
    validator = stop_fixtures.RegionValidator()
    output = tmp_path / "output.json"
    with pytest.raises(RuntimeError, match="DecodeIncomplete.*without natural EOS"):
        run_request(stop_fixtures.worker_request(tmp_path), output, backend, validator)
    assert backend.draft_calls == 1
    assert backend.beam_calls == 1
    assert backend.align_calls == 0
    assert validator.calls == []
    assert not output.exists()


def test_native_and_source_bound_wsl_producers_share_admission_policy() -> None:
    assert OmniAsrProducer().admission_policy == WslOmniAsrProducer().admission_policy
    from hawedit.asr import ASR_COMPLETION_POLICY_ID
    from hawedit.qwen_completion import QWEN_COMPLETION_POLICY_ID

    assert WslOmniAsrProducer().admission_policy == ASR_COMPLETION_POLICY_ID
    assert ASR_COMPLETION_POLICY_ID == COMPLETION_POLICY_ID + "+" + QWEN_COMPLETION_POLICY_ID
    assert OmniAsrProducer(CompletionBackend()).admission_policy is None


def test_completion_observer_refuses_boolean_config_mutation() -> None:
    item = pipeline()
    with (
        pytest.raises(DecodeIncomplete, match="configuration"),
        require_natural_completion(item),
    ):
        item.beam_search_generator.generate_hypotheses_one_segment([[[2]]], "complete")
        item.beam_search_generator.config.nbest = True


@pytest.mark.parametrize("fault", ["version", "generator-class", "decoder-source"])
def test_canonical_entry_refuses_unvalidated_dependency_before_transcription(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    beam_name = "omnilingual_asr.models.wav2vec2_llama.beamsearch"
    model_name = "omnilingual_asr.models.wav2vec2_llama.model"
    beam = ModuleType(beam_name)
    model = ModuleType(model_name)
    monkeypatch.setattr(beam, "Wav2Vec2LlamaBeamSearchSeq2SeqGenerator", Generator, raising=False)
    monkeypatch.setattr(model, "Wav2Vec2LlamaModel", Model, raising=False)
    dependency = tmp_path / "unvalidated_dependency.py"
    dependency.write_text(
        "# Deliberately not the pinned upstream implementation\n", encoding="utf-8"
    )
    beam.__file__ = str(dependency)
    model.__file__ = str(dependency)
    monkeypatch.setitem(sys.modules, beam_name, beam)
    monkeypatch.setitem(sys.modules, model_name, model)
    monkeypatch.setattr(
        importlib.metadata, "version", lambda name: "0.3.0" if fault == "version" else "0.2.0"
    )
    item = IncompletePipeline()
    if fault == "generator-class":

        class UnsupportedGenerator(Generator):
            pass

        item.beam_search_generator = UnsupportedGenerator()
    messages = {
        "version": "not validated for this version",
        "generator-class": "Unsupported decoder",
        "decoder-source": "Installed decoder differs",
    }
    with pytest.raises(DecodeIncomplete, match=messages[fault]):
        transcribe_completed(item, tmp_path / "audio.wav", "ckb_Arab")
    assert item.beam_search_generator.model.calls == []


# --- D-332: loop guard, beam-5 retry of one segment, else an honest halt ---------------------


@pytest.mark.parametrize(
    "text",
    [
        "و و و و",
        "هەر دوو هەر دوو هەر دوو هەر دوو",
        "پێش a b c d a b c d a b c d a b c d دوای",
    ],
)
def test_loop_suspect_flags_a_unit_repeated_four_times(text: str) -> None:
    assert looped(text)
    assert loop_suspect(text, 10.0, environ={}) is not None


@pytest.mark.parametrize("text", ["ئی ئی ئی", "", "ئەمە زۆر باشە", "a b a b a b c"])
def test_loop_suspect_admits_ordinary_text_and_the_ieee_acronym(text: str) -> None:
    assert not looped(text)
    assert loop_suspect(text, 10.0, environ={}) is None


def test_loop_suspect_text_rate_threshold_and_override() -> None:
    assert loop_suspect("x" * 30, 1.0, environ={}) is None
    assert "31.0 chars/s" in str(loop_suspect("x" * 31, 1.0, environ={}))
    assert loop_suspect("x" * 31, 1.0, environ={"HAWEDIT_LOOP_MAX_CHARS_PER_S": "40"}) is None
    for bad in ("0", "-1", "nan", "fast"):
        with pytest.raises(ValueError, match="HAWEDIT_LOOP_MAX_CHARS_PER_S"):
            loop_suspect("x", 1.0, environ={"HAWEDIT_LOOP_MAX_CHARS_PER_S": bad})


class Order:
    def __init__(self, value: list[int]) -> None:
        self.value = value

    def tolist(self) -> list[int]:
        return self.value


class StateBag:
    def __init__(self) -> None:
        self.orders: list[list[int]] = []

    def reorder(self, new_order: Order) -> None:
        self.orders.append(new_order.tolist())


class BeamModel(Model):
    def llama_decoder(self, *, seqs: object, seqs_layout: object, state_bag: StateBag) -> object:
        return seqs


class BeamGenerator:
    """Drives the observer exactly as upstream orders its calls each step."""

    def __init__(self, steps: list[tuple[list[int], list[int]]], nbest: int = 5) -> None:
        self.model: Any = BeamModel()
        self.config = SimpleNamespace(nbest=nbest, compression_window=100)
        self.eos_idx = 2
        self.steps = steps
        self.bags: list[StateBag] = []

    def generate_hypotheses_one_segment(
        self, decoder_context_inputs: object, decoder_context_seq_lens: list[int]
    ) -> object:
        bag = StateBag()
        self.bags.append(bag)
        self.model.llama_decoder(seqs="prefill", seqs_layout=None, state_bag=bag)
        for order, tokens in self.steps:
            self.model.llama_decoder(seqs="step", seqs_layout=None, state_bag=bag)
            bag.reorder(Order(order))
            self.model.embed_text(Tokens([[token] for token in tokens]), dtype="unchanged")
        return "selected"


KEEP = [0, 1, 2, 3, 4]


def _beam(steps: list[tuple[list[int], list[int]]], context: int = 1) -> Any:
    item = SimpleNamespace(beam_search_generator=BeamGenerator(steps))
    with require_natural_completion(item, nbest=5):
        item.beam_search_generator.generate_hypotheses_one_segment(
            decoder_context_inputs=None, decoder_context_seq_lens=[context]
        )
    return item


def test_beam_observer_admits_a_selected_hypothesis_with_sampled_eos() -> None:
    item = _beam(
        [
            ([0, 0, 0, 0, 0], [5, 6, 7, 8, 9]),
            (KEEP, [2, 6, 7, 8, 9]),
            (KEEP, [2, 2, 2, 2, 2]),
        ]
    )
    generator = item.beam_search_generator
    assert "generate_hypotheses_one_segment" not in vars(generator)
    assert all("reorder" not in vars(bag) for bag in generator.bags)
    assert generator.bags[0].orders[-1] == KEEP, "the decoder's own reorder still ran"


def test_beam_observer_follows_ancestry_to_the_selected_row() -> None:
    _beam(
        [
            ([0, 0, 0, 0, 0], [5, 6, 7, 8, 9]),
            (KEEP, [5, 6, 7, 2, 9]),  # row 3 samples EOS
            ([3, 0, 1, 2, 4], [2, 2, 2, 2, 2]),  # and becomes the selected row 0
        ]
    )


def test_beam_observer_refuses_a_selected_row_still_decoding_at_the_limit() -> None:
    with pytest.raises(NoNaturalEos, match="selected hypothesis"):
        _beam([([0, 0, 0, 0, 0], [5, 6, 7, 8, 9]), (KEEP, [5, 2, 7, 8, 9])])


def _until(step_count: int, final: list[int]) -> list[tuple[list[int], list[int]]]:
    return [(KEEP, [5, 6, 7, 8, 9])] * (step_count - 1) + [(KEEP, final)]


def test_beam_observer_refuses_eos_that_a_compression_stop_could_have_forced() -> None:
    # Context 1: upstream's first step is t=0 and it checks compression at t=250 (> 1 + 100),
    # so an EOS first seen at t=251 cannot be told from that check's forced stop.
    with pytest.raises(NoNaturalEos, match="selected hypothesis"):
        _beam(_until(252, [2, 2, 2, 2, 2]), context=1)
    _beam(_until(251, [2, 2, 2, 2, 2]), context=1)  # t=250 itself: sampled before the check


def test_beam_observer_ignores_checks_inside_the_compression_window() -> None:
    # Context 200: first step t=199, and t=250 is not past 200 + 100, so no check can fire.
    _beam(_until(53, [2, 2, 2, 2, 2]), context=200)


def test_beam_observer_refuses_a_greedy_configured_generator() -> None:
    item = SimpleNamespace(beam_search_generator=BeamGenerator([], nbest=1))
    with pytest.raises(DecodeIncomplete, match="beam-5"), require_natural_completion(item, nbest=5):
        pytest.fail("a one-beam generator must not pass as the beam retry")


class RetryBackend(OmniAsrBackend):
    def __init__(
        self,
        greedy: object,
        beam: object,
        *,
        ctc_device: str = "cuda:1",
        restore_error: Exception | None = None,
    ) -> None:
        super().__init__()
        self.greedy, self.beam = greedy, beam
        self.calls: list[str] = []
        # Fixed rather than read from HAWEDIT_ASR_*_DEVICE, so the CTC parking path is exact.
        self.llm_device, self.ctc_device = "cuda:1", ctc_device
        self.restore_error = restore_error
        self.events: list[str] = []

    def _park_ctc(self, ctc: object) -> None:
        self.events.append("park")

    def _restore_ctc(self, ctc: object) -> None:
        self.events.append("restore")
        if self.restore_error is not None:
            raise self.restore_error

    def _load(self) -> tuple[object, object]:
        return object(), object()

    def _decode(self, outcome: object) -> list[str]:
        if isinstance(outcome, Exception):
            raise outcome
        return [str(outcome)]

    def _transcribe_llm(self, item: Any, audio_path: Path) -> list[str]:
        self.calls.append("greedy")
        return self._decode(self.greedy)

    def _transcribe_llm_beam(self, item: Any, audio_path: Path) -> list[str]:
        self.calls.append("beam5")
        self.events.append("beam5")
        return self._decode(self.beam)

    def _ctc_emissions(self, item: object, audio_path: Path) -> tuple[object, int, str]:
        self.events.append("ctc")
        return object(), 100, "ctc"

    def _align_emissions(
        self, item: object, log_probs: object, frames: int, text: str, duration_s: float
    ) -> tuple[Word, ...]:
        return tuple(Word(word, 10 * i, 10 * i + 5, 0.9) for i, word in enumerate(text.split()))


LOOP = "باشە باشە باشە باشە"


@pytest.mark.parametrize(
    ("greedy", "why"),
    [(LOOP, "repeats at least 4 times"), (NoNaturalEos("compression stop"), "no natural EOS")],
)
def test_suspect_greedy_segment_keeps_a_clean_beam_retry(greedy: object, why: str) -> None:
    backend = RetryBackend(greedy, "ئەمە زۆر باشە")
    item = backend.transcribe_segment(Path("speech-0007.wav"), 5.0)
    assert backend.calls == ["greedy", "beam5"]
    assert item.text_raw == "ئەمە زۆر باشە"
    assert item.decode_mode == "beam5_retry"
    assert item.retry_reason is not None and why in item.retry_reason


@pytest.mark.parametrize(
    "beam", [LOOP, NoNaturalEos("beam compression stop"), "x" * 400], ids=["loop", "no-eos", "rate"]
)
def test_segment_suspect_under_both_decodes_halts_naming_it(beam: object) -> None:
    backend = RetryBackend(LOOP, beam)
    with pytest.raises(DecodeIncomplete, match=r"speech-0007\.wav: greedy attempt: .*beam-5 retry"):
        backend.transcribe_segment(Path("speech-0007.wav"), 5.0)
    assert backend.calls == ["greedy", "beam5"]


def test_clean_greedy_segment_is_unchanged_and_never_retried() -> None:
    backend = RetryBackend("ئەمە زۆر باشە", AssertionError("beam must not run"))
    item = backend.transcribe_segment(Path("speech-0007.wav"), 5.0)
    assert backend.calls == ["greedy"]
    assert (item.decode_mode, item.retry_reason) == ("greedy", None)


def test_contract_refusal_is_not_retried() -> None:
    backend = RetryBackend(DecodeIncomplete("Unsupported decoder implementation"), "unused")
    with pytest.raises(DecodeIncomplete, match="Unsupported decoder"):
        backend.transcribe_segment(Path("speech-0007.wav"), 5.0)
    assert backend.calls == ["greedy"]


def test_shared_device_beam_retry_parks_ctc_on_cpu_and_restores_it() -> None:
    """D-332 option 1: the retry runs only after this segment's CTC forward has joined."""
    backend = RetryBackend(LOOP, "ئەمە زۆر باشە")
    item = backend.transcribe_segment(Path("speech-0007.wav"), 5.0)
    assert backend.events == ["ctc", "park", "beam5", "restore"]
    assert item.decode_mode == "beam5_retry"


def test_separate_devices_never_move_ctc() -> None:
    backend = RetryBackend(LOOP, "ئەمە زۆر باشە", ctc_device="cuda:0")
    item = backend.transcribe_segment(Path("speech-0007.wav"), 5.0)
    assert backend.events == ["ctc", "beam5"]
    assert item.decode_mode == "beam5_retry"


@pytest.mark.parametrize("beam", [RuntimeError("beam blew up"), LOOP], ids=["raises", "loops"])
def test_failed_beam_retry_still_restores_ctc(beam: object) -> None:
    backend = RetryBackend(LOOP, beam)
    with pytest.raises((RuntimeError, DecodeIncomplete)):
        backend.transcribe_segment(Path("speech-0007.wav"), 5.0)
    assert backend.events == ["ctc", "park", "beam5", "restore"]


def test_ctc_that_cannot_return_to_its_device_halts_the_run() -> None:
    backend = RetryBackend(LOOP, "ئەمە زۆر باشە", restore_error=RuntimeError("CUDA OOM"))
    with pytest.raises(DecodeIncomplete, match="CTC-3B could not return to cuda:1") as caught:
        backend.transcribe_segment(Path("speech-0007.wav"), 5.0)
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert backend.events == ["ctc", "park", "beam5", "restore"]


def test_clean_greedy_segment_never_moves_ctc_and_its_bytes_do_not_change() -> None:
    from hawedit.asr import _assemble_canonical_transcript, _PreparedSpeechSegment

    def artifact(backend: RetryBackend) -> str:
        item = backend.transcribe_segment(Path("speech-0007.wav"), 5.0)
        segment = _PreparedSpeechSegment(Path("speech-0007.wav"), 0, 5_000)
        return _assemble_canonical_transcript("media-001", ((segment, item),)).to_json()

    shared = RetryBackend("ئەمە زۆر باشە", AssertionError("beam must not run"))
    separate = RetryBackend(
        "ئەمە زۆر باشە", AssertionError("beam must not run"), ctc_device="cuda:0"
    )
    assert artifact(shared) == artifact(separate)
    assert shared.events == separate.events == ["ctc"]
    assert "decode_mode" not in artifact(shared)


def test_retry_provenance_reaches_the_artifact_and_greedy_bytes_do_not_change() -> None:
    from hawedit.asr import _assemble_canonical_transcript, _PreparedSpeechSegment

    greedy = RetryBackend("ئەمە زۆر باشە", "unused").transcribe_segment(Path("a.wav"), 5.0)
    retried = RetryBackend(LOOP, "ئەوە باشە").transcribe_segment(Path("b.wav"), 5.0)
    segments = (
        (_PreparedSpeechSegment(Path("a.wav"), 0, 5_000), greedy),
        (_PreparedSpeechSegment(Path("b.wav"), 5_000, 10_000), retried),
    )
    raw = _assemble_canonical_transcript("media-001", segments)
    data = json.loads(raw.to_json())
    first, second = data["segment_confidence"]
    assert "decode_mode" not in first and "retry_reason" not in first
    assert second["decode_mode"] == "beam5_retry" and "repeats" in second["retry_reason"]
    assert RawTranscript.from_json(raw.to_json()) == raw
    report = PipelineRun("media-001", "source.mp4", "work", raw_diagnostics=raw).to_dict()
    assert report["beam5_retries"] == 1


def test_retry_provenance_survives_segment_origins_and_greedy_origin_bytes() -> None:
    """D-315 origins must agree with D-332 provenance, whether or not the validator routes."""
    from hawedit.asr import (
        VALIDATOR_MODEL_ID,
        _assemble_canonical_transcript,
        _PreparedSpeechSegment,
        _validate_hard_segments,
    )

    class Validator:
        model_id = VALIDATOR_MODEL_ID

        def transcribe_segment(self, audio_path: Path, duration_s: float) -> str:
            return "ئەوە باشە"

    class RealigningBackend(RetryBackend):
        def _load_ctc(self) -> object:
            return object()

    backend = RealigningBackend(LOOP, "ئەوە باشە")
    greedy = RetryBackend("ئەمە زۆر باشە", "unused").transcribe_segment(Path("a.wav"), 5.0)
    retried = backend.transcribe_segment(Path("b.wav"), 5.0)
    results, validated_by, rejected, origins = _validate_hard_segments(
        (
            (_PreparedSpeechSegment(Path("a.wav"), 0, 5_000), greedy),
            (_PreparedSpeechSegment(Path("b.wav"), 5_000, 10_000), retried),
        ),
        backend,
        Validator,
        stop_on_failure=True,
    )
    raw = _assemble_canonical_transcript(
        "media-001",
        results,
        validated_by=validated_by,
        rejected_validator_corrections=rejected,
        segment_origins=origins,
    )
    assert raw.segment_origins is not None
    assert [o.selected.decode_mode for o in raw.segment_origins] == ["greedy", "beam5_retry"]
    assert raw.segment_origins[1].draft.retry_reason == retried.retry_reason
    data = json.loads(raw.to_json())
    first = data["segment_origins"][0]
    for key in ("draft", "selected"):
        assert "decode_mode" not in first[key] and "retry_reason" not in first[key]
    assert data["segment_origins"][1]["selected"]["decode_mode"] == "beam5_retry"
    assert RawTranscript.from_json(raw.to_json()) == raw


def test_loop_guard_policy_refuses_single_beam_cache_records(tmp_path: Path) -> None:
    assert COMPLETION_POLICY_ID.startswith("omni-natural-eos-greedy-beam5-retry-v1:")
    old = COMPLETION_POLICY_ID.replace(
        "omni-natural-eos-greedy-beam5-retry-v1", "omni-natural-eos-single-beam-v1"
    )
    store = TranscriptStore(tmp_path)
    store.write_raw(
        transcript_fixtures.a_raw(), audio_sha256="audio", producer="producer", admission_policy=old
    )
    with pytest.raises(RawTranscriptImmutable):
        store.reusable_raw(
            "media-001",
            "audio",
            "producer",
            transcript_fixtures.MEDIA_SHA256,
            admission_policy=WslOmniAsrProducer().admission_policy,
        )
