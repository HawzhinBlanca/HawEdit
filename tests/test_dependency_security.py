"""Security floors for dependencies whose vulnerable pins reached a release wheel."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from hawedit import wsl_setup

ROOT = Path(__file__).resolve().parents[1]


def _base_dependency_version(project: dict[str, object], package: str) -> tuple[int, ...]:
    dependencies = project["project"]
    assert isinstance(dependencies, dict)
    raw_dependencies = dependencies["dependencies"]
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

    setup_versions = re.findall(r"'fonttools==(\d+(?:\.\d+)+)'", wsl_setup._SETUP_SCRIPT)
    assert len(setup_versions) == 2
    assert {tuple(int(part) for part in version.split(".")) for version in setup_versions} == {
        base_version
    }
