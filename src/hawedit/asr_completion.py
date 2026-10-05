"""Fail-stop completion admission for the validated canonical decoder (D-281)."""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import inspect
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class DecodeIncomplete(RuntimeError):
    """Decoding did not demonstrate natural completion; alignment is not admission."""


_LOCK = threading.RLock()
_ABSENT = object()
_DECODER_SHA256 = "91233570765a2fbd3199f3b65508e53b1be0199cf9e33bcddf9c9b9c2f575481"
_MODEL_SHA256 = "2396193455d10a5d43e0d2904c1714677fded7f714f14f1c1bf284bbfeffd8e4"
COMPLETION_POLICY_ID = f"omni-natural-eos-single-beam-v1:{_DECODER_SHA256}:{_MODEL_SHA256}"


def transcribe_completed(pipeline: Any, audio_path: Path, language: str) -> Any:
    # Validation and temporary bindings share the lock: another valid request must
    # not mistake the first request's observation proxy for an unsupported model.
    with _LOCK:
        module = importlib.import_module("omnilingual_asr.models.wav2vec2_llama.beamsearch")
        model_module = importlib.import_module("omnilingual_asr.models.wav2vec2_llama.model")
        generator = getattr(pipeline, "beam_search_generator", None)
        if importlib.metadata.version("omnilingual-asr") != "0.2.0":
            raise DecodeIncomplete("Decoder completion contract is not validated for this version")
        if type(generator) is not module.Wav2Vec2LlamaBeamSearchSeq2SeqGenerator:
            raise DecodeIncomplete("Unsupported decoder implementation")
        with Path(inspect.getfile(module)).open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != _DECODER_SHA256:
            raise DecodeIncomplete(
                "Installed decoder differs from the validated completion contract"
            )
        with Path(inspect.getfile(model_module)).open("rb") as stream:
            model_digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if (
            model_digest != _MODEL_SHA256
            or type(generator.model) is not model_module.Wav2Vec2LlamaModel
        ):
            raise DecodeIncomplete("Model embedding differs from the validated completion contract")
        if "generate_hypotheses_one_segment" in vars(generator):
            raise DecodeIncomplete("Decoder generation method was already overridden")
        with require_natural_completion(pipeline):
            return pipeline.transcribe([str(audio_path)], lang=[language], batch_size=1)


class _ObservedModel:
    def __init__(self, original: Any) -> None:
        self.original = original
        self.last_tokens: Any = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self.original, name)

    def embed_text(self, seqs: Any, dtype: Any) -> Any:
        result = self.original.embed_text(seqs, dtype=dtype)
        self.last_tokens = seqs
        return result


@contextmanager
def require_natural_completion(pipeline: Any) -> Iterator[None]:
    """Observe each existing single-beam generation without changing its algorithm."""
    with _LOCK:
        generator = getattr(pipeline, "beam_search_generator", None)
        if generator is None:
            raise DecodeIncomplete("Decoder completion observation contract is unavailable")
        config = getattr(generator, "config", None)
        if config is None or type(getattr(config, "nbest", None)) is not int or config.nbest != 1:
            raise DecodeIncomplete(
                "Completion observation supports the validated one-beam decoder only"
            )
        eos = getattr(generator, "eos_idx", None)
        if type(eos) is not int or eos < 0:
            raise DecodeIncomplete("Decoder EOS identity is unavailable")
        model = getattr(generator, "model", None)
        method = getattr(generator, "generate_hypotheses_one_segment", None)
        if (
            model is None
            or not callable(method)
            or not callable(getattr(model, "embed_text", None))
        ):
            raise DecodeIncomplete("Decoder completion observation contract is unavailable")
        config_values = dict(vars(config))
        old_override = vars(generator).get("generate_hypotheses_one_segment", _ABSENT)
        calls = 0

        def check_configuration() -> None:
            if (
                pipeline.beam_search_generator is not generator
                or generator.config is not config
                or vars(config) != config_values
                or type(getattr(config, "nbest", None)) is not int
                or type(generator.eos_idx) is not int
                or generator.eos_idx != eos
            ):
                raise DecodeIncomplete("Decoder identity/configuration changed during observation")

        def checked(*args: Any, **kwargs: Any) -> Any:
            nonlocal calls
            check_configuration()
            if generator.model is not model:
                raise DecodeIncomplete("Decoder model changed before observation")
            observed = _ObservedModel(model)
            generator.model = observed
            try:
                result = method(*args, **kwargs)
                if generator.model is not observed:
                    raise DecodeIncomplete("Decoder model changed during observation")
                if observed.last_tokens is None:
                    raise DecodeIncomplete("Decoder returned without a sampled completion token")
                tokens = observed.last_tokens.detach().cpu().tolist()
                if (
                    not isinstance(tokens, list)
                    or len(tokens) != 1
                    or not isinstance(tokens[0], list)
                    or len(tokens[0]) != 1
                    or type(tokens[0][0]) is not int
                    or tokens[0][0] != eos
                ):
                    raise DecodeIncomplete(
                        "Decoder returned without natural EOS; repetition/length stopping "
                        "is not transcription completion"
                    )
                check_configuration()
                calls += 1
                return result
            finally:
                generator.model = model

        generator.generate_hypotheses_one_segment = checked
        try:
            yield
            check_configuration()
            if generator.generate_hypotheses_one_segment is not checked:
                raise DecodeIncomplete("Decoder generation method changed during observation")
            if generator.model is not model:
                raise DecodeIncomplete("Decoder model changed after observation")
            if calls == 0:
                raise DecodeIncomplete("Pipeline returned without observed decoding")
        finally:
            generator.model = model
            if old_override is _ABSENT:
                vars(generator).pop("generate_hypotheses_one_segment", None)
            else:
                generator.generate_hypotheses_one_segment = old_override
