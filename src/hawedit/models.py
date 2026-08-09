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

import json
import os
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from hawedit.registry import REGISTRY, ModelEntry, Provisioning

__all__ = [
    "DEFAULT_MODELS_ROOT",
    "ModelNotProvisioned",
    "ModelStatus",
    "ModelStore",
    "RevisionNotPinned",
    "SourceNotConfigured",
    "WeightsIncomplete",
    "assert_fully_loaded",
    "readiness_report",
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

# Which pip package supplies each PIP-provisioned component. Kept here rather than in the
# registry because it describes this implementation's packaging, not §7's content.
_PIP_MODULES: Final[Mapping[str, str]] = {
    "PySceneDetect": "scenedetect",
    "Silero VAD": "silero_vad",
    "KLPT": "klpt",
    "omniASR_LLM_7B_v2": "omnilingual_asr",
    "omniASR_CTC_3B_v2": "omnilingual_asr",
}

# Weights that need a loader this environment does not already have. Downloaded is not runnable,
# and reporting `OK` for the first while meaning the second is how M1.4's row came to say "what
# is missing is the composition, not the download" about a model that cannot be loaded here at
# all. Measured 2026-08-09: `transformers` 4.57.6 has no `qwen3_asr` module, `AutoModel` cannot
# map the config's `model_type`, and `Qwen3ASRForConditionalGeneration` is not importable — while
# the checkpoint's own model card says `from qwen_asr import Qwen3ASRModel  # pip install
# qwen-asr`. The import name comes from that card, not from a guess. D-099.
_WEIGHTS_RUNTIMES: Final[Mapping[str, str]] = {
    "rzgar/qwen3-asr-sorani-kurdish-ckb-v1": "qwen_asr",
}


class ModelNotProvisioned(RuntimeError):
    """Raised when a stage is asked to run without the weights it needs."""


class WeightsIncomplete(RuntimeError):
    """Raised when a checkpoint loaded but some of its weights were invented."""


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


class ModelStore:
    """The on-disk home of §7's downloadable checkpoints."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root if root is not None else DEFAULT_MODELS_ROOT
        self._use_installed_sources = root is None

    def path_for(self, entry: ModelEntry) -> Path:
        """Where `entry`'s weights live. `/` in a model id becomes `__` in the directory."""
        return self.root / entry.model_id.replace("/", "__")

    def sources(self) -> Mapping[str, str]:
        """Configured download sources, merged over what §7 states unambiguously.

        `models/sources.json` maps model_id -> Hugging Face repo id. Entries there override
        nothing that §7 already fixes; they supply what §7 leaves as a checkpoint name.
        """
        configured: dict[str, str] = {}
        source_file = self.root / "sources.json"
        if not source_file.exists() and self._use_installed_sources and INSTALLED_SOURCES.exists():
            source_file = INSTALLED_SOURCES
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
                f"{self.root / 'sources.json'}:\n"
                f'  {{"{entry.model_id}": "<org>/<repo>"}}'
            )
        return source

    def revisions(self) -> Mapping[str, str]:
        """Pinned commit revisions, keyed by *repository id* rather than by §7 name.

        Keyed by repo because that is what `snapshot_download` takes, and because two §7 names
        could legitimately resolve to one repository.
        """
        configured: dict[str, str] = {}
        revision_file = self.root / "revisions.json"
        if (
            not revision_file.exists()
            and self._use_installed_sources
            and INSTALLED_REVISIONS.exists()
        ):
            revision_file = INSTALLED_REVISIONS
        if revision_file.exists():
            raw = json.loads(revision_file.read_text(encoding="utf-8"))
            configured = {k: v for k, v in raw.items() if not k.startswith("_")}
        return configured

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
            available = module is not None and _is_importable(module)
            package_managed = entry.model_id.startswith("omniASR_")
            return ModelStatus(
                model_id=entry.model_id,
                component=entry.component,
                provisioning=entry.provisioning,
                available=available,
                detail=(
                    (
                        f"pip package {module!r} importable; official model-card asset is "
                        "downloaded/cached on first load"
                        if package_managed
                        else f"pip package {module!r} importable"
                    )
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

        # A checkpoint on disk that nothing here can load is not an available component. The
        # report is read as "can this stage run", so downloaded-but-unloadable has to say so.
        runtime = _WEIGHTS_RUNTIMES.get(entry.model_id)
        runtime_missing = runtime is not None and not _is_importable(runtime)
        detail = f"weights from {source}" if present else f"not downloaded ({source})"
        if present and runtime_missing:
            detail = (
                f"weights from {source} are on disk, but the loader {runtime!r} is not installed "
                f"— the checkpoint cannot be loaded here, so this component cannot run"
            )

        return ModelStatus(
            model_id=entry.model_id,
            component=entry.component,
            provisioning=entry.provisioning,
            available=present and not runtime_missing,
            detail=detail,
            path=path if present else None,
            size_bytes=_directory_size(path) if present else None,
        )

    def missing_weights(self) -> tuple[ModelEntry, ...]:
        """§7 checkpoints that are not on this machine."""
        return tuple(
            entry
            for entry in REGISTRY.values()
            if entry.provisioning is Provisioning.WEIGHTS and not self.path_for(entry).is_dir()
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
        status = next((s for s in self.status() if s.model_id == model_id), None)
        if status is None:
            raise ModelNotProvisioned(f"{model_id!r} is not in §7")
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


def readiness_report(statuses: Sequence[ModelStatus]) -> str:
    """A human-readable "can this machine run the pipeline?" summary."""
    lines = ["§7 component readiness", "=" * 72]
    for status in statuses:
        mark = "OK  " if status.available else "MISS"
        # `is not None`, not truthiness: a checkpoint directory holding only empty files is
        # non-empty, so it reports present with a measured size of **0**, and a falsy check
        # printed no size at all — the same line a pip component gets, which reads as "nothing
        # here to measure". Measured zero and unmeasured are different facts. D-100.
        size = f"  ({status.size_bytes / 1e9:.1f} GB)" if status.size_bytes is not None else ""
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
