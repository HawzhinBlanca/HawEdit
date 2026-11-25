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
import sys
import tempfile
import time
import wave
from array import array
from collections.abc import Callable, Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager, nullcontext
from dataclasses import dataclass, replace
from itertools import accumulate
from pathlib import Path
from typing import Any, BinaryIO, Final, Protocol, runtime_checkable

from hawedit import omni_assets as _omni_assets
from hawedit.asr_completion import (
    BEAM_RETRY_NBEST,
    COMPLETION_POLICY_ID,
    DecodeIncomplete,
    DecoderContractError,
    NoNaturalEos,
    loop_suspect,
    transcribe_completed,
)
from hawedit.captions import find_ffmpeg
from hawedit.corpus import CorpusItem
from hawedit.escalation import EscalationDecision, SegmentScore, select_for_validation
from hawedit.forced_alignment import align_words
from hawedit.models import ModelStore, assert_transformers_config_safe, verified_checkpoint_access
from hawedit.omni_assets import (
    CANONICAL_CTC_CARD,
    CANONICAL_LLM_CARD,
    OMNI_ASSETS,
    FusedCheckpointAsset,
    _hash_open_stream,
    _open_regular_nofollow,
    assert_canonical_omni_cards,
    assert_effective_omni_cards,
    assert_omni_card_integrity,
    freeze_fairseq2_asset_overrides,
    open_verified_omni_assets,
)
from hawedit.qwen_completion import (
    QWEN_COMPLETION_POLICY_ID,
    assert_qwen_runtime,
    transcribe_qwen_completed,
)
from hawedit.registry import ASR_ROLES, ModelEntry, resolve_role
from hawedit.transcripts import (
    AsrProvenance,
    RawTranscript,
    RejectedValidatorCorrection,
    SegmentConfidence,
    SegmentOrigin,
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
    "CHAMPION_CHECKPOINT_ENV",
    "CLIP_ASR_DEFAULT_PAD_MS",
    "CLIP_ASR_MAX_PAD_MS",
    "CLIP_ASR_MIN_PAD_MS",
    "DEFAULT_CHAMPION_CHECKPOINT_PATHS",
    "LONG_AUDIO_THRESHOLD_S",
    "STRICT_RUNTIME_ENV",
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
    "discover_default_champion_checkpoint",
    "long_audio_failure_rate",
    "resolve_champion_adapter",
    "resolve_champion_checkpoint",
    "select_contextual_regions_for_spans",
    "strict_runtime_enabled",
    "validate_adapter",
]

STRICT_RUNTIME_ENV: Final = "HAWEDIT_STRICT_RUNTIME"
PLAIN_WSL_PYTHON_CANDIDATES: Final = (
    "/home/ai/.cache/hawedit-plain-wsl-venv/bin/python",
    "/home/ai/.venv-wsl-whisper/bin/python",
    "/home/ai/.venv-wsl-whisper/bin/python3",
)


def strict_runtime_enabled(
    env: Mapping[str, str] | None = None,
    *,
    strict: bool | None = None,
) -> bool:
    """Return True when sealed receipt/admission runtime controls are requested (A3, D-337)."""
    if strict is not None:
        return bool(strict)
    environ = os.environ if env is None else env
    raw = environ.get(STRICT_RUNTIME_ENV, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _discover_plain_wsl_python(
    *,
    distro: str | None = None,
    executable: str = "wsl.exe",
) -> str:
    """Locate the plain WSL virtualenv interpreter without requiring a sealed .ready receipt."""
    prefix = wsl_prefix(distro, executable)
    for candidate in PLAIN_WSL_PYTHON_CANDIDATES:
        probe = subprocess.run(
            [*prefix, "test", "-x", candidate],
            capture_output=True,
            check=False,
            timeout=15,
        )
        if probe.returncode == 0:
            return candidate
    raise RuntimeError(
        "plain OmniASR WSL Python interpreter was not found "
        f"(tried {', '.join(PLAIN_WSL_PYTHON_CANDIDATES)}). Set HAWEDIT_WSL_PYTHON or pass "
        "--strict-runtime after hawedit-asr-setup"
    )


# §3 Stage 1: OmniASR's interface ceiling. Stage 0's VAD uses max_speech_duration_s=38 to
# stay under it, so anything past this is by definition outside the designed operating range
# and its failure rate is a property worth measuring rather than an accident.
LONG_AUDIO_THRESHOLD_S: Final = 40.0
# Owner rule (D-331): Stage 1 drafts, aligns and validates on GPU 1 only by default. GPU 0 stays
# visible (gpu_runtime refuses CUDA_VISIBLE_DEVICES) but unused; HAWEDIT_ASR_*_DEVICE override.
DEFAULT_ASR_DEVICE: Final = "cuda:1"
VALIDATOR_MODEL_ID: Final = "rzgar/qwen3-asr-sorani-kurdish-ckb-v1"
_CONTEXT_MAX_GAP_MS: Final = 1_000
_CONTEXT_MAX_SPAN_MS: Final = 18_000
CLIP_ASR_MIN_PAD_MS: Final = 3_000
CLIP_ASR_DEFAULT_PAD_MS: Final = 4_000
CLIP_ASR_MAX_PAD_MS: Final = 5_000
ASR_COMPLETION_POLICY_ID: Final = COMPLETION_POLICY_ID + "+" + QWEN_COMPLETION_POLICY_ID
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
    # D-332: how the draft text was decoded, and why a greedy draft was retried.
    decode_mode: str = "greedy"
    retry_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.text_raw.strip():
            raise ValueError("OmniASR returned an empty speech segment")
        if (self.decode_mode, self.retry_reason is None) not in (
            ("greedy", True),
            ("beam5_retry", False),
        ):
            raise ValueError("segment decode_mode must be greedy, or beam5_retry with a reason")
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
# A fused champion checkpoint (D-331). Unset means the LoRA champion above stays the default.
CHAMPION_CHECKPOINT_ENV: Final = "HAWEDIT_CHAMPION_CHECKPOINT"
DEFAULT_CHAMPION_CHECKPOINT_PATHS: Final = (
    Path(
        r"F:\Kurdish Sorani Dataset\omni_7b_v3_continuation"
        r"\runs\champion_v12_lora64_750_fused\kurdish_omniasr_7b_v12_c750.pt"
    ),
)


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


# A fused trainer checkpoint replaces the stock LLM weights, so only CTC-3B and the canonical
# tokenizer are held from the stock asset set. D-331.
_FUSED_HELD_ASSETS: Final = tuple(
    asset for asset in OMNI_ASSETS if asset.filename != "omniASR-LLM-7B-v2.pt"
)
# The fused v12 checkpoint was trained with the canonical written-v2 tokenizer (10288 ids).
FUSED_VOCAB_SIZE: Final = 10288
# Stat identity -> measured SHA-256: a 15.6 GB checkpoint is hashed once per process, not per load.
_FUSED_DIGESTS: dict[tuple[int, ...], str] = {}


def fused_checkpoint_asset(checkpoint: Path) -> FusedCheckpointAsset:
    """The code-allowlisted entry this path names, or an honest halt. Cheap: no hashing.

    Admission is by ``FUSED_CHECKPOINT_ASSETS`` only (filename and exact size here; the worker
    checks the SHA-256 of the held bytes before any loader). Files beside the checkpoint, such
    as ``SHA256SUMS``, are never an authority: whoever writes the ``.pt`` can write them too.
    """
    try:
        info = checkpoint.lstat()
    except OSError as exc:
        raise ChampionUnavailable(f"fused champion checkpoint is missing: {checkpoint}") from exc
    if not stat.S_ISREG(info.st_mode):
        raise ChampionUnavailable(f"fused champion checkpoint is not a regular file: {checkpoint}")
    allowlist = _omni_assets.FUSED_CHECKPOINT_ASSETS  # read at call time; tests patch it
    matches = [asset for asset in allowlist if asset.filename == checkpoint.name]
    if len(matches) != 1 or matches[0].size != info.st_size:
        raise ChampionUnavailable(
            f"{checkpoint} ({info.st_size} bytes) is not on HawEdit's fused checkpoint "
            "allowlist (exact filename, size and SHA-256); refusing to load it"
        )
    return matches[0]


@contextmanager
def _held_fused_checkpoint(checkpoint: Path, asset: FusedCheckpointAsset) -> Iterator[str]:
    """Verify the allowlisted size and SHA-256 of the held bytes, then load only through them."""
    stream, before = _open_regular_nofollow(checkpoint, require_single_link=True)
    with stream:
        if before.st_size != asset.size:
            raise ChampionUnavailable(
                f"fused champion {checkpoint} is {before.st_size} bytes, not the allowlisted "
                f"{asset.size}; refusing to load it"
            )
        key = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
        digest = _FUSED_DIGESTS.get(key)
        if digest is None:
            _, digest = _hash_open_stream(stream, before, checkpoint)
            _FUSED_DIGESTS[key] = digest
        if digest != asset.sha256:
            raise ChampionUnavailable(
                f"fused champion {checkpoint} hashes to {digest}, not the allowlisted "
                f"{asset.sha256}; refusing to load it"
            )
        fd_root = next((Path(p) for p in ("/proc/self/fd", "/dev/fd") if Path(p).is_dir()), None)
        if fd_root is None:
            raise RuntimeError(
                "Verified fused checkpoint descriptors need Linux; use the WSL ASR runtime"
            )
        aliases = Path(tempfile.mkdtemp(prefix="hawedit-fused-"))
        try:
            aliases.chmod(0o700)
            alias = aliases / checkpoint.name
            alias.symlink_to(fd_root / str(stream.fileno()))
            aliases.chmod(0o500)
            yield alias.as_uri()
        finally:
            aliases.chmod(0o700)
            shutil.rmtree(aliases)
        after = os.fstat(stream.fileno())
        if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) != key:
            raise RuntimeError("Fused champion checkpoint changed during verified access")


def resolve_champion_checkpoint(env: Mapping[str, str] | None = None) -> Path | None:
    """The fused champion named by ``HAWEDIT_CHAMPION_CHECKPOINT``, or ``None`` when unset.

    Set means required: a missing or non-allowlisted ``.pt`` raises ``ChampionUnavailable``
    rather than drafting with the LoRA champion or the base decoder instead (D-260, D-331).
    """
    environ = os.environ if env is None else env
    raw = environ.get(CHAMPION_CHECKPOINT_ENV, "").strip()
    if not raw:
        return None
    checkpoint = Path(raw)
    fused_checkpoint_asset(checkpoint)
    return checkpoint


def discover_default_champion_checkpoint(
    candidates: Sequence[Path] = DEFAULT_CHAMPION_CHECKPOINT_PATHS,
) -> Path | None:
    """Return the default fused champion v12 checkpoint if present and allowlisted."""
    for candidate in candidates:
        path = Path(candidate)
        if not path.is_file():
            continue
        fused_checkpoint_asset(path)
        return path
    return None


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


def _qwen_audio_input(audio_path: Path) -> str | tuple[Any, int]:
    """Use Qwen's tuple API only for Stage 1's bounded canonical PCM (D-303)."""
    try:
        with wave.open(str(audio_path), "rb") as audio:
            if (
                audio.getnchannels(),
                audio.getsampwidth(),
                audio.getframerate(),
                audio.getcomptype(),
            ) != (1, 2, 16_000, "NONE"):
                return str(audio_path)
            frames = audio.getnframes()
            if not 0 < frames <= LONG_AUDIO_THRESHOLD_S * 16_000:
                return str(audio_path)
            pcm = audio.readframes(frames)
    except (OSError, EOFError, wave.Error):
        return str(audio_path)
    if len(pcm) != frames * 2:
        return str(audio_path)
    import numpy as np

    return np.frombuffer(pcm, dtype="<i2").astype("float32") / 32768.0, 16_000


class QwenSoraniValidator:
    """The official Qwen-ASR loader for §3's fine-tuned Sorani validator."""

    model_id = VALIDATOR_MODEL_ID

    def __init__(
        self,
        model_dir: Path,
        *,
        device: str = DEFAULT_ASR_DEVICE,
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
        assert_qwen_runtime()
        model = self._load()
        results = transcribe_qwen_completed(model, _qwen_audio_input(audio_path))
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
        llm_device: str = DEFAULT_ASR_DEVICE,
        ctc_device: str = DEFAULT_ASR_DEVICE,
        language: str = "ckb_Arab",
        llm_card: str = CANONICAL_LLM_CARD,
        ctc_card: str = CANONICAL_CTC_CARD,
        lora_adapter: Path | None = None,
        fused_checkpoint: Path | None = None,
    ) -> None:
        assert_canonical_omni_cards(llm_card, ctc_card)
        if lora_adapter is not None and fused_checkpoint is not None:
            raise ValueError(
                "a fused checkpoint already contains its fine-tune; pass it or a LoRA adapter, "
                "not both"
            )
        self.llm_device = os.environ.get("HAWEDIT_ASR_LLM_DEVICE", llm_device)
        self.ctc_device = os.environ.get("HAWEDIT_ASR_CTC_DEVICE", ctc_device)
        self.language = language
        self.llm_card = llm_card
        self.ctc_card = ctc_card
        self.lora_adapter = Path(lora_adapter) if lora_adapter is not None else None
        self.fused_checkpoint = Path(fused_checkpoint) if fused_checkpoint is not None else None
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
        if self.fused_checkpoint is not None:
            current: str | None = f"fused:{fused_checkpoint_asset(self.fused_checkpoint).sha256}"
        elif self.lora_adapter is not None:
            current = f"lora:{adapter_fingerprint(self.lora_adapter)}"
        else:
            current = None
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
                opened_assets = stack.enter_context(self._open_held_assets())
                adapter_aliases = None
                fused_uri = None
                if self.fused_checkpoint is not None:
                    allowed = fused_checkpoint_asset(self.fused_checkpoint)
                    if f"fused:{allowed.sha256}" != expected_identity:
                        raise RuntimeError("ASR fused identity changed before model construction")
                    fused_uri = stack.enter_context(
                        _held_fused_checkpoint(self.fused_checkpoint, allowed)
                    )
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
                if fused_uri is not None:
                    llm_pipeline = self._load_fused_llm(
                        by_name["omniASR_tokenizer_written_v2.model"].file_uri,
                        checkpoint_uri=fused_uri,
                    )
                elif adapter_aliases is not None:
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

    def _open_held_assets(self) -> Any:
        # A fused run never reads the stock LLM weights, so it does not hold or hash them.
        if self.fused_checkpoint is not None:
            return open_verified_omni_assets(assets=_FUSED_HELD_ASSETS)
        return open_verified_omni_assets()

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
            with self._open_held_assets() as opened_assets:
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
        import torch
        from fairseq2.nn.projection import Linear as Fairseq2Linear
        from omnilingual_asr.models.inference.pipeline import ASRInferencePipeline

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

        base, tokenizer = self._load_trainer_7b(
            "adapted", checkpoint_uri, tokenizers[0].absolute().as_uri()
        )
        device = torch.device(self.llm_device)
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

    def _load_trainer_7b(
        self,
        kind: str,
        checkpoint_uri: str,
        tokenizer_uri: str,
        *,
        expected_vocab: int | None = None,
    ) -> tuple[Any, Any]:
        """The trainer's ``7b`` LLM with tokenizer-derived vocabulary (D-181, D-285).

        Shared by the LoRA base and the fused checkpoint (D-331); no PEFT here.
        """
        import copy

        import torch
        from fairseq2.assets import AssetCard
        from fairseq2.data.tokenizers import load_tokenizer
        from fairseq2.models.hub import load_model
        from fairseq2.runtime.config_registry import get_config
        from fairseq2.runtime.dependency import get_dependency_resolver
        from omnilingual_asr.models.wav2vec2_llama import Wav2Vec2LlamaConfig

        # Direct cards bypass existing metadata/environment providers. Keep derived names free
        # of the canonical trailing @, which previously produced a self-referencing tokenizer.
        base_name = self.llm_card.split("@", 1)[0]
        card_name = f"hawedit_{kind}_{base_name}"
        tokenizer_card = AssetCard(
            f"{card_name}_tokenizer",
            {"tokenizer_family": "char_tokenizer", "tokenizer": tokenizer_uri},
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
        if expected_vocab is not None and vocab_size != expected_vocab:
            raise RuntimeError(
                f"the held tokenizer reports {vocab_size} ids but the fused checkpoint was "
                f"trained with {expected_vocab}; refusing to load mismatched weights"
            )
        config = copy.deepcopy(get_config(get_dependency_resolver(), Wav2Vec2LlamaConfig, "7b"))
        config.llama_config.vocab_size = vocab_size
        config.wav2vec2_asr_config.target_vocab_size = vocab_size
        model = load_model(
            card, device=torch.device(self.llm_device), dtype=torch.bfloat16, config=config
        )
        return model, tokenizer

    def _load_fused_llm(self, tokenizer_uri: str, *, checkpoint_uri: str) -> Any:
        """A fused trainer checkpoint: the LoRA path's ``7b`` load without PEFT (D-331)."""
        import torch
        from omnilingual_asr.models.inference.pipeline import ASRInferencePipeline

        model, tokenizer = self._load_trainer_7b(
            "fused", checkpoint_uri, tokenizer_uri, expected_vocab=FUSED_VOCAB_SIZE
        )
        return ASRInferencePipeline(
            model_card=None,
            model=model,
            tokenizer=tokenizer,
            device=torch.device(self.llm_device),
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

    def _transcribe_llm_beam(self, pipeline: Any, audio_path: Path) -> Any:
        """The same loaded model, tokenizer and device, decoded with upstream beam 5."""
        from omnilingual_asr.models.inference.pipeline import ASRInferencePipeline
        from omnilingual_asr.models.wav2vec2_llama.config import Wav2Vec2LlamaBeamSearchConfig

        beam = ASRInferencePipeline(
            model_card=None,
            model=pipeline.model,
            tokenizer=pipeline.tokenizer,
            device=pipeline.device,
            dtype=pipeline.dtype,
            beam_search_config=Wav2Vec2LlamaBeamSearchConfig(nbest=BEAM_RETRY_NBEST),
        )
        return transcribe_completed(beam, audio_path, self.language, nbest=BEAM_RETRY_NBEST)

    def _greedy_draft(self, pipeline: Any, audio_path: Path, duration_s: float) -> tuple[str, str]:
        """Greedy as before; returns the text and why it is suspect ("" when clean, D-332)."""
        try:
            text = _one_draft(self._transcribe_llm(pipeline, audio_path))
        except NoNaturalEos as exc:
            return "", f"no natural EOS ({exc})"
        return text, loop_suspect(text, duration_s) or ""

    def _beam_retry(
        self, llm: Any, ctc: Any, audio_path: Path, duration_s: float, reason: str
    ) -> str:
        """One beam-5 retry of a suspect segment, else halt (D-332).

        Never trims repeats, splices the attempts or falls back to another model.
        """
        with self._ctc_parked(ctc):
            try:
                retried = _one_draft(self._transcribe_llm_beam(llm, audio_path))
                problem = loop_suspect(retried, duration_s)
            except NoNaturalEos as exc:
                problem = f"no natural EOS ({exc})"
        if problem is not None:
            raise DecodeIncomplete(
                f"segment {audio_path.name}: greedy attempt: {reason}; beam-5 retry: {problem}"
            )
        return retried

    @contextmanager
    def _ctc_parked(self, ctc: Any) -> Iterator[None]:
        """D-332 option 1: beam 5 beside a resident CTC-3B overflows one 24 GB card.

        Only when both models share a CUDA device, CTC waits on the CPU for the retry and always
        returns; if it cannot, the run halts rather than aligning on the CPU or another model.
        """
        if self.llm_device != self.ctc_device or not self.ctc_device.startswith("cuda"):
            yield
            return
        try:
            self._park_ctc(ctc)
            yield
        finally:
            try:
                self._restore_ctc(ctc)
            except Exception as exc:
                raise DecoderContractError(
                    f"CTC-3B could not return to {self.ctc_device} after the beam-5 retry; "
                    "halting rather than continuing with CTC off its device"
                ) from exc

    def _park_ctc(self, ctc: Any) -> None:
        import torch

        ctc.model.to("cpu")
        torch.cuda.empty_cache()

    def _restore_ctc(self, ctc: Any) -> None:
        ctc.model.to(self.ctc_device)

    def transcribe_segment(self, audio_path: Path, duration_s: float) -> SegmentTranscript:
        expected_identity = self.adapter_name
        llm, ctc = self._load()
        # The two greedy forwards are independent. CTC does not need the LLM text until the
        # cheap Viterbi projection after both complete.
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="omniasr") as executor:
            text_future = executor.submit(self._greedy_draft, llm, audio_path, duration_s)
            emissions_future = executor.submit(self._ctc_emissions, ctc, audio_path)
            text, retry_reason = text_future.result()
            log_probs, frame_count, ctc_text = emissions_future.result()
        if retry_reason:
            # After the join, so no CTC forward is running when the retry parks CTC (D-332).
            text = self._beam_retry(llm, ctc, audio_path, duration_s, retry_reason)
        words = self._align_emissions(ctc, log_probs, frame_count, text, duration_s)
        if self.adapter_name != expected_identity:
            raise RuntimeError("ASR adapter identity changed during segment inference")
        return SegmentTranscript(
            text,
            ctc_text,
            words,
            _mean_aligned_logprob(words),
            "beam5_retry" if retry_reason else "greedy",
            retry_reason or None,
        )

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


def _one_draft(texts: Any) -> str:
    if len(texts) != 1 or not str(texts[0]).strip():
        raise RuntimeError("OmniASR LLM returned no transcription for one speech segment")
    return str(texts[0])


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
        fused_checkpoint: Path | None = None,
        validate_hard_segments: bool = True,
    ) -> None:
        if type(context_grouping) is not bool:
            raise ValueError("ASR context grouping must be a boolean")
        if type(validate_hard_segments) is not bool:
            raise ValueError("ASR validator toggle must be a boolean")
        if backend is not None and (lora_adapter is not None or fused_checkpoint is not None):
            raise ValueError(
                "pass the adapter to the backend, not to both: a supplied backend already "
                "decides which weights run, and a second answer here could contradict it"
            )
        if validator is not None and validator_model_dir is not None:
            raise ValueError("provide a validator or validator_model_dir, not both")
        if not validate_hard_segments and (
            validator is not None or validator_model_dir is not None
        ):
            raise ValueError(
                "cannot pass a validator or validator_model_dir when "
                "validate_hard_segments is False"
            )
        self.backend = backend or OmniAsrBackend(
            lora_adapter=lora_adapter, fused_checkpoint=fused_checkpoint
        )
        self.validator = validator
        self.validator_model_dir = validator_model_dir
        self.context_grouping = context_grouping
        self.validate_hard_segments = validate_hard_segments

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
        return _producer_admission_policy(
            type(self.backend) is OmniAsrBackend,
            self.context_grouping,
            self.validate_hard_segments,
        )

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
        results, validated_by, rejected_corrections, origins = _validate_hard_segments(
            initial,
            self.backend,
            self._validator,
            stop_on_failure=True,
            enabled=self.validate_hard_segments,
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
            segment_origins=origins,
        )


@dataclass(frozen=True, slots=True)
class _PreparedSpeechSegment:
    path: Path
    start_ms: int
    end_ms: int
    sub_segments: tuple[tuple[int, int], ...] = ()

    @property
    def duration_s(self) -> float:
        return (self.end_ms - self.start_ms) / 1_000


@dataclass(frozen=True, slots=True)
class _ContextSpeechRegion:
    start_ms: int
    end_ms: int
    constituents: tuple[tuple[int, int], ...] = ()


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
        seg_constituents = tuple(getattr(segment, "constituents", ())) or ((start, end),)
        if (
            windows
            and start - windows[-1].end_ms <= _CONTEXT_MAX_GAP_MS
            and end - windows[-1].start_ms <= _CONTEXT_MAX_SPAN_MS
        ):
            prev = windows[-1]
            merged = (*(prev.constituents or ((prev.start_ms, prev.end_ms),)), *seg_constituents)
            windows[-1] = _ContextSpeechRegion(prev.start_ms, end, merged)
        else:
            windows.append(
                _ContextSpeechRegion(
                    start,
                    end,
                    seg_constituents if len(seg_constituents) >= 2 else (),
                )
            )
        previous_end = end
    return tuple(windows)


def select_contextual_regions_for_spans(
    speech_segments: Sequence[SpeechSegment],
    clip_spans_ms: Sequence[tuple[int, int]],
    *,
    duration_ms: int,
    pad_ms: int = CLIP_ASR_DEFAULT_PAD_MS,
) -> tuple[SpeechSegment, ...]:
    """Select ordered episode-aligned `_ContextSpeechRegion`s overlapping padded clip spans."""
    if type(pad_ms) is not int or not CLIP_ASR_MIN_PAD_MS <= pad_ms <= CLIP_ASR_MAX_PAD_MS:
        raise ValueError(
            f"clip ASR pad_ms must be between {CLIP_ASR_MIN_PAD_MS} and {CLIP_ASR_MAX_PAD_MS} ms"
        )
    if type(duration_ms) is not int or duration_ms <= 0:
        raise ValueError("clip ASR duration_ms must be a positive integer")
    if not clip_spans_ms:
        raise ValueError("clip ASR requires at least one clip span")
    windows: list[tuple[int, int]] = []
    for index, (in_ms, out_ms) in enumerate(clip_spans_ms):
        if (
            type(in_ms) is not int
            or type(out_ms) is not int
            or not 0 <= in_ms < out_ms <= duration_ms
        ):
            raise ValueError(
                f"clip span {index} ({in_ms}..{out_ms}) is invalid for duration {duration_ms}"
            )
        windows.append((max(0, in_ms - pad_ms), min(duration_ms, out_ms + pad_ms)))
    grouped = _contextual_speech_regions(speech_segments)
    return tuple(
        region
        for region in grouped
        if any(region.end_ms > win_in and region.start_ms < win_out for win_in, win_out in windows)
    )


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
        actual_end_ms = start_ms + actual_duration_ms
        raw_subs = tuple(
            (s_start, min(s_end, actual_end_ms))
            for s_start, s_end in getattr(segment, "constituents", ())
            if s_start >= start_ms and min(s_end, actual_end_ms) > s_start
        )
        prepared.append(
            _PreparedSpeechSegment(
                segment_path,
                start_ms,
                actual_end_ms,
                sub_segments=raw_subs if len(raw_subs) >= 2 else (),
            )
        )
    return tuple(prepared)


SINGLETON_DIP_MIN_DURATION_MS: Final = 8_000
SINGLETON_DIP_EDGE_GUARD_MS: Final = 3_000
SINGLETON_DIP_WINDOW_MS: Final = 200
SINGLETON_DIP_HOP_MS: Final = 10
SINGLETON_DIP_MAX_RMS_RATIO: Final = 0.15


def _read_pcm16_wav(path: Path) -> tuple[int, bytes]:
    """Read frame count and raw PCM16 frames from a 16 kHz mono WAV."""
    with wave.open(str(path), "rb") as stream:
        channels = stream.getnchannels()
        sample_width = stream.getsampwidth()
        sample_rate = stream.getframerate()
        compression = stream.getcomptype()
        total_frames = stream.getnframes()
        if (channels, sample_width, sample_rate, compression) != (1, 2, 16_000, "NONE"):
            raise RuntimeError(
                f"cannot split {path.name}: expected 16 kHz mono PCM16, got "
                f"{channels}ch/{sample_width * 8}-bit/{sample_rate}Hz/{compression}"
            )
        return total_frames, stream.readframes(total_frames)


def silence_dip_split_ms(path: Path) -> int | None:
    """Find a deterministic min-RMS breath/pause center in a long singleton WAV (D-343)."""
    total_frames, raw_frames = _read_pcm16_wav(path)
    duration_ms = round(total_frames * 1_000 / 16_000)
    if duration_ms < SINGLETON_DIP_MIN_DURATION_MS or total_frames <= 0:
        return None
    samples = array("h")
    samples.frombytes(raw_frames)
    if sys.byteorder != "little":
        samples.byteswap()
    if len(samples) != total_frames:
        raise RuntimeError(f"ASR segment has truncated PCM frames: {path}")
    sq_prefix = [0, *accumulate(sample * sample for sample in samples)]
    overall_sq = sq_prefix[total_frames]
    if overall_sq <= 0:
        return None
    overall_rms = math.sqrt(overall_sq / total_frames)
    lo_frame = round(SINGLETON_DIP_EDGE_GUARD_MS * 16)
    hi_frame = min(total_frames, round((duration_ms - SINGLETON_DIP_EDGE_GUARD_MS) * 16))
    win_frames = SINGLETON_DIP_WINDOW_MS * 16
    hop_frames = SINGLETON_DIP_HOP_MS * 16
    if hi_frame - lo_frame < win_frames:
        return None
    best_start = lo_frame
    best_win_sq = sq_prefix[lo_frame + win_frames] - sq_prefix[lo_frame]
    for start in range(lo_frame + hop_frames, hi_frame - win_frames + 1, hop_frames):
        win_sq = sq_prefix[start + win_frames] - sq_prefix[start]
        if win_sq < best_win_sq:
            best_win_sq = win_sq
            best_start = start
    min_window_rms = math.sqrt(best_win_sq / win_frames)
    if min_window_rms > SINGLETON_DIP_MAX_RMS_RATIO * overall_rms:
        return None
    split_ms = round((best_start + win_frames / 2.0) / 16.0)
    if not 0 < split_ms < duration_ms:
        return None
    return split_ms


def _write_pcm_slices(
    segment: _PreparedSpeechSegment,
    intervals: Sequence[tuple[int, int]],
    tag: str,
    *,
    contiguous_to_end: bool = False,
) -> tuple[_PreparedSpeechSegment, ...]:
    """Atomically slice sub-intervals from a cut 16 kHz mono PCM16 WAV."""
    total_frames, raw_frames = _read_pcm16_wav(segment.path)
    bytes_per_frame = 2
    sub_prepared: list[_PreparedSpeechSegment] = []
    for idx, (sub_start, sub_end) in enumerate(intervals):
        start_frame = max(0, min(total_frames, round((sub_start - segment.start_ms) * 16)))
        end_frame = (
            total_frames
            if contiguous_to_end and idx == len(intervals) - 1
            else max(0, min(total_frames, round((sub_end - segment.start_ms) * 16)))
        )
        if end_frame <= start_frame:
            raise RuntimeError(
                f"{tag} sub-segment {idx} ({sub_start}..{sub_end} ms) produced no PCM frames"
            )
        sub_path = segment.path.with_name(f"{segment.path.stem}-{tag}-{idx:02d}.wav")
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{sub_path.name}.", suffix=".tmp", dir=str(sub_path.parent)
        )
        os.close(fd)
        tmp_path = Path(tmp_name)
        try:
            with wave.open(str(tmp_path), "wb") as out:
                out.setnchannels(1)
                out.setsampwidth(2)
                out.setframerate(16_000)
                out.writeframes(
                    raw_frames[start_frame * bytes_per_frame : end_frame * bytes_per_frame]
                )
            os.replace(tmp_path, sub_path)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise
        actual_ms = _pcm_duration_ms(sub_path)
        sub_prepared.append(_PreparedSpeechSegment(sub_path, sub_start, sub_start + actual_ms))
    return tuple(sub_prepared)


def _cut_pcm_subsegments(segment: _PreparedSpeechSegment) -> tuple[_PreparedSpeechSegment, ...]:
    """Slice constituent raw VAD sub-segments from a cut 16 kHz mono PCM16 WAV (D-342)."""
    return _write_pcm_slices(segment, segment.sub_segments, "sub")


def _cut_pcm_dip_halves(segment: _PreparedSpeechSegment) -> tuple[_PreparedSpeechSegment, ...]:
    """Slice a long failing singleton into two contiguous WAVs at a silence dip (D-343)."""
    if segment.end_ms - segment.start_ms < SINGLETON_DIP_MIN_DURATION_MS:
        return ()
    split_ms = silence_dip_split_ms(segment.path)
    if split_ms is None:
        return ()
    split_media_ms = segment.start_ms + split_ms
    return _write_pcm_slices(
        segment,
        ((segment.start_ms, split_media_ms), (split_media_ms, segment.end_ms)),
        "dip",
        contiguous_to_end=True,
    )


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


def _is_cuda_oom(exc: BaseException) -> bool:
    """Return True when ``exc`` is a PyTorch CUDA out-of-memory error."""
    return type(exc).__name__ == "OutOfMemoryError" or "CUDA out of memory" in str(exc)


def _clear_cuda_cache() -> None:
    """Release cached CUDA allocator blocks after an OOM before retrying smaller halves."""
    try:
        import torch
    except ImportError:
        return
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _cut_pcm_oom_halves(
    segment: _PreparedSpeechSegment,
) -> tuple[_PreparedSpeechSegment, ...]:
    """Split an oversized (>20 s) segment into two contiguous halves for 24 GiB VRAM fit."""
    if segment.end_ms - segment.start_ms <= 20_000:
        return ()
    if len(segment.sub_segments) >= 2:
        return _cut_pcm_subsegments(segment)
    dip_halves = _cut_pcm_dip_halves(segment)
    if dip_halves:
        return dip_halves
    mid_ms = segment.start_ms + (segment.end_ms - segment.start_ms) // 2
    return _write_pcm_slices(
        segment,
        ((segment.start_ms, mid_ms), (mid_ms, segment.end_ms)),
        "oom",
        contiguous_to_end=True,
    )


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
        except DecodeIncomplete as exc:
            split_segments: tuple[_PreparedSpeechSegment, ...] = ()
            if not isinstance(exc, DecoderContractError):
                split_segments = (
                    _cut_pcm_subsegments(segment)
                    if len(segment.sub_segments) >= 2
                    else _cut_pcm_dip_halves(segment)
                )
            if not split_segments:
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
            for sub in split_segments:
                try:
                    sub_item = backend.transcribe_segment(sub.path, sub.duration_s)
                except Exception as sub_exc:
                    failure = UnalignedSpeech(
                        start_ms=sub.start_ms,
                        end_ms=sub.end_ms,
                        reason=_failure_reason(sub_exc),
                    )
                    if stop_on_failure:
                        raise AsrProductionFailure(
                            "draft/alignment", results, unaligned=(failure,)
                        ) from sub_exc
                    failures.append(failure)
                    continue
                results.append((sub, sub_item))
        except Exception as exc:
            oom_halves: tuple[_PreparedSpeechSegment, ...] = ()
            if _is_cuda_oom(exc):
                _clear_cuda_cache()
                oom_halves = _cut_pcm_oom_halves(segment)
            if oom_halves:
                for sub in oom_halves:
                    try:
                        sub_item = backend.transcribe_segment(sub.path, sub.duration_s)
                    except Exception as sub_exc:
                        failure = UnalignedSpeech(
                            start_ms=sub.start_ms,
                            end_ms=sub.end_ms,
                            reason=_failure_reason(sub_exc),
                        )
                        if stop_on_failure:
                            raise AsrProductionFailure(
                                "draft/alignment", results, unaligned=(failure,)
                            ) from sub_exc
                        failures.append(failure)
                        continue
                    results.append((sub, sub_item))
                continue
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
        else:
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
    segment_origins: tuple[SegmentOrigin, ...] | None = None,
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
                    decode_mode=item.decode_mode,
                    retry_reason=item.retry_reason,
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
        segment_origins=segment_origins,
    )


def _failure_reason(exc: Exception, *, limit: int = 1_024) -> str:
    """Bound one model failure for an immutable client-facing transcript."""
    raw = f"{type(exc).__name__}: {exc}"
    printable = "".join(character if character.isprintable() else " " for character in raw)
    one_line = " ".join(printable.split()) or type(exc).__name__
    return one_line if len(one_line) <= limit else one_line[: limit - 1] + "…"


def _producer_admission_policy(
    has_real_backend: bool,
    context_grouping: bool,
    validate_hard_segments: bool,
) -> str | None:
    """Shared cache-key policy ensuring validated and validator-off runs stay isolated."""
    parts: list[str] = []
    if has_real_backend:
        parts.append(ASR_COMPLETION_POLICY_ID if validate_hard_segments else COMPLETION_POLICY_ID)
    if context_grouping:
        parts.append(CONTEXT_GROUPING_POLICY_ID)
    if not validate_hard_segments:
        parts.append("validator-off")
    return "+".join(parts) if parts else None


def _segment_origin(
    segment: _PreparedSpeechSegment,
    draft: SegmentTranscript,
    selected: SegmentTranscript,
    decision: EscalationDecision,
    outcome: str,
    *,
    validator: str | None = None,
    validator_text: str | None = None,
    rejection_reason: str | None = None,
) -> SegmentOrigin:
    def confidence(item: SegmentTranscript) -> SegmentConfidence:
        return SegmentConfidence(
            segment.start_ms,
            segment.end_ms,
            item.mean_logprob,
            item.text_raw,
            item.ctc_text,
            item.decode_mode,
            item.retry_reason,
        )

    return SegmentOrigin(
        draft=confidence(draft),
        selected=confidence(selected),
        selected_words=tuple(
            replace(
                word,
                start_ms=word.start_ms + segment.start_ms,
                end_ms=word.end_ms + segment.start_ms,
            )
            for word in selected.words
        ),
        escalated=False if outcome == "validator-disabled" else decision.escalate,
        route_reason=decision.reason,
        outcome=outcome,
        validator=validator,
        validator_text=validator_text,
        rejection_reason=rejection_reason,
    )


def _validate_hard_segments(
    results: Sequence[tuple[_PreparedSpeechSegment, SegmentTranscript]],
    backend: OmniSegmentBackend,
    validator_factory: Callable[[], SoraniValidator],
    *,
    stop_on_failure: bool = False,
    enabled: bool = True,
) -> tuple[
    tuple[tuple[_PreparedSpeechSegment, SegmentTranscript], ...],
    str | None,
    tuple[RejectedValidatorCorrection, ...],
    tuple[SegmentOrigin, ...],
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
    if not enabled:
        return (
            tuple(results),
            None,
            (),
            tuple(
                _segment_origin(segment, item, item, decision, "validator-disabled")
                for (segment, item), decision in zip(results, decisions, strict=True)
            ),
        )
    if not any(decision.escalate for decision in decisions):
        return (
            tuple(results),
            None,
            (),
            tuple(
                _segment_origin(segment, item, item, decision, "not-routed")
                for (segment, item), decision in zip(results, decisions, strict=True)
            ),
        )

    validator = validator_factory()
    resolve_role(validator.model_id, frozenset({"asr_validator"}), "the ASR validator")
    routed: list[tuple[_PreparedSpeechSegment, SegmentTranscript]] = []
    rejected: list[RejectedValidatorCorrection] = []
    origins: list[SegmentOrigin] = []
    accepted_correction = False
    for (segment, item), decision in zip(results, decisions, strict=True):
        if not decision.escalate:
            routed.append((segment, item))
            origins.append(_segment_origin(segment, item, item, decision, "not-routed"))
            continue
        failed_stage = "validator transcription"
        corrected: str | None = None
        try:
            corrected = validator.transcribe_segment(segment.path, segment.duration_s)
            if not isinstance(corrected, str):
                corrected = None
                raise ValueError("ASR validator response must be text")
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
            origins.append(
                _segment_origin(
                    segment,
                    item,
                    item,
                    decision,
                    "validator-alignment-refused"
                    if failed_stage == "validator alignment"
                    else "validator-transcription-refused",
                    validator=validator.model_id,
                    validator_text=corrected,
                    rejection_reason=failure.reason,
                )
            )
            continue
        accepted_correction = True
        # The draft's decode provenance (D-332) survives a validator correction.
        selected = replace(aligned, decode_mode=item.decode_mode, retry_reason=item.retry_reason)
        routed.append((segment, selected))
        origins.append(
            _segment_origin(
                segment,
                item,
                selected,
                decision,
                "validator-selected",
                validator=validator.model_id,
                validator_text=corrected,
            )
        )
    return (
        tuple(routed),
        validator.model_id if accepted_correction else None,
        tuple(rejected),
        tuple(origins),
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
        fused_checkpoint: Path | None = None,
        strict_runtime: bool = True,
        validate_hard_segments: bool = True,
    ) -> None:
        if type(context_grouping) is not bool:
            raise ValueError("ASR context grouping must be a boolean")
        if type(validate_hard_segments) is not bool:
            raise ValueError("ASR validator toggle must be a boolean")
        if lora_adapter is not None and fused_checkpoint is not None:
            raise ValueError(
                "a fused checkpoint already contains its fine-tune; pass it or a LoRA adapter, "
                "not both"
            )
        if not validate_hard_segments and validator_model_dir is not None:
            raise ValueError(
                "cannot pass a validator_model_dir when validate_hard_segments is False"
            )
        self.distro = distro
        self.interpreter = interpreter
        self.wsl_executable = wsl_executable
        self.lora_adapter = Path(lora_adapter) if lora_adapter is not None else None
        self.fused_checkpoint = Path(fused_checkpoint) if fused_checkpoint is not None else None
        self.validator_model_dir = validator_model_dir
        self.context_grouping = context_grouping
        self.strict_runtime = strict_runtime
        self.validate_hard_segments = validate_hard_segments
        self._receipt_distro: str | None = None

    @property
    def model_identity(self) -> str | None:
        """This producer's adapter identity, computed host-side so reuse can be keyed on it.

        Read from the bundle on the Windows side rather than reported by the worker: the reuse
        decision happens *before* the worker is invoked, and an identity that only exists after
        a 1,547 s transcription cannot key anything.
        """
        if self.fused_checkpoint is not None:
            # The allowlisted digest, not 15.6 GB of hashing: the worker hashes before loading.
            return f"fused:{fused_checkpoint_asset(self.fused_checkpoint).sha256}"
        if self.lora_adapter is None:
            return None
        return f"lora:{adapter_fingerprint(self.lora_adapter)}"

    @property
    def admission_policy(self) -> str:
        """The source-bound worker uses the same canonical completion contract."""
        policy = _producer_admission_policy(
            True, self.context_grouping, self.validate_hard_segments
        )
        assert policy is not None
        return policy

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

        if not self.strict_runtime:
            if configured_source:
                source = Path(configured_source)
            elif (checkout_source / "hawedit").is_dir():
                source = checkout_source
            else:
                raise RuntimeError(
                    "HAWEDIT_WSL_SOURCE must be set outside a source checkout for plain WSL"
                )
            discovered_python = _discover_plain_wsl_python(
                distro=self.distro,
                executable=self.wsl_executable,
            )
            return discovered_python, self._wsl_path(source)

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
        validator_access: Any
        if self.validate_hard_segments:
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
            validator_access = verified_checkpoint_access(VALIDATOR_MODEL_ID, validator_model_dir)
        else:
            validator_access = nullcontext(None)
        # Windows msvcrt locks and Linux fcntl locks do not interoperate on DrvFS. Hold the host
        # shared lease for the complete WSL subprocess so the host fetcher's exclusive publisher
        # cannot rename this checkpoint while the worker independently verifies and constructs it.
        with validator_access as verified_validator_dir:
            request_path = work_dir / "omni-asr-request.json"
            output_path = work_dir / "omni-asr-worker-output.json"
            request: dict[str, Any] = {
                "schema_version": 2,
                "media_id": media_id,
                "segments": [
                    {
                        "path": segment.path.name,
                        "start_ms": segment.start_ms,
                        "end_ms": segment.end_ms,
                        **(
                            {
                                "sub_segments": [
                                    {"start_ms": sub_start, "end_ms": sub_end}
                                    for sub_start, sub_end in segment.sub_segments
                                ]
                            }
                            if len(segment.sub_segments) >= 2
                            else {}
                        ),
                    }
                    for segment in prepared
                ],
            }
            if verified_validator_dir is not None:
                request["validator_model_dir"] = self._wsl_path(verified_validator_dir)
            else:
                request["validate_hard_segments"] = False
            if self.lora_adapter is not None:
                # Only present for an adapted run, so an unadapted request stays
                # byte-identical to the one D-136's resume check compares against. Its
                # presence is also what stops a killed champion run being resumed by the
                # stock path under the same work directory. Restored across the readiness
                # merge, which rebuilt this request for the validator and carried no
                # adapter field at all.
                request["lora_adapter"] = self._wsl_path(self.lora_adapter)
                request["model_identity"] = expected_identity
            elif self.fused_checkpoint is not None:
                # Same rule for the fused champion (D-331): absent from stock/LoRA requests.
                request["fused_checkpoint"] = self._wsl_path(self.fused_checkpoint)
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
            forwarded_vars = [
                "HAWEDIT_ASR_LLM_DEVICE",
                "HAWEDIT_ASR_CTC_DEVICE",
                "HAWEDIT_ASR_VALIDATOR_DEVICE",
                "HAWEDIT_ASR_MIN_FREE_GPU_GIB",
            ]
            if not self.strict_runtime:
                forwarded_vars.append("CUDA_VISIBLE_DEVICES")
            for var in forwarded_vars:
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
    runtime: str = "auto",
    *,
    distro: str | None = None,
    lora_adapter: Path | None = None,
    fused_checkpoint: Path | None = None,
    strict_runtime: bool | None = None,
    validate_hard_segments: bool = False,
) -> CanonicalTranscriptProducer:
    """Choose direct Linux inference or the WSL bridge without hiding that decision."""
    if runtime not in {"auto", "local", "wsl"}:
        raise ValueError("OmniASR runtime must be one of: auto, local, wsl")
    if type(validate_hard_segments) is not bool:
        raise ValueError("ASR validator toggle must be a boolean")
    if lora_adapter is not None and fused_checkpoint is not None:
        raise ValueError(
            "a fused checkpoint already contains its fine-tune; pass it or a LoRA adapter, not both"
        )
    if lora_adapter is not None:
        # Fingerprinting includes all three inputs, so an incomplete bundle fails here —
        # before Stage 0's regions are cut — rather than 1,547 s later inside WSL.
        adapter_fingerprint(Path(lora_adapter))
    if fused_checkpoint is not None:
        # Same early refusal for a missing or non-allowlisted .pt (D-331).
        fused_checkpoint_asset(Path(fused_checkpoint))
    use_wsl = runtime == "wsl" or (runtime == "auto" and os.name == "nt")
    use_strict = strict_runtime_enabled(strict=strict_runtime)
    if fused_checkpoint is not None:
        return (
            WslOmniAsrProducer(
                distro=distro,
                fused_checkpoint=fused_checkpoint,
                context_grouping=True,
                strict_runtime=use_strict,
                validate_hard_segments=validate_hard_segments,
            )
            if use_wsl
            else OmniAsrProducer(
                fused_checkpoint=fused_checkpoint,
                context_grouping=True,
                validate_hard_segments=validate_hard_segments,
            )
        )
    return (
        WslOmniAsrProducer(
            distro=distro,
            lora_adapter=lora_adapter,
            context_grouping=True,
            strict_runtime=use_strict,
            validate_hard_segments=validate_hard_segments,
        )
        if use_wsl
        else OmniAsrProducer(
            lora_adapter=lora_adapter,
            context_grouping=True,
            validate_hard_segments=validate_hard_segments,
        )
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
