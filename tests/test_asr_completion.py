"""Test-first mechanical completion contract, not speech accuracy evidence."""

from __future__ import annotations

import importlib.metadata
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

import test_asr_stop as stop_fixtures
from hawedit.asr import OmniAsrBackend, OmniAsrProducer, WslOmniAsrProducer
from hawedit.asr_completion import (
    COMPLETION_POLICY_ID,
    DecodeIncomplete,
    require_natural_completion,
    transcribe_completed,
)
from hawedit.asr_worker import run_request
from hawedit.transcripts import Word


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

    def _load(self) -> tuple[object, object]:
        return IncompletePipeline(), object()

    def _transcribe_llm(self, item: Any, audio_path: Path) -> list[str]:
        self.draft_calls += 1
        # Simulate only the optional upstream dependency. The observer and the
        # actual backend's sequencing/refusal path remain under test.
        with require_natural_completion(item):
            result: list[str] = item.transcribe([str(audio_path)])
            return result

    def _ctc_emissions(self, item: object, audio_path: Path) -> tuple[object, int, str]:
        return object(), 100, "speech"

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
    assert backend.align_calls == 0


def test_incomplete_decode_stops_worker_before_later_segments(tmp_path: Path) -> None:
    backend = CompletionBackend()
    validator = stop_fixtures.RegionValidator()
    output = tmp_path / "output.json"
    with pytest.raises(RuntimeError, match="DecodeIncomplete.*without natural EOS"):
        run_request(stop_fixtures.worker_request(tmp_path), output, backend, validator)
    assert backend.draft_calls == 1
    assert backend.align_calls == 0
    assert validator.calls == []
    assert not output.exists()


def test_native_and_source_bound_wsl_producers_share_admission_policy() -> None:
    assert OmniAsrProducer().admission_policy == WslOmniAsrProducer().admission_policy
    assert WslOmniAsrProducer().admission_policy == COMPLETION_POLICY_ID
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
