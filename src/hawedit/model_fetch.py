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
import ctypes
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
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Final, Protocol, cast

from hawedit import windows_security as _windows_security
from hawedit.environment import EnvironmentAuditError, audit_installed_profile
from hawedit.models import (
    CheckpointIntegrityError,
    CheckpointIntegrityReport,
    ModelStatus,
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
_HUGGING_FACE_SECRET: Final = re.compile(r"(?i)(?<![a-z0-9_])hf_[a-z0-9_-]{8,}")
_NAMED_SECRET: Final = re.compile(
    r"(?i)\b(hf_token|access[_-]?token|token|authorization|cookie|set-cookie|"
    r"api[_-]?key|password|secret|x-amz-(?:credential|signature|security-token))"
    r"(\s*[:=]\s*)\S+"
)
_MAX_ERROR_TEXT: Final = 800
_WINDOWS_MUTATING_ROOT_RIGHTS: Final = (
    0x00000002  # FILE_ADD_FILE / FILE_WRITE_DATA
    | 0x00000004  # FILE_ADD_SUBDIRECTORY / FILE_APPEND_DATA
    | 0x00000010  # FILE_WRITE_EA
    | 0x00000040  # FILE_DELETE_CHILD
    | 0x00000100  # FILE_WRITE_ATTRIBUTES
    | 0x00010000  # DELETE
    | 0x00040000  # WRITE_DAC
    | 0x00080000  # WRITE_OWNER
    | 0x10000000  # GENERIC_ALL
    | 0x40000000  # GENERIC_WRITE
)
_WINDOWS_MUTATING_ANCESTOR_RIGHTS: Final = (
    0x00000040  # FILE_DELETE_CHILD
    | 0x00010000  # DELETE
    | 0x00040000  # WRITE_DAC
    | 0x00080000  # WRITE_OWNER
    | 0x10000000  # GENERIC_ALL
    | 0x40000000  # GENERIC_WRITE
)
_INHERIT_ONLY_ACE: Final = 0x08


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


@dataclass(frozen=True, slots=True)
class _ModelRootIdentity:
    path: Path
    device: int
    inode: int
    mode: int
    owner: int | None


def _windows_allowed_root_writers() -> frozenset[str]:
    current_sid = _windows_security._current_user_sid()
    return frozenset((current_sid, "S-1-5-18", "S-1-5-32-544"))


def _assert_windows_acl_has_no_untrusted_mutator(
    path: Path, *, rights: int, require_current_owner: bool
) -> None:
    """Reject an allow ACE that can mutate the root boundary from another principal."""
    libraries = _windows_security._windows_libraries
    advapi32, kernel32 = libraries()
    owner = wintypes.LPVOID()
    dacl = wintypes.LPVOID()
    descriptor = wintypes.LPVOID()
    result = advapi32.GetNamedSecurityInfoW(
        str(path),
        1,  # SE_FILE_OBJECT
        0x00000001 | 0x00000004,  # OWNER_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION
        ctypes.byref(owner),
        None,
        ctypes.byref(dacl),
        None,
        ctypes.byref(descriptor),
    )
    if result != 0:
        raise ModelFetchError(f"cannot inspect model-root ACL {path}: Win32 error {int(result)}")
    try:
        sid_string = _windows_security._sid_string
        allowed = _windows_allowed_root_writers()
        root_owner = sid_string(owner)
        if require_current_owner and root_owner not in allowed:
            raise ModelFetchError(f"model root belongs to an untrusted principal: {path}")
        if not dacl:
            raise ModelFetchError(f"model-root ACL grants unrestricted access: {path}")

        information_type = _windows_security._AclSizeInformation
        information = information_type()
        if not advapi32.GetAclInformation(
            dacl, ctypes.byref(information), ctypes.sizeof(information), 2
        ):
            raise ModelFetchError(f"cannot inspect model-root ACL entries: {path}")
        ace_type = _windows_security._AccessAllowedAce
        for index in range(information.AceCount):
            ace_pointer = wintypes.LPVOID()
            if not advapi32.GetAce(dacl, index, ctypes.byref(ace_pointer)):
                raise ModelFetchError(f"cannot inspect model-root ACL entry {index}: {path}")
            if ace_pointer.value is None:
                raise ModelFetchError(f"model-root ACL has a null entry: {path}")
            header = ctypes.cast(ace_pointer, ctypes.POINTER(_windows_security._AceHeader)).contents
            # An inherit-only ACE does not apply to this directory; it is assessed when that
            # descendant itself is visited. Standard deny ACEs cannot grant mutation. Refuse all
            # other ACE layouts rather than accidentally treating an object-specific allow ACE
            # as harmless without parsing its different SID offset.
            if header.AceFlags & _INHERIT_ONLY_ACE or header.AceType == 1:
                continue
            if header.AceType != 0:
                raise ModelFetchError(f"model-root ACL has an unsupported ACE type: {path}")
            ace = ctypes.cast(ace_pointer, ctypes.POINTER(ace_type)).contents
            principal_pointer = wintypes.LPVOID(ace_pointer.value + ace_type.SidStart.offset)
            principal = sid_string(principal_pointer)
            owner_rights_are_trusted = principal == "S-1-3-4" and root_owner in allowed
            if principal not in allowed and not owner_rights_are_trusted and int(ace.Mask) & rights:
                raise ModelFetchError(
                    f"model-root boundary grants mutation to another principal: {path}"
                )
    finally:
        kernel32.LocalFree(descriptor)


def _validate_model_root(path: Path) -> _ModelRootIdentity:
    root = path.absolute()
    try:
        root_metadata = os.lstat(root)
    except OSError as exc:
        raise ModelFetchError(f"cannot inspect model root {root}: {_safe_error(exc)}") from exc
    if not stat.S_ISDIR(root_metadata.st_mode) or _path_is_reparse(root):
        raise ModelFetchError(f"model root must be an unlinked regular directory: {root}")

    expected_uid = os.getuid() if hasattr(os, "getuid") else None
    if expected_uid is not None:
        if root_metadata.st_uid != expected_uid:
            raise ModelFetchError(f"model root belongs to another user: {root}")
        if stat.S_IMODE(root_metadata.st_mode) & 0o022:
            raise ModelFetchError(f"model root permits group/other mutation: {root}")

    child = root
    for ancestor in root.parents:
        try:
            metadata = os.lstat(ancestor)
        except OSError as exc:
            raise ModelFetchError(
                f"cannot inspect model-root ancestor {ancestor}: {_safe_error(exc)}"
            ) from exc
        if not stat.S_ISDIR(metadata.st_mode) or _path_is_reparse(ancestor):
            raise ModelFetchError(f"model-root ancestor must not be a link: {ancestor}")
        if expected_uid is not None:
            writable = stat.S_IMODE(metadata.st_mode) & 0o022
            if writable and not metadata.st_mode & stat.S_ISVTX:
                raise ModelFetchError(
                    f"model-root ancestor permits replacement of {child}: {ancestor}"
                )
        child = ancestor

    if os.name == "nt":
        _assert_windows_acl_has_no_untrusted_mutator(
            root, rights=_WINDOWS_MUTATING_ROOT_RIGHTS, require_current_owner=True
        )
        if root.parent != root:
            _assert_windows_acl_has_no_untrusted_mutator(
                root.parent,
                rights=_WINDOWS_MUTATING_ANCESTOR_RIGHTS,
                require_current_owner=False,
            )
    return _ModelRootIdentity(
        root,
        root_metadata.st_dev,
        root_metadata.st_ino,
        root_metadata.st_mode,
        root_metadata.st_uid if expected_uid is not None else None,
    )


def _prepare_model_root(path: Path) -> _ModelRootIdentity:
    root = path.absolute()
    if not os.path.lexists(root):
        try:
            root.parent.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                create_private_directory(root)
            else:
                os.mkdir(root, 0o700)
        except FileExistsError:
            pass
        except (OSError, WindowsSecurityError) as exc:
            raise ModelFetchError(
                f"cannot create private model root {root}: {_safe_error(exc)}"
            ) from exc
    return _validate_model_root(root)


def _assert_same_model_root(expected: _ModelRootIdentity) -> None:
    observed = _validate_model_root(expected.path)
    if observed != expected:
        raise ModelFetchError(f"model root changed during checkpoint publication: {expected.path}")


@contextmanager
def _model_root_boundary(path: Path) -> Iterator[_ModelRootIdentity]:
    identity = _prepare_model_root(path)
    try:
        yield identity
    except BaseException as primary:
        try:
            _assert_same_model_root(identity)
        except Exception as boundary_error:
            primary.add_note(
                "model-root postcondition failed: "
                f"{type(boundary_error).__name__}: {_safe_error(boundary_error)}"
            )
        raise
    else:
        _assert_same_model_root(identity)


def _safe_error(exc: BaseException) -> str:
    """Bound provider/filesystem diagnostics without echoing common credential carriers."""
    printable = "".join(character if character.isprintable() else " " for character in str(exc))
    normalized = " ".join(printable.split())
    normalized = _URL_QUERY.sub(r"\1?<redacted>", normalized)
    normalized = _URL_USERINFO.sub(r"\1<redacted>@", normalized)
    normalized = _BEARER_SECRET.sub("Bearer <redacted>", normalized)
    normalized = _NAMED_SECRET.sub(r"\1\2<redacted>", normalized)
    normalized = _HUGGING_FACE_SECRET.sub("hf_<redacted>", normalized)
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
    with (
        _model_root_boundary(destination.parent) as root_identity,
        _fetch_publication_lock(destination),
    ):
        _assert_same_model_root(root_identity)
        if os.path.lexists(destination):
            if _path_is_reparse(destination) or not destination.is_dir():
                raise ModelFetchError(
                    f"existing final path is not a regular checkpoint directory: {destination}"
                )
            try:
                report = store.verify_checkpoint(item.entry.model_id, destination)
                _assert_same_model_root(root_identity)
                return report
            except Exception as exc:
                raise ModelFetchError(
                    "existing final checkpoint is invalid and was preserved: "
                    f"{type(exc).__name__}: {_safe_error(exc)}. Move or quarantine it "
                    "explicitly before retrying; HawEdit will not overwrite operator data."
                ) from exc

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
            _assert_same_model_root(root_identity)
            # The downloader is not trusted merely because it returned. Validate its complete
            # cache/content tree before the manifest verifier deliberately ignores `.cache`.
            validate_private_stage(staging)
            store.verify_checkpoint(item.entry.model_id, staging)
            _assert_same_model_root(root_identity)
            _publish_checkpoint_directory(staging, destination)
            _assert_same_model_root(root_identity)
            # Publication changes the pathname the runtime consumes. Re-open and verify that
            # exact final path under the same writer lock; a staging report is not sufficient.
            report = store.verify_checkpoint(item.entry.model_id, destination)
            _assert_same_model_root(root_identity)
            return report
        except BaseException as exc:
            try:
                _assert_same_model_root(root_identity)
            except Exception as boundary_error:
                if not isinstance(exc, Exception):
                    exc.add_note(
                        "private resume was skipped because the model root changed: "
                        f"{type(boundary_error).__name__}: {_safe_error(boundary_error)}"
                    )
                    raise
                raise boundary_error from exc
            if staging is not None and staging != resume and os.path.lexists(staging):
                try:
                    validate_private_stage(staging)
                    if not os.path.lexists(resume):
                        _publish_checkpoint_directory(staging, resume)
                except Exception as preserve_exc:
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


def _print_status(store: ModelStore) -> tuple[ModelStatus, ...] | None:
    """Print readiness, returning the measured states without leaking routine errors."""
    try:
        statuses = store.status()
    except (OSError, UnicodeError, ValueError, RuntimeError) as exc:
        print(
            f"REFUSED: cannot read model readiness: {type(exc).__name__}: {_safe_error(exc)}",
            file=sys.stderr,
        )
        return None
    print(readiness_report(statuses))
    return tuple(statuses)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    store = ModelStore(root=args.models_dir) if args.models_dir is not None else ModelStore()
    if args.status:
        return int(_print_status(store) is None)
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
        return int(failures or _print_status(store) is None)

    try:
        root_identity = _prepare_model_root(store.root)
        free = shutil.disk_usage(root_identity.path).free
    except (OSError, ModelFetchError) as exc:
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
    if status_ok is None:
        return 1
    status_by_id = {status.model_id: status for status in status_ok}
    unavailable_targets = sorted(
        item.entry.model_id
        for item in plan.items
        if not status_by_id.get(item.entry.model_id)
        or not status_by_id[item.entry.model_id].available
    )
    if unavailable_targets:
        print(
            "FAILED: final checkpoint readiness refused " + ", ".join(unavailable_targets),
            file=sys.stderr,
        )
        failures = True
    return int(failures or not status_ok)


if __name__ == "__main__":  # pragma: no cover - operator entry point
    raise SystemExit(main())
