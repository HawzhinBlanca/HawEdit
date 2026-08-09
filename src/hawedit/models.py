"""Where §7's models live on disk, and whether this machine can actually run a stage.

"Is the app ready?" should be a command, not a guess. This module answers it from the §7
registry, so nothing can be provisioned that the blueprint does not permit and nothing the
blueprint requires can be quietly forgotten.

**Provisioning is not uniform, and pretending it is causes the confusion.** Of §7's fifteen
components, five arrive with a pip package or package-managed model card (Silero VAD ships its
ONNX model inside the wheel), one is our own code, two are cloud APIs needing credentials, one is
a system library, and **six are explicitly provisioned multi-gigabyte checkpoints**. Only that
last group is downloaded by `fetch-models.sh`.

**Source ids are configured, never guessed.** §7 names four models in unambiguous
`org/name` form and those are used directly. The two Qwen models are *checkpoint names*, not
repository ids. Inventing a plausible-looking repo for them would be the kind of
fabrication that fails at 3am on hawapc01 with a 404 nobody can explain, so they require an
explicit entry in `models/sources.json`. See D-022.

The two canonical OmniASR aliases are different: they are model cards shipped by the pinned
`omnilingual-asr` package, which owns their official asset URLs and cache. Fetching similarly
named Hugging Face repositories into `models/` would create weights the runtime never reads.

**Capacity is worth checking before the download, not during.** §6 gives hawapc01 2×24 GiB
of VRAM and the §7 checkpoints total roughly 50 GiB on disk; a machine that cannot hold them
should be told so before it spends an hour finding out.
"""

from __future__ import annotations

import ctypes
import errno
import hashlib
import importlib
import importlib.metadata
import json
import os
import re
import stat
import sys
import time
from collections.abc import Collection, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, cast

from hawedit.registry import REGISTRY, ModelEntry, Provisioning
from hawedit.wsl_setup import WSL_MODEL_METADATA_DIRECTORY, probe_wsl_runtime

__all__ = [
    "DEFAULT_MODELS_ROOT",
    "INSTALLED_INTEGRITY",
    "CheckpointIntegrityError",
    "CheckpointIntegrityReport",
    "ModelNotProvisioned",
    "ModelStatus",
    "ModelStore",
    "RevisionNotPinned",
    "SourceNotConfigured",
    "UnsafeModelConfig",
    "WeightsIncomplete",
    "assert_checkpoint_integrity",
    "assert_fully_loaded",
    "assert_transformers_config_safe",
    "checkpoint_publish_lock",
    "readiness_report",
    "verified_checkpoint_access",
]


def _default_models_root() -> Path:
    configured = os.environ.get("HAWEDIT_MODELS_DIR")
    if configured:
        return Path(configured)
    checkout = Path(__file__).resolve().parents[2] / "models"
    if (checkout / "sources.json").exists():
        return checkout
    if os.name == "nt":
        cache = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return cache / "hawedit" / "models"


DEFAULT_MODELS_ROOT: Final = _default_models_root()
INSTALLED_SOURCES: Final = Path(sys.prefix) / "share" / "hawedit" / "models" / "sources.json"
INSTALLED_REVISIONS: Final = Path(sys.prefix) / "share" / "hawedit" / "models" / "revisions.json"
INSTALLED_INTEGRITY: Final = Path(sys.prefix) / "share" / "hawedit" / "models" / "integrity.json"

# Which pip package supplies each PIP-provisioned component. Kept here rather than in the
# registry because it describes this implementation's packaging, not §7's content.
_PIP_MODULES: Final[Mapping[str, str]] = {
    "PySceneDetect": "scenedetect",
    "Silero VAD": "silero_vad",
    "KLPT": "klpt",
    "omniASR_LLM_7B_v2": "omnilingual_asr",
    "omniASR_CTC_3B_v2": "omnilingual_asr",
}


class ModelNotProvisioned(RuntimeError):
    """Raised when a stage is asked to run without the weights it needs."""


class WeightsIncomplete(RuntimeError):
    """Raised when a checkpoint loaded but some of its weights were invented."""


class UnsafeModelConfig(RuntimeError):
    """Raised before Transformers can execute code named by checkpoint configuration."""


class CheckpointIntegrityError(RuntimeError):
    """Raised when local checkpoint bytes differ from the pinned Hub snapshot."""


@dataclass(frozen=True, slots=True)
class CheckpointIntegrityReport:
    """The exact local snapshot proven against ``models/integrity.json``."""

    model_id: str
    repository: str
    revision: str
    files_verified: int
    size_bytes: int


_INTERNAL_IMPLEMENTATION_FIELDS: Final = frozenset(
    {"_attn_implementation_internal", "_experts_implementation_internal"}
)
_PUBLIC_IMPLEMENTATION_FIELDS: Final = frozenset({"attn_implementation", "experts_implementation"})
_HUB_KERNEL: Final = re.compile(r"^(?:paged\|)?[^/:]+/[^/:]+(?:@[^/:]+)?(?::[^/:]+)?$")


def assert_transformers_config_safe(model_dir: Path, allowed_model_types: Collection[str]) -> None:
    """Refuse checkpoint fields that can make Transformers download and execute code.

    Transformers before 5.3.0 deserialises the private implementation fields below from a
    model's ``config.json``.  A malicious value can name a Hub kernel repository and execute
    its Python even when the caller passed ``trust_remote_code=False`` (CVE-2026-4372).  HawEdit
    is pinned to 4.57.6 because 5.x changes the verified visual checkpoints' behaviour, so this
    is a deliberately stricter backport of the upstream fix: private fields are never accepted,
    and neither are repository-shaped values in their public counterparts.  CVE-2026-5241's
    nested ``trust_remote_code`` override is also refused.  Finally, every nested ``model_type``
    must belong to the checkpoint-specific allowlist supplied by its adapter, which prevents an
    altered Qwen config from dispatching into the vulnerable X-CLIP or LightGlue loaders.
    HawEdit's measured checkpoints use built-in implementations such as ``sdpa`` and need no
    remote kernel.

    The walk is recursive because nested text/vision configs become ``PretrainedConfig`` objects
    too.  It runs before any processor, config, or model loader in every HawEdit-owned
    Transformers path.
    """
    allowed = frozenset(allowed_model_types)
    if not allowed:
        raise ValueError("allowed_model_types must name at least one measured model type")
    config_path = model_dir / "config.json"
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise UnsafeModelConfig(
            f"{config_path} is missing; a Transformers checkpoint without its declared config "
            "cannot be loaded safely"
        ) from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise UnsafeModelConfig(f"cannot safely read {config_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise UnsafeModelConfig(
            f"{config_path} must contain a JSON object, got {type(raw).__name__}"
        )

    seen_model_types: set[str] = set()

    def refuse_remote_implementation(value: object, location: str) -> None:
        if isinstance(value, str) and _HUB_KERNEL.fullmatch(value) is not None:
            raise UnsafeModelConfig(
                f"{config_path} asks {location} to load remote kernel {value!r}. "
                "HawEdit's pinned checkpoints require no remote kernel, so executing one "
                "is refused."
            )
        if isinstance(value, dict):
            for key, child in value.items():
                refuse_remote_implementation(child, f"{location}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                refuse_remote_implementation(child, f"{location}[{index}]")

    def walk(value: object, location: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_location = f"{location}.{key}"
                if key in _INTERNAL_IMPLEMENTATION_FIELDS:
                    raise UnsafeModelConfig(
                        f"{config_path} contains forbidden field {child_location}. "
                        "Transformers <5.3.0 can execute a Hub kernel named there while "
                        "bypassing trust_remote_code (CVE-2026-4372)."
                    )
                if key == "trust_remote_code":
                    raise UnsafeModelConfig(
                        f"{config_path} contains forbidden field {child_location}. "
                        "A nested model config can override the caller's refusal and execute "
                        "remote code (CVE-2026-5241)."
                    )
                if key == "model_type":
                    if not isinstance(child, str) or child not in allowed:
                        raise UnsafeModelConfig(
                            f"{config_path} declares unapproved {child_location}={child!r}; "
                            f"this adapter accepts only {sorted(allowed)}. Dispatching a pinned "
                            "checkpoint through another Transformers model family is refused."
                        )
                    seen_model_types.add(child)
                if key in _PUBLIC_IMPLEMENTATION_FIELDS:
                    refuse_remote_implementation(child, child_location)
                walk(child, child_location)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{location}[{index}]")

    walk(raw, "config")
    if not seen_model_types:
        raise UnsafeModelConfig(
            f"{config_path} declares no model_type; this adapter accepts only {sorted(allowed)}"
        )


def assert_fully_loaded(model_id: str, missing_keys: Iterable[str]) -> None:
    """Refuse a model whose checkpoint did not supply every weight.

    `from_pretrained` fills anything absent from the checkpoint with a **fresh random
    initialisation** and carries on. The model then loads in a few seconds, reports the right
    parameter count, produces output of the right shape, and is wrong in a way no downstream
    check can see. It is reported — as a line in a printed load report — and nothing raises.

    Measured on `MCG-NJU/VideoChat3-4B`: `missing_keys = {'lm_head.weight'}`, randomly
    initialised at std 0.0200, against the real embedding's 0.0201 — so the statistics cannot
    tell them apart and only this list can. `lm_head` is the projection that turns hidden
    states into tokens, so a Path B run would have produced confident nonsense.

    This is `encoder_available`'s lesson for weights: a thing that loads is not a thing that
    works, and the only answer worth having is the one the loader was asked for directly.

    Args:
        model_id: for the message — §7's id, so the refusal names the component.
        missing_keys: `from_pretrained(..., output_loading_info=True)`'s `missing_keys`.

    Raises:
        WeightsIncomplete: any weight was invented.
    """
    missing = sorted(missing_keys)
    if missing:
        raise WeightsIncomplete(
            f"{model_id} loaded with {len(missing)} weight(s) absent from the checkpoint and "
            f"filled with random values: {missing}. The model would run and produce output of "
            f"the right shape. If these are meant to be tied to another tensor, the config says "
            f"so and the load did not honour it — tie them explicitly and record why "
            f"(§7 permits the model, not a differently-initialised copy of it)."
        )


class SourceNotConfigured(RuntimeError):
    """Raised when a checkpoint's download source was never configured (and not guessed)."""


class RevisionNotPinned(RuntimeError):
    """Raised when a repository would be downloaded at whatever its branch head is today."""


@dataclass(frozen=True, slots=True)
class ModelStatus:
    """Whether one §7 component is actually available on this machine."""

    model_id: str
    component: str
    provisioning: Provisioning
    available: bool
    detail: str
    path: Path | None = None
    size_bytes: int | None = None


def _directory_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


_LOCAL_OMNI_PACKAGES: Final[Mapping[str, str]] = {
    "fairseq2": "0.6",
    "fonttools": "4.60.2",
    "klpt": "0.1.7",
    "omnilingual-asr": "0.2.0",
    "qwen-asr": "0.0.6",
    "torch": "2.8.0",
    "torchaudio": "2.8.0",
}
_LOCAL_OMNI_IMPORTS: Final[Mapping[str, str]] = {
    "fairseq2.assets": "get_asset_store",
    "fairseq2.data.tokenizers.hub": "load_tokenizer",
    "fairseq2.models.hub": "load_model",
    "omnilingual_asr.models.inference.pipeline": "ASRInferencePipeline",
    "qwen_asr": "Qwen3ASRModel",
}


def _probe_local_omni_runtime() -> tuple[str, Path, int]:
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError(
            f"canonical local OmniASR requires Python 3.12, got "
            f"{sys.version_info[0]}.{sys.version_info[1]}"
        )
    versions: dict[str, str] = {}
    for distribution, expected in _LOCAL_OMNI_PACKAGES.items():
        try:
            actual = importlib.metadata.version(distribution).split("+", 1)[0]
        except importlib.metadata.PackageNotFoundError as exc:
            raise RuntimeError(f"required local package {distribution!r} is not installed") from exc
        versions[distribution] = actual
        if actual != expected:
            raise RuntimeError(
                f"required local package {distribution!r} must be {expected}, got {actual}"
            )

    from hawedit.omni_assets import (
        assert_effective_omni_cards,
        assert_omni_asset_integrity,
        assert_omni_card_integrity,
        freeze_fairseq2_asset_overrides,
    )

    assert_omni_card_integrity()
    reports = assert_omni_asset_integrity()
    total = sum(report.size for report in reports)
    if len(reports) != 3 or total != 43_546_500_168:
        raise RuntimeError(
            f"canonical local OmniASR asset set drifted: files={len(reports)}, bytes={total}"
        )
    freeze_fairseq2_asset_overrides()
    try:
        torch = importlib.import_module("torch")
        torchaudio = importlib.import_module("torchaudio")
        modules = {
            module_name: importlib.import_module(module_name) for module_name in _LOCAL_OMNI_IMPORTS
        }
        for module_name, symbol in _LOCAL_OMNI_IMPORTS.items():
            getattr(modules[module_name], symbol)
    except (ImportError, AttributeError) as exc:
        raise RuntimeError(f"canonical local OmniASR imports are incomplete: {exc}") from exc
    if str(getattr(torch, "__version__", "")).split("+", 1)[0] != versions["torch"]:
        raise RuntimeError("imported torch version disagrees with installed package metadata")
    if str(getattr(torchaudio, "__version__", "")).split("+", 1)[0] != versions["torchaudio"]:
        raise RuntimeError("imported torchaudio version disagrees with installed package metadata")
    cuda = getattr(torch, "cuda", None)
    device_count = cuda.device_count() if callable(getattr(cuda, "device_count", None)) else 0
    if (
        cuda is None
        or not callable(getattr(cuda, "is_available", None))
        or not cuda.is_available()
        or device_count < 2
    ):
        raise RuntimeError("canonical local OmniASR requires two visible CUDA devices")
    asset_store = modules["fairseq2.assets"].get_asset_store()
    assert_effective_omni_cards(asset_store)
    return (
        f"verified local Python 3.12 runtime, {len(versions)} packages, "
        f"{len(reports)} OmniASR files / {total} bytes and {device_count} CUDA devices",
        reports[0].path.parents[1],
        total,
    )


def _probe_canonical_omni_runtime() -> tuple[str, Path, int]:
    if os.name == "nt":
        probe = probe_wsl_runtime()
        return (
            f"WSL {probe.receipt.distro}: verified {probe.files_verified} files / "
            f"{probe.size_bytes} bytes in verified venv generation {probe.receipt.generation}",
            probe.receipt.generation_root,
            probe.size_bytes,
        )
    return _probe_local_omni_runtime()


class ModelStore:
    """The on-disk home of §7's downloadable checkpoints."""

    def __init__(self, root: Path | None = None, *, metadata_root: Path | None = None) -> None:
        self.root = root if root is not None else DEFAULT_MODELS_ROOT
        if metadata_root is not None:
            self.metadata_root = metadata_root
        else:
            snapshot_metadata = (
                Path(__file__).resolve().parent.parent / WSL_MODEL_METADATA_DIRECTORY
            )
            checkout_metadata = Path(__file__).resolve().parents[2] / "models"
            # A WSL worker snapshot carries a receipt-bound exact copy of all three identity
            # manifests beside the package. If that uniquely named directory exists at all,
            # never fall through to mutable checkpoint roots or unrelated installed metadata:
            # an incomplete/tampered snapshot must fail closed in ``integrity()``.
            if os.path.lexists(snapshot_metadata):
                self.metadata_root = snapshot_metadata
            elif (checkout_metadata / "sources.json").is_file():
                self.metadata_root = checkout_metadata
            else:
                self.metadata_root = INSTALLED_SOURCES.parent
        self._omni_runtime_probe: tuple[bool, str, Path | None, int | None] | None = None

    def _omni_runtime_status(self) -> tuple[bool, str, Path | None, int | None]:
        """Prove the canonical runtime once for both OmniASR registry entries."""
        if self._omni_runtime_probe is not None:
            return self._omni_runtime_probe
        result: tuple[bool, str, Path | None, int | None]
        try:
            detail, path, total = _probe_canonical_omni_runtime()
            result = (True, detail, path, total)
        except (RuntimeError, OSError) as exc:
            result = (False, f"canonical OmniASR runtime verification failed: {exc}", None, None)
        self._omni_runtime_probe = result
        return result

    def path_for(self, entry: ModelEntry) -> Path:
        """Where `entry`'s weights live. `/` in a model id becomes `__` in the directory."""
        return self.root / entry.model_id.replace("/", "__")

    def sources(self) -> Mapping[str, str]:
        """Configured download sources, merged over what §7 states unambiguously.

        `models/sources.json` maps model_id -> Hugging Face repo id. Entries there override
        nothing that §7 already fixes; they supply what §7 leaves as a checkpoint name.
        """
        configured: dict[str, str] = {}
        source_file = self.metadata_root / "sources.json"
        if source_file.exists():
            # JSON has no comments and this file needs one — it is the file most likely to be
            # "helpfully" completed by guessing the two entries that are deliberately absent.
            # A `_`-prefixed key carries the warning; dropping it here keeps the returned
            # mapping honestly str -> str rather than str -> whatever the note happened to be.
            raw = json.loads(source_file.read_text(encoding="utf-8"))
            configured = {k: v for k, v in raw.items() if not k.startswith("_")}
        merged = {e.model_id: e.hf_repo for e in REGISTRY.values() if e.hf_repo}
        merged.update(configured)
        return merged

    def source_for(self, entry: ModelEntry) -> str:
        """The repo id to download `entry` from.

        Raises:
            SourceNotConfigured: §7 gives a checkpoint name rather than a repository, and
                nothing configured one. Guessing here produces a 404 on the machine that can
                least afford to debug it.
        """
        source = self.sources().get(entry.model_id)
        if not source:
            raise SourceNotConfigured(
                f"no download source for {entry.model_id!r}. §7 names it as a checkpoint, "
                f"not a repository id, and this is not something to guess. Add it to "
                f"{self.metadata_root / 'sources.json'}:\n"
                f'  {{"{entry.model_id}": "<org>/<repo>"}}'
            )
        return source

    def revisions(self) -> Mapping[str, str]:
        """Pinned commit revisions, keyed by *repository id* rather than by §7 name.

        Keyed by repo because that is what `snapshot_download` takes, and because two §7 names
        could legitimately resolve to one repository.
        """
        configured: dict[str, str] = {}
        revision_file = self.metadata_root / "revisions.json"
        if revision_file.exists():
            raw = json.loads(revision_file.read_text(encoding="utf-8"))
            configured = {k: v for k, v in raw.items() if not k.startswith("_")}
        return configured

    def integrity(self) -> Mapping[str, object]:
        """The tracked byte manifest for every explicitly downloaded checkpoint.

        A pinned revision identifies intended bytes but does not prove the files currently on
        disk are those bytes.  The manifest records each accessible Hub file's content-addressed
        Git blob id or LFS SHA-256 at that revision; a gated/redacted repository is explicitly
        blocked instead of carrying a made-up digest. Installed wheels carry the same manifest
        beside ``sources.json`` and ``revisions.json``.
        """
        integrity_file = self.metadata_root / "integrity.json"
        if not integrity_file.is_file():
            raise CheckpointIntegrityError(
                f"no checkpoint byte manifest at {integrity_file}. A repository revision names "
                "intended weights but cannot detect a locally changed shard."
            )
        try:
            raw: object = json.loads(integrity_file.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CheckpointIntegrityError(
                f"cannot read checkpoint byte manifest {integrity_file}: {exc}"
            ) from exc
        document = _object_mapping(raw, str(integrity_file))
        if document.get("schema") != 1:
            raise CheckpointIntegrityError(
                f"{integrity_file} has unsupported schema {document.get('schema')!r}; expected 1"
            )
        return _object_mapping(document.get("models"), f"{integrity_file}: models")

    def verify_checkpoint(
        self, model_id: str, checkpoint: Path | None = None
    ) -> CheckpointIntegrityReport:
        """Hash every snapshot file before any HawEdit-owned model loader interprets it.

        Git-managed files use the Git blob id (SHA-1 over the canonical ``blob <size>\\0``
        prefix plus bytes); LFS files use their content SHA-256.  The file set is exact and
        symlinks are refused, so adding executable modelling code is as visible as changing a
        safetensors byte.  ``.cache/huggingface`` download metadata is excluded because it is
        downloader state, not part of the repository snapshot.
        """
        entry = REGISTRY.get(model_id)
        if entry is None or entry.provisioning is not Provisioning.WEIGHTS:
            raise CheckpointIntegrityError(
                f"{model_id!r} is not an explicitly downloaded §7 checkpoint"
            )
        model_manifest = _object_mapping(
            self.integrity().get(model_id), f"integrity manifest for {model_id}"
        )
        repository = _required_string(model_manifest, "repository", model_id)
        revision = _required_string(model_manifest, "revision", model_id)
        configured_repository = self.source_for(entry)
        configured_revision = self.revision_for(configured_repository)
        if (repository, revision) != (configured_repository, configured_revision):
            raise CheckpointIntegrityError(
                f"{model_id} integrity manifest names {repository}@{revision}, but provisioning "
                f"selects {configured_repository}@{configured_revision}. Refusing a manifest "
                "for different weights."
            )
        integrity_status = _required_string(model_manifest, "status", model_id)
        if integrity_status != "verified":
            reason = _required_string(model_manifest, "reason", model_id)
            raise CheckpointIntegrityError(
                f"{model_id} checkpoint verification is {integrity_status}: {reason}"
            )

        files = _object_mapping(model_manifest.get("files"), f"{model_id}: files")
        expected_paths = set(files)
        selected_root = checkpoint if checkpoint is not None else self.path_for(entry)
        if _path_is_reparse(selected_root):
            raise CheckpointIntegrityError(
                f"checkpoint root must not be a symlink or reparse point: {selected_root}"
            )
        root = selected_root.resolve()
        if not root.is_dir():
            raise CheckpointIntegrityError(f"checkpoint directory is missing: {root}")

        actual_paths: set[str] = set()
        for candidate in root.rglob("*"):
            relative = candidate.relative_to(root)
            if relative.parts and relative.parts[0] == ".cache":
                continue
            if _path_is_reparse(candidate):
                raise CheckpointIntegrityError(
                    f"{model_id} contains a link or reparse point "
                    f"{relative.as_posix()}; the manifest "
                    "covers bytes inside the checkpoint, not an external target"
                )
            if candidate.is_file():
                metadata = os.lstat(candidate)
                if metadata.st_nlink != 1:
                    raise CheckpointIntegrityError(
                        f"{model_id}:{relative.as_posix()} must have exactly one hard link; "
                        f"got {metadata.st_nlink}"
                    )
                actual_paths.add(relative.as_posix())
            elif not candidate.is_dir():
                raise CheckpointIntegrityError(
                    f"{model_id} contains a non-regular filesystem member: {relative.as_posix()}"
                )

        missing = sorted(expected_paths - actual_paths)
        extra = sorted(actual_paths - expected_paths)
        if missing or extra:
            raise CheckpointIntegrityError(
                f"{model_id} file set differs from {repository}@{revision}: "
                f"missing={missing[:8]}, extra={extra[:8]}"
            )

        total = 0
        for manifest_path in sorted(expected_paths):
            safe_relative = _safe_manifest_path(manifest_path, model_id)
            expectation = _object_mapping(files[manifest_path], f"{model_id}:{manifest_path}")
            algorithm = _required_string(expectation, "algorithm", f"{model_id}:{manifest_path}")
            digest = _required_string(expectation, "digest", f"{model_id}:{manifest_path}")
            size = _required_int(expectation, "size_bytes", f"{model_id}:{manifest_path}")
            target = root.joinpath(*safe_relative.parts)
            actual_size = target.stat().st_size
            if actual_size != size:
                raise CheckpointIntegrityError(
                    f"{model_id}:{manifest_path} is {actual_size} bytes; pinned snapshot requires "
                    f"{size}. The checkpoint is incomplete or changed."
                )
            actual_digest = _checkpoint_digest(target, algorithm, size)
            if actual_digest != digest:
                raise CheckpointIntegrityError(
                    f"{model_id}:{manifest_path} {algorithm} is {actual_digest}; pinned snapshot "
                    f"requires {digest}. Same-size weight corruption is not safe to load."
                )
            total += size
        final_paths: set[str] = set()
        for candidate in root.rglob("*"):
            relative = candidate.relative_to(root)
            if relative.parts and relative.parts[0] == ".cache":
                continue
            if _path_is_reparse(candidate):
                raise CheckpointIntegrityError(
                    f"{model_id} gained a link or reparse point while verifying: "
                    f"{relative.as_posix()}"
                )
            if candidate.is_file():
                metadata = os.lstat(candidate)
                if metadata.st_nlink != 1:
                    raise CheckpointIntegrityError(
                        f"{model_id}:{relative.as_posix()} gained another hard link while verifying"
                    )
                final_paths.add(relative.as_posix())
            elif not candidate.is_dir():
                raise CheckpointIntegrityError(
                    f"{model_id} gained a non-regular filesystem member while verifying: "
                    f"{relative.as_posix()}"
                )
        if final_paths != expected_paths:
            raise CheckpointIntegrityError(
                f"{model_id} file set changed while verifying: "
                f"missing={sorted(expected_paths - final_paths)[:8]}, "
                f"extra={sorted(final_paths - expected_paths)[:8]}"
            )
        return CheckpointIntegrityReport(
            model_id=model_id,
            repository=repository,
            revision=revision,
            files_verified=len(expected_paths),
            size_bytes=total,
        )

    def revision_for(self, repo_id: str) -> str:
        """The commit to download `repo_id` at.

        `snapshot_download` without `revision=` resolves whatever the branch head points at on
        the day it runs. Two machines then hold different weights under one name, and every
        number in `evidence/` is about weights nobody can identify — which is the same failure
        the project's "a number carries the hardware and adapter that produced it" rule exists
        to prevent, one level down. Measured 2026-08-09: nothing on disk or in the tree
        recorded which revision produced the 27 GB already here.

        Raises:
            RevisionNotPinned: no pin for this repository. Refused rather than resolved
                silently, mirroring `source_for` — the fetcher does not guess a repo id and it
                does not guess a revision either.
        """
        revision = self.revisions().get(repo_id)
        if not revision:
            raise RevisionNotPinned(
                f"no pinned revision for {repo_id!r}. Downloading a branch head makes the "
                f"weights unidentifiable and every measurement taken against them "
                f"unreproducible. Resolve the commit and record it in "
                f"{self.root / 'revisions.json'}:\n"
                f'  {{"{repo_id}": "<40-hex commit sha>"}}\n'
                f'  python -c "from huggingface_hub import HfApi; '
                f"print(HfApi().model_info('{repo_id}').sha)\""
            )
        if not isinstance(revision, str) or re.fullmatch(r"[0-9a-f]{40}", revision) is None:
            raise RevisionNotPinned(
                f"invalid pinned revision for {repo_id!r}: {revision!r}. Expected one full "
                f"lowercase 40-hex commit SHA in {self.root / 'revisions.json'}"
            )
        return revision

    def status(self) -> tuple[ModelStatus, ...]:
        """Availability of every §7 component on this machine, in registry order."""
        statuses: list[ModelStatus] = []
        for entry in REGISTRY.values():
            statuses.append(self._status_for(entry))
        return tuple(statuses)

    def _status_for(self, entry: ModelEntry) -> ModelStatus:
        if entry.provisioning is Provisioning.PIP:
            module = _PIP_MODULES.get(entry.model_id)
            if entry.model_id.startswith("omniASR_"):
                available, detail, path, size_bytes = self._omni_runtime_status()
                return ModelStatus(
                    model_id=entry.model_id,
                    component=entry.component,
                    provisioning=entry.provisioning,
                    available=available,
                    detail=detail,
                    path=path,
                    size_bytes=size_bytes,
                )
            available = module is not None and _is_importable(module)
            return ModelStatus(
                model_id=entry.model_id,
                component=entry.component,
                provisioning=entry.provisioning,
                available=available,
                detail=(
                    f"pip package {module!r} importable"
                    if available
                    else f"pip package {module!r} not installed"
                ),
            )
        if entry.provisioning is Provisioning.IN_HOUSE:
            return ModelStatus(
                entry.model_id, entry.component, entry.provisioning, True, "in-house code"
            )
        if entry.provisioning is Provisioning.CLOUD:
            has_key = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
            return ModelStatus(
                model_id=entry.model_id,
                component=entry.component,
                provisioning=entry.provisioning,
                available=has_key,
                detail="API credentials present" if has_key else "no API credentials in env",
            )
        if entry.provisioning is Provisioning.SYSTEM:
            from hawedit.captions import find_ffmpeg

            ffmpeg = find_ffmpeg()
            return ModelStatus(
                model_id=entry.model_id,
                component=entry.component,
                provisioning=entry.provisioning,
                available=ffmpeg is not None,
                detail=(
                    f"ffmpeg at {ffmpeg}" if ffmpeg else "no ffmpeg — run scripts/fetch-ffmpeg.sh"
                ),
                path=ffmpeg,
            )

        path = self.path_for(entry)
        present = path.is_dir() and any(path.iterdir())
        try:
            source = self.source_for(entry)
        except SourceNotConfigured:
            source = "<source not configured>"
        size_bytes = None
        if present:
            try:
                with _checkpoint_lock_stream(path, exclusive=False):
                    size_bytes = _directory_size(path)
                    integrity = self.verify_checkpoint(entry.model_id, path)
            except (CheckpointIntegrityError, RevisionNotPinned, SourceNotConfigured) as exc:
                return ModelStatus(
                    model_id=entry.model_id,
                    component=entry.component,
                    provisioning=entry.provisioning,
                    available=False,
                    detail=f"checkpoint integrity failed: {exc}",
                    path=path,
                    size_bytes=size_bytes,
                )
            detail = (
                f"verified {integrity.files_verified} files from "
                f"{integrity.repository}@{integrity.revision}"
            )
        else:
            detail = f"not downloaded ({source})"
        return ModelStatus(
            model_id=entry.model_id,
            component=entry.component,
            provisioning=entry.provisioning,
            available=present,
            detail=detail,
            path=path if present else None,
            size_bytes=size_bytes,
        )

    def missing_weights(self) -> tuple[ModelEntry, ...]:
        """§7 checkpoints that do not pass exact byte-manifest verification."""
        return tuple(
            entry
            for entry in REGISTRY.values()
            if entry.provisioning is Provisioning.WEIGHTS and not self._status_for(entry).available
        )

    def unconfigured_sources(self) -> tuple[ModelEntry, ...]:
        """Checkpoints whose download source §7 does not fix and nobody configured."""
        configured = self.sources()
        return tuple(
            entry
            for entry in REGISTRY.values()
            if entry.provisioning is Provisioning.WEIGHTS and not configured.get(entry.model_id)
        )

    def assert_available(self, model_id: str) -> Path | None:
        """Refuse to start a stage whose model is not on this machine.

        Raises:
            ModelNotProvisioned: the component is unavailable, with what to do about it.
        """
        entry = REGISTRY.get(model_id)
        if entry is None:
            raise ModelNotProvisioned(f"{model_id!r} is not in §7")
        # Do not build the whole readiness report here. That would hash every 37 GB checkpoint
        # before a stage asking for one of them could start.
        status = self._status_for(entry)
        if not status.available:
            if status.provisioning is Provisioning.WEIGHTS:
                remedy = "Run scripts/fetch-models.sh."
            elif status.provisioning is Provisioning.SYSTEM:
                remedy = "Run scripts/fetch-ffmpeg.sh."
            elif status.provisioning is Provisioning.CLOUD:
                remedy = "Configure the required cloud credentials."
            elif status.model_id.startswith("omniASR_") and os.name == "nt":
                remedy = "Run hawedit-asr-setup."
            else:
                remedy = "Install the optional package that supplies this component."
            raise ModelNotProvisioned(
                f"{model_id!r} ({status.component}) is not available: {status.detail}. {remedy}"
            )
        return status.path


def _is_importable(module: str) -> bool:
    from importlib.util import find_spec

    try:
        return find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def _object_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise CheckpointIntegrityError(f"{label} must be a JSON object with string keys")
    return cast(dict[str, object], value)


def _required_string(document: Mapping[str, object], key: str, label: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise CheckpointIntegrityError(f"{label}.{key} must be a non-empty string")
    return value


def _required_int(document: Mapping[str, object], key: str, label: str) -> int:
    value = document.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CheckpointIntegrityError(f"{label}.{key} must be a non-negative integer")
    return value


def _safe_manifest_path(relative: str, model_id: str) -> PurePosixPath:
    path = PurePosixPath(relative)
    if not relative or "\\" in relative or path.is_absolute() or ".." in path.parts:
        raise CheckpointIntegrityError(
            f"{model_id} integrity manifest contains unsafe path {relative!r}"
        )
    return path


def _path_is_reparse(path: Path) -> bool:
    try:
        metadata = os.lstat(path)
    except OSError:
        return False
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & reparse_flag
    )


def _publish_checkpoint_directory(source: Path, destination: Path) -> None:
    """Atomically rename one verified directory without replacing any existing final path."""
    if os.name == "nt":
        # Windows MoveFile already has no-replace semantics for os.rename().
        os.rename(source, destination)
        return

    encoded_source = os.fsencode(source)
    encoded_destination = os.fsencode(destination)
    library = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(library, "renameat2", None)
    if renameat2 is not None:
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        # Linux: RENAME_NOREPLACE, relative to the current directory when paths are relative.
        result = renameat2(-100, encoded_source, -100, encoded_destination, 1)
    else:
        renamex_np = getattr(library, "renamex_np", None)
        if renamex_np is None:
            raise CheckpointIntegrityError(
                "this platform has no atomic no-replace directory publication primitive"
            )
        renamex_np.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        renamex_np.restype = ctypes.c_int
        # Darwin: RENAME_EXCL.
        result = renamex_np(encoded_source, encoded_destination, 0x00000004)
    if result != 0:
        error = ctypes.get_errno()
        if error in {errno.EEXIST, errno.ENOTEMPTY}:
            raise FileExistsError(error, os.strerror(error), destination)
        raise OSError(error, os.strerror(error), destination)


def _checkpoint_digest(path: Path, algorithm: str, size: int) -> str:
    if algorithm == "sha256":
        digest = hashlib.sha256()
    elif algorithm == "git-sha1":
        # This reproduces Git's upstream object identity; it is not a new password/signature
        # primitive. The already-fixed blob would require a second preimage to substitute.
        digest = hashlib.sha1(usedforsecurity=False)
        digest.update(f"blob {size}\0".encode())
    else:
        raise CheckpointIntegrityError(
            f"unsupported checkpoint digest algorithm {algorithm!r} for {path}"
        )
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise CheckpointIntegrityError(f"cannot safely open checkpoint file {path}: {exc}") from exc
    try:
        before = os.fstat(descriptor)
        named = os.lstat(path)
        if (
            not stat.S_ISREG(before.st_mode)
            or not stat.S_ISREG(named.st_mode)
            or before.st_nlink != 1
            or named.st_nlink != 1
            or _path_is_reparse(path)
            or (before.st_dev, before.st_ino) != (named.st_dev, named.st_ino)
        ):
            raise CheckpointIntegrityError(
                f"checkpoint file must be one unlinked regular file: {path}"
            )
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            while chunk := stream.read(8 * 1024 * 1024):
                digest.update(chunk)
            after = os.fstat(stream.fileno())
        current = os.lstat(path)
        descriptor_before = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
            before.st_nlink,
        )
        descriptor_after = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
            after.st_nlink,
        )
        path_before = (
            named.st_dev,
            named.st_ino,
            named.st_size,
            named.st_mtime_ns,
            named.st_ctime_ns,
            named.st_nlink,
        )
        path_after = (
            current.st_dev,
            current.st_ino,
            current.st_size,
            current.st_mtime_ns,
            current.st_ctime_ns,
            current.st_nlink,
        )
        # Windows gives descriptor ``ctime`` the meaning/value of mtime while pathname stat
        # reports the filesystem creation/change time. Preserve ctime race detection within
        # each API, and bind the descriptor to the pathname using cross-platform fields.
        descriptor_binding = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_nlink,
        )
        path_binding = (
            current.st_dev,
            current.st_ino,
            current.st_size,
            current.st_mtime_ns,
            current.st_nlink,
        )
        if (
            descriptor_before != descriptor_after
            or path_before != path_after
            or descriptor_binding != path_binding
        ):
            raise CheckpointIntegrityError(f"checkpoint file changed while hashing: {path}")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return digest.hexdigest()


@contextmanager
def _checkpoint_lock_stream(model_dir: Path, *, exclusive: bool) -> Iterator[None]:
    lock_path = model_dir.parent / f".{model_dir.name}.hawedit.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOINHERIT", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise CheckpointIntegrityError(
            f"cannot safely open checkpoint lock {lock_path}: {exc}"
        ) from exc
    try:
        opened = os.fstat(descriptor)
        named = os.lstat(lock_path)
        if (
            not stat.S_ISREG(opened.st_mode)
            or not stat.S_ISREG(named.st_mode)
            or opened.st_nlink != 1
            or named.st_nlink != 1
            or _path_is_reparse(lock_path)
            or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
        ):
            raise CheckpointIntegrityError(
                f"checkpoint lock must be one unlinked regular file: {lock_path}"
            )
        with os.fdopen(descriptor, "r+b") as stream:
            descriptor = -1
            if stream.seek(0, os.SEEK_END) == 0:
                stream.write(b"\0")
                stream.flush()
                os.fsync(stream.fileno())
            stream.seek(0)
            if os.name == "nt":
                msvcrt = importlib.import_module("msvcrt")
                mode = (
                    msvcrt.LK_NBLCK if exclusive else getattr(msvcrt, "LK_NBRLCK", msvcrt.LK_NBLCK)
                )
                deadline = time.monotonic() + 6 * 60 * 60
                while True:
                    stream.seek(0)
                    try:
                        msvcrt.locking(stream.fileno(), mode, 1)
                        break
                    except OSError as exc:
                        if time.monotonic() >= deadline:
                            raise CheckpointIntegrityError(
                                f"timed out waiting for checkpoint lock {lock_path}"
                            ) from exc
                        time.sleep(0.25)
                try:
                    yield
                except BaseException:
                    with suppress(OSError):
                        stream.seek(0)
                        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                    raise
                else:
                    try:
                        stream.seek(0)
                        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                    except OSError as exc:
                        raise CheckpointIntegrityError(
                            f"cannot release checkpoint lock {lock_path}: {exc}"
                        ) from exc
            else:
                fcntl = importlib.import_module("fcntl")
                operation = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
                try:
                    fcntl.flock(stream.fileno(), operation)
                except OSError as exc:
                    raise CheckpointIntegrityError(
                        f"cannot acquire checkpoint lock {lock_path}: {exc}"
                    ) from exc
                try:
                    yield
                except BaseException:
                    with suppress(OSError):
                        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
                    raise
                else:
                    try:
                        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
                    except OSError as exc:
                        raise CheckpointIntegrityError(
                            f"cannot release checkpoint lock {lock_path}: {exc}"
                        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


@contextmanager
def checkpoint_publish_lock(model_dir: Path) -> Iterator[None]:
    """Hold the exclusive writer lock used for staged checkpoint publication."""
    with _checkpoint_lock_stream(model_dir, exclusive=True):
        yield


@contextmanager
def verified_checkpoint_access(model_id: str, model_dir: Path | None = None) -> Iterator[Path]:
    """Verify and hold a shared lock while a consumer opens every checkpoint file."""
    store = ModelStore()
    entry = REGISTRY.get(model_id)
    selected = model_dir if model_dir is not None else (store.path_for(entry) if entry else None)
    if selected is None:
        raise CheckpointIntegrityError(f"{model_id!r} is not a downloadable checkpoint")
    with _checkpoint_lock_stream(selected, exclusive=False):
        store.verify_checkpoint(model_id, selected)
        yield selected.resolve()


def assert_checkpoint_integrity(model_id: str, model_dir: Path) -> CheckpointIntegrityReport:
    """Verify an explicitly supplied model directory against the tracked snapshot manifest."""
    return ModelStore().verify_checkpoint(model_id, model_dir)


def readiness_report(statuses: Sequence[ModelStatus]) -> str:
    """A human-readable "can this machine run the pipeline?" summary."""
    lines = ["§7 component readiness", "=" * 72]
    for status in statuses:
        mark = "OK  " if status.available else "MISS"
        size = f"  ({status.size_bytes / 1e9:.1f} GB)" if status.size_bytes else ""
        lines.append(
            f"{mark} {status.model_id:44} {status.provisioning.value:8} {status.detail}{size}"
        )
    missing = [s for s in statuses if not s.available]
    lines.append("=" * 72)
    lines.append(
        f"{len(statuses) - len(missing)}/{len(statuses)} available"
        + (f" — missing: {', '.join(s.model_id for s in missing)}" if missing else "")
    )
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover - operator entry point
    print(readiness_report(ModelStore().status()))
