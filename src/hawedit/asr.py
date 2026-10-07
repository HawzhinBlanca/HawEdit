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

import gc
import hashlib
import json
import math
import os
import shutil
import stat
import subprocess
import tempfile
import time
import wave
from collections.abc import Callable, Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, BinaryIO, Final, Protocol, runtime_checkable

from hawedit.asr_completion import COMPLETION_POLICY_ID, transcribe_completed
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
    RejectedValidatorCorrection,
    SegmentConfidence,
    UnalignedSpeech,
    Word,
)
from hawedit.wsl_setup import (
    WslRuntimeError,
    configured_wsl_runtime,
    load_wsl_runtime_receipt,
    wsl_path,
    wsl_prefix,
)

__all__ = [
    "CHAMPION_ADAPTER_ENV",
    "LONG_AUDIO_THRESHOLD_S",
    "ASRAdapter",
    "ASRResult",
    "AsrProductionFailure",
    "CanonicalTranscriptProducer",
    "ChampionUnavailable",
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
    "resolve_champion_adapter",
    "validate_adapter",
]

# §3 Stage 1: OmniASR's interface ceiling. Stage 0's VAD uses max_speech_duration_s=38 to
# stay under it, so anything past this is by definition outside the designed operating range
# and its failure rate is a property worth measuring rather than an accident.
LONG_AUDIO_THRESHOLD_S: Final = 40.0
VALIDATOR_MODEL_ID: Final = "rzgar/qwen3-asr-sorani-kurdish-ckb-v1"
_CONTEXT_MAX_GAP_MS: Final = 1_000
_CONTEXT_MAX_SPAN_MS: Final = 18_000
CONTEXT_GROUPING_POLICY_ID: Final = (
    f"vad-context-v1-gap{_CONTEXT_MAX_GAP_MS}-span{_CONTEXT_MAX_SPAN_MS}"
)


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


# Where the owner's fine-tuned decoder lives. WSL paths, in the UNC forms Windows can read,
# because `adapter_fingerprint` reads the bundle host-side — the reuse decision happens before
# the worker is invoked, so an identity that only exists inside WSL cannot key anything.
CHAMPION_ADAPTER_CANDIDATES: Final = (
    r"\\wsl.localhost\Ubuntu\home\ai\cortex_champion_model",
    r"\\wsl$\Ubuntu\home\ai\cortex_champion_model",
)
CHAMPION_ADAPTER_ENV: Final = "HAWEDIT_CHAMPION_ADAPTER"


class ChampionUnavailable(RuntimeError):
    """The fine-tuned decoder could not be found, and this run refuses to draft without it."""


def resolve_champion_adapter(
    candidates: Sequence[str] = CHAMPION_ADAPTER_CANDIDATES,
    env: Mapping[str, str] | None = None,
) -> Path:
    """The champion bundle, or a refusal. Never a silent fall back to the base decoder.

    **The owner's canon, decided 2026-08-11 and marked FINAL:** the champion transcribes every
    clip, nothing may divert it, and a failure halts the run rather than degrading it. The
    incident behind that rule is 494 of 494 clips drafted by the wrong engine — a dataset that
    looked finished and whose mixed provenance poisoned every measurement taken from it.

    It is not a cosmetic preference. Measured on this machine against the same in-memory
    checkpoint, base and champion differ on **3 of 3** real Sorani clips, and at 1:00 the base
    opens with a hallucinated `سانە` the champion does not emit
    (`evidence/the-champion-adapter-would-have-shipped-the-base-models-words.md`).

    Raises:
        ChampionUnavailable: no bundle found, naming every path tried and how to point at one.
    """
    environ = os.environ if env is None else env
    override = environ.get(CHAMPION_ADAPTER_ENV, "").strip()
    tried: list[str] = []
    for raw in ([override] if override else []) + list(candidates):
        bundle = Path(raw)
        tried.append(str(bundle))
        if (bundle / "adapter_config.json").is_file() and (
            bundle / "adapter_model.safetensors"
        ).is_file():
            return bundle
    raise ChampionUnavailable(
        "the fine-tuned OmniASR-7B champion is required for Stage 1 and no bundle was found. "
        f"Tried: {', '.join(tried)}. Set {CHAMPION_ADAPTER_ENV} to the bundle, pass "
        "--omni-asr-adapter, or ask for the base decoder deliberately with --stock-decoder. "
        "Falling back on its own is what the owner's Champion Supremacy canon forbids: the base "
        "model hallucinates words the champion does not emit, and a transcript drafted by the "
        "wrong engine poisons every measurement taken from it."
    )


def adapter_fingerprint(adapter_dir: Path) -> str:
    """Versioned config/weights/tokenizer identity, not licence or loader authorization."""
    with _open_adapter_bundle(adapter_dir) as (fingerprint, _streams):
        return fingerprint


@contextmanager
def _open_adapter_bundle(adapter_dir: Path) -> Iterator[tuple[str, dict[str, BinaryIO]]]:
    """Retain the exact hashed inputs until consumption and drift checks finish."""
    root = adapter_dir.absolute()
    root_info = root.lstat()
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)

    def identity(info: os.stat_result) -> tuple[int, ...]:
        return (
            info.st_dev,
            info.st_ino,
            info.st_mode,
            info.st_size,
            info.st_mtime_ns,
            info.st_ctime_ns,
            info.st_nlink,
        )

    def plain(info: os.stat_result, *, directory: bool = False) -> None:
        regular = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
        if (
            not regular
            or getattr(info, "st_file_attributes", 0) & reparse
            or (not directory and info.st_nlink != 1)
        ):
            raise RuntimeError("Adapter identity requires non-linked regular bundle inputs")

    plain(root_info, directory=True)
    for name in ("adapter_config.json", "adapter_model.safetensors"):
        plain((root / name).lstat())

    def tokenizer_name() -> str:
        names = []
        for index, path in enumerate(root.iterdir()):
            if index >= 4096:
                raise RuntimeError("Adapter identity directory exceeds the entry bound")
            if path.match("*.model"):
                names.append(path.name)
                if len(names) > 1:
                    raise RuntimeError("Adapter identity requires exactly one tokenizer (*.model)")
        if len(names) != 1:
            raise RuntimeError("Adapter identity requires exactly one tokenizer (*.model)")
        return names[0]

    tokenizer = tokenizer_name()
    members = (
        ("configuration", "adapter_config.json", 4 * 1024**2),
        ("weights", "adapter_model.safetensors", 32 * 1024**3),
        ("tokenizer", tokenizer, 16 * 1024**2),
    )
    records = []
    deadline = time.monotonic() + 120
    # Keep all input descriptors open until the complete set has been rechecked.
    with ExitStack() as stack:
        opened_members = []
        for role, name, ceiling in members:
            path = root / name
            before = path.lstat()
            plain(before)
            if not 0 < before.st_size <= ceiling:
                raise RuntimeError("Adapter identity input exceeds its size bounds")
            descriptor = os.open(
                path,
                os.O_RDONLY
                | getattr(os, "O_BINARY", 0)
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_NONBLOCK", 0),
            )
            try:
                stream = os.fdopen(descriptor, "rb")
            except BaseException:
                os.close(descriptor)
                raise
            stack.enter_context(stream)
            opened = os.fstat(stream.fileno())
            plain(opened)
            # Windows CRT/path ctime meanings differ; compare ctime only within each source.
            if identity(before)[:5] + (before.st_nlink,) != identity(opened)[:5] + (
                opened.st_nlink,
            ):
                raise RuntimeError("Adapter identity input changed while opening")
            opened_members.append((role, name, path, before, opened, stream))
        for role, name, _path, _before, opened, stream in opened_members:
            digest = hashlib.sha256()
            count = 0
            while chunk := stream.read(1024**2):
                count += len(chunk)
                if count > opened.st_size or time.monotonic() > deadline:
                    raise RuntimeError("Adapter identity input exceeds hashing bounds")
                digest.update(chunk)
            if count != opened.st_size:
                raise RuntimeError("Adapter identity input changed while hashing")
            records.append(
                {"role": role, "name": name, "size_bytes": count, "sha256": digest.hexdigest()}
            )
            stream.seek(0)

        def assert_unchanged() -> None:
            for _role, _name, path, before, opened, stream in opened_members:
                if identity(os.fstat(stream.fileno())) != identity(opened) or identity(
                    path.lstat()
                ) != identity(before):
                    raise RuntimeError("Adapter identity input changed during verified access")
            if tokenizer_name() != tokenizer or identity(root.lstat()) != identity(root_info):
                raise RuntimeError("Adapter identity bundle changed during verified access")

        assert_unchanged()
        manifest = {"schema": 2, "kind": "hawedit-peft-bundle", "files": records}
        fingerprint = hashlib.sha256(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        yield (
            fingerprint,
            {name: stream for _role, name, _path, _before, _opened, stream in opened_members},
        )
        assert_unchanged()


@contextmanager
def _verified_adapter_aliases(adapter_dir: Path) -> Iterator[tuple[Path, str]]:
    """PEFT-compatible names pointing only at held original descriptors (D-285)."""
    fd_root = next((Path(p) for p in ("/proc/self/fd", "/dev/fd") if Path(p).is_dir()), None)
    if fd_root is None:
        raise RuntimeError(
            "Verified champion descriptor aliases need Linux; use the WSL ASR runtime"
        )
    with _open_adapter_bundle(adapter_dir) as (fingerprint, streams):
        aliases = Path(tempfile.mkdtemp(prefix="hawedit-champion-"))
        try:
            aliases.chmod(0o700)
            for name, stream in streams.items():
                (aliases / name).symlink_to(fd_root / str(stream.fileno()))
            aliases.chmod(0o500)
            yield aliases, fingerprint
        finally:
            aliases.chmod(0o700)
            shutil.rmtree(aliases)


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
        self.device = os.environ.get("HAWEDIT_ASR_VALIDATOR_DEVICE", device)
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
        llm_card: str = CANONICAL_LLM_CARD,
        ctc_card: str = CANONICAL_CTC_CARD,
        lora_adapter: Path | None = None,
    ) -> None:
        assert_canonical_omni_cards(llm_card, ctc_card)
        self.llm_device = os.environ.get("HAWEDIT_ASR_LLM_DEVICE", llm_device)
        self.ctc_device = os.environ.get("HAWEDIT_ASR_CTC_DEVICE", ctc_device)
        self.language = language
        self.llm_card = llm_card
        self.ctc_card = ctc_card
        self.lora_adapter = Path(lora_adapter) if lora_adapter is not None else None
        self._pipelines: tuple[Any, Any] | None = None
        self._ctc_pipeline: Any | None = None
        self._loaded_adapter_identity: str | None = None

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
        current = (
            None if self.lora_adapter is None else f"lora:{adapter_fingerprint(self.lora_adapter)}"
        )
        if (
            self._pipelines is not None or self._ctc_pipeline is not None
        ) and current != self._loaded_adapter_identity:
            raise RuntimeError("Cached ASR adapter identity changed after model construction")
        return current

    def _load(self) -> tuple[Any, Any]:
        expected_identity = self.adapter_name
        if self._pipelines is None:
            # Both default champion and explicit stock routes consume held canonical files,
            # never a freshly reopened URL-cache pathname or environment-overridden card.
            with ExitStack() as stack:
                opened_assets = stack.enter_context(open_verified_omni_assets())
                adapter_aliases = None
                if self.lora_adapter is not None:
                    adapter_aliases, fingerprint = stack.enter_context(
                        _verified_adapter_aliases(self.lora_adapter)
                    )
                    if f"lora:{fingerprint}" != expected_identity:
                        raise RuntimeError("ASR adapter identity changed before model construction")
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
                llm_pipeline = None
                if adapter_aliases is not None:
                    llm_pipeline = self._load_adapted_llm(
                        adapter_aliases,
                        checkpoint_uri=by_name["omniASR-LLM-7B-v2.pt"].file_uri,
                    )
                else:
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
                ctc_pipeline = self._ctc_pipeline
                if ctc_pipeline is None:
                    ctc_pipeline = self._make_ctc_pipeline(
                        tokenizer, by_name["omniASR-CTC-3B-v2.pt"].file_uri
                    )
                if llm_pipeline is None:
                    llm_pipeline = ASRInferencePipeline(
                        model_card=None,
                        model=llm_model,
                        tokenizer=tokenizer,
                        device=self.llm_device,
                    )
                pipelines = (llm_pipeline, ctc_pipeline)
            # A context-exit drift/cleanup failure must not leave an admitted cache.
            if self.adapter_name != expected_identity:
                raise RuntimeError("ASR adapter identity changed during model construction")
            self._loaded_adapter_identity = expected_identity
            self._pipelines = pipelines
            self._ctc_pipeline = ctc_pipeline
        return self._pipelines

    def _make_ctc_pipeline(self, tokenizer: Any, checkpoint_uri: str) -> Any:
        import torch
        from fairseq2.assets import AssetCard
        from fairseq2.models.hub import load_model
        from omnilingual_asr.models.inference.pipeline import ASRInferencePipeline

        model = load_model(
            AssetCard(
                "hawedit_omniASR_CTC_3B_v2",
                {
                    "model_family": "wav2vec2_asr",
                    "model_arch": "3b_v2",
                    "checkpoint": checkpoint_uri,
                },
            ),
            device=torch.device(self.ctc_device),
            dtype=torch.bfloat16,
        )
        return ASRInferencePipeline(
            model_card=None, model=model, tokenizer=tokenizer, device=self.ctc_device
        )

    def _load_ctc(self) -> Any:
        expected_identity = self.adapter_name
        if self._pipelines is not None:
            return self._pipelines[1]
        if self._ctc_pipeline is None:
            with open_verified_omni_assets() as opened_assets:
                assert_omni_card_integrity()
                freeze_fairseq2_asset_overrides()
                try:
                    from fairseq2.assets import AssetCard, get_asset_store
                    from fairseq2.data.tokenizers.hub import load_tokenizer
                except ImportError as exc:
                    raise RuntimeError(
                        "canonical ASR needs the 'asr' extra: pip install -e '.[asr]'"
                    ) from exc
                assert_effective_omni_cards(get_asset_store())
                by_name = {opened.asset.filename: opened for opened in opened_assets}
                tokenizer = load_tokenizer(
                    AssetCard(
                        "hawedit_omniASR_tokenizer_written_v2",
                        {
                            "tokenizer_family": "char_tokenizer",
                            "tokenizer": by_name["omniASR_tokenizer_written_v2.model"].file_uri,
                        },
                    )
                )
                ctc_pipeline = self._make_ctc_pipeline(
                    tokenizer, by_name["omniASR-CTC-3B-v2.pt"].file_uri
                )
            if self.adapter_name != expected_identity:
                raise RuntimeError("ASR adapter identity changed during CTC construction")
            self._loaded_adapter_identity = expected_identity
            self._ctc_pipeline = ctc_pipeline
        return self._ctc_pipeline

    def release_draft_model(self) -> None:
        """D-286: called only after all draft forwards have joined, before validation."""
        expected_identity = self.adapter_name
        if self._pipelines is None:
            return
        self._ctc_pipeline = self._pipelines[1]
        self._pipelines = None
        gc.collect()
        import torch

        torch.cuda.empty_cache()
        if self.adapter_name != expected_identity:
            raise RuntimeError("ASR adapter identity changed during draft release")

    def _load_adapted_llm(self, adapter_dir: Path, *, checkpoint_uri: str) -> Any:
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
        * **the base checkpoint** — supplied by the held verified canonical asset boundary.

        The `Linear` shim and the `LoraConfig` registration are PEFT/fairseq2 glue: PEFT looks
        for `in_features`/`out_features`, fairseq2's projection names them `input_dim`/
        `output_dim`, and without the mapping PEFT cannot see a layer to attach to.
        """
        import copy

        import torch
        from fairseq2.assets import AssetCard
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
        Fairseq2Linear.in_features = property(lambda self: self.input_dim)
        Fairseq2Linear.out_features = property(lambda self: self.output_dim)

        # Direct cards bypass existing metadata/environment providers. Keep derived names free
        # of the canonical trailing @, which previously produced a self-referencing tokenizer.
        base_name = self.llm_card.split("@", 1)[0]
        card_name = f"hawedit_adapted_{base_name}"
        tokenizer_card = AssetCard(
            f"{card_name}_tokenizer",
            {
                "tokenizer_family": "char_tokenizer",
                "tokenizer": tokenizers[0].absolute().as_uri(),
            },
        )
        card = AssetCard(
            card_name,
            {
                "model_family": "wav2vec2_llama",
                # Preserve the measured trainer recipe, not the official 7b_v2 shape (D-181).
                "model_arch": "7b",
                "checkpoint": checkpoint_uri,
                "tokenizer_ref": tokenizer_card.name,
            },
        )
        # The tokenizer card has no tokenizer_ref, so it cannot recurse through the model card.
        tokenizer = load_tokenizer(tokenizer_card)
        vocab_size = int(tokenizer.vocab_info.size)
        config = copy.deepcopy(get_config(get_dependency_resolver(), Wav2Vec2LlamaConfig, "7b"))
        config.llama_config.vocab_size = vocab_size
        config.wav2vec2_asr_config.target_vocab_size = vocab_size

        device = torch.device(self.llm_device)
        base = load_model(card, device=device, dtype=torch.bfloat16, config=config)
        adapter_config = LoraConfig.from_pretrained(str(adapter_dir))
        adapter_config._register_custom_module({Fairseq2Linear: LoraLinear})
        adapted = PeftModel.from_pretrained(base, str(adapter_dir), config=adapter_config)
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

    def _transcribe_llm(self, pipeline: Any, audio_path: Path) -> Any:
        return transcribe_completed(pipeline, audio_path, self.language)

    def transcribe_segment(self, audio_path: Path, duration_s: float) -> SegmentTranscript:
        expected_identity = self.adapter_name
        llm, ctc = self._load()
        # The two model forwards are independent and live on different GPUs. CTC does not need
        # the LLM text until the cheap Viterbi projection after both complete.
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="omniasr") as executor:
            text_future = executor.submit(
                self._transcribe_llm,
                llm,
                audio_path,
            )
            emissions_future = executor.submit(self._ctc_emissions, ctc, audio_path)
            texts = text_future.result()
            log_probs, frame_count, ctc_text = emissions_future.result()
        if len(texts) != 1 or not str(texts[0]).strip():
            raise RuntimeError("OmniASR LLM returned no transcription for one speech segment")
        text = str(texts[0])
        words = self._align_emissions(ctc, log_probs, frame_count, text, duration_s)
        if self.adapter_name != expected_identity:
            raise RuntimeError("ASR adapter identity changed during segment inference")
        return SegmentTranscript(text, ctc_text, words, _mean_aligned_logprob(words))

    def align_segment(self, audio_path: Path, duration_s: float, text: str) -> SegmentTranscript:
        """Align a validator correction with a fresh CTC pass on the same bounded audio."""
        if not text.strip():
            raise ValueError("cannot align an empty validator transcription")
        expected_identity = self.adapter_name
        ctc = self._load_ctc()
        log_probs, frame_count, ctc_text = self._ctc_emissions(ctc, audio_path)
        words = self._align_emissions(ctc, log_probs, frame_count, text, duration_s)
        if self.adapter_name != expected_identity:
            raise RuntimeError("ASR adapter identity changed during validator realignment")
        return SegmentTranscript(text, ctc_text, words, _mean_aligned_logprob(words))


def _mean_aligned_logprob(words: Sequence[Word]) -> float:
    """Compute duration-weighted mean log-probability in natural log units (nats, <= 0.0).

    Each word's `conf` is `exp(mean_logprob)` derived from CTC frame-level posteriors.
    Taking `ln(conf)` recovers the frame-averaged log-posterior in nats, and weighting
    by word duration yields the segment's mean log-probability in nats.
    """
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
        *,
        # Keyword-only, and after the two above: the readiness side's callers pass `validator`
        # positionally, so a `*` in front of it turns every one of them into a TypeError. The
        # adapter was keyword-only on this branch and stays that way, which costs nobody.
        lora_adapter: Path | None = None,
        context_grouping: bool = False,
    ) -> None:
        if type(context_grouping) is not bool:
            raise ValueError("ASR context grouping must be a boolean")
        if backend is not None and lora_adapter is not None:
            raise ValueError(
                "pass the adapter to the backend, not to both: a supplied backend already "
                "decides which weights run, and a second answer here could contradict it"
            )
        if validator is not None and validator_model_dir is not None:
            raise ValueError("provide a validator or validator_model_dir, not both")
        self.backend = backend or OmniAsrBackend(lora_adapter=lora_adapter)
        self.validator = validator
        self.validator_model_dir = validator_model_dir
        self.context_grouping = context_grouping

    @property
    def model_identity(self) -> str | None:
        """The adapter half of this producer's identity, or `None` when it runs stock weights.

        `pipeline.run_pipeline` keys transcript reuse on the producer, and every OmniASR run
        answers to the same class name. Without this an adapted run reuses an unadapted run's
        transcript - the same hole D-136 closed for test doubles, one axis over.
        """
        return getattr(self.backend, "adapter_name", None)

    @property
    def admission_policy(self) -> str | None:
        """Cache binding for the real canonical backend, not a fidelity attestation."""
        completion = COMPLETION_POLICY_ID if type(self.backend) is OmniAsrBackend else None
        if self.context_grouping:
            return (
                f"{completion}+{CONTEXT_GROUPING_POLICY_ID}"
                if completion is not None
                else CONTEXT_GROUPING_POLICY_ID
            )
        return completion

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
        expected_identity = self.model_identity
        expected_policy = self.admission_policy
        if self.context_grouping:
            speech_segments = _contextual_speech_regions(speech_segments)
        prepared = _cut_speech_regions(audio_path, speech_segments, work_dir, ffmpeg)
        initial, unaligned = transcribe_prepared_segments(
            self.backend, prepared, stop_on_failure=True
        )
        if type(self.backend) is OmniAsrBackend:
            self.backend.release_draft_model()
        results, validated_by, rejected_corrections = _validate_hard_segments(
            initial, self.backend, self._validator, stop_on_failure=True
        )
        if self.model_identity != expected_identity:
            raise RuntimeError("Native ASR adapter identity changed during inference")
        if self.admission_policy != expected_policy:
            raise RuntimeError("Native ASR context policy changed during inference")
        return _assemble_canonical_transcript(
            media_id,
            results,
            unaligned,
            adapter=expected_identity,
            validated_by=validated_by,
            rejected_validator_corrections=rejected_corrections,
        )


@dataclass(frozen=True, slots=True)
class _PreparedSpeechSegment:
    path: Path
    start_ms: int
    end_ms: int

    @property
    def duration_s(self) -> float:
        return (self.end_ms - self.start_ms) / 1_000


@dataclass(frozen=True, slots=True)
class _ContextSpeechRegion:
    start_ms: int
    end_ms: int


def _contextual_speech_regions(
    speech_segments: Sequence[SpeechSegment],
) -> tuple[_ContextSpeechRegion, ...]:
    """Keep complete neighboring speech under the input budget, never trim a region."""
    windows: list[_ContextSpeechRegion] = []
    previous_end: int | None = None
    for index, segment in enumerate(speech_segments):
        start, end = segment.start_ms, segment.end_ms
        if (
            type(start) is not int
            or type(end) is not int
            or not 0 <= start < end
            or end - start > int(LONG_AUDIO_THRESHOLD_S * 1_000)
        ):
            raise ValueError(f"speech region {index} has invalid interval bounds")
        if previous_end is not None and start < previous_end:
            raise ValueError(f"speech region {index} overlaps or precedes the previous interval")
        if (
            windows
            and start - windows[-1].end_ms <= _CONTEXT_MAX_GAP_MS
            and end - windows[-1].start_ms <= _CONTEXT_MAX_SPAN_MS
        ):
            windows[-1] = _ContextSpeechRegion(windows[-1].start_ms, end)
        else:
            windows.append(_ContextSpeechRegion(start, end))
        previous_end = end
    return tuple(windows)


class AsrProductionFailure(RuntimeError):
    """A production halt with original in-memory diagnostic input, not completed ASR."""

    def __init__(
        self,
        stage: str,
        diagnostic_results: Sequence[tuple[_PreparedSpeechSegment, SegmentTranscript]],
        *,
        unaligned: Sequence[UnalignedSpeech] = (),
        rejected_validator_corrections: Sequence[RejectedValidatorCorrection] = (),
    ) -> None:
        if len(unaligned) + len(rejected_validator_corrections) != 1:
            raise ValueError("a production ASR halt must name exactly its first failure")
        self.stage = stage
        self.diagnostic_results = tuple(diagnostic_results)
        self.unaligned = tuple(unaligned)
        self.rejected_validator_corrections = tuple(rejected_validator_corrections)
        failure = self.unaligned[0] if self.unaligned else self.rejected_validator_corrections[0]
        super().__init__(
            f"production ASR halted during {stage} at {failure.start_ms}..{failure.end_ms} ms: "
            f"{failure.reason}"
        )


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
            timeout=max(30.0, 10.0 + 2.0 * duration_s),
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
    *,
    stop_on_failure: bool = False,
) -> tuple[
    tuple[tuple[_PreparedSpeechSegment, SegmentTranscript], ...],
    tuple[UnalignedSpeech, ...],
]:
    """Account for diagnostic failures, or halt at the first in production (D-278).

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
        except Exception as exc:
            failure = UnalignedSpeech(
                start_ms=segment.start_ms,
                end_ms=segment.end_ms,
                reason=_failure_reason(exc),
            )
            if stop_on_failure:
                raise AsrProductionFailure(
                    "draft/alignment", results, unaligned=(failure,)
                ) from exc
            failures.append(failure)
            continue
        results.append((segment, item))
    return tuple(results), tuple(failures)


def _assemble_canonical_transcript(
    media_id: str,
    results: Sequence[tuple[_PreparedSpeechSegment, SegmentTranscript]],
    unaligned: Sequence[UnalignedSpeech] = (),
    adapter: str | None = None,
    *,
    validated_by: str | None = None,
    rejected_validator_corrections: Sequence[RejectedValidatorCorrection] = (),
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
            validated_by=validated_by,
            mean_logprob=sum(logprobs) / len(logprobs) if logprobs else None,
        ),
        unaligned=tuple(unaligned),
        segment_confidence=tuple(confidences),
        rejected_validator_corrections=tuple(rejected_validator_corrections),
    )


def _failure_reason(exc: Exception, *, limit: int = 1_024) -> str:
    """Bound one model failure for an immutable client-facing transcript."""
    raw = f"{type(exc).__name__}: {exc}"
    printable = "".join(character if character.isprintable() else " " for character in raw)
    one_line = " ".join(printable.split()) or type(exc).__name__
    return one_line if len(one_line) <= limit else one_line[: limit - 1] + "…"


def _validate_hard_segments(
    results: Sequence[tuple[_PreparedSpeechSegment, SegmentTranscript]],
    backend: OmniSegmentBackend,
    validator_factory: Callable[[], SoraniValidator],
    *,
    stop_on_failure: bool = False,
) -> tuple[
    tuple[tuple[_PreparedSpeechSegment, SegmentTranscript], ...],
    str | None,
    tuple[RejectedValidatorCorrection, ...],
]:
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
        return tuple(results), None, ()

    validator = validator_factory()
    resolve_role(validator.model_id, frozenset({"asr_validator"}), "the ASR validator")
    routed: list[tuple[_PreparedSpeechSegment, SegmentTranscript]] = []
    rejected: list[RejectedValidatorCorrection] = []
    accepted_correction = False
    for (segment, item), decision in zip(results, decisions, strict=True):
        if not decision.escalate:
            routed.append((segment, item))
            continue
        failed_stage = "validator transcription"
        try:
            corrected = validator.transcribe_segment(segment.path, segment.duration_s)
            failed_stage = "validator alignment"
            aligned = backend.align_segment(segment.path, segment.duration_s, corrected)
        except Exception as exc:
            failure = RejectedValidatorCorrection(
                start_ms=segment.start_ms,
                end_ms=segment.end_ms,
                validator=validator.model_id,
                reason=_failure_reason(exc),
            )
            if stop_on_failure:
                raise AsrProductionFailure(
                    failed_stage, results, rejected_validator_corrections=(failure,)
                ) from exc
            # A rejected correction cannot erase an already admissible canonical alignment.
            # Preserve that alignment and make the failed escalation explicit in the artifact.
            routed.append((segment, item))
            rejected.append(failure)
            continue
        accepted_correction = True
        routed.append((segment, aligned))
    return (
        tuple(routed),
        validator.model_id if accepted_correction else None,
        tuple(rejected),
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
        validator_model_dir: Path | None = None,
        context_grouping: bool = False,
    ) -> None:
        if type(context_grouping) is not bool:
            raise ValueError("ASR context grouping must be a boolean")
        self.distro = distro
        self.interpreter = interpreter
        self.wsl_executable = wsl_executable
        self.lora_adapter = Path(lora_adapter) if lora_adapter is not None else None
        self.validator_model_dir = validator_model_dir
        self.context_grouping = context_grouping
        self._receipt_distro: str | None = None

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

    @property
    def admission_policy(self) -> str:
        """The source-bound worker uses the same canonical completion contract."""
        return (
            f"{COMPLETION_POLICY_ID}+{CONTEXT_GROUPING_POLICY_ID}"
            if self.context_grouping
            else COMPLETION_POLICY_ID
        )

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
        runtime = configured_wsl_runtime()
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
        expected_identity = self.model_identity
        expected_policy = self.admission_policy
        interpreter, wsl_source = self._runtime()
        if self.context_grouping:
            speech_segments = _contextual_speech_regions(speech_segments)
        prepared = _cut_speech_regions(audio_path, speech_segments, work_dir, ffmpeg)
        if self.validator_model_dir is not None:
            validator_model_dir = self.validator_model_dir
        else:
            # `assert_available()` includes loader importability in the *calling* runtime.
            # That is correct for QwenSoraniValidator's local path, but this producer loads
            # qwen-asr inside the receipt-verified WSL generation. On Windows the checkpoint
            # can therefore be exact and runnable in WSL while intentionally not importable
            # on the host. Resolve only the registered host checkpoint path here; the held
            # access context below still verifies every byte before the WSL worker sees it.
            validator_entry = resolve_role(
                VALIDATOR_MODEL_ID,
                frozenset({"asr_validator"}),
                "the WSL ASR validator",
            )
            validator_model_dir = ModelStore().path_for(validator_entry)
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
            if self.lora_adapter is not None:
                # Only present for an adapted run, so an unadapted request stays
                # byte-identical to the one D-136's resume check compares against. Its
                # presence is also what stops a killed champion run being resumed by the
                # stock path under the same work directory. Restored across the readiness
                # merge, which rebuilt this request for the validator and carried no
                # adapter field at all.
                request["lora_adapter"] = self._wsl_path(self.lora_adapter)
                request["model_identity"] = expected_identity
            payload = json.dumps(request, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
            try:
                with request_path.open("x", encoding="utf-8", newline="\n") as stream:
                    stream.write(payload)
            except FileExistsError:
                # A run killed mid-transcription leaves this behind, and the next attempt used to
                # die
                # on a bare FileExistsError naming a path with no instruction - measured at 78 s
                # wasted
                # after Stage 0 had already been re-verified. If the request describes exactly this
                # work it is a resumed run; if it describes different segments, two runs share one
                # work
                # directory and that is refused loudly. D-136, restored across the readiness merge,
                # whose rebuilt request dropped the handler along with the request it guarded.
                existing = request_path.read_text(encoding="utf-8")
                if existing != payload:
                    raise RuntimeError(
                        f"{request_path} already describes a different Stage 1 request "
                        f"({len(json.loads(existing).get('segments', ()))} segments, this run has "
                        f"{len(prepared)}). Source, speech regions, validator or adapter inputs "
                        f"changed, or another run uses this directory. Preserve existing Stage 1 "
                        f"artifacts and use a new work directory after recovery reconciliation."
                    ) from None

            wsl_request = self._wsl_path(request_path)
            wsl_output = self._wsl_path(output_path)
            env_args = ["env", "PYTHONDONTWRITEBYTECODE=1", f"PYTHONPATH={wsl_source}"]
            for var in (
                "HAWEDIT_ASR_LLM_DEVICE",
                "HAWEDIT_ASR_CTC_DEVICE",
                "HAWEDIT_ASR_VALIDATOR_DEVICE",
            ):
                val = os.environ.get(var)
                if val:
                    env_args.append(f"{var}={val}")
            if self.model_identity != expected_identity:
                raise RuntimeError("Host ASR adapter identity changed before worker execution")
            if self.admission_policy != expected_policy:
                raise RuntimeError("Host ASR context policy changed before worker execution")
            result = subprocess.run(
                [
                    *self._prefix(),
                    *env_args,
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
                timeout=max(300.0, 60.0 + 4.0 * len(prepared) * 30.0),
            )
            if result.returncode != 0 or not output_path.is_file():
                # Keep the final cause inside the pipeline's 1,024-character detail budget.
                stderr = result.stderr.decode("utf-8", "replace")[-900:]
                raise RuntimeError(
                    f"canonical OmniASR failed in WSL2 (exit {result.returncode}); "
                    f"worker diagnostic tail: {stderr or 'no transcript was returned'}"
                )
            transcript = RawTranscript.from_json(output_path.read_text(encoding="utf-8"))
            if transcript.media_id != media_id:
                raise RuntimeError(
                    f"WSL OmniASR returned media_id {transcript.media_id!r} for {media_id!r}"
                )
            if (
                transcript.asr.adapter != expected_identity
                or self.model_identity != expected_identity
            ):
                raise RuntimeError("WSL ASR returned foreign or changed adapter identity")
            if self.admission_policy != expected_policy:
                raise RuntimeError("WSL ASR context policy changed during inference")
            return transcript


def create_omni_asr_producer(
    runtime: str = "auto", *, distro: str | None = None, lora_adapter: Path | None = None
) -> CanonicalTranscriptProducer:
    """Choose direct Linux inference or the WSL bridge without hiding that decision."""
    if runtime not in {"auto", "local", "wsl"}:
        raise ValueError("OmniASR runtime must be one of: auto, local, wsl")
    if lora_adapter is not None:
        # Fingerprinting includes all three inputs, so an incomplete bundle fails here —
        # before Stage 0's regions are cut — rather than 1,547 s later inside WSL.
        adapter_fingerprint(Path(lora_adapter))
    use_wsl = runtime == "wsl" or (runtime == "auto" and os.name == "nt")
    return (
        WslOmniAsrProducer(distro=distro, lora_adapter=lora_adapter, context_grouping=True)
        if use_wsl
        else OmniAsrProducer(lora_adapter=lora_adapter, context_grouping=True)
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
