"""Fail-closed identity check for the Python environment grading HawEdit.

Importing :mod:`hawedit` is not enough evidence that an interpreter belongs to the current
checkout. Editable installs can point at another clone, stale distribution metadata can
describe dependencies that are no longer declared, and duplicate metadata can make the
answer depend on import-path order. The canonical gate executes this file directly from the
checkout and requires it to prove one authoritative editable install plus the exact direct
dependencies used by the gate.

The module also supports checking an ordinary installed wheel when no project root or extras
are requested. That mode validates the wheel's unconditional runtime requirements without
pretending that installed code is suitable for grading a source checkout.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import hmac
import importlib.metadata as metadata
import json
import os
import platform
import re
import runpy
import sys
import tomllib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname


def _load_host_lock_sha256() -> dict[str, str]:
    if __package__:
        from hawedit.host_lock_hashes import HOST_LOCK_SHA256

        return HOST_LOCK_SHA256
    # The installer executes this file by path under ``-I`` before HawEdit exists. Loading the
    # generated sibling explicitly both supports that bootstrap and prevents a different
    # checkout's installed ``hawedit`` package from supplying the trusted lock identities.
    return cast(
        dict[str, str],
        runpy.run_path(str(Path(__file__).with_name("host_lock_hashes.py")))["HOST_LOCK_SHA256"],
    )


HOST_LOCK_SHA256 = _load_host_lock_sha256()

__all__ = [
    "EnvironmentAuditError",
    "EnvironmentReport",
    "HostLock",
    "audit_environment",
    "audit_installed_profile",
    "dependency_contract_digest",
    "main",
    "resolve_installed_hawedit_data",
    "resolve_installed_host_lock",
    "validate_host_lock",
]

_PROJECT_NAME: Final = "hawedit"
_EXACT_REQUIREMENT: Final = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*==\s*([^,;\s*]+)\s*(?:;\s*(.+))?$"
)
_PYTHON_BOUND: Final = re.compile(r"^(>=|<)([0-9]+)\.([0-9]+)$")
_SUCCESS_TOKEN: Final = "hawedit-environment-ok"
_LOCK_HEADER: Final = re.compile(r"^# ([a-z][a-z0-9-]*): (\S.*)$")
_LOCK_REQUIREMENT: Final = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;\\]+) --hash=sha256:([0-9a-f]{64})$"
)
_CPU_LOCK_OPTIONS: Final = frozenset(
    {
        "--extra-index-url https://download.pytorch.org/whl/cpu",
        "--only-binary=:all:",
    }
)
_GPU_LOCK_OPTIONS: Final = frozenset(
    {
        "--index-url https://download.pytorch.org/whl/cu130",
        "--extra-index-url https://pypi.org/simple",
        "--only-binary=:all:",
    }
)
# Must stay equal to `scripts/install-host.sh`'s per-scope `extras=(...)` and to
# `scripts/lock_host_dependencies.py`'s `TARGETS`. Three declaring sites for one fact; this is
# the one that *refuses* on a mismatch, which is how a partial edit of the other two is caught
# (measured: adding `agentic` to those two alone made `install-host.sh` refuse here by name).
_PROFILE_EXTRAS: Final = {
    "base": (),
    # `agentic` is in the gate scope because the gate floors on tests that *passed*
    # (`gate.py`); without dbos + pydantic-ai, ~150 agent tests skip and the run is refused
    # for a floor it cannot reach. D-A26.
    "gate": ("dev", "media", "agentic"),
    "models": ("models",),
    "gpu": ("media", "gpu"),
}


class EnvironmentAuditError(RuntimeError):
    """The interpreter cannot honestly grade this HawEdit checkout or installation."""


@dataclass(frozen=True, slots=True)
class EnvironmentReport:
    """Identity that was proved for a usable environment."""

    python_version: tuple[int, int]
    project_version: str
    project_root: Path | None
    checked_requirements: tuple[tuple[str, str], ...]
    lock_sha256: str | None = None
    locked_requirements: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class HostLock:
    """A target-specific, hash-locked host dependency graph."""

    path: Path
    sha256: str
    scope: str
    platform: str
    python_version: tuple[int, int]
    extras: tuple[str, ...]
    project_version: str
    contract_sha256: str
    requirements: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class _Manifest:
    project_version: str
    requires_python: str
    requirements: tuple[str, ...]


def _canonical_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _read_project_manifest(project_root: Path, extras: Sequence[str]) -> _Manifest:
    manifest_path = project_root / "pyproject.toml"
    try:
        document = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
        project = cast(dict[str, object], document["project"])
    except (OSError, KeyError, tomllib.TOMLDecodeError, TypeError) as exc:
        raise EnvironmentAuditError(f"cannot read {manifest_path}: {exc}") from exc

    if project.get("name") != _PROJECT_NAME:
        raise EnvironmentAuditError(f"{manifest_path} does not declare project {_PROJECT_NAME!r}")
    project_version = project.get("version")
    requires_python = project.get("requires-python")
    dependencies = project.get("dependencies")
    optional = project.get("optional-dependencies", {})
    if not isinstance(project_version, str) or not isinstance(requires_python, str):
        raise EnvironmentAuditError(f"{manifest_path} has incomplete project identity")
    if not isinstance(dependencies, list) or not all(
        isinstance(item, str) for item in dependencies
    ):
        raise EnvironmentAuditError(f"{manifest_path} project.dependencies is not a string list")
    if not isinstance(optional, dict):
        raise EnvironmentAuditError(f"{manifest_path} project.optional-dependencies is not a table")

    requirements = list(cast(list[str], dependencies))
    for extra in extras:
        selected = optional.get(extra)
        if not isinstance(selected, list) or not all(isinstance(item, str) for item in selected):
            raise EnvironmentAuditError(f"{manifest_path} has no valid {extra!r} extra")
        requirements.extend(cast(list[str], selected))
    return _Manifest(project_version, requires_python, tuple(requirements))


def dependency_contract_digest(project_root: Path, extras: Sequence[str]) -> str:
    """Hash the semantic inputs whose resolver output a host lock represents."""

    manifest = _read_project_manifest(project_root.resolve(), extras)
    builder_lock = project_root.resolve() / "requirements" / "release-build.txt"
    try:
        builder_sha256 = hashlib.sha256(builder_lock.read_bytes()).hexdigest()
    except OSError as exc:
        raise EnvironmentAuditError(
            f"cannot read locked installer contract {builder_lock}: {exc}"
        ) from exc
    payload = {
        "extras": list(extras),
        "project_version": manifest.project_version,
        "requires_python": manifest.requires_python,
        "requirements": list(manifest.requirements),
        "release_build_sha256": builder_sha256,
    }
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _target_platform(system: str) -> str:
    target = system.casefold()
    if target not in {"linux", "windows"}:
        raise EnvironmentAuditError(
            f"host locks support Linux and Windows, not platform {system!r}"
        )
    return target


def validate_host_lock(
    lock_path: Path,
    *,
    project_root: Path | None,
    extras: Sequence[str],
    python_version: tuple[int, int],
    platform_name: str,
    _lock_hashes: Mapping[str, str] = HOST_LOCK_SHA256,
) -> HostLock:
    """Parse and bind one deliberately small, fail-closed host-lock format."""

    resolved = lock_path.resolve()
    try:
        raw = resolved.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise EnvironmentAuditError(f"cannot read host dependency lock {resolved}: {exc}") from exc

    actual_sha256 = hashlib.sha256(raw).hexdigest()
    expected_sha256 = _lock_hashes.get(resolved.name)
    if expected_sha256 is None:
        raise EnvironmentAuditError(
            f"host dependency lock has no trusted byte identity: {resolved}"
        )
    if actual_sha256 != expected_sha256:
        raise EnvironmentAuditError(
            f"host dependency lock bytes do not match trusted SHA-256: {resolved}"
        )

    headers: dict[str, str] = {}
    options: set[str] = set()
    requirements: dict[str, tuple[str, str]] = {}
    for number, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            match = _LOCK_HEADER.fullmatch(line)
            if match is None:
                continue
            key, value = match.groups()
            if key in headers:
                raise EnvironmentAuditError(f"duplicate {key!r} header in {resolved}:{number}")
            headers[key] = value
            continue
        if line.startswith("--"):
            options.add(line)
            continue
        match = _LOCK_REQUIREMENT.fullmatch(line)
        if match is None:
            raise EnvironmentAuditError(
                f"invalid or unhashed host-lock requirement at {resolved}:{number}: {line!r}"
            )
        display_name, version, digest = match.groups()
        canonical = _canonical_name(display_name)
        if canonical in requirements:
            raise EnvironmentAuditError(f"duplicate locked package {display_name!r} in {resolved}")
        requirements[canonical] = (version, digest)

    required_headers = {
        "hawedit-lock-version",
        "scope",
        "target-platform",
        "target-python",
        "extras",
        "project-version",
        "contract-sha256",
        "resolver",
        "exclude-newer",
    }
    missing_headers = sorted(required_headers - headers.keys())
    if missing_headers:
        raise EnvironmentAuditError(f"host lock {resolved} lacks headers: {missing_headers}")
    if headers["hawedit-lock-version"] != "1":
        raise EnvironmentAuditError(
            f"unsupported host lock version {headers['hawedit-lock-version']!r}"
        )
    scope = headers["scope"]
    expected_options = _GPU_LOCK_OPTIONS if scope == "gpu" else _CPU_LOCK_OPTIONS
    if options != expected_options:
        raise EnvironmentAuditError(
            f"host lock {resolved} has unsafe or incomplete installer options: {sorted(options)}"
        )
    torch_backend = headers.get("torch-backend")
    if scope == "gpu" and torch_backend != "cu130":
        raise EnvironmentAuditError("GPU host lock does not declare torch-backend cu130")
    if scope != "gpu" and torch_backend is not None:
        raise EnvironmentAuditError(f"non-GPU host lock declares torch backend {torch_backend!r}")
    if not requirements:
        raise EnvironmentAuditError(f"host lock {resolved} contains no requirements")

    target = _target_platform(platform_name)
    if headers["target-platform"] != target:
        raise EnvironmentAuditError(
            f"host lock targets {headers['target-platform']}, current platform is {target}"
        )
    requested_python = f"{python_version[0]}.{python_version[1]}"
    if headers["target-python"] != requested_python:
        raise EnvironmentAuditError(
            f"host lock targets Python {headers['target-python']}, current interpreter is "
            f"Python {requested_python}"
        )
    locked_extras = () if headers["extras"] == "-" else tuple(headers["extras"].split(","))
    if locked_extras != tuple(extras):
        raise EnvironmentAuditError(
            f"host lock extras are {locked_extras}, requested extras are {tuple(extras)}"
        )
    scope_by_extras = {extras: profile for profile, extras in _PROFILE_EXTRAS.items()}
    expected_scope = scope_by_extras.get(tuple(extras))
    if expected_scope is None:
        raise EnvironmentAuditError(f"no host-lock profile exists for extras {tuple(extras)}")
    if scope != expected_scope:
        raise EnvironmentAuditError(f"host lock scope is {scope!r}, expected {expected_scope!r}")
    contract_sha256 = headers["contract-sha256"]
    if not re.fullmatch(r"[0-9a-f]{64}", contract_sha256):
        raise EnvironmentAuditError("host lock contract-sha256 is not a SHA-256 digest")
    if project_root is not None:
        declared_project_version = _read_project_manifest(
            project_root.resolve(), extras
        ).project_version
        if headers["project-version"] != declared_project_version:
            raise EnvironmentAuditError(
                f"host lock project version is {headers['project-version']}, current project is "
                f"{declared_project_version}"
            )
        expected_contract = dependency_contract_digest(project_root, extras)
        if contract_sha256 != expected_contract:
            raise EnvironmentAuditError(
                "host dependency lock is stale for the current project dependency contract"
            )

    return HostLock(
        path=resolved,
        sha256=actual_sha256,
        scope=scope,
        platform=target,
        python_version=python_version,
        extras=locked_extras,
        project_version=headers["project-version"],
        contract_sha256=contract_sha256,
        requirements=tuple(
            (name, version_digest[0]) for name, version_digest in sorted(requirements.items())
        ),
    )


def _read_installed_manifest(
    distribution: metadata.Distribution, extras: Sequence[str]
) -> _Manifest:
    requires_python = distribution.metadata["Requires-Python"]
    if not requires_python:
        raise EnvironmentAuditError("installed HawEdit metadata has no Requires-Python")

    requirements: list[str] = []
    for declared in distribution.requires or ():
        requirement, separator, marker = declared.partition(";")
        if not separator:
            requirements.append(requirement.strip())
            continue
        # Wheel metadata expresses optional dependencies with ``extra ==`` markers. Avoid
        # importing packaging in the minimal base environment; no selected extra means every
        # such requirement is inactive. A selected installed-wheel profile already contains
        # packaging in its locked graph, so evaluate the complete marker rather than trying to
        # parse compound platform/extra expressions ourselves.
        if re.search(r"\bextra\s*==", marker):
            if not extras:
                continue
            try:
                from packaging.markers import default_environment
                from packaging.requirements import InvalidRequirement, Requirement
            except ModuleNotFoundError as exc:
                raise EnvironmentAuditError(
                    "cannot evaluate installed optional requirements without packaging"
                ) from exc
            try:
                parsed = Requirement(declared)
            except InvalidRequirement as exc:
                raise EnvironmentAuditError(
                    f"installed HawEdit requirement is invalid: {declared!r}"
                ) from exc
            active = False
            for extra in extras:
                environment = cast(dict[str, str], dict(default_environment()))
                environment["extra"] = extra
                if parsed.marker is not None and parsed.marker.evaluate(environment=environment):
                    active = True
                    break
            if active:
                requirements.append(requirement.strip())
            continue
        raise EnvironmentAuditError(
            f"cannot evaluate marked installed requirement without its project manifest: "
            f"{declared!r}"
        )
    return _Manifest(distribution.version, requires_python, tuple(requirements))


def _check_python(requires_python: str, python_version: tuple[int, int]) -> None:
    compact = requires_python.replace(" ", "")
    items = compact.split(",")
    bounds: dict[str, tuple[int, int]] = {}
    for item in items:
        match = _PYTHON_BOUND.fullmatch(item)
        if match is None or match.group(1) in bounds:
            break
        bounds[match.group(1)] = (int(match.group(2)), int(match.group(3)))
    if len(items) != 2 or len(bounds) != 2 or set(bounds) != {">=", "<"}:
        raise EnvironmentAuditError(
            f"unsupported Requires-Python form {requires_python!r}; refusing to guess"
        )
    lower = bounds[">="]
    upper = bounds["<"]
    if not lower <= python_version < upper:
        raise EnvironmentAuditError(
            f"Python {python_version[0]}.{python_version[1]} is unsupported; "
            f"project requires {requires_python}"
        )


def _editable_root(distribution: metadata.Distribution) -> Path:
    try:
        raw = distribution.read_text("direct_url.json")
    except (OSError, UnicodeError) as exc:
        raise EnvironmentAuditError(f"cannot read HawEdit direct_url.json: {exc}") from exc
    if raw is None:
        raise EnvironmentAuditError(
            "source gate requires an editable HawEdit install with direct_url.json"
        )
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise EnvironmentAuditError(f"HawEdit direct_url.json is invalid: {exc}") from exc
    if not isinstance(document, dict):
        raise EnvironmentAuditError("HawEdit direct_url.json is not an object")
    directory = document.get("dir_info")
    if not isinstance(directory, dict) or directory.get("editable") is not True:
        raise EnvironmentAuditError("source gate requires an editable HawEdit install")
    url = document.get("url")
    if not isinstance(url, str):
        raise EnvironmentAuditError("HawEdit direct_url.json has no file URL")
    split = urlsplit(url)
    if split.scheme != "file" or split.netloc not in ("", "localhost"):
        raise EnvironmentAuditError(f"HawEdit editable root is not a local file URL: {url!r}")
    return Path(url2pathname(unquote(split.path))).resolve()


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left.resolve())) == os.path.normcase(str(right.resolve()))


def _metadata_path(distribution: metadata.Distribution) -> Path:
    path = getattr(distribution, "_path", None)
    if not isinstance(path, str | os.PathLike):
        raise EnvironmentAuditError("HawEdit distribution has no inspectable metadata path")
    return Path(path).resolve()


def _source_distribution(
    distributions: Sequence[metadata.Distribution], project_root: Path
) -> metadata.Distribution:
    authoritative: list[metadata.Distribution] = []
    for distribution in distributions:
        path = _metadata_path(distribution)
        try:
            direct_url = distribution.read_text("direct_url.json")
        except (OSError, UnicodeError) as exc:
            raise EnvironmentAuditError(f"cannot read HawEdit direct_url.json: {exc}") from exc
        if path.name.endswith(".dist-info") and direct_url is not None:
            authoritative.append(distribution)

    if len(authoritative) != 1:
        locations = ", ".join(str(_metadata_path(item)) for item in distributions)
        detail = f" ({locations})" if locations else ""
        raise EnvironmentAuditError(
            "expected exactly one authoritative editable HawEdit .dist-info; "
            f"found {len(authoritative)}{detail}"
        )

    selected = authoritative[0]
    editable_root = _editable_root(selected)
    if not _same_path(editable_root, project_root):
        raise EnvironmentAuditError(
            f"HawEdit editable root is {editable_root}, not current checkout {project_root}"
        )

    expected_companion = project_root / "src" / "hawedit.egg-info"
    companions = [item for item in distributions if item is not selected]
    if len(companions) > 1:
        locations = ", ".join(str(_metadata_path(item)) for item in companions)
        raise EnvironmentAuditError(f"unexpected HawEdit metadata records: {locations}")
    if companions:
        companion = companions[0]
        companion_path = _metadata_path(companion)
        if not _same_path(companion_path, expected_companion):
            raise EnvironmentAuditError(
                f"unexpected HawEdit metadata record {companion_path}; only the generated "
                f"{expected_companion} companion is allowed"
            )
        if companion.version != selected.version:
            raise EnvironmentAuditError(
                f"generated HawEdit egg-info is {companion.version}, authoritative install is "
                f"{selected.version}"
            )
    return selected


def _declared_versions(
    requirements: Sequence[str], python_version: tuple[int, int]
) -> dict[str, tuple[str, str]]:
    declared: dict[str, tuple[str, str]] = {}
    for requirement in requirements:
        match = _EXACT_REQUIREMENT.fullmatch(requirement)
        if match is not None and match.group(3) is None:
            display_name, expected = match.group(1), match.group(2)
        elif ";" in requirement:
            try:
                from packaging.markers import default_environment
                from packaging.requirements import InvalidRequirement, Requirement
            except ModuleNotFoundError as exc:
                raise EnvironmentAuditError(
                    f"cannot evaluate marked direct requirement without packaging: {requirement!r}"
                ) from exc
            try:
                parsed = Requirement(requirement)
            except InvalidRequirement as exc:
                raise EnvironmentAuditError(
                    f"invalid marked direct requirement: {requirement!r}"
                ) from exc
            environment = cast(dict[str, str], dict(default_environment()))
            environment["python_version"] = f"{python_version[0]}.{python_version[1]}"
            micro = (
                sys.version_info.micro
                if python_version == (sys.version_info.major, sys.version_info.minor)
                else 0
            )
            environment["python_full_version"] = f"{python_version[0]}.{python_version[1]}.{micro}"
            environment["extra"] = ""
            if parsed.marker is None or not parsed.marker.evaluate(environment=environment):
                continue
            specifiers = tuple(parsed.specifier)
            if (
                len(specifiers) != 1
                or specifiers[0].operator != "=="
                or specifiers[0].version.endswith(".*")
            ):
                raise EnvironmentAuditError(
                    f"active direct requirement is not an exact pin: {requirement!r}"
                )
            display_name, expected = parsed.name, specifiers[0].version
        else:
            raise EnvironmentAuditError(
                f"direct requirement is not an unconditional exact pin: {requirement!r}"
            )
        canonical = _canonical_name(display_name)
        previous = declared.get(canonical)
        if previous is not None and previous[1] != expected:
            raise EnvironmentAuditError(
                f"conflicting direct pins for {display_name}: {previous[1]} and {expected}"
            )
        declared[canonical] = (display_name, expected)
    return declared


def _version_matches(expected: str, installed: str) -> bool:
    if installed == expected:
        return True
    # PEP 440's ``==2.13.0`` accepts a local build such as ``2.13.0+cpu``. HawEdit uses
    # that intentionally so one media pin works for the CPU and CUDA PyTorch indexes.
    return "+" not in expected and installed.partition("+")[0] == expected


def _exact_installed_versions(
    distributions: Sequence[metadata.Distribution],
) -> dict[str, str]:
    installed: dict[str, str] = {}
    for distribution in distributions:
        display_name = distribution.metadata["Name"]
        if not display_name:
            raise EnvironmentAuditError("installed distribution has no Name metadata")
        canonical = _canonical_name(display_name)
        if canonical == _PROJECT_NAME:
            continue
        if canonical in installed:
            raise EnvironmentAuditError(
                f"duplicate installed distribution metadata for {display_name!r}"
            )
        installed[canonical] = distribution.version
    return installed


def _has_editable_direct_url(distribution: metadata.Distribution) -> bool:
    try:
        raw = distribution.read_text("direct_url.json")
    except (OSError, UnicodeError) as exc:
        raise EnvironmentAuditError(f"cannot read HawEdit direct_url.json: {exc}") from exc
    if raw is None:
        return False
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise EnvironmentAuditError(f"HawEdit direct_url.json is invalid: {exc}") from exc
    if not isinstance(document, dict):
        raise EnvironmentAuditError("HawEdit direct_url.json is not an object")
    directory = document.get("dir_info")
    return isinstance(directory, dict) and directory.get("editable") is True


def _runtime_hawedit_distribution() -> metadata.Distribution:
    records = tuple(metadata.distributions(name=_PROJECT_NAME))
    if not records:
        raise EnvironmentAuditError("installed HawEdit distribution metadata is missing")
    editable = [record for record in records if _has_editable_direct_url(record)]
    if editable:
        return _source_distribution(records, _editable_root(editable[0]))
    if len(records) != 1:
        raise EnvironmentAuditError(
            "installed profile requires exactly one HawEdit wheel distribution; "
            f"found {len(records)}"
        )
    return records[0]


def _resolve_installed_hawedit_data(
    distribution: metadata.Distribution, relative_path: str
) -> Path:
    """Locate and authenticate wheel data for one already-authoritative distribution."""

    if "\\" in relative_path:
        raise EnvironmentAuditError("installed HawEdit data path must use forward slashes")
    parts = relative_path.split("/")
    if (
        len(parts) < 3
        or parts[:2] != ["share", "hawedit"]
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise EnvironmentAuditError(
            "installed HawEdit data path must be normalized beneath share/hawedit"
        )
    try:
        raw_record = distribution.read_text("RECORD")
    except (OSError, UnicodeError) as exc:
        raise EnvironmentAuditError(f"cannot read installed HawEdit RECORD: {exc}") from exc
    if raw_record is None:
        raise EnvironmentAuditError("installed HawEdit metadata has no RECORD file inventory")
    matches: list[tuple[str, str, str]] = []
    try:
        for number, row in enumerate(csv.reader(raw_record.splitlines()), 1):
            if len(row) != 3:
                raise EnvironmentAuditError(
                    f"installed HawEdit RECORD row {number} has {len(row)} fields, expected 3"
                )
            recorded_path, recorded_hash, recorded_size = row
            recorded_parts = recorded_path.split("/")
            if recorded_parts[-len(parts) :] == parts:
                prefix = recorded_parts[: -len(parts)]
                if "\\" in recorded_path or len(prefix) > 4 or any(item != ".." for item in prefix):
                    raise EnvironmentAuditError(
                        f"installed HawEdit RECORD has unsafe data path {recorded_path!r}"
                    )
                matches.append((recorded_path, recorded_hash, recorded_size))
    except csv.Error as exc:
        raise EnvironmentAuditError(f"installed HawEdit RECORD is invalid CSV: {exc}") from exc
    if len(matches) != 1:
        raise EnvironmentAuditError(
            f"installed HawEdit RECORD must name exactly one {relative_path}; found {len(matches)}"
        )
    recorded_path, recorded_hash, recorded_size = matches[0]
    primary = Path(str(distribution.locate_file(metadata.PackagePath(recorded_path))))
    distribution_root = Path(str(distribution.locate_file("")))
    relocated = distribution_root.joinpath(*parts)
    candidates: list[Path] = []
    for candidate in (primary, relocated):
        if candidate.is_file() and not any(_same_path(candidate, item) for item in candidates):
            candidates.append(candidate.resolve())
    if len(candidates) != 1:
        raise EnvironmentAuditError(
            f"installed HawEdit RECORD resolves {relative_path} to {len(candidates)} files"
        )

    algorithm, separator, encoded_digest = recorded_hash.partition("=")
    if algorithm != "sha256" or separator != "=" or not encoded_digest:
        raise EnvironmentAuditError(f"installed HawEdit RECORD has no SHA-256 for {relative_path}")
    try:
        expected_digest = base64.b64decode(
            encoded_digest + "=" * (-len(encoded_digest) % 4), altchars=b"-_", validate=True
        )
        expected_size = int(recorded_size)
        content = candidates[0].read_bytes()
    except (OSError, ValueError) as exc:
        raise EnvironmentAuditError(
            f"cannot authenticate installed HawEdit data file {relative_path}: {exc}"
        ) from exc
    if expected_size < 0 or len(expected_digest) != hashlib.sha256().digest_size:
        raise EnvironmentAuditError(
            f"installed HawEdit RECORD identity is invalid for {relative_path}"
        )
    if len(content) != expected_size or not hmac.compare_digest(
        hashlib.sha256(content).digest(), expected_digest
    ):
        raise EnvironmentAuditError(
            f"installed HawEdit data file does not match RECORD SHA-256: {relative_path}"
        )
    return candidates[0]


def resolve_installed_hawedit_data(relative_path: str) -> Path:
    """Locate and authenticate exactly one installed HawEdit wheel data file."""

    return _resolve_installed_hawedit_data(_runtime_hawedit_distribution(), relative_path)


def _host_lock_name(profile: str) -> str:
    if profile not in _PROFILE_EXTRAS:
        raise EnvironmentAuditError(f"unknown host-lock profile {profile!r}")
    target = _target_platform(platform.system())
    version = (sys.version_info.major, sys.version_info.minor)
    if version not in {(3, 11), (3, 12)}:
        raise EnvironmentAuditError(f"no installed host lock for Python {version[0]}.{version[1]}")
    return f"host-{profile}-{target}-py{version[0]}{version[1]}.txt"


def resolve_installed_host_lock(profile: str) -> Path:
    """Return this installed wheel's host lock for the current OS and Python minor."""

    name = _host_lock_name(profile)
    return resolve_installed_hawedit_data(f"share/hawedit/requirements/{name}")


def audit_installed_profile(profile: str) -> HostLock:
    """Require every distribution in an installed profile, while allowing unrelated extras.

    Model provisioning calls this subset audit at runtime. A dedicated installer and the
    canonical gate use :func:`audit_environment`'s stricter exact-inventory audit instead.
    """

    extras = _PROFILE_EXTRAS.get(profile)
    if extras is None:
        raise EnvironmentAuditError(f"unknown host-lock profile {profile!r}")
    distribution = _runtime_hawedit_distribution()
    if _has_editable_direct_url(distribution):
        project_root = _editable_root(distribution)
        lock_path = project_root / "requirements" / _host_lock_name(profile)
        manifest = _read_project_manifest(project_root, extras)
    else:
        project_root = None
        lock_path = _resolve_installed_hawedit_data(
            distribution,
            f"share/hawedit/requirements/{_host_lock_name(profile)}",
        )
        manifest = _read_installed_manifest(distribution, extras)
    lock = validate_host_lock(
        lock_path,
        project_root=project_root,
        extras=extras,
        python_version=(sys.version_info.major, sys.version_info.minor),
        platform_name=platform.system(),
    )
    if distribution.version != lock.project_version:
        raise EnvironmentAuditError(
            f"installed HawEdit {distribution.version} does not match host lock project version "
            f"{lock.project_version}"
        )
    direct = _declared_versions(
        manifest.requirements, (sys.version_info.major, sys.version_info.minor)
    )
    expected = dict(lock.requirements)
    for canonical, (display_name, version) in direct.items():
        locked = expected.get(canonical)
        if locked is None or not _version_matches(version, locked):
            raise EnvironmentAuditError(
                f"installed profile lock does not cover {display_name}=={version}"
            )

    installed = _exact_installed_versions(tuple(metadata.distributions()))
    missing = sorted(expected.keys() - installed.keys())
    drifted = sorted(
        name for name in expected.keys() & installed.keys() if installed[name] != expected[name]
    )
    if missing or drifted:
        details: list[str] = []
        if missing:
            details.append(f"missing={missing}")
        if drifted:
            details.append(
                "drifted="
                + repr([f"{name}=={installed[name]} (locked {expected[name]})" for name in drifted])
            )
        raise EnvironmentAuditError(
            f"installed {profile} profile does not match its host lock: " + "; ".join(details)
        )
    return lock


def _audit_environment(
    project_root: Path | None,
    extras: Sequence[str],
    *,
    python_version: tuple[int, int],
    distributions: Sequence[metadata.Distribution],
    version_getter: Callable[[str], str],
    lock_path: Path | None = None,
    installed_distributions: Sequence[metadata.Distribution] = (),
    platform_name: str | None = None,
    _lock_hashes: Mapping[str, str] = HOST_LOCK_SHA256,
) -> EnvironmentReport:
    resolved_root = project_root.resolve() if project_root is not None else None
    if resolved_root is not None:
        distribution = _source_distribution(distributions, resolved_root)
        manifest = _read_project_manifest(resolved_root, extras)
        if distribution.version != manifest.project_version:
            raise EnvironmentAuditError(
                f"installed HawEdit is {distribution.version}, project declares "
                f"{manifest.project_version}"
            )
    else:
        if len(distributions) != 1:
            raise EnvironmentAuditError(
                "installed-only audit requires exactly one HawEdit distribution; "
                f"found {len(distributions)}"
            )
        distribution = distributions[0]
        manifest = _read_installed_manifest(distribution, extras)

    _check_python(manifest.requires_python, python_version)
    declared = _declared_versions(manifest.requirements, python_version)
    checked: list[tuple[str, str]] = []
    for canonical in sorted(declared):
        display_name, expected_version = declared[canonical]
        try:
            installed_version = version_getter(display_name)
        except (metadata.PackageNotFoundError, KeyError) as exc:
            raise EnvironmentAuditError(
                f"declared direct dependency {display_name}=={expected_version} is not installed"
            ) from exc
        if not _version_matches(expected_version, installed_version):
            raise EnvironmentAuditError(
                f"declared direct dependency {display_name} drifted: expected {expected_version}, "
                f"installed {installed_version}"
            )
        checked.append((canonical, installed_version))

    host_lock: HostLock | None = None
    if lock_path is not None:
        host_lock = validate_host_lock(
            lock_path,
            project_root=resolved_root,
            extras=extras,
            python_version=python_version,
            platform_name=platform_name or platform.system(),
            _lock_hashes=_lock_hashes,
        )
        if distribution.version != host_lock.project_version:
            raise EnvironmentAuditError(
                f"installed HawEdit is {distribution.version}, host lock is for HawEdit "
                f"{host_lock.project_version}"
            )
        if not installed_distributions:
            raise EnvironmentAuditError(
                "host-lock audit requires the complete installed distribution inventory"
            )
        locked_expected = dict(host_lock.requirements)
        installed_versions = _exact_installed_versions(installed_distributions)
        missing = sorted(locked_expected.keys() - installed_versions.keys())
        unexpected = sorted(installed_versions.keys() - locked_expected.keys())
        drifted = sorted(
            name
            for name in locked_expected.keys() & installed_versions.keys()
            if installed_versions[name] != locked_expected[name]
        )
        if missing or unexpected or drifted:
            details: list[str] = []
            if missing:
                details.append(f"missing={missing}")
            if unexpected:
                details.append(f"unexpected={unexpected}")
            if drifted:
                details.append(
                    "drifted="
                    + repr(
                        [
                            f"{name}=={installed_versions[name]} (locked {locked_expected[name]})"
                            for name in drifted
                        ]
                    )
                )
            raise EnvironmentAuditError(
                "installed environment does not exactly match host lock: " + "; ".join(details)
            )

    return EnvironmentReport(
        python_version=python_version,
        project_version=manifest.project_version,
        project_root=resolved_root,
        checked_requirements=tuple(checked),
        lock_sha256=host_lock.sha256 if host_lock else None,
        locked_requirements=host_lock.requirements if host_lock else (),
    )


def audit_environment(
    project_root: Path | None = None,
    extras: Sequence[str] = (),
    lock_path: Path | None = None,
) -> EnvironmentReport:
    """Prove that the current interpreter matches a checkout or installed wheel.

    A ``project_root`` selects source-gate mode and therefore requires an editable install
    rooted at that exact directory. Without it, only an ordinary installed wheel and its
    unconditional runtime dependencies are checked.
    """

    return _audit_environment(
        project_root,
        extras,
        python_version=(sys.version_info.major, sys.version_info.minor),
        distributions=tuple(metadata.distributions(name=_PROJECT_NAME)),
        version_getter=metadata.version,
        lock_path=lock_path,
        installed_distributions=tuple(metadata.distributions()),
        platform_name=platform.system(),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="hawedit.environment",
        description="Refuse a Python environment that cannot honestly grade HawEdit.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        help="require an editable HawEdit install rooted at this checkout",
    )
    parser.add_argument(
        "--extra",
        action="append",
        default=[],
        help="also require one named project extra (source-gate mode only)",
    )
    parser.add_argument(
        "--lock",
        type=Path,
        help="require the complete installed environment to match this host lock",
    )
    parser.add_argument(
        "--validate-lock-only",
        action="store_true",
        help="validate lock target and source contract before installing anything",
    )
    parser.add_argument(
        "--show-lock",
        choices=tuple(_PROFILE_EXTRAS),
        help="print the packaged current-target lock path for an installed-wheel profile",
    )
    args = parser.parse_args(argv)
    try:
        if args.show_lock:
            if args.project_root is not None or args.lock is not None or args.extra:
                raise EnvironmentAuditError("--show-lock cannot be combined with audit options")
            lock = resolve_installed_host_lock(args.show_lock)
            validate_host_lock(
                lock,
                project_root=None,
                extras=_PROFILE_EXTRAS[args.show_lock],
                python_version=(sys.version_info.major, sys.version_info.minor),
                platform_name=platform.system(),
            )
            print(lock)
            return 0
        extras = tuple(args.extra)
        if args.validate_lock_only:
            if args.project_root is None or args.lock is None:
                raise EnvironmentAuditError(
                    "--validate-lock-only requires both --project-root and --lock"
                )
            validate_host_lock(
                args.lock,
                project_root=args.project_root.resolve(),
                extras=extras,
                python_version=(sys.version_info.major, sys.version_info.minor),
                platform_name=platform.system(),
            )
        else:
            audit_environment(args.project_root, extras, args.lock)
    except EnvironmentAuditError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 3
    print(_SUCCESS_TOKEN)
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    raise SystemExit(main())
