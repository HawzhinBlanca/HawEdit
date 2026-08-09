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
import importlib.metadata as metadata
import json
import os
import re
import sys
import tomllib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname

__all__ = ["EnvironmentAuditError", "EnvironmentReport", "audit_environment", "main"]

_PROJECT_NAME: Final = "hawedit"
_EXACT_REQUIREMENT: Final = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*==\s*([^,;\s*]+)\s*(?:;\s*(.+))?$"
)
_SUPPORTED_PYTHON: Final = re.compile(r"^>=([0-9]+)\.([0-9]+),<([0-9]+)\.([0-9]+)$")
_SUCCESS_TOKEN: Final = "hawedit-environment-ok"


class EnvironmentAuditError(RuntimeError):
    """The interpreter cannot honestly grade this HawEdit checkout or installation."""


@dataclass(frozen=True, slots=True)
class EnvironmentReport:
    """Identity that was proved for a usable environment."""

    python_version: tuple[int, int]
    project_version: str
    project_root: Path | None
    checked_requirements: tuple[tuple[str, str], ...]


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


def _read_installed_manifest(distribution: metadata.Distribution) -> _Manifest:
    requires_python = distribution.metadata["Requires-Python"]
    if not requires_python:
        raise EnvironmentAuditError("installed HawEdit metadata has no Requires-Python")

    requirements: list[str] = []
    for declared in distribution.requires or ():
        requirement, separator, marker = declared.partition(";")
        if not separator:
            requirements.append(requirement.strip())
            continue
        # Wheel metadata expresses every optional dependency with an ``extra ==`` marker.
        # No extra is active in installed-only mode, so those requirements are inapplicable.
        if re.search(r"\bextra\s*==", marker):
            continue
        raise EnvironmentAuditError(
            f"cannot evaluate marked installed requirement without its project manifest: "
            f"{declared!r}"
        )
    return _Manifest(distribution.version, requires_python, tuple(requirements))


def _check_python(requires_python: str, python_version: tuple[int, int]) -> None:
    compact = requires_python.replace(" ", "")
    match = _SUPPORTED_PYTHON.fullmatch(compact)
    if match is None:
        raise EnvironmentAuditError(
            f"unsupported Requires-Python form {requires_python!r}; refusing to guess"
        )
    lower = (int(match.group(1)), int(match.group(2)))
    upper = (int(match.group(3)), int(match.group(4)))
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


def _audit_environment(
    project_root: Path | None,
    extras: Sequence[str],
    *,
    python_version: tuple[int, int],
    distributions: Sequence[metadata.Distribution],
    version_getter: Callable[[str], str],
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
        if extras:
            raise EnvironmentAuditError("installed-only audit cannot prove optional extras")
        if len(distributions) != 1:
            raise EnvironmentAuditError(
                "installed-only audit requires exactly one HawEdit distribution; "
                f"found {len(distributions)}"
            )
        distribution = distributions[0]
        manifest = _read_installed_manifest(distribution)

    _check_python(manifest.requires_python, python_version)
    declared = _declared_versions(manifest.requirements, python_version)
    checked: list[tuple[str, str]] = []
    for canonical in sorted(declared):
        display_name, expected = declared[canonical]
        try:
            installed = version_getter(display_name)
        except (metadata.PackageNotFoundError, KeyError) as exc:
            raise EnvironmentAuditError(
                f"declared direct dependency {display_name}=={expected} is not installed"
            ) from exc
        if not _version_matches(expected, installed):
            raise EnvironmentAuditError(
                f"declared direct dependency {display_name} drifted: expected {expected}, "
                f"installed {installed}"
            )
        checked.append((canonical, installed))

    return EnvironmentReport(
        python_version=python_version,
        project_version=manifest.project_version,
        project_root=resolved_root,
        checked_requirements=tuple(checked),
    )


def audit_environment(
    project_root: Path | None = None, extras: Sequence[str] = ()
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
    args = parser.parse_args(argv)
    try:
        audit_environment(args.project_root, tuple(args.extra))
    except EnvironmentAuditError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 3
    print(_SUCCESS_TOKEN)
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    raise SystemExit(main())
