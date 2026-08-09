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

import json
import math
import os
import subprocess
import time
import wave
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Final, Protocol, runtime_checkable

from hawedit.captions import find_ffmpeg
from hawedit.corpus import CorpusItem
from hawedit.escalation import SegmentScore, select_for_validation
from hawedit.forced_alignment import align_words
from hawedit.models import ModelStore, assert_transformers_config_safe, verified_checkpoint_access
from hawedit.omni_assets import (
    CANONICAL_CTC_CARD,
    CANONICAL_LLM_CARD,
    assert_canonical_omni_cards,
    assert_effective_omni_cards,
    assert_omni_card_integrity,
    freeze_fairseq2_asset_overrides,
    open_verified_omni_assets,
)
from hawedit.registry import ASR_ROLES, ModelEntry, resolve_role
from hawedit.transcripts import (
    AsrProvenance,
    RawTranscript,
    SegmentConfidence,
    UnalignedSpeech,
    Word,
)
from hawedit.wsl_setup import (
    WslRuntimeError,
    default_wsl_runtime,
    load_wsl_runtime_receipt,
    wsl_path,
)
from hawedit.wsl_setup import _prefix as wsl_prefix

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
    "QwenSoraniValidator",
    "SegmentTranscript",
    "SoraniValidator",
    "WslOmniAsrProducer",
    "create_omni_asr_producer",
    "long_audio_failure_rate",
    "validate_adapter",
]

# §3 Stage 1: OmniASR's interface ceiling. Stage 0's VAD uses max_speech_duration_s=38 to
# stay under it, so anything past this is by definition outside the designed operating range
# and its failure rate is a property worth measuring rather than an accident.
LONG_AUDIO_THRESHOLD_S: Final = 40.0
VALIDATOR_MODEL_ID: Final = "rzgar/qwen3-asr-sorani-kurdish-ckb-v1"


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
    ctc_text: str
    words: tuple[Word, ...]
    mean_logprob: float

    def __post_init__(self) -> None:
        if not self.text_raw.strip():
            raise ValueError("OmniASR returned an empty speech segment")
        if not isinstance(self.ctc_text, str):
            raise ValueError("CTC hypothesis must be a string")
        if not self.words:
            raise ValueError("canonical ASR returned text without CTC-aligned words")
        if not math.isfinite(self.mean_logprob) or self.mean_logprob > 0:
            raise ValueError("segment mean_logprob must be a finite log-probability <= 0")


class OmniSegmentBackend(Protocol):
    def transcribe_segment(self, audio_path: Path, duration_s: float) -> SegmentTranscript: ...

    def align_segment(
        self, audio_path: Path, duration_s: float, text: str
    ) -> SegmentTranscript: ...


class SoraniValidator(Protocol):
    """One registry-approved second opinion for an escalated Stage 1 segment."""

    model_id: str

    def transcribe_segment(self, audio_path: Path, duration_s: float) -> str: ...


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


class QwenSoraniValidator:
    """The official Qwen-ASR loader for §3's fine-tuned Sorani validator."""

    model_id = VALIDATOR_MODEL_ID

    def __init__(
        self,
        model_dir: Path,
        *,
        device: str = "cuda:1",
        model_id: str = VALIDATOR_MODEL_ID,
    ) -> None:
        resolve_role(model_id, frozenset({"asr_validator"}), "the ASR validator")
        if not model_dir.is_dir():
            raise RuntimeError(
                f"no validator weights at {model_dir}. Run hawedit-fetch-models {model_id}."
            )
        self.model_id = model_id
        self.model_dir = model_dir
        self.device = device
        self._model: Any | None = None

    def _load(self) -> Any:
        if self._model is None:
            # Verification owns a shared checkpoint lock through every parse and reopen. Without
            # it, a same-size hardlink mutation after hashing can change what Qwen-ASR constructs,
            # including the config surface interpreted by Transformers. D-115.
            with verified_checkpoint_access(self.model_id, self.model_dir) as verified_dir:
                # Qwen-ASR delegates checkpoint construction to Transformers. Apply the same
                # pre-deserialisation guard as the visual loaders before qwen_asr imports or reads
                # config.json; otherwise the canonical Stage 1 route would retain CVE-2026-4372
                # while Stage 2 refused it.
                assert_transformers_config_safe(
                    verified_dir,
                    frozenset(
                        {
                            "qwen3_asr",
                            "qwen3_asr_audio_encoder",
                            "qwen3_asr_text",
                            "qwen3_asr_thinker",
                        }
                    ),
                )
                try:
                    import torch
                    from qwen_asr import Qwen3ASRModel
                except ImportError as exc:
                    raise RuntimeError(
                        "the Sorani validator needs qwen-asr==0.0.6 and a CUDA Stage 1 runtime"
                    ) from exc
                if self.device.startswith("cuda") and not torch.cuda.is_available():
                    raise RuntimeError(
                        f"validator device {self.device!r} was requested but CUDA is unavailable"
                    )
                self._model = Qwen3ASRModel.from_pretrained(
                    str(verified_dir),
                    dtype=torch.bfloat16,
                    device_map=self.device,
                    max_inference_batch_size=1,
                )
        return self._model

    def transcribe_segment(self, audio_path: Path, duration_s: float) -> str:
        if not audio_path.is_file():
            raise FileNotFoundError(f"validator audio segment is missing: {audio_path}")
        if not 0 < duration_s <= LONG_AUDIO_THRESHOLD_S:
            raise ValueError(
                f"validator segment is {duration_s:.3f}s; expected 0..{LONG_AUDIO_THRESHOLD_S:.0f}s"
            )
        results = self._load().transcribe(audio=str(audio_path))
        if len(results) != 1 or not str(results[0].text).strip():
            raise RuntimeError("Sorani validator returned no transcription for one speech segment")
        return str(results[0].text)


class OmniAsrBackend:
    """Meta's official LLM-7B decoder plus CTC-3B emissions and our Viterbi aligner.

    Imports and model loads are deferred until the first segment. The official package exposes
    transcription but not timestamp extraction, so this uses the same public pipeline's audio
    preprocessing and CTC model forward pass, then projects the posterior matrix to only the
    target symbols needed by :func:`align_words`. No timing is inferred from text length.
    """

    def __init__(
        self,
        *,
        llm_device: str = "cuda:0",
        ctc_device: str = "cuda:1",
        language: str = "ckb_Arab",
        llm_card: str = CANONICAL_LLM_CARD,
        ctc_card: str = CANONICAL_CTC_CARD,
    ) -> None:
        assert_canonical_omni_cards(llm_card, ctc_card)
        self.llm_device = llm_device
        self.ctc_device = ctc_device
        self.language = language
        self.llm_card = llm_card
        self.ctc_card = ctc_card
        self._pipelines: tuple[Any, Any] | None = None

    def _load(self) -> tuple[Any, Any]:
        if self._pipelines is None:
            # fairseq2 trusts an existing URL-keyed cache entry and model-card ``@user``
            # fields can override the official URI. Hash the three canonical files before
            # importing a pipeline that can deserialize either model, and use the trailing
            # ``@`` card names above to disable environment lookup.
            with open_verified_omni_assets() as opened_assets:
                assert_omni_card_integrity()
                freeze_fairseq2_asset_overrides()
                try:
                    import torch
                    from fairseq2.assets import AssetCard, get_asset_store
                    from fairseq2.data.tokenizers.hub import load_tokenizer
                    from fairseq2.models.hub import load_model
                    from omnilingual_asr.models.inference.pipeline import ASRInferencePipeline
                except ImportError as exc:
                    raise RuntimeError(
                        "canonical ASR needs the 'asr' extra: pip install -e '.[asr]'"
                    ) from exc
                assert_effective_omni_cards(get_asset_store())
                by_name = {opened.asset.filename: opened for opened in opened_assets}
                tokenizer_card = AssetCard(
                    "hawedit_omniASR_tokenizer_written_v2",
                    {
                        "tokenizer_family": "char_tokenizer",
                        "tokenizer": by_name["omniASR_tokenizer_written_v2.model"].file_uri,
                    },
                )
                tokenizer = load_tokenizer(tokenizer_card)
                llm_model = load_model(
                    AssetCard(
                        "hawedit_omniASR_LLM_7B_v2",
                        {
                            "model_family": "wav2vec2_llama",
                            "model_arch": "7b_v2",
                            "checkpoint": by_name["omniASR-LLM-7B-v2.pt"].file_uri,
                        },
                    ),
                    device=torch.device(self.llm_device),
                    dtype=torch.bfloat16,
                )
                ctc_model = load_model(
                    AssetCard(
                        "hawedit_omniASR_CTC_3B_v2",
                        {
                            "model_family": "wav2vec2_asr",
                            "model_arch": "3b_v2",
                            "checkpoint": by_name["omniASR-CTC-3B-v2.pt"].file_uri,
                        },
                    ),
                    device=torch.device(self.ctc_device),
                    dtype=torch.bfloat16,
                )
                self._pipelines = (
                    ASRInferencePipeline(
                        model_card=None,
                        model=llm_model,
                        tokenizer=tokenizer,
                        device=self.llm_device,
                    ),
                    ASRInferencePipeline(
                        model_card=None,
                        model=ctc_model,
                        tokenizer=tokenizer,
                        device=self.ctc_device,
                    ),
                )
        return self._pipelines

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

    def _ctc_emissions(self, pipeline: Any, audio_path: Path) -> tuple[Any, int, str]:
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
            if frame_count <= 0:
                raise RuntimeError("OmniASR CTC returned no acoustic frames for a speech segment")
            segment_logits = logits[0, :frame_count]
            log_probs = torch.log_softmax(segment_logits.float(), dim=-1).cpu()
            # This is the official omnilingual-asr CTC greedy decoder: collapse consecutive
            # ids, then let the tokenizer's skip-special decoder remove blank/special ids.
            sequence = torch.argmax(segment_logits, dim=-1)
            keep = torch.ones(sequence.shape[0], dtype=torch.bool, device=sequence.device)
            keep[1:] = sequence[1:] != sequence[:-1]
            ctc_text = str(pipeline.token_decoder(sequence[keep]))
        return log_probs, frame_count, ctc_text

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
            log_probs, frame_count, ctc_text = emissions_future.result()
        if len(texts) != 1 or not str(texts[0]).strip():
            raise RuntimeError("OmniASR LLM returned no transcription for one speech segment")
        text = str(texts[0])
        words = self._align_emissions(ctc, log_probs, frame_count, text, duration_s)
        return SegmentTranscript(text, ctc_text, words, _mean_aligned_logprob(words))

    def align_segment(self, audio_path: Path, duration_s: float, text: str) -> SegmentTranscript:
        """Align a validator correction with a fresh CTC pass on the same bounded audio."""
        if not text.strip():
            raise ValueError("cannot align an empty validator transcription")
        _, ctc = self._load()
        log_probs, frame_count, ctc_text = self._ctc_emissions(ctc, audio_path)
        words = self._align_emissions(ctc, log_probs, frame_count, text, duration_s)
        return SegmentTranscript(text, ctc_text, words, _mean_aligned_logprob(words))


def _mean_aligned_logprob(words: Sequence[Word]) -> float:
    total_ms = sum(word.end_ms - word.start_ms for word in words)
    if total_ms <= 0:
        raise RuntimeError("CTC alignment produced no positive-duration words")
    return (
        sum(math.log(max(word.conf, 1e-12)) * (word.end_ms - word.start_ms) for word in words)
        / total_ms
    )


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
        validator: SoraniValidator | None = None,
        validator_model_dir: Path | None = None,
    ) -> None:
        if validator is not None and validator_model_dir is not None:
            raise ValueError("provide a validator or validator_model_dir, not both")
        self.backend = backend or OmniAsrBackend()
        self.validator = validator
        self.validator_model_dir = validator_model_dir

    def _validator(self) -> SoraniValidator:
        if self.validator is not None:
            return self.validator
        model_dir = self.validator_model_dir or ModelStore().assert_available(VALIDATOR_MODEL_ID)
        if model_dir is None:  # WEIGHTS entries always return a path; keep the type honest.
            raise RuntimeError(f"{VALIDATOR_MODEL_ID} did not resolve to a model directory")
        self.validator = QwenSoraniValidator(model_dir)
        return self.validator

    def transcribe(
        self,
        media_id: str,
        audio_path: Path,
        speech_segments: Sequence[SpeechSegment],
        work_dir: Path,
        ffmpeg: Path | None = None,
    ) -> RawTranscript:
        prepared = _cut_speech_regions(audio_path, speech_segments, work_dir, ffmpeg)
        initial, unaligned = transcribe_prepared_segments(self.backend, prepared)
        results, validated_by = _validate_hard_segments(initial, self.backend, self._validator)
        return _assemble_canonical_transcript(
            media_id, results, unaligned, validated_by=validated_by
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
        actual_duration_ms = _pcm_duration_ms(segment_path)
        requested_duration_ms = end_ms - start_ms
        if actual_duration_ms > requested_duration_ms + 1:
            raise RuntimeError(
                f"ffmpeg emitted {actual_duration_ms}ms for ASR segment {index}, longer than "
                f"the requested {requested_duration_ms}ms"
            )
        prepared.append(
            _PreparedSpeechSegment(segment_path, start_ms, start_ms + actual_duration_ms)
        )
    return tuple(prepared)


def _pcm_duration_ms(path: Path) -> int:
    """Read the exact duration of Stage 1's emitted 16 kHz mono PCM, without ffprobe."""
    try:
        with wave.open(str(path), "rb") as stream:
            channels = stream.getnchannels()
            sample_width = stream.getsampwidth()
            sample_rate = stream.getframerate()
            frame_count = stream.getnframes()
            compression = stream.getcomptype()
    except (EOFError, wave.Error) as exc:
        raise RuntimeError(f"ASR segment is not a readable PCM WAV: {path}") from exc
    if (channels, sample_width, sample_rate, compression) != (1, 2, 16_000, "NONE"):
        raise RuntimeError(
            f"ASR segment has unexpected WAV format at {path}: "
            f"channels={channels}, sample_width={sample_width}, sample_rate={sample_rate}, "
            f"compression={compression}"
        )
    duration_ms = round(frame_count * 1_000 / sample_rate)
    if duration_ms <= 0:
        raise RuntimeError(f"ASR segment contains no audio frames: {path}")
    return duration_ms


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
    bad item produces no rate at all. The same reasoning, one stage earlier. D-135.
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
    *,
    validated_by: str | None = None,
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
            # real 38-minute run: 547 values were computed and reduced to -6.5234. D-144.
            confidences.append(
                SegmentConfidence(
                    start_ms=segment.start_ms,
                    end_ms=segment.end_ms,
                    mean_logprob=item.mean_logprob,
                )
            )
    return RawTranscript(
        media_id=media_id,
        text_ckb="\n".join(texts),
        words=tuple(words),
        asr=AsrProvenance(
            canonical="omniASR_LLM_7B_v2",
            aligner="ctc_viterbi",
            validated_by=validated_by,
            mean_logprob=sum(logprobs) / len(logprobs) if logprobs else None,
        ),
        unaligned=tuple(unaligned),
        segment_confidence=tuple(confidences),
    )


def _validate_hard_segments(
    results: Sequence[tuple[_PreparedSpeechSegment, SegmentTranscript]],
    backend: OmniSegmentBackend,
    validator_factory: Callable[[], SoraniValidator],
) -> tuple[tuple[tuple[_PreparedSpeechSegment, SegmentTranscript], ...], str | None]:
    """Apply §3's confidence/disagreement router and realign only corrected segments."""
    scores = tuple(
        SegmentScore(
            segment_id=f"segment-{index:04d}",
            mean_logprob=item.mean_logprob,
            llm_text=item.text_raw,
            ctc_text=item.ctc_text,
            duration_s=segment.duration_s,
        )
        for index, (segment, item) in enumerate(results)
    )
    decisions = select_for_validation(scores)
    if not any(decision.escalate for decision in decisions):
        return tuple(results), None

    validator = validator_factory()
    resolve_role(validator.model_id, frozenset({"asr_validator"}), "the ASR validator")
    routed: list[tuple[_PreparedSpeechSegment, SegmentTranscript]] = []
    for (segment, item), decision in zip(results, decisions, strict=True):
        if not decision.escalate:
            routed.append((segment, item))
            continue
        corrected = validator.transcribe_segment(segment.path, segment.duration_s)
        aligned = backend.align_segment(segment.path, segment.duration_s, corrected)
        routed.append((segment, aligned))
    return tuple(routed), validator.model_id


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
        validator_model_dir: Path | None = None,
    ) -> None:
        self.distro = distro
        self.interpreter = interpreter
        self.wsl_executable = wsl_executable
        self.validator_model_dir = validator_model_dir
        self._receipt_distro: str | None = None

    def _prefix(self) -> list[str]:
        selected_distro = self._receipt_distro or self.distro
        # The shared builder, not a second copy. This one used `--`, which routes the command
        # through the distribution's default shell and loses the `env PYTHONPATH=…` assignment
        # below — so `hawedit.asr_worker` would have been unimportable inside WSL however well
        # the runtime was provisioned. Measured 2026-08-09; see `wsl_setup._prefix`. D-134.
        return wsl_prefix(selected_distro, self.wsl_executable)

    def _wsl_path(self, path: Path) -> str:
        return wsl_path(path, self._receipt_distro or self.distro, self.wsl_executable)

    def _runtime(self) -> tuple[str, str]:
        """Return (WSL Python, WSL PYTHONPATH), supporting checkouts and installed wheels."""
        configured_python = self.interpreter or os.environ.get("HAWEDIT_WSL_PYTHON")
        configured_source = os.environ.get("HAWEDIT_WSL_SOURCE")
        repo_root = Path(__file__).resolve().parents[2]
        checkout_source = repo_root / "src"
        runtime = Path(os.environ.get("HAWEDIT_WSL_RUNTIME", default_wsl_runtime()))
        if configured_python:
            if configured_source:
                source = Path(configured_source)
            elif (checkout_source / "hawedit").is_dir():
                source = checkout_source
            else:
                raise RuntimeError(
                    "HAWEDIT_WSL_SOURCE must accompany a custom HAWEDIT_WSL_PYTHON "
                    "outside a source checkout"
                )
            return configured_python, self._wsl_path(source)

        try:
            receipt = load_wsl_runtime_receipt(
                distro=self.distro,
                runtime_root=runtime,
                executable=self.wsl_executable,
            )
        except WslRuntimeError as exc:
            raise RuntimeError(
                f"canonical OmniASR WSL2 runtime receipt is invalid: {exc}. Run hawedit-asr-setup"
            ) from exc
        self._receipt_distro = receipt.distro
        translated_generation = self._wsl_path(receipt.generation_root)
        return f"{translated_generation}/bin/python", self._wsl_path(receipt.source_root)

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
        validator_model_dir = self.validator_model_dir or ModelStore().assert_available(
            VALIDATOR_MODEL_ID
        )
        if validator_model_dir is None:
            raise RuntimeError(f"{VALIDATOR_MODEL_ID} did not resolve to a model directory")
        # Windows msvcrt locks and Linux fcntl locks do not interoperate on DrvFS. Hold the host
        # shared lease for the complete WSL subprocess so the host fetcher's exclusive publisher
        # cannot rename this checkpoint while the worker independently verifies and constructs it.
        with verified_checkpoint_access(
            VALIDATOR_MODEL_ID, validator_model_dir
        ) as verified_validator_dir:
            request_path = work_dir / "omni-asr-request.json"
            output_path = work_dir / "omni-asr-worker-output.json"
            request = {
                "schema_version": 2,
                "media_id": media_id,
                "validator_model_dir": self._wsl_path(verified_validator_dir),
                "segments": [
                    {
                        "path": segment.path.name,
                        "start_ms": segment.start_ms,
                        "end_ms": segment.end_ms,
                    }
                    for segment in prepared
                ],
            }
            with request_path.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(request, stream, ensure_ascii=False, sort_keys=True, indent=2)
                stream.write("\n")

            wsl_request = self._wsl_path(request_path)
            wsl_output = self._wsl_path(output_path)
            result = subprocess.run(
                [
                    *self._prefix(),
                    "env",
                    "PYTHONDONTWRITEBYTECODE=1",
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
    runtime: str = "auto", *, distro: str | None = None
) -> CanonicalTranscriptProducer:
    """Choose direct Linux inference or the WSL bridge without hiding that decision."""
    if runtime not in {"auto", "local", "wsl"}:
        raise ValueError("OmniASR runtime must be one of: auto, local, wsl")
    use_wsl = runtime == "wsl" or (runtime == "auto" and os.name == "nt")
    return WslOmniAsrProducer(distro=distro) if use_wsl else OmniAsrProducer()


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
