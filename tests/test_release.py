"""Release artifacts are reproducible, complete and atomically published."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from hawedit.release import (
    ReleaseError,
    _publish_directory,
    _spdx_sbom,
    build_reproducible_wheel,
)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _release_source(root: Path) -> Path:
    """A tiny clean Git package with HawEdit's release-critical wheel members."""
    project = root / "project"
    (project / "src" / "hawedit").mkdir(parents=True)
    (project / "assets" / "fonts").mkdir(parents=True)
    (project / "models").mkdir()
    (project / "src" / "hawedit" / "__init__.py").write_text("", encoding="utf-8")
    (project / "src" / "hawedit" / "release.py").write_text(
        '"""release fixture"""\n', encoding="utf-8"
    )
    (project / "assets" / "fonts" / "NotoNaskhArabic-Regular.ttf").write_bytes(b"font")
    (project / "assets" / "fonts" / "OFL.txt").write_text("OFL", encoding="utf-8")
    (project / "models" / "sources.json").write_text("{}\n", encoding="utf-8")
    (project / "models" / "revisions.json").write_text("{}\n", encoding="utf-8")
    (project / ".gitignore").write_text("/build/\n/dist/\n*.egg-info/\n", encoding="utf-8")
    (project / "pyproject.toml").write_text(
        """[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "hawedit-release-fixture"
version = "1.0.0"
dependencies = ["base-dep==2.3.4"]

[project.optional-dependencies]
feature = ["optional-dep>=5"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.data-files]
"share/hawedit/assets/fonts" = [
    "assets/fonts/NotoNaskhArabic-Regular.ttf",
    "assets/fonts/OFL.txt",
]
"share/hawedit/models" = ["models/sources.json", "models/revisions.json"]
""",
        encoding="utf-8",
    )
    _git(project, "init", "--quiet")
    _git(project, "add", "--", ".")
    _git(
        project,
        "-c",
        "user.name=HawEdit Test",
        "-c",
        "user.email=test@hawedit.invalid",
        "commit",
        "--quiet",
        "-m",
        "fixture",
    )
    return project


def test_release_builds_twice_and_publishes_verified_provenance(tmp_path: Path) -> None:
    project = _release_source(tmp_path)
    destination = tmp_path / "published"

    artifact = build_reproducible_wheel(project, destination, python=Path(sys.executable))

    assert artifact.output_dir == destination
    assert artifact.wheel.is_file()
    assert artifact.checksum_file.read_text(encoding="utf-8") == (
        f"{artifact.sha256}  {artifact.wheel.name}\n"
        f"{artifact.sbom_sha256}  {artifact.sbom_file.name}\n"
        f"{artifact.provenance_sha256}  {artifact.provenance_file.name}\n"
    )
    provenance = json.loads(artifact.provenance_file.read_text(encoding="utf-8"))
    assert provenance == {
        "schema": 2,
        "revision": _git(project, "rev-parse", "HEAD"),
        "source_date_epoch": artifact.source_date_epoch,
        "wheel": artifact.wheel.name,
        "sha256": artifact.sha256,
        "size_bytes": artifact.size_bytes,
        "sbom": artifact.sbom_file.name,
        "sbom_format": "SPDX-2.3-json",
        "sbom_sha256": artifact.sbom_sha256,
    }
    sbom = json.loads(artifact.sbom_file.read_text(encoding="utf-8"))
    assert sbom["spdxVersion"] == "SPDX-2.3"
    assert sbom["dataLicense"] == "CC0-1.0"
    assert sbom["documentDescribes"] == ["SPDXRef-Package-HawEdit"]
    assert sbom["documentNamespace"].endswith(f"/{artifact.revision}/{artifact.sha256}")
    packages = {package["name"]: package for package in sbom["packages"]}
    assert set(packages) == {
        "hawedit-release-fixture",
        "Noto Naskh Arabic",
        "base-dep",
        "optional-dep",
    }
    assert packages["hawedit-release-fixture"]["checksums"] == [
        {"algorithm": "SHA256", "checksumValue": artifact.sha256}
    ]
    assert packages["base-dep"]["versionInfo"] == "2.3.4"
    assert "versionInfo" not in packages["optional-dep"]
    relationships = {
        (
            relationship["spdxElementId"],
            relationship["relationshipType"],
            relationship["relatedSpdxElement"],
        )
        for relationship in sbom["relationships"]
    }
    root = "SPDXRef-Package-HawEdit"
    font_id = packages["Noto Naskh Arabic"]["SPDXID"]
    base_id = packages["base-dep"]["SPDXID"]
    optional_id = packages["optional-dep"]["SPDXID"]
    assert ("SPDXRef-DOCUMENT", "DESCRIBES", root) in relationships
    assert (root, "CONTAINS", font_id) in relationships
    assert (root, "DEPENDS_ON", base_id) in relationships
    assert (optional_id, "OPTIONAL_DEPENDENCY_OF", root) in relationships
    assert packages["Noto Naskh Arabic"]["checksums"] == [
        {"algorithm": "SHA256", "checksumValue": hashlib.sha256(b"font").hexdigest()}
    ]
    expected_sbom = _spdx_sbom(
        artifact.wheel,
        revision=artifact.revision,
        epoch=artifact.source_date_epoch,
        wheel_sha256=artifact.sha256,
    )
    assert artifact.sbom_file.read_bytes() == expected_sbom
    assert expected_sbom == _spdx_sbom(
        artifact.wheel,
        revision=artifact.revision,
        epoch=artifact.source_date_epoch,
        wheel_sha256=artifact.sha256,
    )
    assert {path.name for path in destination.iterdir()} == {
        artifact.wheel.name,
        artifact.sbom_file.name,
        "SHA256SUMS",
        "release-provenance.json",
    }
    with zipfile.ZipFile(artifact.wheel) as wheel:
        assert wheel.testzip() is None
        assert any(name.endswith("share/hawedit/models/sources.json") for name in wheel.namelist())
        assert any(
            name.endswith("share/hawedit/models/revisions.json") for name in wheel.namelist()
        )

    with pytest.raises(ReleaseError, match="refusing to overwrite"):
        build_reproducible_wheel(project, destination, python=Path(sys.executable))


def test_release_refuses_uncommitted_or_untracked_source(tmp_path: Path) -> None:
    project = _release_source(tmp_path)
    (project / "untracked-client-change.txt").write_text("not reviewed", encoding="utf-8")

    with pytest.raises(ReleaseError, match="dirty checkout.*untracked-client-change"):
        build_reproducible_wheel(project, tmp_path / "must-not-exist", python=Path(sys.executable))

    assert not (tmp_path / "must-not-exist").exists()


def test_atomic_release_publication_preserves_the_winner(tmp_path: Path) -> None:
    staging = tmp_path / ".release.worker-two"
    output = tmp_path / "release"
    staging.mkdir()
    output.mkdir()
    (staging / "wheel.whl").write_bytes(b"second")
    (output / "wheel.whl").write_bytes(b"first")

    with pytest.raises(ReleaseError, match="refusing to overwrite"):
        _publish_directory(staging, output)

    assert (output / "wheel.whl").read_bytes() == b"first"
    assert (staging / "wheel.whl").read_bytes() == b"second"
