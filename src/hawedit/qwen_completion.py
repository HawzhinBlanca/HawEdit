"""Fail-stop observation of the pinned validator's original tokens (D-324)."""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import inspect
import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from hawedit.asr_completion import DecodeIncomplete

_LOCK = threading.RLock()
_EOS = (151645, 151643)
_CAP = 512
_SOURCES = {
    "qwen-asr": {
        "qwen_asr/inference/qwen3_asr.py": (
            "0b1770f8e907b6c5a0a1e9ebce037cb63f48555f3cd15eaf6ea2078e9df41a7b"
        ),
        "qwen_asr/core/transformers_backend/modeling_qwen3_asr.py": (
            "2fb5d98da1933748f5117ee05ce4e7150c9ead8154fb8e25f7af3968b853adc7"
        ),
    },
    "transformers": {
        "transformers/generation/utils.py": (
            "55fd5c50aa785e226afa03e4507b8d27c0328714c0bd048bc60af9e8813a1173"
        ),
        "transformers/generation/configuration_utils.py": (
            "d83f2281f939402be1633a29f3c760e29f5d2f284258d8ed99693b873744074b"
        ),
        "transformers/generation/stopping_criteria.py": (
            "495628e4c877f667fbbd9ed4cc83b680de9eac2abc97ec3903f6e9219af3ecd2"
        ),
        "transformers/generation/logits_process.py": (
            "6481506629ff6f021157e893fc64c4e7b5b06a72072771809d679387cb54a4b1"
        ),
    },
}
QWEN_COMPLETION_POLICY_ID = (
    "qwen-natural-eos-greedy-before512-v2:"
    + hashlib.sha256(
        json.dumps(_SOURCES, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()
)


def assert_qwen_runtime() -> dict[str, Path]:
    """Verify installed files before importing the vendor; not a security approval."""
    paths: dict[str, Path] = {}
    try:
        if (
            importlib.metadata.version("qwen-asr") != "0.0.6"
            or importlib.metadata.version("transformers") != "4.57.6"
            or importlib.metadata.version("torch") not in {"2.8.0", "2.8.0+cu128"}
        ):
            raise DecodeIncomplete("Validator completion runtime version is not validated")
        for distribution, sources in _SOURCES.items():
            installed = importlib.metadata.distribution(distribution)
            for relative, expected in sources.items():
                path = Path(str(installed.locate_file(relative))).resolve(strict=True)
                with path.open("rb") as stream:
                    actual = hashlib.file_digest(stream, "sha256").hexdigest()
                if actual != expected:
                    raise DecodeIncomplete(
                        "Validator completion source differs from pinned contract"
                    )
                paths[relative] = path
    except (importlib.metadata.PackageNotFoundError, OSError) as exc:
        raise DecodeIncomplete("Validated validator completion runtime is unavailable") from exc
    return paths


def _method_at(value: Any, name: str, path: Path) -> bool:
    method = getattr(value, name, None)
    try:
        return (
            name not in vars(value)
            and callable(method)
            and Path(inspect.getfile(inspect.unwrap(method))).resolve() == path
        )
    except (TypeError, ValueError, OSError):
        return False


def transcribe_qwen_completed(sdk: Any, audio: Any) -> Any:
    """Only the genuine pinned SDK can turn observation into production admission."""
    with _LOCK:
        paths = assert_qwen_runtime()
        sdk_module = importlib.import_module("qwen_asr.inference.qwen3_asr")
        model_module = importlib.import_module(
            "qwen_asr.core.transformers_backend.modeling_qwen3_asr"
        )
        config_module = importlib.import_module("transformers.generation.configuration_utils")
        for module, relative in (
            (sdk_module, "qwen_asr/inference/qwen3_asr.py"),
            (model_module, "qwen_asr/core/transformers_backend/modeling_qwen3_asr.py"),
            (config_module, "transformers/generation/configuration_utils.py"),
        ):
            if Path(inspect.getfile(module)).resolve() != paths[relative]:
                raise DecodeIncomplete("Imported validator differs from installed contract")
        base = getattr(sdk, "model", None)
        thinker = getattr(base, "thinker", None)
        if (
            type(sdk) is not sdk_module.Qwen3ASRModel
            or type(base) is not model_module.Qwen3ASRForConditionalGeneration
            or type(thinker) is not model_module.Qwen3ASRThinkerForConditionalGeneration
            or type(getattr(thinker, "generation_config", None))
            is not config_module.GenerationConfig
            or not _method_at(sdk, "transcribe", paths["qwen_asr/inference/qwen3_asr.py"])
            or not _method_at(
                sdk, "_infer_asr_transformers", paths["qwen_asr/inference/qwen3_asr.py"]
            )
            or not _method_at(
                base, "generate", paths["qwen_asr/core/transformers_backend/modeling_qwen3_asr.py"]
            )
            or not _method_at(thinker, "generate", paths["transformers/generation/utils.py"])
            or not _method_at(
                thinker.generation_config,
                "to_dict",
                paths["transformers/generation/configuration_utils.py"],
            )
        ):
            raise DecodeIncomplete("Unsupported validator generation implementation")
        if inspect.signature(base.generate).parameters["eos_token_id"].default != list(_EOS):
            raise DecodeIncomplete("Validator EOS signature differs from pinned contract")
        with require_qwen_completion(sdk):
            return sdk.transcribe(audio=audio)


def _configuration(config: Any) -> str:
    try:
        values = config.to_dict()
        if not isinstance(values, dict):
            raise ValueError("configuration must be a dictionary")
        if type(values.get("do_sample")) is not bool or values["do_sample"]:
            raise ValueError("only greedy generation is supported")
        for name in ("num_beams", "num_beam_groups", "num_return_sequences"):
            if type(values.get(name)) is not int or values[name] != 1:
                raise ValueError("only one beam/sequence is supported")
        for name in (
            "forced_eos_token_id",
            "forced_bos_token_id",
            "forced_decoder_ids",
            "max_time",
            "stop_strings",
            "constraints",
            "force_words_ids",
            "penalty_alpha",
            "prompt_lookup_num_tokens",
            "assistant_early_exit",
            "dola_layers",
            "watermarking_config",
            "exponential_decay_length_penalty",
        ):
            if values.get(name) is not None:
                raise ValueError("unsupported forced/custom stopping configuration")
        # JSON preserves the difference between True and 1, unlike dictionary equality.
        return json.dumps(values, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (AttributeError, TypeError, ValueError) as exc:
        raise DecodeIncomplete("Unsupported validator generation configuration") from exc


def _tokens(tensor: Any) -> list[int]:
    try:
        rows = tensor.detach().cpu().tolist()
        if (
            not isinstance(rows, list)
            or len(rows) != 1
            or not isinstance(rows[0], list)
            or not rows[0]
            or any(type(token) is not int or token < 0 for token in rows[0])
        ):
            raise ValueError("expected one nonempty integer token row")
        return rows[0]
    except (AttributeError, TypeError, ValueError, RuntimeError) as exc:
        raise DecodeIncomplete("Validator completion token evidence is malformed") from exc


@contextmanager
def require_qwen_completion(sdk: Any) -> Iterator[None]:
    """Mechanical observer. Production additionally requires pinned source/types above."""
    with _LOCK:
        base = getattr(sdk, "model", None)
        thinker = getattr(base, "thinker", None)
        config = getattr(thinker, "generation_config", None)
        method = getattr(base, "generate", None)
        if base is None or not callable(method) or "generate" in vars(base):
            raise DecodeIncomplete("Validator generation observation is unavailable or overridden")
        frozen = _configuration(config)
        thinker_generate = getattr(thinker, "generate", None)
        calls = 0
        completed = 0

        def check() -> None:
            if (
                sdk.model is not base
                or base.thinker is not thinker
                or thinker.generation_config is not config
                or _configuration(config) != frozen
                or getattr(thinker, "generate", None) != thinker_generate
                or getattr(sdk, "backend", None) != "transformers"
                or type(getattr(sdk, "max_new_tokens", None)) is not int
                or sdk.max_new_tokens != _CAP
                or type(getattr(sdk, "max_inference_batch_size", None)) is not int
                or sdk.max_inference_batch_size != 1
                or getattr(sdk, "forced_aligner", None) is not None
                or getattr(sdk, "sampling_params", None) is not None
            ):
                raise DecodeIncomplete("Validator identity/configuration changed or is unsupported")

        def checked(*args: Any, **kwargs: Any) -> Any:
            nonlocal calls, completed
            calls += 1
            check()
            if (
                args
                or not {"input_ids", "max_new_tokens"}.issubset(kwargs)
                or set(kwargs)
                - {
                    "input_ids",
                    "max_new_tokens",
                    "attention_mask",
                    "feature_attention_mask",
                    "input_features",
                }
                or type(kwargs["max_new_tokens"]) is not int
                or kwargs["max_new_tokens"] != _CAP
                or calls != 1
            ):
                raise DecodeIncomplete("Unsupported validator generation arguments/call count")
            prefix = _tokens(kwargs["input_ids"])
            result = method(**kwargs)
            check()
            if base.generate is not checked or _tokens(kwargs["input_ids"]) != prefix:
                raise DecodeIncomplete("Validator generation method changed during observation")
            tokens = _tokens(getattr(result, "sequences", None))
            generated = tokens[len(prefix) :]
            if (
                tokens[: len(prefix)] != prefix
                or not generated
                or len(generated) >= _CAP
                or generated[-1] not in _EOS
                or any(token in _EOS for token in generated[:-1])
            ):
                raise DecodeIncomplete(
                    "Validator returned without unambiguous natural EOS before cap"
                )
            completed += 1
            return result

        check()
        base.generate = checked
        try:
            yield
            check()
            if calls != 1 or completed != 1 or base.generate is not checked:
                raise DecodeIncomplete("Validator returned without exactly one observed generation")
        finally:
            vars(base).pop("generate", None)
