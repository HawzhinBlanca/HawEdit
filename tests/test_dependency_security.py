"""Security floors for dependencies whose vulnerable pins reached a release wheel."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from hawedit import wsl_asr_locks, wsl_setup

ROOT = Path(__file__).resolve().parents[1]


def _base_dependency_version(project: dict[str, object], package: str) -> tuple[int, ...]:
    return _dependency_version(project, None, package)


def _dependency_version(
    document: dict[str, object], group: str | None, package: str
) -> tuple[int, ...]:
    project = document["project"]
    assert isinstance(project, dict)
    if group is None:
        raw_dependencies = project["dependencies"]
    else:
        optional = project["optional-dependencies"]
        assert isinstance(optional, dict)
        raw_dependencies = optional[group]
    assert isinstance(raw_dependencies, list)
    matches = [
        dependency
        for dependency in raw_dependencies
        if isinstance(dependency, str) and dependency.lower().startswith(f"{package.lower()}==")
    ]
    assert len(matches) == 1, f"expected one exact {package} pin, got {matches!r}"
    version = matches[0].split("==", 1)[1]
    assert re.fullmatch(r"\d+(?:\.\d+)+", version), f"non-numeric {package} pin {version!r}"
    return tuple(int(part) for part in version.split("."))


def test_fonttools_pin_contains_the_cve_2025_66034_fix() -> None:
    """4.33.0 through 4.60.1 allow varLib designspace path traversal/arbitrary writes."""
    document = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    base_version = _base_dependency_version(document, "fonttools")
    assert base_version >= (4, 60, 2)

    locked_version = tuple(
        int(part) for part in wsl_asr_locks.LOCKED_DISTRIBUTIONS["fonttools"].split(".")
    )
    assert locked_version == base_version
    assert wsl_setup._EXPECTED_PACKAGES["fonttools"] == ".".join(str(part) for part in base_version)
    assert wsl_setup._EXPECTED_LOCKS["runtime_sha256"] == wsl_asr_locks.RUNTIME_LOCK_SHA256


def test_pytest_pin_contains_the_pysec_2026_1845_fix() -> None:
    document = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert _dependency_version(document, "dev", "pytest") >= (9, 0, 3)


def test_gpu_and_cloud_runtime_dependencies_are_exactly_reproducible() -> None:
    """Open floors silently changed the model runtime underneath recorded measurements."""
    document = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    expected = {
        ("gpu", "transformers"): (4, 57, 6),
        ("gpu", "accelerate"): (1, 14, 0),
        ("gpu", "pillow"): (12, 3, 0),
        ("gpu", "torchvision"): (0, 28, 0),
        ("cloud", "google-auth"): (2, 56, 3),
    }
    assert {
        (group, package): _dependency_version(document, group, package)
        for group, package in expected
    } == expected

    tool = document["tool"]
    assert isinstance(tool, dict)
    mypy = tool["mypy"]
    assert isinstance(mypy, dict)
    assert mypy["untyped_calls_exclude"] == ["google.auth.credentials.Credentials.refresh"]
