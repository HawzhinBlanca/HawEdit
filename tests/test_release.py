"""Release artifacts are reproducible, complete and atomically published."""

from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from hawedit.release import (
    ReleaseError,
    _publish_directory,
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
    )
    provenance = json.loads(artifact.provenance_file.read_text(encoding="utf-8"))
    assert provenance == {
        "schema": 1,
        "revision": _git(project, "rev-parse", "HEAD"),
        "source_date_epoch": artifact.source_date_epoch,
        "wheel": artifact.wheel.name,
        "sha256": artifact.sha256,
        "size_bytes": artifact.size_bytes,
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
