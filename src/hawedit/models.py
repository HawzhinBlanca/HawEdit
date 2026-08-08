"""Where §7's models live on disk, and whether this machine can actually run a stage.

"Is the app ready?" should be a command, not a guess. This module answers it from the §7
registry, so nothing can be provisioned that the blueprint does not permit and nothing the
blueprint requires can be quietly forgotten.

**Provisioning is not uniform, and pretending it is causes the confusion.** Of §7's fifteen
components, three arrive with a pip package (Silero VAD ships its ONNX model inside the
wheel), one is our own code, two are cloud APIs needing credentials rather than disk, one is
a system library, and **eight are multi-gigabyte checkpoints**. Only that last group can be
"missing" in a way that stops a stage.

**Source ids are configured, never guessed.** §7 names four models in unambiguous
`org/name` form and those are used directly. The other four — `omniASR_LLM_7B_v2`,
`omniASR_CTC_3B_v2`, `Qwen3-VL-Embedding-2B`, `Qwen3-VL-Reranker-2B` — are *checkpoint
names*, not repository ids. Inventing a plausible-looking repo for them would be the kind of
fabrication that fails at 3am on hawapc01 with a 404 nobody can explain, so they require an
explicit entry in `models/sources.json`. See D-022.

**Capacity is worth checking before the download, not during.** §6 gives hawapc01 2×24 GiB
of VRAM and the §7 checkpoints total roughly 50 GiB on disk; a machine that cannot hold them
should be told so before it spends an hour finding out.
"""

from __future__ import annotations

import json
import os
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
    "SourceNotConfigured",
    "WeightsIncomplete",
    "assert_fully_loaded",
    "readiness_report",
]

DEFAULT_MODELS_ROOT: Final = Path(__file__).resolve().parents[2] / "models"

# Which pip package supplies each PIP-provisioned component. Kept here rather than in the
# registry because it describes this implementation's packaging, not §7's content.
_PIP_MODULES: Final[Mapping[str, str]] = {
    "PySceneDetect": "scenedetect",
    "Silero VAD": "silero_vad",
    "KLPT": "klpt",
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

    def __init__(self, root: Path = DEFAULT_MODELS_ROOT) -> None:
        self.root = root

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
        return ModelStatus(
            model_id=entry.model_id,
            component=entry.component,
            provisioning=entry.provisioning,
            available=present,
            detail=f"weights from {source}" if present else f"not downloaded ({source})",
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
            raise ModelNotProvisioned(
                f"{model_id!r} ({status.component}) is not available: {status.detail}. "
                f"Run scripts/fetch-models.sh, or scripts/fetch-ffmpeg.sh for the render "
                f"stack."
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
