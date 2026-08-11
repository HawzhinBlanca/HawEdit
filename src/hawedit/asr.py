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
canonical LLM-7B + CTC-3B producer is implemented locally and through WSL2; real benchmark
claims still require the package-managed assets and labelled Sorani audio.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Final, Protocol, runtime_checkable

from hawedit.captions import find_ffmpeg
from hawedit.corpus import CorpusItem
from hawedit.forced_alignment import align_words, collapse_ctc_path
from hawedit.registry import ASR_ROLES, ModelEntry, resolve_role
from hawedit.transcripts import (
    AsrProvenance,
    RawTranscript,
    SegmentConfidence,
    UnalignedSpeech,
    Word,
)
from hawedit.wsl_setup import _prefix as wsl_prefix
from hawedit.wsl_setup import default_wsl_runtime, default_wsl_source, wsl_path

__all__ = [
    "LONG_AUDIO_THRESHOLD_S",
    "ASRAdapter",
    "ASRResult",
    "CanonicalTranscriptProducer",
    "Hardware",
    "IncomparableHardware",
    "Measurement",
    "MeasurementSession",
    "OmniAsrAdapter",
    "OmniAsrBackend",
    "OmniAsrProducer",
    "SegmentTranscript",
    "WslOmniAsrProducer",
    "create_omni_asr_producer",
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


@dataclass(frozen=True, slots=True)
class SegmentTranscript:
    """One sub-40-second OmniASR result with CTC-Viterbi word timings."""

    text_raw: str
    words: tuple[Word, ...]
    mean_logprob: float | None = None
    # CTC-3B's independent greedy decode of the same segment. Empty when the acoustic model
    # emitted only blanks, which is a real answer and not a missing measurement (D-135).
    ctc_text: str = ""

    def __post_init__(self) -> None:
        if not self.text_raw.strip():
            raise ValueError("OmniASR returned an empty speech segment")
        if not self.words:
            raise ValueError("canonical ASR returned text without CTC-aligned words")


class OmniSegmentBackend(Protocol):
    def transcribe_segment(self, audio_path: Path, duration_s: float) -> SegmentTranscript: ...


class SpeechSegment(Protocol):
    @property
    def start_ms(self) -> int: ...

    @property
    def end_ms(self) -> int: ...


class CanonicalTranscriptProducer(Protocol):
    """Stage 1 producer consumed directly by ``pipeline.run_pipeline``."""

    def transcribe(
        self,
        media_id: str,
        audio_path: Path,
        speech_segments: Sequence[SpeechSegment],
        work_dir: Path,
        ffmpeg: Path | None = None,
    ) -> RawTranscript: ...


def adapter_fingerprint(adapter_dir: Path) -> str:
    """Stable identity of a PEFT adapter bundle, for the reuse key and the artifact's claim.

    Two files decide what the adapter *does*: the weights, and the config that says where they
    attach. Both are hashed, so retraining the same rank onto the same modules still yields a
    different identity and a re-transcription rather than yesterday's words.
    """
    config = adapter_dir / "adapter_config.json"
    weights = adapter_dir / "adapter_model.safetensors"
    for required in (config, weights):
        if not required.is_file():
            raise FileNotFoundError(
                f"{adapter_dir} is not a PEFT adapter bundle: {required.name} is missing"
            )
    digest = hashlib.sha256()
    for path in (config, weights):
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


class OmniAsrBackend:
    """Meta's official LLM-7B decoder plus CTC-3B emissions and our Viterbi aligner.

    Imports and model loads are deferred until the first segment. The official package exposes
    transcription but not timestamp extraction, so this uses the same public pipeline's audio
    preprocessing and CTC model forward pass, then projects the posterior matrix to only the
    target symbols needed by :func:`align_words`. No timing is inferred from text length.

    `lora_adapter` points at a PEFT bundle to apply to the LLM — a fine-tune of the canonical
    decoder, not a different model. Only the LLM is adapted: invariant #5 puts every timing on
    CTC-3B's Viterbi path, and that model and its tokenizer are untouched, so an adapter can
    change *which words are read* and never *when they are said*.
    """

    def __init__(
        self,
        *,
        llm_device: str = "cuda:0",
        ctc_device: str = "cuda:1",
        language: str = "ckb_Arab",
        llm_card: str = "omniASR_LLM_7B_v2",
        ctc_card: str = "omniASR_CTC_3B_v2",
        lora_adapter: Path | None = None,
    ) -> None:
        self.llm_device = llm_device
        self.ctc_device = ctc_device
        self.language = language
        self.llm_card = llm_card
        self.ctc_card = ctc_card
        self.lora_adapter = Path(lora_adapter) if lora_adapter is not None else None
        self._pipelines: tuple[Any, Any] | None = None

    @property
    def adapter_name(self) -> str | None:
        """What `AsrProvenance.adapter` must record, or `None` for a stock run.

        Beside `canonical`, never inside it: §7 checks `canonical` by role and a fine-tune of a
        §7 model is still that model. Folding the digest in there made `AsrProvenance` refuse
        every adapted transcript with `ModelNotInRegistry` — and the cheapest way to make that
        pass would have been to loosen the §7 check, which is exactly the trade this project
        does not make. `asr.py`'s rule is that a measurement carries the adapter that produced
        it; this is where it carries it.
        """
        if self.lora_adapter is None:
            return None
        return f"lora:{adapter_fingerprint(self.lora_adapter)}"

    def _load(self) -> tuple[Any, Any]:
        if self._pipelines is None:
            try:
                from omnilingual_asr.models.inference.pipeline import ASRInferencePipeline
            except ImportError as exc:
                raise RuntimeError(
                    "canonical ASR needs the 'asr' extra: pip install -e '.[asr]'"
                ) from exc
            llm = (
                ASRInferencePipeline(model_card=self.llm_card, device=self.llm_device)
                if self.lora_adapter is None
                else self._load_adapted_llm(self.lora_adapter)
            )
            self._pipelines = (
                llm,
                ASRInferencePipeline(model_card=self.ctc_card, device=self.ctc_device),
            )
        return self._pipelines

    def _load_adapted_llm(self, adapter_dir: Path) -> Any:
        """Base checkpoint + PEFT adapter, assembled the way the trainer serves it.

        fairseq2 does not accept an adapter through `ASRInferencePipeline(model_card=…)`, so the
        model is built by hand and handed to the pipeline pre-adapted. Three things this cannot
        guess and therefore reads:

        * **the tokenizer** — an adapter trained against a different tokenizer must be decoded
          with that tokenizer, so it is required to sit in the bundle rather than be assumed;
        * **the vocabulary size** — taken from that tokenizer's own `vocab_info`, never written
          down as a constant. Measured on this machine: the champion bundle's tokenizer reports
          **10288**, exactly the literal its trainer's server hardcodes, so the number is
          derivable and a hardcoded one would only be a guess for the next adapter;
        * **the base checkpoint** — resolved from the same asset store the unadapted path uses.

        The `Linear` shim and the `LoraConfig` registration are PEFT/fairseq2 glue: PEFT looks
        for `in_features`/`out_features`, fairseq2's projection names them `input_dim`/
        `output_dim`, and without the mapping PEFT cannot see a layer to attach to.
        """
        import copy

        import torch
        from fairseq2.assets import get_asset_store, load_in_memory_asset_metadata
        from fairseq2.data.tokenizers import load_tokenizer
        from fairseq2.models.hub import load_model
        from fairseq2.nn.projection import Linear as Fairseq2Linear
        from fairseq2.runtime.config_registry import get_config
        from fairseq2.runtime.dependency import get_dependency_resolver
        from omnilingual_asr.models.inference.pipeline import ASRInferencePipeline
        from omnilingual_asr.models.wav2vec2_llama import Wav2Vec2LlamaConfig

        try:
            from peft import LoraConfig, PeftModel
            from peft.tuners.lora import Linear as LoraLinear
        except ImportError as exc:
            # An instruction, not a traceback: this raises inside WSL after Stage 0 has run and
            # every speech region has been cut, and `peft` was genuinely absent from the runtime
            # venv until the setup script named it.
            raise RuntimeError(
                "--omni-asr-adapter needs PEFT in the OmniASR runtime. Re-run hawedit-asr-setup "
                "(or scripts/setup-wsl-asr.ps1) to provision it"
            ) from exc

        tokenizers = sorted(adapter_dir.glob("*.model"))
        if len(tokenizers) != 1:
            raise RuntimeError(
                f"{adapter_dir} must hold exactly one tokenizer (*.model) so the adapter is "
                f"decoded with the tokenizer it was trained against; found {len(tokenizers)}"
            )
        # The official card's own checkpoint value, not a path this module went looking for.
        # It is a URL (`https://dl.fbaipublicfiles.com/mms/omniASR-LLM-7B-v2.pt`, measured
        # 2026-08-12), so handing it straight back to fairseq2 reuses whatever that already has
        # cached and downloads only if it does not — where a hardcoded `~/.cache/...` path, which
        # is what the trainer's own server uses, is a guess about someone else's disk layout.
        official = get_asset_store().retrieve_card(self.llm_card)
        checkpoint = official.field("checkpoint").as_(str)

        Fairseq2Linear.in_features = property(lambda self: self.input_dim)
        Fairseq2Linear.out_features = property(lambda self: self.output_dim)
        original_post_init = LoraConfig.__post_init__

        def register_fairseq2_linear(config: Any) -> None:
            original_post_init(config)
            config._register_custom_module({Fairseq2Linear: LoraLinear})

        LoraConfig.__post_init__ = register_fairseq2_linear

        card = f"hawedit_adapted_{self.llm_card}"
        tokenizer_card = f"{card}_tokenizer"
        store = get_asset_store()
        store._metadata_providers = [
            provider
            for provider in store._metadata_providers
            if getattr(provider, "_source", "") != "hawedit_adapted"
        ]
        store._metadata_providers.append(
            load_in_memory_asset_metadata(
                "hawedit_adapted",
                [
                    {
                        "name": tokenizer_card,
                        "tokenizer_family": "char_tokenizer",
                        "tokenizer": str(tokenizers[0].resolve()),
                    },
                    {
                        "name": card,
                        "model_family": "wav2vec2_llama",
                        # `7b`, though the official card declares `7b_v2`. This follows the
                        # recipe the adapter's own trainer serves it with, because an adapter is
                        # only valid against the module shapes it was trained on and that recipe
                        # is the one measured to produce it. D-181 records the discrepancy.
                        "model_arch": "7b",
                        "checkpoint": checkpoint,
                        "tokenizer_ref": tokenizer_card,
                    },
                ],
            )
        )

        tokenizer = load_tokenizer(card)
        vocab_size = int(tokenizer.vocab_info.size)
        config = copy.deepcopy(get_config(get_dependency_resolver(), Wav2Vec2LlamaConfig, "7b"))
        config.llama_config.vocab_size = vocab_size
        config.wav2vec2_asr_config.target_vocab_size = vocab_size

        device = torch.device(self.llm_device)
        base = load_model(card, device=device, dtype=torch.bfloat16, config=config)
        adapted = PeftModel.from_pretrained(base, str(adapter_dir))
        return ASRInferencePipeline(
            model_card=None,
            model=adapted.base_model.model,
            tokenizer=tokenizer,
            device=device,
            dtype=torch.bfloat16,
        )

    @staticmethod
    def _token_ids(pipeline: Any, surface: str) -> tuple[int, ...]:
        encoded = pipeline.token_encoder(surface)
        values = encoded.tolist() if hasattr(encoded, "tolist") else list(encoded)
        vocab = pipeline.tokenizer.vocab_info
        special = {
            value
            for value in (
                getattr(vocab, "pad_idx", None),
                getattr(vocab, "bos_idx", None),
                getattr(vocab, "eos_idx", None),
            )
            if value is not None
        }
        return tuple(int(value) for value in values if int(value) not in special)

    @staticmethod
    def _ctc_hypothesis(pipeline: Any, log_probs: Any) -> str:
        """CTC-3B's own transcription of this segment, from the full-vocabulary posteriors.

        §3 Stage 1 escalates "any segment where LLM-7B and CTC-3B disagree materially", and that
        comparison needs a second hypothesis. It was never computed: the CTC pass produced
        emissions, `_align_emissions` spent them on timing the LLM's words, and
        `escalation.select_for_validation` had no input for its other half. D-135.

        Decoded from `log_probs` **before** `_align_emissions` compacts the vocabulary — a decode
        restricted to the LLM's own token columns could not produce a different word, so the
        trigger could never fire on the substitution it is for.

        The argmax runs in torch, not through `greedy_ctc_tokens`. Measured on a 200-frame
        segment against a 32,000-token vocabulary, the Python route costs 210 ms for the argmax
        plus 183 ms to materialise the matrix — roughly 215 s across this file's 547 segments —
        against 2.03 ms in torch. `collapse_ctc_path` is the O(frames) half and is shared.
        """
        import torch

        blank = int(getattr(pipeline.tokenizer.vocab_info, "pad_idx", 0) or 0)
        tokens = collapse_ctc_path(log_probs.argmax(dim=-1).tolist(), blank_id=blank)
        if not tokens:
            return ""
        decoded = pipeline.token_decoder(torch.tensor(tokens, dtype=torch.int64))
        return str(decoded).strip()

    def _ctc_emissions(self, pipeline: Any, audio_path: Path) -> tuple[Any, int]:
        try:
            import torch
            from fairseq2.nn.batch_layout import BatchLayout
        except ImportError as exc:
            raise RuntimeError("OmniASR CTC alignment requires fairseq2 and torch") from exc

        waveforms = list(pipeline._build_audio_wavform_pipeline([str(audio_path)]).and_return())
        if len(waveforms) != 1:
            raise RuntimeError(f"OmniASR decoded {len(waveforms)} waveforms for one segment")
        batch = pipeline._create_batch_simple([(waveforms[0], None)])
        layout = BatchLayout(
            batch.source_seqs.shape,
            seq_lens=batch.source_seq_lens,
            device=batch.source_seqs.device,
        )
        with torch.inference_mode():
            logits, output_layout = pipeline.model(batch.source_seqs, layout)
            frame_count = int(output_layout.seq_lens[0])
            log_probs = torch.log_softmax(logits[0, :frame_count].float(), dim=-1).cpu()
        return log_probs, frame_count

    def _align_emissions(
        self,
        pipeline: Any,
        log_probs: Any,
        frame_count: int,
        text: str,
        duration_s: float,
    ) -> tuple[Word, ...]:
        import torch

        surfaces = tuple(text.split())
        token_groups = tuple(self._token_ids(pipeline, surface) for surface in surfaces)
        if any(not group for group in token_groups):
            missing = [
                surface for surface, group in zip(surfaces, token_groups, strict=True) if not group
            ]
            raise RuntimeError(f"CTC tokenizer produced no acoustic tokens for {missing!r}")
        blank = int(getattr(pipeline.tokenizer.vocab_info, "pad_idx", 0) or 0)
        needed = sorted({blank, *(token for group in token_groups for token in group)})
        compact_id = {token: index for index, token in enumerate(needed)}
        columns = torch.tensor(needed)
        compact = log_probs.index_select(1, columns).tolist()
        compact_groups = tuple(
            (surface, tuple(compact_id[token] for token in group))
            for surface, group in zip(surfaces, token_groups, strict=True)
        )
        return align_words(
            compact,
            compact_groups,
            frame_duration_ms=duration_s * 1000 / frame_count,
            blank_id=compact_id[blank],
        )

    def transcribe_segment(self, audio_path: Path, duration_s: float) -> SegmentTranscript:
        llm, ctc = self._load()
        # The two model forwards are independent and live on different GPUs. CTC does not need
        # the LLM text until the cheap Viterbi projection after both complete.
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="omniasr") as executor:
            text_future = executor.submit(
                llm.transcribe,
                [str(audio_path)],
                lang=[self.language],
                batch_size=1,
            )
            emissions_future = executor.submit(self._ctc_emissions, ctc, audio_path)
            texts = text_future.result()
            log_probs, frame_count = emissions_future.result()
        if len(texts) != 1 or not str(texts[0]).strip():
            raise RuntimeError("OmniASR LLM returned no transcription for one speech segment")
        text = str(texts[0])
        words = self._align_emissions(ctc, log_probs, frame_count, text, duration_s)
        # CTC's own hypothesis, from the same posteriors and the full vocabulary. §3 Stage 1's
        # second escalation trigger needs it and nothing computed it (D-135).
        ctc_text = self._ctc_hypothesis(ctc, log_probs)
        total_ms = sum(word.end_ms - word.start_ms for word in words)
        mean_logprob = (
            sum(math.log(max(word.conf, 1e-12)) * (word.end_ms - word.start_ms) for word in words)
            / total_ms
            if total_ms
            else None
        )
        return SegmentTranscript(text, words, mean_logprob, ctc_text)


class OmniAsrAdapter:
    """Canonical OmniASR behind the §8.1 benchmark adapter contract."""

    model_id = "omniASR_LLM_7B_v2"

    def __init__(self, backend: OmniSegmentBackend | None = None) -> None:
        self.backend = backend or OmniAsrBackend()

    def transcribe(self, audio_path: Path, duration_s: float) -> ASRResult:
        if not 0 < duration_s <= LONG_AUDIO_THRESHOLD_S:
            raise ValueError(
                f"OmniASR benchmark item is {duration_s:.3f}s; split it below "
                f"{LONG_AUDIO_THRESHOLD_S:.0f}s and preserve its labels"
            )
        item = self.backend.transcribe_segment(audio_path, duration_s)
        return ASRResult(
            text_raw=item.text_raw,
            mean_logprob=item.mean_logprob,
            words=item.words,
        )


class OmniAsrProducer:
    """Run canonical ASR on Stage 0's VAD-bounded speech regions."""

    def __init__(
        self,
        backend: OmniSegmentBackend | None = None,
        *,
        lora_adapter: Path | None = None,
    ) -> None:
        if backend is not None and lora_adapter is not None:
            raise ValueError(
                "pass the adapter to the backend, not to both: a supplied backend already "
                "decides which weights run, and a second answer here could contradict it"
            )
        self.backend = backend or OmniAsrBackend(lora_adapter=lora_adapter)

    @property
    def model_identity(self) -> str | None:
        """The adapter half of this producer's identity, or `None` when it runs stock weights.

        `pipeline.run_pipeline` keys transcript reuse on the producer, and every OmniASR run
        answers to the same class name. Without this an adapted run reuses an unadapted run's
        transcript — the same hole D-136 closed for test doubles, one axis over.
        """
        return getattr(self.backend, "adapter_name", None)

    def transcribe(
        self,
        media_id: str,
        audio_path: Path,
        speech_segments: Sequence[SpeechSegment],
        work_dir: Path,
        ffmpeg: Path | None = None,
    ) -> RawTranscript:
        prepared = _cut_speech_regions(audio_path, speech_segments, work_dir, ffmpeg)
        results, unaligned = transcribe_prepared_segments(self.backend, prepared)
        return _assemble_canonical_transcript(
            media_id, results, unaligned, adapter=getattr(self.backend, "adapter_name", None)
        )


@dataclass(frozen=True, slots=True)
class _PreparedSpeechSegment:
    path: Path
    start_ms: int
    end_ms: int

    @property
    def duration_s(self) -> float:
        return (self.end_ms - self.start_ms) / 1_000


def _cut_speech_regions(
    audio_path: Path,
    speech_segments: Sequence[SpeechSegment],
    work_dir: Path,
    ffmpeg: Path | None,
) -> tuple[_PreparedSpeechSegment, ...]:
    """Materialize Stage 0's bounded regions once for either local or WSL inference."""
    binary = ffmpeg or find_ffmpeg()
    if binary is None:
        raise RuntimeError("canonical ASR needs ffmpeg to cut Stage 0 speech regions")
    if not speech_segments:
        raise RuntimeError("canonical ASR received no Stage 0 speech regions")
    work_dir.mkdir(parents=True, exist_ok=True)
    prepared: list[_PreparedSpeechSegment] = []
    for index, segment in enumerate(speech_segments):
        start_ms = int(segment.start_ms)
        end_ms = int(segment.end_ms)
        duration_s = (end_ms - start_ms) / 1_000
        if not 0 < duration_s <= LONG_AUDIO_THRESHOLD_S:
            raise ValueError(
                f"speech segment {index} is {duration_s:.3f}s; OmniASR accepts at most "
                f"{LONG_AUDIO_THRESHOLD_S:.0f}s"
            )
        segment_path = work_dir / f"speech-{index:04d}.wav"
        result = subprocess.run(
            [
                str(binary),
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{start_ms / 1_000:.3f}",
                "-t",
                f"{duration_s:.3f}",
                "-i",
                str(audio_path),
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                "-y",
                str(segment_path),
            ],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0 or not segment_path.exists():
            raise RuntimeError(
                f"ffmpeg failed to cut ASR segment {index}: "
                f"{result.stderr.decode('utf-8', 'replace')[-400:]}"
            )
        prepared.append(_PreparedSpeechSegment(segment_path, start_ms, end_ms))
    return tuple(prepared)


def transcribe_prepared_segments(
    backend: OmniSegmentBackend,
    prepared: Sequence[_PreparedSpeechSegment],
) -> tuple[
    tuple[tuple[_PreparedSpeechSegment, SegmentTranscript], ...],
    tuple[UnalignedSpeech, ...],
]:
    """Transcribe every Stage 0 region, recording the ones that fail instead of aborting.

    Both producers built this list with a generator expression, so the first raise discarded a
    finished Stage 0 and every other region's inference. Measured 2026-08-09 on a real 38-minute
    file: 547 regions cut, one 316 ms region produced 15 CTC frames for 15 tokens, and
    `AlignmentInfeasible` refused — correctly, since inventing a word boundary is what Kurdish
    invariant #5 forbids. The operator got no transcript for 38 minutes of Kurdish because of it.

    This repo already settled the shape in `MeasurementSession.measure`: "a raised exception
    becomes a recorded failure rather than an aborted run", because a run that dies on the first
    bad item produces no rate at all. The same reasoning, one stage earlier. D-103.
    """
    results: list[tuple[_PreparedSpeechSegment, SegmentTranscript]] = []
    failures: list[UnalignedSpeech] = []
    for segment in prepared:
        try:
            item = backend.transcribe_segment(segment.path, segment.duration_s)
        except Exception as exc:  # broad on purpose: the failure IS part of the transcript
            failures.append(
                UnalignedSpeech(
                    start_ms=segment.start_ms,
                    end_ms=segment.end_ms,
                    reason=f"{type(exc).__name__}: {exc}",
                )
            )
            continue
        results.append((segment, item))
    return tuple(results), tuple(failures)


def _assemble_canonical_transcript(
    media_id: str,
    results: Sequence[tuple[_PreparedSpeechSegment, SegmentTranscript]],
    unaligned: Sequence[UnalignedSpeech] = (),
    adapter: str | None = None,
) -> RawTranscript:
    if not results:
        raise RuntimeError(
            f"canonical ASR aligned none of {len(unaligned)} speech regions; there is no "
            f"transcript to write. First reason: "
            f"{unaligned[0].reason if unaligned else 'no regions were supplied'}"
        )
    texts: list[str] = []
    words: list[Word] = []
    logprobs: list[float] = []
    confidences: list[SegmentConfidence] = []
    for index, (segment, item) in enumerate(results):
        segment_ms = segment.end_ms - segment.start_ms
        if item.words[-1].end_ms > segment_ms + 100:
            raise RuntimeError(
                f"ASR alignment for segment {index} runs past its audio "
                f"({item.words[-1].end_ms}ms > {segment_ms}ms)"
            )
        texts.append(item.text_raw)
        words.extend(
            replace(
                word,
                start_ms=word.start_ms + segment.start_ms,
                end_ms=word.end_ms + segment.start_ms,
            )
            for word in item.words
        )
        if item.mean_logprob is not None:
            logprobs.append(item.mean_logprob)
            # Kept per segment, not only averaged. §3 Stage 1 ranks segments by log-probability
            # and takes the bottom quartile; a quartile of one average is nothing. Measured on the
            # real 38-minute run: 547 values were computed and reduced to -6.5234. D-109.
            confidences.append(
                SegmentConfidence(
                    start_ms=segment.start_ms,
                    end_ms=segment.end_ms,
                    mean_logprob=item.mean_logprob,
                    llm_text=item.text_raw,
                    ctc_text=item.ctc_text,
                )
            )
    return RawTranscript(
        media_id=media_id,
        text_ckb="\n".join(texts),
        words=tuple(words),
        asr=AsrProvenance(
            canonical="omniASR_LLM_7B_v2",
            # …and the fine-tune it ran, if any. A transcript decoded by adapted weights is a
            # different transcript, and this field is the only place the artifact says so.
            adapter=adapter,
            aligner="ctc_viterbi",
            mean_logprob=sum(logprobs) / len(logprobs) if logprobs else None,
        ),
        unaligned=tuple(unaligned),
        segment_confidence=tuple(confidences),
    )


class WslOmniAsrProducer:
    """Run the official Linux-only OmniASR stack through WSL2 on a Windows host.

    Stage 0 and WAV cutting remain in the host runner. One WSL worker receives every bounded
    segment, loads LLM-7B and CTC-3B once, returns a validated canonical transcript, and never
    communicates through lossy stdout JSON. The shared work directory is the only bridge.
    """

    def __init__(
        self,
        *,
        distro: str | None = None,
        interpreter: str | None = None,
        wsl_executable: str = "wsl.exe",
        lora_adapter: Path | None = None,
    ) -> None:
        self.distro = distro
        self.interpreter = interpreter
        self.wsl_executable = wsl_executable
        self.lora_adapter = Path(lora_adapter) if lora_adapter is not None else None

    @property
    def model_identity(self) -> str | None:
        """This producer's adapter identity, computed host-side so reuse can be keyed on it.

        Read from the bundle on the Windows side rather than reported by the worker: the reuse
        decision happens *before* the worker is invoked, and an identity that only exists after
        a 1,547 s transcription cannot key anything.
        """
        if self.lora_adapter is None:
            return None
        return f"lora:{adapter_fingerprint(self.lora_adapter)}"

    def _prefix(self) -> list[str]:
        # The shared builder, not a second copy. This one used `--`, which routes the command
        # through the distribution's default shell and loses the `env PYTHONPATH=…` assignment
        # below — so `hawedit.asr_worker` would have been unimportable inside WSL however well
        # the runtime was provisioned. Measured 2026-08-09; see `wsl_setup._prefix`. D-102.
        return wsl_prefix(self.distro, self.wsl_executable)

    def _wsl_path(self, path: Path) -> str:
        return wsl_path(path, self.distro, self.wsl_executable)

    def _runtime(self) -> tuple[str, str]:
        """Return (WSL Python, WSL PYTHONPATH), supporting checkouts and installed wheels."""
        configured_python = self.interpreter or os.environ.get("HAWEDIT_WSL_PYTHON")
        configured_source = os.environ.get("HAWEDIT_WSL_SOURCE")
        repo_root = Path(__file__).resolve().parents[2]
        checkout_source = repo_root / "src"
        runtime = Path(os.environ.get("HAWEDIT_WSL_RUNTIME", default_wsl_runtime()))
        source_snapshot = (
            Path(configured_source)
            if configured_source
            else default_wsl_source(runtime_root=runtime)
        )

        if configured_python:
            source = (
                Path(configured_source)
                if configured_source
                else checkout_source
                if (checkout_source / "hawedit").is_dir()
                else source_snapshot
            )
            return configured_python, self._wsl_path(source)

        if (source_snapshot / ".ready").is_file():
            translated = self._wsl_path(runtime)
            return f"{translated}/venv/bin/python", self._wsl_path(source_snapshot)

        legacy = repo_root / ".venv-wsl" / "bin" / "python"
        if legacy.exists() and (checkout_source / "hawedit").is_dir():
            return self._wsl_path(legacy), self._wsl_path(checkout_source)

        raise RuntimeError(
            "canonical OmniASR WSL2 runtime is not provisioned. Run hawedit-asr-setup "
            "(or scripts/setup-wsl-asr.ps1 from a checkout) first"
        )

    def transcribe(
        self,
        media_id: str,
        audio_path: Path,
        speech_segments: Sequence[SpeechSegment],
        work_dir: Path,
        ffmpeg: Path | None = None,
    ) -> RawTranscript:
        interpreter, wsl_source = self._runtime()
        prepared = _cut_speech_regions(audio_path, speech_segments, work_dir, ffmpeg)
        request_path = work_dir / "omni-asr-request.json"
        output_path = work_dir / "omni-asr-worker-output.json"
        request: dict[str, Any] = {
            "schema_version": 1,
            "media_id": media_id,
            "segments": [
                {
                    "path": segment.path.name,
                    "start_ms": segment.start_ms,
                    "end_ms": segment.end_ms,
                }
                for segment in prepared
            ],
        }
        if self.lora_adapter is not None:
            # Only present for an adapted run, so an unadapted request is byte-identical to the
            # one D-136's resume check compares against. Its presence also makes the two runs'
            # requests differ, which is what stops a killed champion run from being resumed by
            # the stock path under the same work directory.
            request["lora_adapter"] = self._wsl_path(self.lora_adapter)
            request["model_identity"] = self.model_identity
        payload = json.dumps(request, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        try:
            with request_path.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(payload)
        except FileExistsError:
            # A run killed mid-transcription leaves this behind, and the next attempt used to die
            # on a bare FileExistsError naming a path with no instruction — measured at 78 s
            # wasted after Stage 0 had already been re-verified. If the request describes exactly
            # this work, it is a resumed run and there is nothing to protect; if it describes
            # different segments, two runs are sharing one work directory and that is refused
            # loudly. D-132's rule one stage over: a dying run must not leave a record that
            # blocks or misleads the next one. D-136.
            existing = request_path.read_text(encoding="utf-8")
            if existing != payload:
                raise RuntimeError(
                    f"{request_path} already describes a different Stage 1 request "
                    f"({len(json.loads(existing).get('segments', ()))} segments, this run has "
                    f"{len(prepared)}). Another run is using this work directory, or Stage 0's "
                    f"speech regions changed. Delete that file to re-transcribe from scratch."
                ) from None

        # The worker's own output is exclusive-create too, so a killed run left *two* blockers and
        # the next attempt tripped on whichever came first — found by the test written for the
        # request file alone. If a finished output sits beside an identical request, that is this
        # run's answer and the worker has nothing left to do: the resume. Verified, never assumed
        # — a truncated or foreign output is deleted and the worker runs again, which is the
        # expensive answer rather than the wrong one.
        if output_path.is_file():
            try:
                finished = RawTranscript.from_json(output_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                finished = None
            if finished is not None and finished.media_id == media_id:
                return finished
            output_path.unlink(missing_ok=True)

        wsl_request = self._wsl_path(request_path)
        wsl_output = self._wsl_path(output_path)
        result = subprocess.run(
            [
                *self._prefix(),
                "env",
                f"PYTHONPATH={wsl_source}",
                interpreter,
                "-m",
                "hawedit.asr_worker",
                "--request",
                wsl_request,
                "--output",
                wsl_output,
            ],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0 or not output_path.is_file():
            stderr = result.stderr.decode("utf-8", "replace")[-1_200:]
            raise RuntimeError(
                "canonical OmniASR failed in WSL2. Run hawedit-asr-setup first; "
                f"worker said: {stderr or 'no transcript was returned'}"
            )
        transcript = RawTranscript.from_json(output_path.read_text(encoding="utf-8"))
        if transcript.media_id != media_id:
            raise RuntimeError(
                f"WSL OmniASR returned media_id {transcript.media_id!r} for {media_id!r}"
            )
        return transcript


def create_omni_asr_producer(
    runtime: str = "auto", *, distro: str | None = None, lora_adapter: Path | None = None
) -> CanonicalTranscriptProducer:
    """Choose direct Linux inference or the WSL bridge without hiding that decision."""
    if runtime not in {"auto", "local", "wsl"}:
        raise ValueError("OmniASR runtime must be one of: auto, local, wsl")
    if lora_adapter is not None:
        # Fingerprinting reads both files, so a path that is not an adapter bundle fails here —
        # before Stage 0's regions are cut — rather than 1,547 s later inside WSL.
        adapter_fingerprint(Path(lora_adapter))
    use_wsl = runtime == "wsl" or (runtime == "auto" and os.name == "nt")
    return (
        WslOmniAsrProducer(distro=distro, lora_adapter=lora_adapter)
        if use_wsl
        else OmniAsrProducer(lora_adapter=lora_adapter)
    )


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
            # Module-qualified, not the bare class name. A bare name identifies nothing a
            # reader can act on: a scripted stub called `OmniAsrAdapter` — no weights, no GPU,
            # no model — produced a §8.1 report reading `normalized_cer: 0.0`, `mean_rtf: 0.1`
            # on `hawapc01` / `2x RTX 3090 Ti` with `adapter_impls: ["OmniAsrAdapter"]`, byte
            # for byte what the real adapter emits. Measured 2026-08-09. The hard rule is that
            # a number carries the adapter that produced it, and `test_bench.OmniAsrAdapter`
            # carries it while `OmniAsrAdapter` only asserts it. D-097.
            adapter_impl=f"{type(adapter).__module__}.{type(adapter).__name__}",
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
