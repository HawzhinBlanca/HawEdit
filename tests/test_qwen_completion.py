"""Actual token-admission logic with controlled generation, not model accuracy."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import torch

from hawedit.asr import QwenSoraniValidator
from hawedit.asr_completion import DecodeIncomplete
from hawedit.qwen_completion import require_qwen_completion


class Configuration:
    def __init__(self) -> None:
        self.values: dict[str, Any] = {
            "do_sample": False,
            "num_beams": 1,
            "num_beam_groups": 1,
            "num_return_sequences": 1,
            "forced_eos_token_id": None,
            "forced_bos_token_id": None,
            "max_time": None,
            "stop_strings": None,
            "constraints": None,
            "force_words_ids": None,
            "penalty_alpha": None,
        }

    def to_dict(self) -> dict[str, Any]:
        return dict(self.values)


class Generator:
    def __init__(self, tokens: object = None) -> None:
        self.thinker = SimpleNamespace(generation_config=Configuration())
        self.tokens = [[8, 9, 10, 151645]] if tokens is None else tokens
        self.calls: list[dict[str, Any]] = []
        self.during: Callable[[], None] = lambda: None
        self.result: Any = None

    def generate(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        self.during()
        self.result = SimpleNamespace(sequences=torch.tensor(self.tokens))
        return self.result


def sdk(tokens: object = None) -> SimpleNamespace:
    return SimpleNamespace(
        model=Generator(tokens),
        backend="transformers",
        max_new_tokens=512,
        max_inference_batch_size=1,
        forced_aligner=None,
        sampling_params=None,
    )


def generate(value: Any, **extra: Any) -> Any:
    return value.model.generate(input_ids=torch.tensor([[8, 9]]), max_new_tokens=512, **extra)


def test_qwen_observer_admits_original_natural_eos() -> None:
    value = sdk()
    original = value.model.generate
    with require_qwen_completion(value):
        result = generate(value)
        assert result is value.model.result
    assert value.model.generate == original
    assert "generate" not in vars(value.model)
    assert len(value.model.calls) == 1
    assert value.model.calls[0]["max_new_tokens"] == 512


@pytest.mark.parametrize(
    "tokens",
    [
        [[8, 9]],
        [[8, 9, 10]],
        [[8, 7, 10, 151645]],
        [[8, 9, 151645, 151645]],
        [[8, 9, 10, True]],
        [[8, 9, 10, 151645], [8, 9, 10, 151645]],
        [[8, 9] + [10] * 511 + [151645]],
        [[8, 9] + [10] * 513 + [151645]],
        [[8.0, 9.0, 10.0, 151645.0]],
        [[8, 9, -1, 151645]],
    ],
)
def test_qwen_observer_refuses_invalid_sequences(tokens: object) -> None:
    value = sdk(tokens)
    original = value.model.generate
    with pytest.raises(DecodeIncomplete), require_qwen_completion(value):
        generate(value)
    assert value.model.generate == original
    assert "generate" not in vars(value.model)


@pytest.mark.parametrize("calls", [0, 2])
def test_qwen_observer_requires_one_generation(calls: int) -> None:
    value = sdk()
    with pytest.raises(DecodeIncomplete), require_qwen_completion(value):
        for _ in range(calls):
            generate(value)
    assert "generate" not in vars(value.model)


@pytest.mark.parametrize(
    "name,bad",
    [
        ("do_sample", True),
        ("do_sample", 0),
        ("num_beams", 2),
        ("num_beams", True),
        ("num_beam_groups", 2),
        ("num_return_sequences", 2),
        ("forced_eos_token_id", 151645),
        ("forced_bos_token_id", 1),
        ("stop_strings", ["end"]),
        ("max_time", 1.0),
        ("constraints", [1]),
        ("force_words_ids", [[151645]]),
        ("penalty_alpha", 0.5),
    ],
)
def test_qwen_observer_refuses_configuration(name: str, bad: object) -> None:
    value = sdk()
    value.model.thinker.generation_config.values[name] = bad
    with pytest.raises(DecodeIncomplete), require_qwen_completion(value):
        pytest.fail("unsupported configuration entered observation")
    assert value.model.calls == []
    assert "generate" not in vars(value.model)


@pytest.mark.parametrize(
    "extra",
    [
        {"stopping_criteria": []},
        {"logits_processor": []},
        {"eos_token_id": 151645},
        {"custom_generate": "remote/code"},
        {"generation_config": object()},
        {"do_sample": False},
        {"max_time": None},
    ],
)
def test_qwen_observer_refuses_unvalidated_forwarded_options(extra: dict[str, Any]) -> None:
    value = sdk()
    with pytest.raises(DecodeIncomplete), require_qwen_completion(value):
        generate(value, **extra)
    assert value.model.calls == []


@pytest.mark.parametrize("mutation", ["config", "model", "thinker", "cap", "generate"])
def test_qwen_observer_refuses_mutation(mutation: str) -> None:
    value = sdk()
    original_model = value.model

    def mutate() -> None:
        if mutation == "config":
            original_model.thinker.generation_config.values["num_beams"] = True
        elif mutation == "model":
            value.model = Generator()
        elif mutation == "thinker":
            original_model.thinker = SimpleNamespace(generation_config=Configuration())
        elif mutation == "cap":
            value.max_new_tokens = 1024
        else:
            original_model.generate = lambda **_: original_model.result

    original_model.during = mutate
    with pytest.raises(DecodeIncomplete), require_qwen_completion(value):
        generate(value)
    assert "generate" not in vars(original_model)


def test_qwen_observer_restores_after_exception() -> None:
    value = sdk()
    failure = RuntimeError("genuine generator failure")

    def fail() -> None:
        raise failure

    value.model.during = fail
    with pytest.raises(RuntimeError) as caught, require_qwen_completion(value):
        generate(value)
    assert caught.value is failure
    assert "generate" not in vars(value.model)


@pytest.mark.parametrize("bad", ["tokens", "arguments", "second-call"])
def test_qwen_observer_refuses_swallowed_generation_failure(bad: str) -> None:
    value = sdk([[8, 9, 10]] if bad == "tokens" else None)
    with pytest.raises(DecodeIncomplete), require_qwen_completion(value):
        if bad == "second-call":
            generate(value)
        with suppress(DecodeIncomplete):
            generate(value, **({"stopping_criteria": []} if bad == "arguments" else {}))
    assert "generate" not in vars(value.model)


def test_qwen_observer_refuses_changed_input_tensor() -> None:
    value = sdk()
    ids = torch.tensor([[8, 9]])
    value.model.during = lambda: ids.fill_(7)
    with pytest.raises(DecodeIncomplete), require_qwen_completion(value):
        value.model.generate(input_ids=ids, max_new_tokens=512)


def test_qwen_public_validator_refuses_unvalidated_dependency(tmp_path: Path) -> None:
    model_dir = tmp_path / "validator"
    model_dir.mkdir()
    audio = tmp_path / "speech.wav"
    audio.write_bytes(b"not-inference-evidence")
    calls: list[object] = []

    class TextOnly:
        def transcribe(self, **kwargs: object) -> list[SimpleNamespace]:
            calls.append(kwargs)
            return [SimpleNamespace(text="nonempty is not EOS evidence")]

    validator = QwenSoraniValidator(model_dir)
    validator._model = TextOnly()
    with pytest.raises(DecodeIncomplete):
        validator.transcribe_segment(audio, 1.0)
    assert calls == []


@pytest.mark.parametrize("ids", [[], [[8, 9], [8, 9]], [[8.0, 9.0]], [[True, False]]])
def test_qwen_observer_refuses_malformed_prompt(ids: object) -> None:
    value = sdk()
    with pytest.raises(DecodeIncomplete), require_qwen_completion(value):
        value.model.generate(input_ids=torch.tensor(ids), max_new_tokens=512)
    assert value.model.calls == []


@pytest.mark.parametrize(
    "field,bad",
    [
        ("backend", "vllm"),
        ("max_new_tokens", 1024),
        ("max_new_tokens", True),
        ("max_inference_batch_size", 2),
        ("forced_aligner", object()),
        ("sampling_params", object()),
    ],
)
def test_qwen_observer_refuses_unvalidated_sdk_settings(field: str, bad: object) -> None:
    value = sdk()
    setattr(value, field, bad)
    with pytest.raises(DecodeIncomplete), require_qwen_completion(value):
        pytest.fail("unsupported SDK settings must refuse before inference")
    assert value.model.calls == []
