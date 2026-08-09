"""Installed-wheel checkpoint provisioning for HawEdit's exact model allowlist.

The historical Bash entry point contained the transaction itself and installed its own download
client at runtime.  That made provisioning checkout-only and let an operator command silently
mutate the environment it was supposed to prepare.  This module is the one implementation used by
both the wheel console script and the checkout wrapper.  It plans only registry checkpoints,
requires the reviewed Hugging Face client version, stages privately, exact-verifies through
``ModelStore`` and publishes with the existing no-replace writer transaction.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import os
import re
import secrets
import shutil
import stat
import sys
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Final, Protocol, cast

from hawedit.environment import EnvironmentAuditError, audit_installed_profile
from hawedit.models import (
    CheckpointIntegrityError,
    CheckpointIntegrityReport,
    ModelStore,
    RevisionNotPinned,
    SourceNotConfigured,
    _path_is_reparse,
    _publish_checkpoint_directory,
    checkpoint_publish_lock,
    readiness_report,
    validate_hf_repository_id,
)
from hawedit.registry import REGISTRY, ModelEntry, Provisioning, assert_commercially_usable
from hawedit.windows_security import (
    WindowsSecurityError,
    assert_private_windows_path,
    create_private_directory,
)

DOWNLOAD_CLIENT_VERSION: Final = "0.36.2"
MINIMUM_RECOMMENDED_FREE_BYTES: Final = 55 * 1_000_000_000
_URL_QUERY: Final = re.compile(r"(?i)\b(https?://[^\s?]+)\?\S+")
_URL_USERINFO: Final = re.compile(r"(?i)\b(https?://)[^/\s@]+@")
_BEARER_SECRET: Final = re.compile(r"(?i)\bbearer\s+\S+")
_NAMED_SECRET: Final = re.compile(
    r"(?i)\b(hf_token|access[_-]?token|token|authorization|cookie|set-cookie|"
    r"api[_-]?key|password|secret|x-amz-(?:credential|signature|security-token))"
    r"(\s*[:=]\s*)\S+"
)
_MAX_ERROR_TEXT: Final = 800


class ModelFetchError(RuntimeError):
    """Provisioning could not safely finish; no final checkpoint was overwritten."""


class Download(Protocol):
    def __call__(
        self,
        *,
        repo_id: str,
        revision: str,
        local_dir: str,
        resume_download: bool,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class FetchItem:
    entry: ModelEntry
    repository: str
    revision: str
    destination: Path


@dataclass(frozen=True, slots=True)
class FetchPlan:
    items: tuple[FetchItem, ...]
    unconfigured: tuple[str, ...]
    refused: tuple[tuple[str, str], ...] = ()


def _safe_error(exc: BaseException) -> str:
    """Bound provider/filesystem diagnostics without echoing common credential carriers."""
    printable = "".join(character if character.isprintable() else " " for character in str(exc))
    normalized = " ".join(printable.split())
    normalized = _URL_QUERY.sub(r"\1?<redacted>", normalized)
    normalized = _URL_USERINFO.sub(r"\1<redacted>@", normalized)
    normalized = _BEARER_SECRET.sub("Bearer <redacted>", normalized)
    normalized = _NAMED_SECRET.sub(r"\1\2<redacted>", normalized)
    if len(normalized) > _MAX_ERROR_TEXT:
        return normalized[: _MAX_ERROR_TEXT - 1] + "…"
    return normalized


def build_fetch_plan(store: ModelStore, only: str = "") -> FetchPlan:
    """Return missing, configured, immutable checkpoint work without guessing identities."""
    if only:
        requested = REGISTRY.get(only)
        if requested is None or requested.provisioning is not Provisioning.WEIGHTS:
            raise ModelFetchError(f"{only!r} is not a downloadable checkpoint")

    items: list[FetchItem] = []
    unconfigured: list[str] = []
    refused: list[tuple[str, str]] = []
    for entry in store.missing_weights():
        if only and entry.model_id != only:
            continue
        assert_commercially_usable(entry)
        try:
            repository = validate_hf_repository_id(
                store.source_for(entry), f"download source for {entry.model_id!r}"
            )
        except SourceNotConfigured:
            unconfigured.append(entry.model_id)
            continue
        except CheckpointIntegrityError as exc:
            raise ModelFetchError(_safe_error(exc)) from exc
        try:
            revision = store.revision_for(repository)
        except RevisionNotPinned as exc:
            raise ModelFetchError(str(exc)) from exc
        try:
            store.assert_checkpoint_provisionable(entry.model_id, repository, revision)
        except CheckpointIntegrityError as exc:
            refused.append((entry.model_id, _safe_error(exc)))
            continue
        items.append(
            FetchItem(
                entry=entry,
                repository=repository,
                revision=revision,
                destination=store.path_for(entry),
            )
        )
    return FetchPlan(tuple(items), tuple(unconfigured), tuple(refused))


def validate_private_stage(path: Path) -> None:
    """Refuse any existing member a downloader could follow outside its owned tree."""
    if _path_is_reparse(path):
        raise ModelFetchError(f"private staging root must not be a link or reparse point: {path}")
    try:
        root_before = os.lstat(path)
    except OSError as exc:
        raise ModelFetchError(f"cannot inspect private staging root {path}: {exc}") from exc
    if not stat.S_ISDIR(root_before.st_mode):
        raise ModelFetchError(f"private staging root is not a directory: {path}")
    expected_uid = os.getuid() if hasattr(os, "getuid") else None
    if expected_uid is not None and root_before.st_uid != expected_uid:
        raise ModelFetchError(f"private staging root belongs to another user: {path}")
    if expected_uid is not None and stat.S_IMODE(root_before.st_mode) & 0o077:
        raise ModelFetchError(f"private staging root permits group/other access: {path}")
    if os.name == "nt":
        try:
            assert_private_windows_path(path, require_protected=True)
        except WindowsSecurityError as exc:
            raise ModelFetchError(str(exc)) from exc
    try:
        members = tuple(path.rglob("*"))
    except OSError as exc:
        raise ModelFetchError(f"cannot enumerate private staging root {path}: {exc}") from exc
    for member in members:
        try:
            metadata = os.lstat(member)
        except OSError as exc:
            raise ModelFetchError(f"cannot inspect private staging member {member}: {exc}") from exc
        if _path_is_reparse(member):
            raise ModelFetchError(f"private staging contains a link or reparse point: {member}")
        if expected_uid is not None and metadata.st_uid != expected_uid:
            raise ModelFetchError(f"private staging member belongs to another user: {member}")
        if os.name == "nt":
            try:
                assert_private_windows_path(member, require_protected=False)
            except WindowsSecurityError as exc:
                raise ModelFetchError(str(exc)) from exc
        if stat.S_ISREG(metadata.st_mode):
            if metadata.st_nlink != 1:
                raise ModelFetchError(
                    f"private staging file must have exactly one hard link: {member}: "
                    f"got {metadata.st_nlink}"
                )
        elif not stat.S_ISDIR(metadata.st_mode):
            raise ModelFetchError(f"private staging contains a non-regular member: {member}")
    root_after = os.lstat(path)
    if (root_before.st_dev, root_before.st_ino) != (root_after.st_dev, root_after.st_ino):
        raise ModelFetchError(f"private staging root changed during validation: {path}")


def _unique_stage_path(destination: Path, revision: str) -> Path:
    for _attempt in range(100):
        candidate = destination.with_name(
            f".{destination.name}.download-{revision}-{secrets.token_hex(16)}"
        )
        if not os.path.lexists(candidate):
            return candidate
    raise ModelFetchError("could not allocate a unique private checkpoint staging path")


def _create_fresh_private_stage(destination: Path, revision: str) -> Path:
    if os.name == "nt":
        candidate = _unique_stage_path(destination, revision)
        try:
            create_private_directory(candidate)
        except WindowsSecurityError as exc:
            raise ModelFetchError(
                f"cannot create private Windows staging: {_safe_error(exc)}"
            ) from exc
        return candidate
    try:
        return Path(
            tempfile.mkdtemp(
                prefix=f".{destination.name}.download-{revision}-",
                dir=destination.parent,
            )
        )
    except OSError as exc:
        raise ModelFetchError(f"cannot create private staging: {_safe_error(exc)}") from exc


@contextmanager
def _fetch_publication_lock(destination: Path) -> Iterator[None]:
    """Normalize expected lock/path failures at the public provisioning boundary."""
    try:
        with checkpoint_publish_lock(destination):
            yield
    except ModelFetchError:
        raise
    except (OSError, RuntimeError) as exc:
        raise ModelFetchError(f"{type(exc).__name__}: {_safe_error(exc)}") from exc


def fetch_checkpoint(
    item: FetchItem,
    store: ModelStore,
    download: Download,
) -> CheckpointIntegrityReport:
    """Fetch one exact revision into a private stage and publish it without replacement."""
    destination = item.destination
    with _fetch_publication_lock(destination):
        if os.path.lexists(destination):
            if _path_is_reparse(destination) or not destination.is_dir():
                raise ModelFetchError(
                    f"existing final path is not a regular checkpoint directory: {destination}"
                )
            try:
                return store.verify_checkpoint(item.entry.model_id, destination)
            except Exception as exc:
                raise ModelFetchError(
                    "existing final checkpoint is invalid and was preserved: "
                    f"{type(exc).__name__}: {_safe_error(exc)}. Move or quarantine it "
                    "explicitly before retrying; HawEdit will not overwrite operator data."
                ) from exc

        destination.parent.mkdir(parents=True, exist_ok=True)
        resume = destination.with_name(f".{destination.name}.resume-{item.revision}")
        staging: Path | None = None
        try:
            if os.path.lexists(resume):
                validate_private_stage(resume)
                staging = resume
            else:
                fresh_stage = _create_fresh_private_stage(destination, item.revision)
                validate_private_stage(fresh_stage)
                _publish_checkpoint_directory(fresh_stage, resume)
                staging = resume
                validate_private_stage(staging)

            download(
                repo_id=item.repository,
                revision=item.revision,
                local_dir=str(staging),
                resume_download=True,
            )
            # The downloader is not trusted merely because it returned. Validate its complete
            # cache/content tree before the manifest verifier deliberately ignores `.cache`.
            validate_private_stage(staging)
            report = store.verify_checkpoint(item.entry.model_id, staging)
            _publish_checkpoint_directory(staging, destination)
            return report
        except BaseException as exc:
            if staging is not None and staging != resume and os.path.lexists(staging):
                try:
                    validate_private_stage(staging)
                    if not os.path.lexists(resume):
                        _publish_checkpoint_directory(staging, resume)
                except Exception as preserve_exc:
                    if hasattr(exc, "add_note"):
                        exc.add_note(
                            "private staging could not be published for safe resume and remains "
                            f"at {staging}: {type(preserve_exc).__name__}: {preserve_exc}"
                        )
            if not isinstance(exc, Exception):
                raise
            if isinstance(exc, ModelFetchError):
                raise
            raise ModelFetchError(f"{type(exc).__name__}: {_safe_error(exc)}") from exc


def _download_client() -> Download:
    try:
        audit_installed_profile("models")
    except EnvironmentAuditError as exc:
        raise ModelFetchError(
            f"checkpoint download environment refused: {_safe_error(exc)}"
        ) from exc
    try:
        installed = importlib.metadata.version("huggingface-hub")
    except importlib.metadata.PackageNotFoundError as exc:
        raise ModelFetchError(
            "checkpoint downloads require the models extra: install `hawedit[models]`"
        ) from exc
    if installed != DOWNLOAD_CLIENT_VERSION:
        raise ModelFetchError(
            "checkpoint download client drift: "
            f"huggingface-hub=={installed}, expected {DOWNLOAD_CLIENT_VERSION}"
        )
    try:
        module: ModuleType = __import__("huggingface_hub", fromlist=["snapshot_download"])
        candidate = module.snapshot_download
    except (ImportError, AttributeError) as exc:
        raise ModelFetchError("huggingface_hub.snapshot_download is unavailable") from exc
    if not callable(candidate):
        raise ModelFetchError("huggingface_hub.snapshot_download is unavailable")
    return cast(Download, candidate)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hawedit-fetch-models",
        description="Fetch exact §7 checkpoints through verified atomic publication.",
    )
    parser.add_argument("model_id", nargs="?", help="fetch only one §7 checkpoint")
    parser.add_argument("--status", action="store_true", help="print readiness without downloading")
    parser.add_argument(
        "--models-dir",
        type=Path,
        default=None,
        help="mutable checkpoint root (otherwise HAWEDIT_MODELS_DIR/platform default)",
    )
    return parser


def _print_status(store: ModelStore) -> bool:
    """Print readiness, returning false instead of leaking routine metadata/filesystem errors."""
    try:
        statuses = store.status()
    except (OSError, UnicodeError, ValueError, RuntimeError) as exc:
        print(
            f"REFUSED: cannot read model readiness: {type(exc).__name__}: {_safe_error(exc)}",
            file=sys.stderr,
        )
        return False
    print(readiness_report(statuses))
    return True


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    store = ModelStore(root=args.models_dir) if args.models_dir is not None else ModelStore()
    if args.status:
        return int(not _print_status(store))
    try:
        plan = build_fetch_plan(store, args.model_id or "")
    except (OSError, UnicodeError, ValueError, RuntimeError) as exc:
        print(f"REFUSED: {_safe_error(exc)}", file=sys.stderr)
        return 1

    failures = bool(plan.unconfigured or plan.refused)
    if plan.unconfigured:
        print(
            "REFUSED: no download source configured for " + ", ".join(plan.unconfigured),
            file=sys.stderr,
        )
    for model_id, reason in plan.refused:
        print(f"REFUSED: {model_id} cannot be fetched: {reason}", file=sys.stderr)
    if not plan.items:
        if failures:
            print("nothing fetchable - see refusals above")
        else:
            print("nothing to fetch - every targeted configured checkpoint is verified")
        return int(failures or not _print_status(store))

    try:
        store.root.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(store.root).free
    except OSError as exc:
        print(
            f"REFUSED: cannot prepare model root {store.root}: {_safe_error(exc)}",
            file=sys.stderr,
        )
        return 1
    print(f"{free / 1_000_000_000:.0f} GB free at {store.root}; full §7 is roughly 50 GB")
    if free < MINIMUM_RECOMMENDED_FREE_BYTES:
        print("WARNING: less than the recommended 55 GB is free", file=sys.stderr)
    try:
        download = _download_client()
    except ModelFetchError as exc:
        print(f"REFUSED: {_safe_error(exc)}", file=sys.stderr)
        return 1

    for item in plan.items:
        print(f"==> {item.entry.model_id}: {item.repository}@{item.revision} -> {item.destination}")
        if item.entry.gated and not os.environ.get("HF_TOKEN"):
            print(
                f"SKIPPED: {item.repository} is gated and HF_TOKEN is not set",
                file=sys.stderr,
            )
            failures = True
            continue
        try:
            report = fetch_checkpoint(item, store, download)
        except ModelFetchError as exc:
            print(f"FAILED: {item.entry.model_id}: {_safe_error(exc)}", file=sys.stderr)
            failures = True
            continue
        print(f"done: {report.files_verified} files, {report.size_bytes} bytes")

    status_ok = _print_status(store)
    return int(failures or not status_ok)


if __name__ == "__main__":  # pragma: no cover - operator entry point
    raise SystemExit(main())
