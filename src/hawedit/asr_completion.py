"""Fail-stop completion admission for the validated canonical decoder (D-281, D-332)."""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import inspect
import operator
import os
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class DecodeIncomplete(RuntimeError):
    """Decoding did not demonstrate natural completion; alignment is not admission."""


class NoNaturalEos(DecodeIncomplete):
    """The selected hypothesis stopped without a sampled natural EOS (repetition/length stop).

    The only failure D-332's beam retry answers; contract failures never retry.
    """


_LOCK = threading.RLock()
_ABSENT = object()
_DECODER_SHA256 = "91233570765a2fbd3199f3b65508e53b1be0199cf9e33bcddf9c9b9c2f575481"
_MODEL_SHA256 = "2396193455d10a5d43e0d2904c1714677fded7f714f14f1c1bf284bbfeffd8e4"
COMPLETION_POLICY_ID = f"omni-natural-eos-greedy-beam5-retry-v1:{_DECODER_SHA256}:{_MODEL_SHA256}"
# D-332: the one retry decodes the same segment with the omniasr production beam width.
BEAM_RETRY_NBEST = 5
# Upstream beamsearch.py checks compression every 250 steps (literal, pinned by the hash above).
_COMPRESSION_CHECK_EVERY = 250
LOOP_MAX_CHARS_PER_S_ENV = "HAWEDIT_LOOP_MAX_CHARS_PER_S"
# Measured reference text peaks at 19.3 chars/s (Hawzhin TTS) and 14.9 (FLEURS); research.md.
DEFAULT_LOOP_MAX_CHARS_PER_S = 30.0


def looped(text: str, reps: int = 4, max_unit: int = 4) -> bool:
    """A unit of 1..max_unit words repeated at least ``reps`` times in a row (research.md).

    0 of 3,726 benchmark references match at 4 repeats; 3 repeats flags a spelled acronym.
    """
    w = text.split()
    for u in range(1, max_unit + 1):
        for i in range(len(w) - u * reps + 1):
            if all(w[i + k * u : i + (k + 1) * u] == w[i : i + u] for k in range(1, reps)):
                return True
    return False


def loop_suspect(
    text: str, duration_s: float, environ: Mapping[str, str] = os.environ
) -> str | None:
    """Why a naturally completed segment still reads as a loop, or ``None`` (D-332)."""
    raw = environ.get(LOOP_MAX_CHARS_PER_S_ENV, "").strip()
    try:
        limit = float(raw) if raw else DEFAULT_LOOP_MAX_CHARS_PER_S
    except ValueError:
        limit = float("nan")
    if not limit > 0:
        raise ValueError(f"{LOOP_MAX_CHARS_PER_S_ENV} must be a positive number, got {raw!r}")
    if looped(text):
        return "a 1-4 word unit repeats at least 4 times in a row"
    rate = len(text) / duration_s
    if rate > limit:
        return f"{rate:.1f} chars/s exceeds {LOOP_MAX_CHARS_PER_S_ENV}={limit:g}"
    return None


def transcribe_completed(pipeline: Any, audio_path: Path, language: str, *, nbest: int = 1) -> Any:
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
        with require_natural_completion(pipeline, nbest=nbest):
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


class _ObservedBeamModel(_ObservedModel):
    """Follow beam ancestry through the generation's own state-bag reorders (D-332).

    Upstream keeps the selected hypothesis in row 0 after the last reorder. Rows are
    permuted every step, so only the recorded reorders can say which row's EOS it inherited.
    Hooks live on this proxy and on that one call's local state bag; nothing global.
    """

    def __init__(self, original: Any) -> None:
        super().__init__(original)
        self.bags: list[Any] = []
        self.pending: list[list[int]] = []
        self.steps: list[tuple[list[list[int]], Any]] = []

    def llama_decoder(self, *args: Any, **kwargs: Any) -> Any:
        bag = kwargs.get("state_bag")
        if bag is not None and not any(bag is seen for seen in self.bags):
            reorder = bag.reorder

            def recorded(new_order: Any) -> Any:
                self.pending.append(new_order.tolist())
                return reorder(new_order)

            bag.reorder = recorded
            self.bags.append(bag)
        return self.original.llama_decoder(*args, **kwargs)

    def embed_text(self, seqs: Any, dtype: Any) -> Any:
        result = self.original.embed_text(seqs, dtype=dtype)
        self.last_tokens = seqs
        self.steps.append((self.pending, seqs.detach().cpu().tolist()))
        self.pending = []
        return result

    def release(self) -> None:
        for bag in self.bags:
            vars(bag).pop("reorder", None)

    def selected_ended_naturally(self, context_len: int, nbest: int, eos: int, window: int) -> bool:
        """Row 0 must hold an EOS it sampled, not one a compression stop forced."""
        if not self.steps:
            return False
        state = ["active"] * nbest
        step = context_len - 1  # upstream's first decoding step for one segment
        for orders, tokens in self.steps:
            if (
                len(orders) != 1
                or len(orders[0]) != nbest
                or any(type(row) is not int or not 0 <= row < nbest for row in orders[0])
                or not isinstance(tokens, list)
                or len(tokens) != nbest
                or any(
                    not isinstance(row, list) or len(row) != 1 or type(row[0]) is not int
                    for row in tokens
                )
            ):
                return False
            state = [state[parent] for parent in orders[0]]
            # An EOS first seen right after a compression check may be that check's forced stop.
            ambiguous = (step - 1) % _COMPRESSION_CHECK_EVERY == 0 and step - 1 > (
                context_len + window
            )
            for row, (token,) in enumerate(tokens):
                if state[row] != "active":
                    if token != eos:
                        return False
                elif token == eos:
                    state[row] = "unproven" if ambiguous else "natural"
            step += 1
        return state[0] == "natural"


def _one_length(value: Any) -> int | None:
    """One batch row's context length; upstream may hand a 0-d integer tensor."""
    if not isinstance(value, list | tuple) or len(value) != 1 or isinstance(value[0], bool):
        return None
    try:
        return operator.index(value[0])
    except TypeError:
        return None


@contextmanager
def require_natural_completion(pipeline: Any, *, nbest: int = 1) -> Iterator[None]:
    """Observe each existing generation without changing its algorithm.

    ``nbest=1`` is D-281's greedy contract; ``BEAM_RETRY_NBEST`` is D-332's beam variant.
    """
    with _LOCK:
        generator = getattr(pipeline, "beam_search_generator", None)
        if generator is None:
            raise DecodeIncomplete("Decoder completion observation contract is unavailable")
        config = getattr(generator, "config", None)
        if (
            nbest not in (1, BEAM_RETRY_NBEST)
            or config is None
            or type(getattr(config, "nbest", None)) is not int
            or config.nbest != nbest
        ):
            raise DecodeIncomplete(
                "Completion observation supports the validated one-beam decoder only"
                if nbest == 1
                else "Completion observation supports the validated beam-5 retry decoder only"
            )
        window = getattr(config, "compression_window", None)
        if nbest != 1 and (type(window) is not int or window < 0):
            raise DecodeIncomplete("Beam decoder compression window is unavailable")
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
            observed = _ObservedModel(model) if nbest == 1 else _ObservedBeamModel(model)
            context_len = _one_length(kwargs.get("decoder_context_seq_lens"))
            if nbest != 1 and context_len is None:
                raise DecodeIncomplete("Beam observation needs one segment's context length")
            beam_window = window if type(window) is int else 0
            generator.model = observed
            try:
                result = method(*args, **kwargs)
                if generator.model is not observed:
                    raise DecodeIncomplete("Decoder model changed during observation")
                if observed.last_tokens is None:
                    raise NoNaturalEos("Decoder returned without a sampled completion token")
                if isinstance(observed, _ObservedBeamModel):
                    if context_len is None or not observed.selected_ended_naturally(
                        context_len, nbest, eos, beam_window
                    ):
                        raise NoNaturalEos(
                            "Beam decoder's selected hypothesis did not end on a sampled natural "
                            "EOS; repetition/length stopping is not transcription completion"
                        )
                else:
                    tokens = observed.last_tokens.detach().cpu().tolist()
                    if (
                        not isinstance(tokens, list)
                        or len(tokens) != 1
                        or not isinstance(tokens[0], list)
                        or len(tokens[0]) != 1
                        or type(tokens[0][0]) is not int
                        or tokens[0][0] != eos
                    ):
                        raise NoNaturalEos(
                            "Decoder returned without natural EOS; repetition/length stopping "
                            "is not transcription completion"
                        )
                check_configuration()
                calls += 1
                return result
            finally:
                generator.model = model
                if isinstance(observed, _ObservedBeamModel):
                    observed.release()

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
